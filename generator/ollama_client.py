#!/usr/bin/env python3
"""Ollama backend: one streamed /api/generate call per prompt.

run_prompt(prompt, think=None, format=None, options=None, limits=None)
returns (thinking, response) and leaves what happened in self.last_call:

  seconds, thinking_bytes, response_bytes
  aborted        None, or the circuit breaker that cut the call off:
                 'thinking_bytes' | 'response_bytes' | 'wall_clock' (the
                 limits the caller passed) | 'loop' (the reasoning is
                 repeating itself; see detect_loops) | 'max_duration'
                 (this client's own cap, a last resort: 4 hours unless
                 configured)
  done_reason    the server's own reason ('stop', 'length', ...); 'length'
                 means num_predict or the context window ran out
  prompt_tokens, output_tokens, eval_seconds, load_seconds
  think_sent, format_sent, options  what was actually put on the wire

The caller decides what an aborted or truncated call means (main.py retries
a thinking call once with thinking off). A transport failure raises
LlmCallError, which carries whatever had streamed so far, so a call that
dies mid-sentence still leaves its partial trace on disk.

A failure that is the server's and not the request's (the model runner
crashed, a ROCm library failed to load, the stream stopped, the server was
restarting) is retried here first: crash_retries times, crash_wait seconds
apart, the whole call from the start. Ollama starts a new runner on the next
request, so one crash costs a minute, not the run. last_call then has
crash_retries, the number of retries spent.

think:   None sends nothing (the model's default), False sends think:false.
         A server that does not treat the model as a thinking model
         rejects that parameter (HTTP 400); the call is then repeated
         without it, with `no_think_suffix` appended to the prompt instead
         (Qwen's own soft switch, "/no_think"), and the parameter is not
         sent again this run.
format:  a JSON schema (or "json") for Ollama's structured outputs. Whether
         it is sent depends on `structured`:
           'no_think' (default)  only when think is False. Structured output
                                 without thinking is long-supported; with
                                 thinking it has depended on the server
                                 version, so it is off until probe_ollama.py
                                 says it works on yours.
           'always'              on every call that passes a schema.
           'never'               never.
         If the server rejects the schema (HTTP 400), the call is repeated
         without it and schemas are switched off for the rest of the run.
options: per-call model options (sampler settings, num_predict). Options
         given to the constructor win over per-call ones, so what you put
         in dynamic_config.py is what runs.
limits:  {'max_thinking_bytes', 'max_response_bytes', 'max_seconds'}; any
         may be missing or None. Checked as chunks arrive; on a breach the
         connection is closed, which stops generation on the server.
         With 'force_answer': True, a call cut by max_thinking_bytes before
         any answer text arrived is not thrown away: the client sends one
         raw-mode continuation holding the prompt, the thinking so far and
         a CLOSED think block, so the model writes its answer from what it
         has ("budget forcing"). last_call then has forced_answer True,
         thinking_at_force, and aborted None. The continuation needs the
         model's chat template (raw_template, Qwen's ChatML by default);
         probe_ollama.py checks it. If forcing fails, the call is reported
         as cut, exactly as without it.
         With 'detect_loops': True, reasoning that repeats itself (see
         LoopDetector) is cut at once with aborted 'loop', and last_call's
         loop_line holds what repeated. Its answer is never forced: a
         looping trace has nothing left to answer from.
"""

from llm_client import LlmClient, LlmCallError
import argparse
import collections
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# A plain /api/generate request to a Qwen-family model becomes ChatML with
# the whole prompt as the user turn. The forced continuation rebuilds that
# by hand, in raw mode, with the thinking so far inside a closed think block.
CHATML_TEMPLATE = ("<|im_start|>user\n{prompt}<|im_end|>\n"
                   "<|im_start|>assistant\n<think>\n{thinking}\n</think>\n\n")
FORCE_CLOSE = ("\n\nI have deliberated enough. I will stop here and write the final answer "
               "now, exactly in the requested output format.")
FORCED_ANSWER_TOKENS = 6144
# what a crashed or restarting server looks like from here (batch.py's
# TRANSIENT list is the same idea one level up, for a whole job)
CRASH_SIGNS = ('an error was encountered while running the model', 'tensilelibrary', 'runner process',
               'ended before the call finished', 'failed mid-stream', 'could not reach ollama', 'idle timeout')


