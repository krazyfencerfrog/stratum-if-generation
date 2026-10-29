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

Timing: each call records when it started, how long it waited on the model
(`seconds`) and how long the Python after the answer took (`check_seconds`:
parsing, validating, saving). Each run is a session in the file's
`sessions`, and each stage of the run a span in it: its wall time split
into model time (the time calls were in flight, overlapping calls counted
once) and Python time (the rest). A `[timing]` line is printed as each
stage ends, and a table at the end of the run.

Progress: the open session also holds its process id, the stages the run
means to go through (`plan`), the calls in flight (`running`) and where
long Python work has got (`python_work`: the engine playtest's phase and
count), and the file is saved as each stage and call starts, so
generator/dashboard.py can show a run while it is going. On the Claude backend each call also
records the subscription's 5-hour and weekly usage (`usage_limits`), and
the session keeps the newest reading.

The numbers come from the archived kernel1 run (qwen 27B-class, about 17
output bytes per second end to end): 25 KB of thinking is about 25 minutes.
"""

import contextlib
import json
import os
import re
import threading
import time

SCHEMA_VERSION = 5

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
        'limit_thinking_bytes': 24000, 'limit_seconds': 1500, 'limit_response_bytes': 16000,
        'num_predict': 8192, 'fallback': 'no_think', 'force_answer': True,
    },
    # construction: the premise pieces, the line plans, the node fill.
    # Qwen3.8 27B runs every build call to any limit tried (40 KB on Q5 and
    # IQ3_XS; 89 KB when unlimited), and the last part of a long trace is
    # re-checking settled details. On kernel1 (2026-10-02) a 25 KB limit gave
    # main lines as good as 40 KB or unlimited, and a full outline with more
    # lines in less time; its forced answers passed or passed on retry.
    'build': {
        'think': None,
        'target_thinking_bytes': 20000, 'target_seconds': 900,
        'limit_thinking_bytes': 35000, 'limit_seconds': 1800, 'limit_response_bytes': 48000,
        'num_predict': 14000, 'fallback': 'no_think', 'force_answer': True,
    },
    # prose revision and targeted entity rewrites: thinking off,
    # structured output matching schemas.PROSE_EDIT. Cuts downstream
    # rewrite latency from ~4-5 minutes per unit to ~15-30 seconds.
    'edit': {
        'think': False,
        'target_thinking_bytes': 0, 'target_seconds': 180,
        'limit_thinking_bytes': 20000, 'limit_seconds': 600, 'limit_response_bytes': 16000,
        'num_predict': 14000, 'fallback': None,
    },
}


def call_profile(klass):
    """A call class's budget. STRATUM_THINKING_LIMIT overrides the thinking
    limit per class for experiments ("build=40000,judge=30000"); the target
    moves with it (80% of the limit)."""
    profile = dict(CALL_CLASSES.get(klass) or CALL_CLASSES['extract'])
    for item in os.environ.get('STRATUM_THINKING_LIMIT', '').split(','):
        name, _, value = item.partition('=')
        if name.strip() == klass and value.strip().isdigit():
            profile['limit_thinking_bytes'] = int(value)
            profile['target_thinking_bytes'] = int(int(value) * 0.8)
            profile['limit_seconds'] = max(profile.get('limit_seconds') or 0, int(int(value) / 25000 * 1800))
    return profile


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
        p = re.sub(r'^(s\d+[a-z0-9]*)_.*$', r'\1', p)
    return p


def stamp(t):
    """An epoch time as local ISO time to the millisecond."""
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t)) + f'.{int(t % 1 * 1000):03d}'


def duration(seconds):
    """0.04s, 12.3s, 4m05s, 1h02m."""
    seconds = seconds or 0
    if seconds < 10:
        return f'{seconds:.2f}s'
    if seconds < 60:
        return f'{seconds:.1f}s'
    if seconds < 3600:
        return f'{int(seconds // 60)}m{int(seconds % 60):02d}s'
    return f'{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m'


# a Claude subscription's usage windows (claude_client.usage_limits_from) and their labels
USAGE_WINDOWS = (('five_hour', '5h'), ('seven_day', 'week'))


def usage_line(limits):
    """'5h 34% (resets 15:00), week 12% (resets Mon 10:00)'."""
    parts = []
    for key, label in USAGE_WINDOWS:
        w = (limits or {}).get(key)
        if not w:
            continue
        reset = ''
        if w.get('resets_at'):
            fmt = '%H:%M' if w['resets_at'] - time.time() < 86400 else '%a %H:%M'
            reset = f" (resets {time.strftime(fmt, time.localtime(w['resets_at']))})"
        parts.append(f"{label} {w['used'] * 100:.0f}%{reset}")
    return ', '.join(parts)


def busy_seconds(intervals, start, end):
    """How much of [start, end] the (t0, t1) intervals cover, overlaps once."""
    total, reach = 0.0, start
    for t0, t1 in sorted((max(a, start), min(b, end)) for a, b in intervals):
        if t1 > reach:
            total += t1 - max(t0, reach)
            reach = t1
    return total


def timing_lines(session):
    """A session's stages as a table: wall, model and Python time each.
    Nested stages are indented under the stage they ran in."""
    rows = [('  ' * st.get('depth', 0) + st['stage'] + ('' if st.get('outcome', 'ok') == 'ok' else f" ({st['outcome']})"), st)
            for st in session.get('stages') or [] if 'seconds' in st]
    if 'seconds' in session:
        rows.append(('TOTAL', session))
    width = max([len('stage')] + [len(label) for label, _ in rows])
    lines = [f"{'stage':{width}s} {'calls':>5s} {'wall':>8s} {'model':>8s} {'python':>8s}"]
    for label, st in rows:
        lines.append(f"{label:{width}s} {st.get('calls', 0):5d} {duration(st.get('seconds')):>8s} "
                     f"{duration(st.get('model_seconds')):>8s} {duration(st.get('python_seconds')):>8s}")
    return lines


def working_on(owner, label, i, n=None, part=None):
    """owner.working_on(...) (the item a loop is on, for the dashboard),
    or nothing for a test's stand-in generator."""
    fn = getattr(owner, 'working_on', None)
    return fn(label, i, n, part) if callable(fn) else contextlib.nullcontext()


