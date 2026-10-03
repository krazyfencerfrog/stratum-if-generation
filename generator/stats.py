"""Per-call budgets and run statistics.

Trace length on the production model is a function of what a call is given
and what it is asked to return, not of instructions about how to reason
(docs/fable_response_4.md, section 2). So every model call belongs to a
CLASS that fixes how it runs (thinking on or off), what it is expected to
cost (targets, reported), and where it is cut off (limits, enforced by the
client as circuit breakers). When a thinking call passes its thinking
limit, the client first forces an answer from the thinking so far; if that
fails, or another limit tripped, the call is retried once with thinking
off, so one runaway trace costs a bounded amount instead of the run.

Every attempt of every call is appended to stories/<id>/<id>_run_stats.json;
generator/report.py reads it.

The numbers come from the archived kernel1 run (qwen 27B-class, about 17
output bytes per second end to end): 25 KB of thinking is about 25 minutes.
"""

import json
import os
import re
import time

SCHEMA_VERSION = 4

# Qwen's published guidance for its thinking models: never greedy; these
# values in thinking mode, the second set with thinking off. repeat_penalty
# 1.0 because Ollama's default 1.1 penalizes the quotes and braces JSON is
# made of. presence_penalty is not sent; set STRATUM_PRESENCE_PENALTY (0-2)
# if a trace or an output starts looping.
SAMPLER_THINK = {'temperature': 0.6, 'top_p': 0.95, 'top_k': 20, 'repeat_penalty': 1.0}
SAMPLER_NO_THINK = {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'repeat_penalty': 1.0}

# think: None = the model's default (thinking on for a thinking model),
#        False = thinking off.
# target_*: what a healthy call costs; over-target calls are flagged in the
#        report and nothing else happens.
# limit_*: circuit breakers. None = no breaker of that kind.
# force_answer: when the thinking-byte breaker trips before any answer has
#        started, the client first tries budget forcing (it closes the think
#        block and asks for the answer from the thinking so far; see
#        ollama_client.py). Only if that fails does `fallback` apply.
# Every class with breakers on also cuts reasoning that loops (the client's
#        detect_loops); a looped call is re-run once from a new seed, thinking
#        still on, before `fallback` applies.
# fallback: what to do when a breaker trips on a thinking call.
CALL_CLASSES = {
    # phase 3 and the rating filter: untouched judgment prompts. Reported
    # against the target; no breaker, because a no-think retry of an
    # extraction would silently weaken phase 3.
    'extract': {
        'think': None,
        'target_thinking_bytes': 30000, 'target_seconds': 1800,
        'limit_thinking_bytes': None, 'limit_seconds': None, 'limit_response_bytes': None,
        'num_predict': None, 'fallback': None,
    },
    # classification and transcription: thinking off, a short rationale
    # field first in the schema, structured output. The thinking limit is
    # generous on purpose: a server that ignores think:false should make
    # these calls slow (and visible in the report), not kill the run.
    'classify': {
        'think': False,
        'target_thinking_bytes': 0, 'target_seconds': 360,
        'limit_thinking_bytes': 40000, 'limit_seconds': 2700, 'limit_response_bytes': 16000,
        'num_predict': 14000, 'fallback': None,
    },
    # the premise audit (3.5v): a fixed checklist over the premise, answered
    # with thinking ON. With thinking off it passed a turn that was the
    # decision axis as a two-way pick, and a premise copied from a
    # calibration example (2026-10-02 kernel1 runs). Its answer runs 5-7 KB,
    # so the response limit is the build class's, not the judge's.
    'audit': {
        'think': None,
        'target_thinking_bytes': 12000, 'target_seconds': 720,
        'limit_thinking_bytes': 24000, 'limit_seconds': 1500, 'limit_response_bytes': 24000,
        'num_predict': 14000, 'fallback': 'no_think', 'force_answer': True,
    },
    # a small judgment over a short digest (the next-line seed).
    'judge': {
        'think': None,
        'target_thinking_bytes': 12000, 'target_seconds': 720,
        'limit_thinking_bytes': 24000, 'limit_seconds': 1500, 'limit_response_bytes': 8000,
        'num_predict': 8192, 'fallback': 'no_think', 'force_answer': True,
    },
    # construction: the premise pieces, the line plans, the node fill.
    'build': {
        'think': None,
        'target_thinking_bytes': 25000, 'target_seconds': 1500,
        'limit_thinking_bytes': 40000, 'limit_seconds': 2700, 'limit_response_bytes': 24000,
        'num_predict': 14000, 'fallback': 'no_think', 'force_answer': True,
    },
}


