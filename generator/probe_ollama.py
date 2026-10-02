#!/usr/bin/env python3
"""Ask the local Ollama server what it can do, before spending hours on it.

    cd generator
    python probe_ollama.py                 # uses dynamic_config.get_client()
    python probe_ollama.py --ctx-test 32768  # also time a smaller context window
    python probe_ollama.py --host http://localhost:11434 --model qwen3:8b

A few short calls (a couple of minutes on a 27B model, plus the load) that
answer the questions the pipeline's defaults had to guess at:

  1. server version, the model's own parameters and context window
  2. does a plain call return its reasoning in a separate `thinking` field,
     and how fast does this machine generate
  3. does think:false really switch the reasoning off
  4. structured outputs (format = a JSON schema) with thinking off: are the
     enum, the nullable field and the key order honored
  5. structured outputs WITH thinking: do you get both a trace and valid
     JSON (if yes, set structured='always' in dynamic_config.py)
  6. does num_predict cut a call off with done_reason "length"
  7. does closing the connection stop generation (the circuit breakers
     depend on it)
  8. optionally, is a smaller num_ctx faster on this hardware

It prints PASS / FAIL / INFO per check and, at the end, the client
settings it recommends. Nothing is written to disk.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from llm_client import LlmCallError
from ollama_client import OllamaClient
from stats import SAMPLER_THINK, SAMPLER_NO_THINK

PROBE_SCHEMA = {
    'type': 'object',
    'properties': {
        'note': {'type': 'string'},
        'answer': {'type': 'string', 'enum': ['yes', 'no']},
        'count': {'type': ['integer', 'null']},
        'items': {'type': 'array', 'items': {'type': 'object',
                                              'properties': {'id': {'type': 'integer'}, 'label': {'type': 'string'}},
                                              'required': ['id', 'label']}},
        'maybe': {'anyOf': [{'type': 'object', 'properties': {'x': {'type': 'string'}}, 'required': ['x']},
                            {'type': 'null'}]},
    },
    'required': ['note', 'answer', 'count', 'items', 'maybe'],
}

QUESTION = ('A ferry holds 12 cars. 30 cars are waiting. Is two crossings enough to carry them all? '
            'Answer in one short sentence.')
JSON_QUESTION = ('A ferry holds 12 cars. 30 cars are waiting. Is two crossings enough to carry them all?\n'
                 'Output ONLY JSON: {"note": one sentence of reasoning, "answer": "yes" or "no", '
                 '"count": the number of crossings needed or null, "items": [{"id": 1, "label": "first crossing"}, ...], '
                 '"maybe": null}')
LONG_QUESTION = ('Think step by step, at length, about how you would schedule 40 ferry crossings across a week '
                 'for 7 crews with different rest rules. Consider at least ten alternatives before answering.')

results = []


def report(status, name, detail=''):
    results.append((status, name, detail))
    print(f'[{status:4s}] {name}' + (f': {detail}' if detail else ''))


def http_json(host, path, payload=None, timeout=30):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(host.rstrip('/') + path, data=data,
                                 headers={'Content-Type': 'application/json'},
                                 method='POST' if payload is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def speed(info):
    if info.get('output_tokens') and info.get('eval_seconds'):
        return info['output_tokens'] / info['eval_seconds']
    return None


def valid_probe_json(text):
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f'not JSON ({e})'
    if not isinstance(obj, dict):
        return False, 'not an object'
    keys = list(obj.keys())
    if keys != ['note', 'answer', 'count', 'items', 'maybe']:
        return False, f'keys or key order differ: {keys}'
    if obj['answer'] not in ('yes', 'no'):
        return False, f"answer outside the enum: {obj['answer']!r}"
    if obj['count'] is not None and not isinstance(obj['count'], int):
        return False, 'count is neither an integer nor null'
    if not isinstance(obj['items'], list):
        return False, 'items is not a list'
    return True, f"answer={obj['answer']}, count={obj['count']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default='')
    parser.add_argument('--model', default='')
    parser.add_argument('--ctx-test', type=int, default=0,
                        help='also time generation with this num_ctx (reloads the model twice)')
    args = parser.parse_args()

    if args.host and args.model:
        client = OllamaClient(host=args.host, model=args.model, echo=False, idle_timeout=600, max_duration=1800)
    else:
        import dynamic_config
        client = dynamic_config.get_client()
        if not isinstance(client, OllamaClient):
            print('dynamic_config.get_client() did not return an OllamaClient; pass --host and --model.')
            return 2
        if args.host:
            client.host = args.host
        if args.model:
            client.model = args.model
        client.echo = False
    configured_structured = client.structured
    host, model = client.host, client.model
    print(f'probing {model} at {host}\n')

    # 1 ---- version and model
    try:
        version = http_json(host, '/api/version').get('version')
        report('INFO', 'server version', str(version))
    except (urllib.error.URLError, OSError) as e:
        report('FAIL', 'server reachable', str(e))
        return 1
    try:
        show = http_json(host, '/api/show', {'model': model})
        params = (show.get('parameters') or '').strip()
        report('INFO', 'model parameters (Modelfile)', '; '.join(' '.join(line.split()) for line in params.split('\n')) or '(none set: server defaults apply)')
        caps = show.get('capabilities')
        if caps is not None:
            report('PASS' if 'thinking' in caps else 'INFO', 'model capabilities', ', '.join(caps))
        details = show.get('details') or {}
        report('INFO', 'model', f"{details.get('parameter_size', '?')} {details.get('quantization_level', '?')}")
        ctx = [v for k, v in (show.get('model_info') or {}).items() if k.endswith('context_length')]
        num_ctx = [line.split()[-1] for line in params.split('\n') if line.strip().startswith('num_ctx')]
        report('INFO', 'context window', f"trained {ctx[0] if ctx else '?'}, num_ctx "
               f"{client.options.get('num_ctx') or (num_ctx[0] if num_ctx else 'server default')}")
        if 'temperature' not in params and 'temperature' not in client.options:
            report('INFO', 'sampler', 'the Modelfile sets no temperature; the pipeline sends its own per call (stats.py)')
    except (urllib.error.URLError, OSError, KeyError) as e:
        report('INFO', 'model details unavailable', str(e))

    limits = {'num_predict': 1200, 'max_seconds': 900}

    # 2 ---- a plain call: thinking field, speed
    base_speed = None
    try:
        thinking, response = client.run_prompt(QUESTION, options=dict(SAMPLER_THINK), limits=limits)
        info = client.last_call
        base_speed = speed(info)
        if thinking:
            report('PASS', 'thinking arrives separately from the response',
                   f'{len(thinking)} chars of reasoning, {len(response)} of answer')
        else:
            report('INFO', 'no reasoning trace on a default call',
                   'this model does not think by default, or the server folded it into the response')
        if base_speed:
            report('INFO', 'generation speed', f"{base_speed:.1f} tokens/s (~{base_speed * 4:.0f} bytes/s); "
                   f"prompt {info.get('prompt_tokens')} tokens; load {info.get('load_seconds') or 0:.0f}s")
    except LlmCallError as e:
        report('FAIL', 'plain call', str(e))
        return 1

    # 3 ---- think:false
    no_think_ok = False
    try:
        thinking, response = client.run_prompt(QUESTION, think=False, options=dict(SAMPLER_NO_THINK), limits=limits)
        no_think_ok = not thinking and bool(response)
        report('PASS' if no_think_ok else 'FAIL', 'think:false switches the reasoning off',
               f'{len(thinking)} chars of reasoning, {len(response)} of answer, {client.last_call.get("seconds")}s')
    except LlmCallError as e:
        report('FAIL', 'think:false', str(e))

    # 4 ---- structured output, thinking off
    structured_no_think = False
    client.structured = 'always'
    try:
        thinking, response = client.run_prompt(JSON_QUESTION, think=False, format=PROBE_SCHEMA,
                                               options=dict(SAMPLER_NO_THINK), limits=limits)
        if not client.last_call.get('format_sent'):
            report('FAIL', 'structured output with thinking off', 'the server rejected the schema (HTTP 400)')
        else:
            ok, detail = valid_probe_json(response)
            structured_no_think = ok
            report('PASS' if ok else 'FAIL', 'structured output with thinking off', detail)
    except LlmCallError as e:
        report('FAIL', 'structured output with thinking off', str(e))

    # 5 ---- structured output, thinking on
    structured_think = False
    client.structured = 'always'
    try:
        thinking, response = client.run_prompt(JSON_QUESTION, format=PROBE_SCHEMA,
                                               options=dict(SAMPLER_THINK), limits=limits)
        if not client.last_call.get('format_sent'):
            report('FAIL', 'structured output with thinking on', 'the server rejected the schema (HTTP 400)')
        else:
            ok, detail = valid_probe_json(response)
            if ok and thinking:
                structured_think = True
                report('PASS', 'structured output with thinking on', f'{len(thinking)} chars of reasoning and valid JSON ({detail})')
            elif ok:
                report('FAIL', 'structured output with thinking on',
                       'valid JSON but NO reasoning trace: the schema suppressed thinking; keep structured="no_think"')
            else:
                report('FAIL', 'structured output with thinking on', f'{detail}; reasoning {len(thinking)} chars')
    except LlmCallError as e:
        report('FAIL', 'structured output with thinking on', str(e))
    client.structured = configured_structured

    # 6 ---- num_predict
    try:
        client.run_prompt(LONG_QUESTION, options=dict(SAMPLER_THINK), limits={'num_predict': 24, 'max_seconds': 300})
        reason = client.last_call.get('done_reason')
        report('PASS' if reason == 'length' else 'FAIL', 'num_predict cuts a call off',
               f'done_reason={reason!r} after {client.last_call.get("output_tokens")} tokens')
    except LlmCallError as e:
        report('FAIL', 'num_predict', str(e))

    # 7 ---- the byte breaker, and whether the server really stops
    try:
        started = time.time()
        client.run_prompt(LONG_QUESTION, options=dict(SAMPLER_THINK), limits={'max_thinking_bytes': 300, 'max_response_bytes': 300, 'max_seconds': 300})
        cut = client.last_call.get('aborted')
        cut_seconds = time.time() - started
        started = time.time()
        client.run_prompt('Reply with the single word: ready', think=False, options=dict(SAMPLER_NO_THINK),
                          limits={'num_predict': 16, 'max_seconds': 300})
        follow = time.time() - started
        if cut:
            report('PASS' if follow < max(30, cut_seconds * 3) else 'INFO', 'circuit breaker closes the call',
                   f'cut by {cut} after {cut_seconds:.0f}s; the next call answered in {follow:.0f}s'
                   + ('' if follow < max(30, cut_seconds * 3) else ' (slow: the server may have kept generating)'))
        else:
            report('INFO', 'circuit breaker', 'the call finished before reaching the 300-byte limit')
    except LlmCallError as e:
        report('FAIL', 'circuit breaker', str(e))

    # 8 ---- context window size against speed
    if args.ctx_test:
        try:
            saved = dict(client.options)
            client.options['num_ctx'] = args.ctx_test
            client.run_prompt(QUESTION, options=dict(SAMPLER_THINK), limits=limits)
            small = speed(client.last_call)
            client.options = saved
            if small and base_speed:
                gain = small / base_speed
                report('INFO', f'num_ctx {args.ctx_test}', f'{small:.1f} tokens/s against {base_speed:.1f} at the configured window '
                       f'({gain:.2f}x)' + ('; set options={"num_ctx": %d} in dynamic_config.py' % args.ctx_test if gain > 1.15 else ''))
            # put the configured window back so the next real run does not start with a reload surprise
            client.run_prompt('Reply with the single word: ready', think=False, limits={'num_predict': 16, 'max_seconds': 600})
        except LlmCallError as e:
            report('FAIL', 'ctx test', str(e))

    print('\nrecommended client settings:')
    structured = 'always' if structured_think else ('no_think' if structured_no_think else 'never')
    print(f'  OllamaClient(..., structured={structured!r})')
    if not no_think_ok:
        print('  think:false is not honored by this model/server: the "classify" calls will run with a trace;')
        print('  expect them to cost minutes instead of seconds (report.py will show thinking bytes on them).')
    if base_speed:
        print(f'  at {base_speed:.1f} tokens/s the 25 KB thinking target is about {25000 / (base_speed * 4) / 60:.0f} minutes per call.')
    return 0 if not any(s == 'FAIL' for s, _, _ in results) else 1


if __name__ == '__main__':
    sys.exit(main())