class LoopDetector:
    """Watches reasoning as it streams and says when it has started going
    round: among its last WINDOW prose lines, one seen five times, or three
    different lines seen three times each. A looping trace cycles through
    a paragraph with small variations ("OK." / "Let me write the JSON." /
    the same doubt again), so its lines recur but rarely back to back.
    Short lines and lines that start like drafted JSON or a list are not
    counted: a drafted answer repeats its field lines legitimately.
    Calibrated on kernel1 traces: 7 of 7 loops caught, 4-12 KB in; none of
    75 healthy traces (up to 77 KB) flagged. A looping trace never
    recovers; the thinking breaker would only catch it after the whole
    budget is spent."""
    WINDOW = 80
    MIN_CHARS = 21

    def __init__(self):
        self.tail = ''
        self.window = collections.deque()
        self.counts = collections.Counter()

    def feed(self, text):
        """Takes the next fragment; returns the repeating line, or None."""
        self.tail += text
        *done, self.tail = self.tail.split('\n')
        self.tail = self.tail[-4000:]
        for line in done:
            line = line.strip()
            if len(line) < self.MIN_CHARS or line[0] in '{["}]|-':
                continue
            self.window.append(line)
            self.counts[line] += 1
            if len(self.window) > self.WINDOW:
                self.counts[self.window.popleft()] -= 1
            if self.counts[line] >= 5 or sum(1 for n in self.counts.values() if n >= 3) >= 3:
                return line
        return None


def _ollama_url(host, path):
    return host.rstrip("/") + path