def call_profile(klass):
    return dict(CALL_CLASSES.get(klass) or CALL_CLASSES['extract'])


def sampler_for(think):
    """Sampler options for one call. STRATUM_SAMPLER=model sends none, so
    the Modelfile's own parameters apply; options set on the client in
    dynamic_config.py override these either way."""
    if os.environ.get('STRATUM_SAMPLER', '').lower() == 'model':
        return {}
    opts = dict(SAMPLER_NO_THINK if think is False else SAMPLER_THINK)
    penalty = os.environ.get('STRATUM_PRESENCE_PENALTY')
    if penalty:
        try:
            opts['presence_penalty'] = float(penalty)
        except ValueError:
            pass
    return opts


def step_of(prefix):
    """The step a call prefix belongs to, without its iteration or round:
    s4b_i2 -> s4b, s3_5v_r1 -> s3_5v, s3_5r2 -> s3_5r, s5b_n03 -> s5b."""
    p = re.sub(r'_(i|r)\d+', '', prefix)
    p = re.sub(r'^(s3_5r)\d+$', r'\1', p)
    if re.match(r'^s[4-9]', p):
        p = re.sub(r'^(s\d+[a-z]?)_.*$', r'\1', p)
    return p


class RunStats:
    """Appends one record per call attempt to <id>_run_stats.json."""

    def __init__(self, path, story_id):
        self.path = path
        self.story_id = story_id
        self.calls = []
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as f:
                    self.calls = (json.load(f) or {}).get('calls') or []
            except (json.JSONDecodeError, OSError):
                self.calls = []
        self.session_start = len(self.calls)

    def record(self, **rec):
        profile = call_profile(rec.get('klass'))
        rec.setdefault('at', time.strftime('%Y-%m-%dT%H:%M:%S'))
        rec['target_thinking_bytes'] = profile['target_thinking_bytes']
        rec['target_seconds'] = profile['target_seconds']
        over = []
        if rec.get('thinking_bytes', 0) > profile['target_thinking_bytes'] and rec.get('mode') != 'no_think':
            over.append('thinking')
        if rec.get('seconds', 0) > profile['target_seconds']:
            over.append('seconds')
        rec['over_target'] = over
        self.calls.append(rec)
        self.save()
        return rec

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump({'schema_version': SCHEMA_VERSION, 'story_id': self.story_id, 'calls': self.calls},
                      f, indent=1, ensure_ascii=False)

    def session(self):
        return self.calls[self.session_start:]

    def summary_lines(self):
        """A few lines for the end of a run: what this session cost and
        which calls went over."""
        calls = self.session()
        if not calls:
            return ['run stats: no model calls this session (everything was loaded from saved files)']
        seconds = sum(c.get('seconds', 0) for c in calls)
        thinking = sum(c.get('thinking_bytes', 0) for c in calls)
        lines = [f'run stats: {len(calls)} model call(s) this session, {seconds / 60:.1f} min, '
                 f'{thinking / 1000:.1f} KB of thinking -> {os.path.basename(self.path)}']
        for c in calls:
            flags = list(c.get('over_target') or [])
            if c.get('breaker'):
                flags.append(f"breaker:{c['breaker']}")
            if not c.get('ok'):
                flags.append('rejected')
            if flags:
                lines.append(f"  {c.get('prefix')}_{c.get('name')} attempt {c.get('attempt')}: "
                             f"{c.get('thinking_bytes', 0) / 1000:.1f} KB thinking, {c.get('seconds', 0) / 60:.1f} min "
                             f"[{', '.join(flags)}]")
        return lines