def set_working_on(owner, label=None, i=None, n=None, part=None):
    """owner.set_working_on(...), where owner has it."""
    fn = getattr(owner, 'set_working_on', None)
    if callable(fn):
        fn(label, i, n, part)


def parallel_work(owner, work_seconds, wall_seconds):
    """owner.stats.parallel_work(...), where the owner keeps run stats."""
    st = getattr(owner, 'stats', None)
    if isinstance(st, RunStats):
        st.parallel_work(work_seconds, wall_seconds)


@contextlib.contextmanager
def python_work(owner):
    """A progress callback for long Python work (the engine playtest),
    for the length of the block: what it reports is the session's
    `python_work`, which the dashboard shows while no call is in flight.
    None for an owner without an open session."""
    st = getattr(owner, 'stats', None)
    if not isinstance(st, RunStats) or st.current is None:
        yield None
        return
    try:
        yield st.python_progress
    finally:
        st.python_progress()


def stage(owner, name):
    """owner.stats.stage(name), or nothing for an owner without run stats
    (a test's stand-in generator)."""
    stats = getattr(owner, 'stats', None)
    return stats.stage(name) if isinstance(stats, RunStats) else contextlib.nullcontext()


class RunStats:
    """Appends one record per call attempt to <id>_run_stats.json, and the
    timing of each run (session) and its stages."""

    def __init__(self, path, story_id):
        self.path = path
        self.story_id = story_id
        self.calls = []
        self.extra = {}
        if os.path.isfile(path):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f) or {}
                    self.calls = data.get('calls') or []
                    self.extra = {k: v for k, v in data.items() if k not in ('schema_version', 'story_id', 'calls')}
            except (json.JSONDecodeError, OSError):
                self.calls = []
                self.extra = {}
        self.session_start = len(self.calls)
        self.lock = threading.RLock()       # parallel calls record from worker threads
        self.intervals = []                 # (start, end) of this session's model waits, epoch seconds
        self.current = None                 # this session's record in extra['sessions']
        self.open_stages = []
        self.open_recs = []                 # their records, for parallel_work()
        self.last_progress_save = 0.0

    def record_extra(self, key, value):
        with self.lock:
            self.extra[key] = value
            self.save()

    def record(self, model_started=None, model_ended=None, nested_seconds=0.0, **rec):
        """One call attempt. model_started/model_ended (epoch seconds) are
        when the client was called and when it returned: stored as the
        call's `started`, and what came after as its `check_seconds`.
        nested_seconds is the time the check spent in calls of its own (a
        judge the validator asks): those are recorded as calls, so they are
        not counted again as this call's checking."""
        profile = call_profile(rec.get('klass'))
        now = time.time()
        rec.setdefault('at', time.strftime('%Y-%m-%dT%H:%M:%S'))
        if model_started is not None and model_ended is not None:
            rec['started'] = stamp(model_started)
            rec['check_seconds'] = round(max(0.0, now - model_ended - nested_seconds), 3)
        rec['target_thinking_bytes'] = profile['target_thinking_bytes']
        rec['target_seconds'] = profile['target_seconds']
        over = []
        if rec.get('thinking_bytes', 0) > profile['target_thinking_bytes'] and rec.get('mode') != 'no_think':
            over.append('thinking')
        if rec.get('seconds', 0) > profile['target_seconds']:
            over.append('seconds')
        rec['over_target'] = over
        with self.lock:
            self.calls.append(rec)
            if model_started is not None and model_ended is not None:
                self.intervals.append((model_started, model_ended))
            if rec.get('usage_limits') and self.current is not None:
                # the newest reading of the subscription's windows, for the dashboard and the summary
                self.current['usage_limits'] = dict(rec['usage_limits'], at=stamp(now))
            self.save()
        return rec

    # ------------------------------------------------------------ timing

    def start_session(self, argv=None, plan=None):
        """Opens this run's record in `sessions`; end_session closes it.
        plan: the top-level stages the run means to go through."""
        self.session_t0 = time.time()
        with self.lock:
            self.current = {'started': stamp(self.session_t0), 'argv': list(argv or []), 'pid': os.getpid(),
                            'first_call': len(self.calls), 'plan': list(plan or []), 'stages': [], 'running': [],
                            'outcome': 'running'}
            self.extra.setdefault('sessions', []).append(self.current)
            self.save()

    def _spent(self, t0, t1, first_call):
        """(calls, model seconds) for this session's calls from first_call on, within [t0, t1]."""
        with self.lock:
            calls = len(self.intervals) - first_call
            model = busy_seconds(self.intervals[first_call:], t0, t1)
        return calls, model

    @contextlib.contextmanager
    def stage(self, name):
        """Times a stage of the run: its wall time, the model time of the
        calls made inside it and the Python time around them. Stages nest.
        Without an open session (a test driving the generator directly)
        it only runs the body."""
        if self.current is None:
            yield
            return
        t0 = time.time()
        first = len(self.intervals)
        depth = len(self.open_stages)
        self.open_stages.append(name)
        # in the list from the start, so stages stay in the order they began
        rec = {'stage': name, 'depth': depth, 'started': stamp(t0), 'outcome': 'running'}
        with self.lock:
            self.current['stages'].append(rec)
            self.open_recs.append(rec)
            self.save()
        outcome = 'ok'
        try:
            yield
        except BaseException as e:
            outcome = type(e).__name__
            raise
        finally:
            self.open_stages.pop()
            with self.lock:
                self.open_recs.remove(rec)
            t1 = time.time()
            calls, model = self._spent(t0, t1, first)
            with self.lock:
                rec.update({'seconds': round(t1 - t0, 3), 'model_seconds': round(model, 3),
                            'python_seconds': round(t1 - t0 - model, 3), 'calls': calls, 'outcome': outcome})
                self.save()
            print(f"[timing] {'  ' * depth}{name}: {duration(rec['seconds'])} wall = "
                  f"{duration(rec['model_seconds'])} model ({calls} call{'' if calls == 1 else 's'}) + "
                  f"{duration(rec['python_seconds'])} python" + ('' if outcome == 'ok' else f' [{outcome}]'),
                  flush=True)

    def parallel_work(self, work_seconds, wall_seconds):
        """Python done in worker processes (the engine playtest's scenes):
        `work_seconds` of it in all, over `wall_seconds`. What the workers
        did beyond that wall time is counted, as `parallel_python_seconds`,
        on every stage open now and on the session: the dashboard adds it
        to say how long the run would have taken one thing at a time."""
        extra = max(0.0, work_seconds - wall_seconds)
        if self.current is None or not extra:
            return
        with self.lock:
            for rec in self.open_recs + [self.current]:
                rec['parallel_python_seconds'] = round(rec.get('parallel_python_seconds', 0) + extra, 3)
            self.save()

    def progress(self, call, force=False, **fields):
        """Adds to a call's in-flight record (from in_flight) as the client
        reports it. Streamed tokens report many times a second, so the
        file is saved at most once a second unless `force`."""
        with self.lock:
            call.update(fields)
            live = any(c is call for c in self.current['running'])
            if live and (force or time.time() - self.last_progress_save >= 1):
                self.last_progress_save = time.time()
                self.save()

    def python_progress(self, **fields):
        """Where long Python work has got (python_work): its `phase`, and
        for a phase with a count its `done` and `total`. No fields clears
        it. Saved when the phase changes, else at most once a second."""
        if self.current is None:
            return
        now = time.time()
        with self.lock:
            before = self.current.get('python_work')
            if not fields:
                if before is not None:
                    del self.current['python_work']
                    self.save()
                return
            new_phase = not before or before.get('phase') != fields.get('phase')
            self.current['python_work'] = dict(
                fields, stage=self.open_stages[-1] if self.open_stages else None,
                started=before['started'] if before else stamp(now),
                phase_started=stamp(now) if new_phase else before['phase_started'])
            if new_phase or now - self.last_progress_save >= 1:
                self.last_progress_save = now
                self.save()

    @contextlib.contextmanager
    def in_flight(self, **call):
        """Lists a call under the session's `running` while its body runs,
        and yields its record for progress()."""
        if self.current is None:
            yield
            return
        call['started'] = stamp(time.time())
        with self.lock:
            self.current['running'].append(call)
            self.save()
        try:
            yield call
        finally:
            with self.lock:
                self.current['running'].remove(call)
                # saved by the record() that follows

    def end_session(self, outcome='ok'):
        if self.current is None:
            return
        t1 = time.time()
        calls, model = self._spent(self.session_t0, t1, 0)
        with self.lock:
            self.current['running'] = []
            self.current.pop('python_work', None)
            self.current.update({'ended': stamp(t1), 'seconds': round(t1 - self.session_t0, 3),
                                 'model_seconds': round(model, 3),
                                 'python_seconds': round(t1 - self.session_t0 - model, 3),
                                 'calls': calls, 'outcome': outcome})
            self.save()

    def save(self):
        """Written whole and then renamed into place, so a reader (the
        dashboard) never sees half a file."""
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            data = {'schema_version': SCHEMA_VERSION, 'story_id': self.story_id, 'calls': self.calls}
            data.update(self.extra)
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def session(self):
        return self.calls[self.session_start:]

    def summary_lines(self):
        """A few lines for the end of a run: what this session cost and
        which calls went over."""
        calls = self.session()
        if not calls:
            lines = ['run stats: no model calls this session (everything was loaded from saved files)']
        else:
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
        if self.current is not None and self.current.get('usage_limits'):
            lines.append(f"claude usage after the last call: {usage_line(self.current['usage_limits'])}")
        if self.current is not None and 'seconds' in self.current:
            lines.append(f"run timing ({self.current['outcome']}):")
            lines += ['  ' + line for line in timing_lines(self.current)]
        return lines