class OllamaClient(LlmClient):
    def __init__(self, host=DEFAULT_OLLAMA_HOST, model='my model', keep_alive='30m', idle_timeout=180,
                 max_duration=14400, echo=True, options=None, structured='no_think',
                 no_think_suffix='/no_think', raw_template=CHATML_TEMPLATE, implicit_think=True,
                 crash_retries=2, crash_wait=30):
        self.host = host
        self.model = model
        self.keep_alive = keep_alive
        self.idle_timeout = idle_timeout
        self.max_duration = max_duration
        self.echo = echo
        # Ollama model options sent with every request, e.g.
        #   {"num_ctx": 32768}
        # num_ctx matters twice. Too small and the server truncates the
        # prompt SILENTLY (the warning goes to the server log). Too large
        # and the context cache takes memory the model's layers could have
        # used: a 128k window on a 16 GB card pushes a 27B model onto the
        # CPU. The largest prompt here is about 13k tokens and the largest
        # allowed output about 14k, so 32768 is enough for every call.
        self.options = dict(options or {})
        self.structured = structured
        self.no_think_suffix = no_think_suffix
        self.think_param = True    # goes False if the server rejects think:false
        self.raw_template = raw_template
        # Some chat templates (Qwen-family imports among them) open the
        # <think> block in the PROMPT, so the reasoning streams in
        # `response` with no opening tag, closed by "</think>", and the
        # server's thinking parser does not split it out. With
        # implicit_think, a thinking call whose response starts with prose
        # is read as reasoning until "</think>"; a response that never
        # closes the block was all answer after all.
        self.implicit_think = implicit_think
        self._call_format = None
        self.crash_retries = crash_retries
        self.crash_wait = crash_wait
        self.last_call = {}

    # ------------------------------------------------------------------ request

    def _use_format(self, think, format):
        if format is None or self.structured == 'never':
            return False
        if self.structured == 'always':
            return True
        return think is False

    def _payload(self, prompt, think, format, options, limits):
        opts = dict(options or {})
        limits = limits or {}
        if limits.get('num_predict') and 'num_predict' not in opts:
            opts['num_predict'] = int(limits['num_predict'])
        opts.update(self.options)
        if os.environ.get('STRATUM_NUM_CTX', '').isdigit():
            opts['num_ctx'] = int(os.environ['STRATUM_NUM_CTX'])     # for budget experiments; reloads the model
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": self.keep_alive,
        }
        if opts:
            payload["options"] = opts
        if think is not None:
            if self.think_param:
                payload["think"] = bool(think)
            elif think is False:
                self._soft_no_think(payload)
        if self._use_format(think, format):
            payload["format"] = format
        return payload

    def _soft_no_think(self, payload):
        if self.no_think_suffix and not payload["prompt"].rstrip().endswith(self.no_think_suffix):
            payload["prompt"] = payload["prompt"].rstrip() + "\n\n" + self.no_think_suffix

    def run_prompt(self, prompt, think=None, format=None, options=None, limits=None, **_ignored):
        # a forced continuation answers after a closed think block, so a
        # schema is safe there even when this call could not send one
        self._call_format = format if self.structured != 'never' else None
        payload = self._payload(prompt, think, format, options, limits)
        for _ in range(3):
            try:
                return self._stream(payload, limits or {})
            except LlmCallError as e:
                # A server that cannot take a parameter answers 400 before
                # generating anything. Drop the parameter it objects to and
                # run without it rather than fail the step.
                if e.http_status != 400:
                    raise
                message = str(e).lower()
                if 'think' in payload and 'think' in message:
                    print(f'NOTE: ollama rejected the think parameter ({e}); using the prompt suffix '
                          f'{self.no_think_suffix!r} to switch reasoning off for the rest of this run.', file=sys.stderr)
                    self.think_param = False
                    wanted_off = payload.pop('think') is False
                    if wanted_off:
                        self._soft_no_think(payload)
                elif 'format' in payload:
                    print(f'NOTE: ollama rejected the output schema ({e}); continuing without structured '
                          f'outputs for the rest of this run.', file=sys.stderr)
                    self.structured = 'never'
                    payload.pop('format')
                else:
                    raise
        return self._stream(payload, limits or {})

    # ------------------------------------------------------------------ stream

    @staticmethod
    def is_crash(e):
        """A failure of the server rather than of this request."""
        return (e.http_status is not None and e.http_status >= 500) or any(t in str(e).lower() for t in CRASH_SIGNS)

    def _stream(self, payload, limits):
        for retry in range(self.crash_retries + 1):
            try:
                result = self._stream_once(payload, limits)
            except LlmCallError as e:
                if retry == self.crash_retries or not self.is_crash(e):
                    raise
                print(f'\n[ollama failed: {str(e)[:300]}; retrying the call in {self.crash_wait} s '
                      f'({retry + 1} of {self.crash_retries})]', flush=True)
                print(f'NOTE: ollama failed ({str(e)[:200]}); retrying the call ({retry + 1} of {self.crash_retries}).',
                      file=sys.stderr)
                time.sleep(self.crash_wait)
                continue
            if retry:
                self.last_call['crash_retries'] = retry
            return result

    def _stream_once(self, payload, limits):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _ollama_url(self.host, "/api/generate"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        max_thinking = limits.get('max_thinking_bytes')
        max_response = limits.get('max_response_bytes')
        max_seconds = limits.get('max_seconds')

        start = time.time()
        thinking_chunks = []     # the server's separate `thinking` field
        chunks = []              # the `response` field, as it arrived
        thinking_bytes = 0
        response_bytes = 0
        aborted = None
        final = None
        loops = LoopDetector() if limits.get('detect_loops') else None
        loop_line = None
        # Servers before 0.9 put the reasoning inside `response`, between
        # <think> tags. inline: None until the first non-blank response
        # text says which it is, then 'open' (inside the tags), 'closed'
        # (past them) or 'no' (this response has no inline reasoning).
        # 'open' also covers a block the TEMPLATE opened (tagged False, see
        # implicit_think in __init__).
        inline = None
        tagged = True
        inline_closed_at = 0
        implicit_ok = (self.implicit_think and payload.get('think') is not False and not payload.get('raw')
                       and not str(payload.get('prompt', '')).rstrip().endswith('/no_think'))

        def split_inline():
            text = "".join(chunks)
            if inline in ('open', 'closed'):
                body = text.lstrip()
                if tagged:
                    body = body[len('<think>'):]
                if '</think>' in body:
                    thought, _, answer = body.partition('</think>')
                    return thought, answer
                if not tagged and not aborted:
                    return '', body          # the implicit block never closed: it was all answer
                return body, ''
            if implicit_ok and '</think>' in text and '<think>' not in text:
                # an answer-looking start (a drafted object) that turned out
                # to be reasoning closed by the template's think block
                thought, _, answer = text.partition('</think>')
                return thought, answer
            return '', text

        def partial():
            thought, answer = split_inline()
            return ("".join(thinking_chunks) + thought).strip(), answer.strip()

        def fail(message, http_status=None):
            thinking, response = partial()
            self.last_call = self._info(payload, start, thinking, response, 'error', {})
            return LlmCallError(message, thinking=thinking, response=response, http_status=http_status)

        try:
            with urllib.request.urlopen(req, timeout=self.idle_timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # ignore stray non-JSON lines rather than aborting the call
                    if "error" in obj:
                        raise fail(f"ollama returned an error: {obj['error']}")
                    thought = obj.get("thinking", "")
                    if thought:
                        thinking_chunks.append(thought)
                        thinking_bytes += len(thought.encode("utf-8"))
                        if self.echo:
                            print(thought, end="", flush=True)
                        if loops and not loop_line:
                            loop_line = loops.feed(thought)
                    fragment = obj.get("response", "")
                    if fragment:
                        chunks.append(fragment)
                        response_bytes += len(fragment.encode("utf-8"))
                        if self.echo:
                            print(fragment, end="", flush=True)
                        if inline is None:
                            seen = "".join(chunks).lstrip()
                            if seen.startswith('<think>'):
                                inline = 'open'
                            elif seen and not '<think>'.startswith(seen):
                                if implicit_ok and seen[0] not in '{[':
                                    inline, tagged = 'open', False
                                else:
                                    inline = 'no'
                        if inline == 'open' and '</think>' in "".join(chunks[-3:]):
                            inline = 'closed'
                            inline_closed_at = response_bytes
                        elif inline == 'open' and loops and not loop_line:
                            loop_line = loops.feed(fragment)
                    if obj.get("done"):
                        final = obj
                        if self.echo:
                            print()  # newline after the streamed response
                        break
                    # breakers, checked only after a chunk that did not finish
                    # the call, so a complete answer is never thrown away
                    elapsed = time.time() - start
                    if inline == 'open':        # everything in `response` so far is reasoning
                        thought_so_far, answer_so_far = thinking_bytes + response_bytes, 0
                    elif inline == 'closed':    # counted to the fragment that closed the tag
                        thought_so_far = thinking_bytes + inline_closed_at
                        answer_so_far = response_bytes - inline_closed_at
                    else:
                        thought_so_far, answer_so_far = thinking_bytes, response_bytes
                    if loop_line:
                        aborted = 'loop'
                    elif max_thinking and thought_so_far > max_thinking:
                        aborted = 'thinking_bytes'
                    elif max_response and answer_so_far > max_response:
                        aborted = 'response_bytes'
                    elif max_seconds and elapsed > max_seconds:
                        aborted = 'wall_clock'
                    elif self.max_duration and elapsed > self.max_duration:
                        aborted = 'max_duration'
                    if aborted:
                        break
                # leaving the with-block closes the connection; the server
                # stops generating when its client goes away
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise fail(f"ollama HTTP {e.code} error: {body}", http_status=e.code)
        except urllib.error.URLError as e:
            # A timeout during connection/header setup sometimes surfaces
            # wrapped inside URLError rather than as a raw socket.timeout
            # (which python raises instead if the timeout happens later,
            # while iterating the streamed body). Check for both so the
            # message is never "can't reach ollama" when the real problem is
            # the idle-timeout / mid-generation-unload scenario.
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise fail(_idle_timeout_message(self.keep_alive, self.idle_timeout))
            raise fail(
                f"could not reach ollama at {self.host} ({e.reason}). Is `ollama serve` running "
                f"there? Set the host in dynamic_config.py or the OLLAMA_HOST environment variable "
                f"if it's not on the default address."
            )
        except (socket.timeout, TimeoutError):
            raise fail(_idle_timeout_message(self.keep_alive, self.idle_timeout))
        except (ConnectionError, OSError) as e:
            raise fail(f"connection to ollama at {self.host} failed mid-stream: {e}")

        if final is None and not aborted:
            # the stream stopped without the server's closing object: the
            # server died or something between us cut the connection. What
            # arrived is a fragment, not an answer.
            raise fail(f"the stream from ollama at {self.host} ended before the call finished "
                       f"(no closing 'done' object); check `ollama ps` and the server log")
        final = final or {}

        thinking, text = partial()
        if (aborted == 'thinking_bytes' and limits.get('force_answer') and not text.strip()
                and inline in (None, 'open') and not payload.get('raw')):
            forced = self._force(payload, thinking, limits, start)
            if forced is not None:
                return forced
        if aborted and self.echo:
            print(f'\n[call cut off: {aborted}' + (f': {loop_line[:120]!r}' if loop_line else '') + ']')
        self.last_call = self._info(payload, start, thinking, text, aborted, final)
        if loop_line:
            self.last_call['loop_line'] = loop_line
        return (thinking, text)

    def _force(self, payload, thinking, limits, start):
        """Budget forcing: one raw continuation that closes the think block
        and asks for the answer. Returns (thinking, response), or None if
        the continuation failed (the caller then reports the cut)."""
        if self.echo:
            print('\n[thinking budget reached: forcing the answer]', flush=True)
        opts = dict(payload.get('options') or {})
        opts['num_predict'] = min(int(opts.get('num_predict') or FORCED_ANSWER_TOKENS), FORCED_ANSWER_TOKENS)
        raw = {
            "model": self.model,
            "prompt": self.raw_template.format(prompt=payload["prompt"], thinking=thinking + FORCE_CLOSE),
            "raw": True,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": opts,
        }
        if self._call_format is not None:
            raw["format"] = self._call_format
        spent = time.time() - start
        sub_limits = {'max_response_bytes': limits.get('max_response_bytes')}
        if limits.get('max_seconds'):
            # the continuation gets what is left of the wall clock, and at
            # least ten minutes: the answer is the point of the whole call
            sub_limits['max_seconds'] = max(600, limits['max_seconds'] - spent)
        try:
            extra, answer = self._stream(raw, {k: v for k, v in sub_limits.items() if v})
        except LlmCallError as e:
            print(f'NOTE: the forced answer failed ({e}); reporting the call as cut.', file=sys.stderr)
            return None
        sub = self.last_call
        if sub.get('aborted') or not answer.strip():
            return None
        full_thinking = thinking + ("\n" + extra if extra else "")
        info = self._info(payload, start, full_thinking, answer, None, {})
        info.update({'forced_answer': True, 'thinking_at_force': len(thinking.encode('utf-8')),
                     'done_reason': sub.get('done_reason'), 'output_tokens': sub.get('output_tokens')})
        self.last_call = info
        return (full_thinking, answer)

    @staticmethod
    def _info(payload, start, thinking, response, aborted, final):
        eval_ns = final.get('eval_duration') or 0
        return {
            'seconds': round(time.time() - start, 2),
            'thinking_bytes': len(thinking.encode('utf-8')),
            'response_bytes': len(response.encode('utf-8')),
            'aborted': aborted,
            'done_reason': final.get('done_reason'),
            'prompt_tokens': final.get('prompt_eval_count'),
            'output_tokens': final.get('eval_count'),
            'eval_seconds': round(eval_ns / 1e9, 2) if eval_ns else None,
            'load_seconds': round((final.get('load_duration') or 0) / 1e9, 2) if final.get('load_duration') else None,
            'think_sent': payload.get('think'),
            'soft_no_think': str(payload.get('prompt', '')).rstrip().endswith('/no_think'),
            'format_sent': 'format' in payload,
            'options': payload.get('options') or {},
        }


def _idle_timeout_message(keep_alive, idle_timeout):
    return (
        f"ollama produced no output for more than the idle timeout ({idle_timeout}s). "
        f"This is the symptom of the model unloading mid-generation -- check "
        f"`ollama ps` right after this fails; if the model is gone, try a longer "
        f"keep_alive (currently {keep_alive!r}; '-1' means never expire from "
        f"idleness), or raise idle_timeout if this is just a slow cold model load."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model tag to run")
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST,
                         help="Base URL of the Ollama server (default: $OLLAMA_HOST or http://localhost:11434)")
    parser.add_argument("--keep-alive", default="30m",
                         help="Sent on every request so the server has no ambiguity about the model "
                              "being in use. Ollama duration string ('30m'), seconds as a number, "
                              "or '-1' for never-expire-from-idleness. Default: 30m")
    parser.add_argument("--timeout", type=int, default=14400,
                         help="Overall wall-clock cap in seconds for a single generate call "
                              "(default: 14400 = 4 h). Separate from --idle-timeout.")
    parser.add_argument("--num-ctx", type=int, default=0,
                         help="Context window (tokens) to request from the server; 0 sends nothing "
                              "and uses the model's default. The pipeline needs about 32k.")
    parser.add_argument("--idle-timeout", type=int, default=180,
                         help="Seconds of complete silence (no new output at all) before giving up "
                              "on a call -- this is what actually catches the model getting "
                              "unloaded mid-generation. Also covers cold model load time, since "
                              "that's the wait before the first byte arrives; raise this if you're "
                              "using a large or slow-loading model. Default: 180")
    parser.add_argument("--no-think", action="store_true", help="send think:false")
    args = parser.parse_args()
    client = OllamaClient(host=args.ollama_host,
                          model=args.model,
                          keep_alive=args.keep_alive,
                          idle_timeout=args.idle_timeout,
                          max_duration=args.timeout,
                          echo=True,
                          options={"num_ctx": args.num_ctx} if args.num_ctx else None)
    print('enter prompt and close stdin:')
    client.run_prompt(sys.stdin.read(), think=False if args.no_think else None)
    print(json.dumps(client.last_call, indent=2))
