#!/usr/bin/env python3
"""Claude Code CLI backend: calls `claude -p` non-interactively for inference.

Runs the Stratum IF pipeline on a Claude subscription (or whatever auth the
local Claude Code install uses) instead of local Ollama inference. Each call
is a single stateless completion: tools, MCP servers, skills, CLAUDE.md
discovery and session persistence are all switched off, and the Claude Code
system prompt is replaced with a minimal one.

Environment:
  STRATUM_CLAUDE_MODEL       model or alias (opus, sonnet, haiku, claude-...);
                             falls back to STRATUM_MODEL, then the CLI default
  STRATUM_CLAUDE_EFFORT      effort for thinking calls (default high);
                             think=False calls always run at low
  STRATUM_CLAUDE_PATH        path to the claude executable
  STRATUM_CLAUDE_LIMIT_WAIT  seconds to sleep when the usage limit is hit
                             (default 900)
  STRATUM_CLAUDE_LIMIT_MAX   total seconds to keep waiting on usage limits
                             before giving up (default 21600)

Every call also reports how much of the subscription's 5-hour and weekly
usage windows is used (last_call['usage_limits']); main.py logs it and
saves it in run_stats.json, and generator/dashboard.py shows it.

(Claude Code sets CLAUDE_EFFORT etc. in its own environment, hence the
STRATUM_ prefix.)
"""

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from llm_client import LlmClient, LlmCallError
from stats import USAGE_WINDOWS, usage_line


SYSTEM_PROMPT = ("You are a text generation backend for an automated story pipeline. "
                 "Follow the user's instructions exactly and reply with only the requested output.")

LIMIT_PATTERN = re.compile(r"usage limit|hit your limit|rate limit|rate_limit|overloaded|\b429\b|\b529\b", re.I)


def usage_limits_from(info):
    """A rate_limit_event's rate_limit_info as {'five_hour': {'used': 0.34,
    'resets_at': epoch}, 'seven_day': {...}, 'status': 'allowed'}, or None
    when it carries no windows."""
    if not isinstance(info, dict):
        return None
    windows = info.get('unifiedWindows') or {}
    out = {}
    for key, _ in USAGE_WINDOWS:
        w = windows.get(key)
        if isinstance(w, dict) and isinstance(w.get('utilization'), (int, float)):
            out[key] = {'used': w['utilization'], 'resets_at': w.get('resetsAt')}
    if not out:
        return None
    out['status'] = info.get('status')
    return out



class ClaudeClient(LlmClient):
    """LlmClient implementation dispatching prompts to the `claude` CLI."""

    def __init__(self, model=None, effort=None, claude_path=None, echo=True):
        super().__init__()
        self.model = model or os.environ.get("STRATUM_CLAUDE_MODEL") or os.environ.get("STRATUM_MODEL") or None
        self.effort = effort or os.environ.get("STRATUM_CLAUDE_EFFORT") or "high"
        self.claude_path = (claude_path or os.environ.get("STRATUM_CLAUDE_PATH") or shutil.which("claude")
                            or os.path.expanduser("~/.local/bin/claude"))
        self.limit_wait = int(os.environ.get("STRATUM_CLAUDE_LIMIT_WAIT", 900))
        self.limit_max = int(os.environ.get("STRATUM_CLAUDE_LIMIT_MAX", 21600))
        self.echo = echo
        self.last_call = {}
        self.usage_limits = None    # the latest usage windows any call reported
        # an empty working directory keeps the repo's CLAUDE.md / GEMINI.md
        # out of the model's context
        self.workdir = tempfile.mkdtemp(prefix="stratum_claude_")

    def _effort_for(self, think):
        return "low" if think is False else self.effort

    def _build_cmd(self, think, schema):
        # stream-json (which -p only writes with --verbose) carries the
        # rate_limit_event with the usage windows; its last line is the
        # same result object --output-format json prints
        # --include-partial-messages streams the answer as it is written
        cmd = [self.claude_path, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
               "--no-session-persistence", "--system-prompt", SYSTEM_PROMPT,
               "--effort", self._effort_for(think)]
        if self.model:
            cmd.extend(["--model", self.model])
        if isinstance(schema, dict):
            cmd.extend(["--json-schema", json.dumps(schema)])
        return cmd

    @staticmethod
    def _parse_output(raw_output):
        """(the result object, the usage windows or None) from the CLI's
        stream-json lines. A single JSON object (--output-format json, or
        an error printed before any stream) is taken as the result."""
        data, limits_info = None, None
        try:
            whole = json.loads(raw_output)
            if isinstance(whole, dict):
                return whole, None
        except json.JSONDecodeError:
            pass
        for line in raw_output.splitlines():
            line = line.strip()
            if not line.startswith('{'):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                data = event
            elif event.get("type") == "rate_limit_event":
                limits_info = usage_limits_from(event.get("rate_limit_info")) or limits_info
        if data is None:
            start, end = raw_output.find('{'), raw_output.rfind('}')
            if start != -1 and end > start:
                try:
                    data = json.loads(raw_output[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return data, limits_info

    def describe(self, think=None):
        return {'model': self.model or 'default', 'effort': self._effort_for(think)}

    def _run_cli(self, cmd, prompt, timeout):
        """Runs claude and reads its stream-json lines as they come, so the
        call's progress (thinking tokens, the answer as it is written) can
        be reported and the answer echoed to the call's log while it runs.
        Returns (returncode, stdout, stderr) like subprocess.run, with the
        token-by-token stream_event lines left out of stdout. Raises
        subprocess.TimeoutExpired after `timeout` seconds."""
        # its own session: claude never sees the terminal, so ctrl-c interrupts
        # this process (which kills claude below) instead of killing claude and
        # leaving the retry loop to go on
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, cwd=self.workdir, start_new_session=True)
        lines = queue.Queue()
        err = []

        def feed():
            try:
                proc.stdin.write(prompt)
                proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

        def drain(stream, into, end=None):
            for line in stream:
                into(line)
            if end:
                end()

        readers = [threading.Thread(target=feed, daemon=True),
                   threading.Thread(target=drain, args=(proc.stdout, lines.put, lambda: lines.put(None)), daemon=True),
                   threading.Thread(target=drain, args=(proc.stderr, err.append), daemon=True)]
        for t in readers:
            t.start()
        kept, live = [], {'started': time.time(), 'answer_chars': 0, 'writing': False}
        deadline = time.time() + timeout
        try:
            # read in this thread, not a reader thread: the pipeline routes
            # this thread's stdout to the call's log
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(cmd, timeout)
                try:
                    line = lines.get(timeout=min(remaining, 1.0))
                except queue.Empty:
                    continue
                if line is None:
                    break
                if not self._on_event(line, live):
                    kept.append(line)
            proc.wait(timeout=max(1, deadline - time.time()))
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        finally:
            if live['writing'] and self.echo:
                print(flush=True)       # end the streamed answer's line
        for t in readers[1:]:
            t.join(1)
        return subprocess.CompletedProcess(cmd, proc.returncode, ''.join(kept), ''.join(err))

    def _on_event(self, line, live):
        """Reports one streamed line's progress. True for the token-by-token
        stream_event lines, which are not kept for parsing."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        kind = event.get('type')
        if kind == 'system' and event.get('subtype') == 'thinking_tokens':
            # the thinking itself is withheld from -p output; its size is not
            self.report(phase='thinking', thinking_tokens=event.get('estimated_tokens'))
            return False
        if kind == 'rate_limit_event':
            limits_info = usage_limits_from(event.get('rate_limit_info'))
            if limits_info:
                self.report(usage_limits=limits_info)
            return False
        if kind != 'stream_event':
            return False
        ev = event.get('event') or {}
        if ev.get('type') == 'content_block_delta':
            delta = ev.get('delta') or {}
            text = delta.get('text') or delta.get('partial_json') or ''
            if text:
                if not live['writing']:
                    live['writing'] = True
                    self.report(force=True, phase='writing',
                                first_token_seconds=round(time.time() - live['started'], 2))
                    if self.echo:
                        print('  [answer] ', end='')
                live['answer_chars'] += len(text)
                self.report(answer_chars=live['answer_chars'])
                if self.echo:
                    print(text, end='', flush=True)
        elif ev.get('type') == 'message_delta':
            tokens = (ev.get('usage') or {}).get('output_tokens')
            if tokens:
                self.report(output_tokens=tokens)
        return True

    @staticmethod
    def _is_limit(text, data=None):
        status = (data or {}).get("api_error_status")
        return status in (429, 529) or bool(LIMIT_PATTERN.search(text or ""))

    def run_prompt(self, prompt, **kwargs):
        """Run a single prompt through claude and return (thinking, response)."""
        think = kwargs.get("think")
        schema = kwargs.get("format")
        limits = kwargs.get("limits") or {}

        cmd = self._build_cmd(think, schema)
        format_sent = isinstance(schema, dict)

        timeout = limits.get("max_seconds")
        timeout = max(int(timeout), 60) if timeout is not None else 1800

        max_attempts = 3
        attempt = 0
        limit_waited = 0
        while True:
            attempt += 1
            started = time.time()
            self.report(force=True, phase='requesting', retry=attempt - 1 or None, waiting_until=None,
                        thinking_tokens=None, answer_chars=0, first_token_seconds=None, output_tokens=None)
            try:
                proc = self._run_cli(cmd, prompt, timeout)
            except subprocess.TimeoutExpired:
                elapsed = round(time.time() - started, 2)
                self.last_call = {
                    'seconds': elapsed,
                    'aborted': 'wall_clock',
                    'done_reason': 'timeout',
                    'format_sent': format_sent,
                }
                raise LlmCallError(f"claude call timed out after {elapsed:.1f}s")

            raw_output = proc.stdout.strip()
            data, limits_info = self._parse_output(raw_output)
            if limits_info:
                self.usage_limits = limits_info

            if data is None or proc.returncode != 0 or data.get("is_error"):
                err_msg = (data or {}).get("result") or proc.stderr.strip() or raw_output
                err_msg = str(err_msg)[:500]
                if self._is_limit(err_msg, data):
                    if limit_waited >= self.limit_max:
                        raise LlmCallError(f"claude usage limit persisted for {limit_waited}s: {err_msg}",
                                           http_status=429)
                    if self.echo:
                        print(f"  [claude] Usage limit reached ({err_msg.strip()}). Pausing for {self.limit_wait}s..."
                              + (f" ({usage_line(limits_info)})" if limits_info else ""))
                    self.report(force=True, phase='usage limit', waiting_until=time.time() + self.limit_wait,
                                limit_message=err_msg.strip()[:200])
                    time.sleep(self.limit_wait)
                    limit_waited += self.limit_wait
                    attempt -= 1    # waiting out a limit does not spend an attempt
                    continue
                if data is None:
                    last_error = LlmCallError(f"Could not parse claude output as JSON: {raw_output[:500]}")
                else:
                    last_error = LlmCallError(f"claude failed ({data.get('subtype') or proc.returncode}): {err_msg}")
                if attempt < max_attempts:
                    self.report(force=True, phase='retrying', retry_reason=str(last_error)[:200])
                    time.sleep(attempt * 4)
                    continue
                self.last_call = {
                    'seconds': round(time.time() - started, 2),
                    'aborted': 'error',
                    'done_reason': 'error',
                    'format_sent': format_sent,
                    'crash_retries': attempt - 1,
                }
                raise last_error

            if data.get("structured_output") is not None:
                response_text = json.dumps(data["structured_output"])
            else:
                response_text = data.get("result") or ""
                # Strip markdown code blocks if the model wrapped its output
                clean = response_text.strip()
                if clean.startswith("```"):
                    clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
                    clean = re.sub(r"\n?```$", "", clean)
                    response_text = clean.strip()

            if not response_text.strip():
                if attempt < max_attempts:
                    time.sleep(2)
                    continue
                raise LlmCallError("claude returned an empty response")

            usage = data.get("usage") or {}
            duration = (data.get("duration_ms") or (time.time() - started) * 1000) / 1000
            prompt_tokens = ((usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0)
                             + (usage.get("cache_read_input_tokens") or 0))
            output_tokens = usage.get("output_tokens") or 0
            thinking_tokens = (usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0

            thinking_text = f"[Claude thinking tokens: {thinking_tokens}]" if thinking_tokens > 0 else ""

            self.last_call = {
                'seconds': round(duration, 2),
                'thinking_bytes': len(thinking_text.encode('utf-8')),
                'response_bytes': len(response_text.encode('utf-8')),
                'prompt_tokens': prompt_tokens,
                'output_tokens': output_tokens,
                'thinking_tokens': thinking_tokens,
                'total_tokens': prompt_tokens + output_tokens,
                'done_reason': 'length' if data.get("stop_reason") == "max_tokens" else 'stop',
                'format_sent': format_sent,
                'aborted': None,
                'crash_retries': attempt - 1,
                # the CLI's time waiting on the API (the rest of `seconds` is the CLI itself),
                # and what this call spent asleep on usage limits before it ran
                'api_seconds': round(data['duration_api_ms'] / 1000, 2) if data.get('duration_api_ms') else None,
                'limit_wait_seconds': limit_waited or None,
                # the subscription's 5-hour and weekly windows as this call left them
                'usage_limits': limits_info,
            }

            if self.echo:
                model_disp = next(iter(data.get("modelUsage") or {}), None) or self.model or "default"
                retries_disp = f" (retry {attempt-1})" if attempt > 1 else ""
                print(f"  [{model_disp}] {duration:.1f}s | in: {prompt_tokens} | out: {output_tokens} "
                      f"(think: {thinking_tokens}){retries_disp}"
                      + (f" | {usage_line(limits_info)}" if limits_info else ""))

            return thinking_text, response_text
