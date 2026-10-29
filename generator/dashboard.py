#!/usr/bin/env python3
"""A web page that follows story generation runs as they go.

    python generator/dashboard.py                  # http://127.0.0.1:8765
    python generator/dashboard.py --port 9000 --stories /path/to/stories

It reads each story's stories/<id>/<id>_run_stats.json, which main.py
saves as every stage and call starts and ends (see stats.py), so it works
for runs already going, finished, or stopped, and needs nothing from the
run itself. The page lists the stories, newest first, and for one story
shows its latest run: the stages planned and how far it has got, the
calls in flight with the tail of their log, the stages done with their
model and Python time, and the calls so far. Above it, for runs on the
Claude backend, the subscription's 5-hour and weekly usage as the newest
call left them. It polls every two seconds.

Standard library only, and bound to 127.0.0.1 unless --host says otherwise.
"""

import argparse
import json
import os
import re
import signal
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from stats import busy_seconds

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORIES = os.path.normpath(os.path.join(THIS_DIR, '..', 'stories'))
PAGE = os.path.join(THIS_DIR, 'dashboard.html')

SAFE_NAME = re.compile(r'^[A-Za-z0-9_.-]+$')
LOG_TAIL = 6000     # bytes of a call's log shown by default

# the fields of a finished call the page shows
CALL_FIELDS = ('prefix', 'name', 'step', 'klass', 'mode', 'attempt', 'ok', 'breaker', 'error', 'started', 'at',
               'seconds', 'check_seconds', 'thinking_bytes', 'response_bytes', 'over_target', 'api_seconds',
               'limit_wait_seconds', 'eval_seconds', 'load_seconds', 'prompt_eval_seconds')


def parse_stamp(text):
    """stats.stamp()'s local ISO time back to epoch seconds, or None."""
    if not text:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    return None


def alive(pid):
    """Whether a process with this id is running on this machine."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def stats_path(root, story_id):
    if not SAFE_NAME.match(story_id or '') or story_id.startswith('.'):
        return None
    return os.path.join(root, story_id, f'{story_id}_run_stats.json')


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return None


def state_of(session):
    """'running', 'stopped' (marked running, but its process is gone: killed
    or crashed without closing the session) or the session's own outcome."""
    if not session:
        return 'no runs'
    outcome = session.get('outcome') or 'unknown'
    if outcome == 'running':
        return 'running' if alive(session.get('pid')) else 'stopped'
    return outcome


def last_activity(session, calls):
    """When a run that was stopped without closing its record last did
    anything: the latest end of its stages and calls."""
    ends = [parse_stamp(session.get('started')) or 0]
    for st in session.get('stages') or []:
        start = parse_stamp(st.get('started'))
        if start is not None:
            ends.append(start + (st.get('seconds') or 0))
    for c in calls:
        start = parse_stamp(c.get('started'))
        if start is not None:
            ends.append(start + (c.get('seconds') or 0) + (c.get('check_seconds') or 0))
    return max(ends)


def serial_time(calls, running, start, wall, extra, now):
    """How long a span (a stage, a run) would have taken one thing at a
    time: every model call's wait and the Python that checked its answer
    added up, not overlapped; the Python outside any call; and the Python
    done in worker processes beyond its own wall time (`extra`, recorded by
    stats.parallel_work). Returns (model seconds, Python seconds)."""
    end = start + wall
    spans, model, checking = [], 0.0, 0.0
    for c in calls:
        s = parse_stamp(c.get('started'))
        if s is None or not start - 0.001 <= s <= end:
            continue
        seconds, check = c.get('seconds') or 0, c.get('check_seconds') or 0
        spans.append((s, s + seconds + check))
        model += seconds
        checking += check
    for c in running:
        s = now - c['elapsed']
        if start - 0.001 <= s <= end + 0.001:      # a call that began after the span closed is not its work
            spans.append((s, now))
            model += c['elapsed']
    outside = max(0.0, wall - busy_seconds(spans, start, end))
    return model, checking + outside + (extra or 0)


def add_serial(rec, calls, running, start, wall, now):
    model, python = serial_time(calls, running, start, wall, rec.get('parallel_python_seconds'), now)
    rec['serial_model_seconds'], rec['serial_python_seconds'] = model, python
    rec['serial_seconds'] = model + python


def totals_of(calls):
    done = [c for c in calls if c.get('seconds') is not None]
    return {
        'calls': len(done),
        'rejected': sum(1 for c in done if not c.get('ok')),
        'model_seconds': sum(c.get('seconds') or 0 for c in done),
        'check_seconds': sum(c.get('check_seconds') or 0 for c in done),
        'thinking_bytes': sum(c.get('thinking_bytes') or 0 for c in done),
        'response_bytes': sum(c.get('response_bytes') or 0 for c in done),
    }


# a stage's and a run's times that add up over the runs of a story
SUMMED = ('model_seconds', 'python_seconds', 'serial_seconds', 'serial_model_seconds', 'serial_python_seconds',
          'parallel_python_seconds')


def combined(views):
    """Every run of a story as one: each stage's wall, model and Python
    time and calls added up over the runs that worked on it (a resumed run
    redoes only what the stopped one did not save), its outcome the latest
    run's. The latest run's calls in flight and planned stages."""
    latest = views[-1]
    stages, order = {}, []
    for v in views:
        for st in v.get('stages') or []:
            key = (st['stage'], st.get('depth', 0))
            if key not in stages:
                stages[key] = {'stage': st['stage'], 'depth': st.get('depth', 0), 'seconds': 0.0, 'calls': 0, 'runs': 0,
                               **{k: 0.0 for k in SUMMED}}
                order.append(key)
            total = stages[key]
            live = 'seconds' not in st and 'elapsed' in st
            total['seconds'] += st.get('seconds') or st.get('elapsed') or 0
            for k in SUMMED:
                total[k] += st.get(k) or 0
            total['calls'] += st.get('calls') or 0
            total['runs'] += 1 if st.get('calls') else 0       # runs that worked on it, not ones that loaded it
            total['outcome'] = st.get('outcome')
            total['started'] = total.get('started') or st.get('started')
            if live:
                total['elapsed'] = total.pop('seconds')     # still going: the page ticks it on
    out = dict(latest)
    out['stages'] = [stages[k] for k in order]
    for key in ('elapsed', *SUMMED):
        out[key] = sum(v.get(key) or 0 for v in views)
    out['started'] = views[0].get('started')
    out['calls'] = sum(v.get('calls') or 0 for v in views)
    return out


def story_detail(root, story_id, view='all'):
    """The story's runs for the page: view 'all' adds up every run of the
    story (a stopped and resumed story reads as one), 'latest' is the
    newest run alone."""
    path = stats_path(root, story_id)
    data = load(path) if path else None
    if data is None:
        return None
    now = time.time()
    sessions = data.get('sessions') or []
    session = sessions[-1] if sessions else None
    calls = data.get('calls') or []
    state = state_of(session)
    detail = {'story_id': story_id, 'now': now, 'updated': os.path.getmtime(path), 'state': state,
              'runs': len(sessions), 'view': view, 'session': None, 'calls': [], 'totals': {}}
    if session is None:
        detail['calls'] = [{k: c[k] for k in CALL_FIELDS if k in c} for c in calls[-200:]]
        return detail
    views = []
    for i, sess in enumerate(sessions):
        first = sess.get('first_call', len(calls))
        upto = sessions[i + 1].get('first_call', len(calls)) if i + 1 < len(sessions) else len(calls)
        # only the newest run can still be going
        views.append(session_view(root, story_id, sess, calls[first:upto], state if i == len(sessions) - 1 else
                                  ('stopped' if sess.get('outcome') == 'running' else sess.get('outcome')), now))
    if view == 'latest' or len(views) == 1:
        detail['session'], mine = views[-1], calls[session.get('first_call', len(calls)):]
    else:
        detail['session'], mine = combined(views), calls[sessions[0].get('first_call', 0):]
    detail['calls'] = [{k: c[k] for k in CALL_FIELDS if k in c} for c in mine]
    detail['totals'] = totals_of(mine)
    work = detail['session'].get('python_work')
    if work:
        work['left_seconds'] = scenes_left(work, data.get('playtest_timing'))
    return detail


def python_work_view(work, now):
    """The session's long Python work in progress (stats.python_progress)
    with its times so far."""
    if not work:
        return None
    work = dict(work)
    work['elapsed'] = now - (parse_stamp(work.get('started')) or now)
    work['phase_elapsed'] = now - (parse_stamp(work.get('phase_started')) or now)
    return work


def scenes_left(work, timing):
    """About how long the playtest's scene exploration has left, from what
    each scene took the last time this story was playtested: that run's
    wall time, scaled by the share of its scene time still to do. None
    without a last playtest that knew most of these scenes."""
    if not work or work.get('phase') != 'exploring scenes' or not timing:
        return None
    before = timing.get('scene_seconds') or {}
    total = sum(before.values())
    finished = set(work.get('finished') or [])
    if not total or not timing.get('seconds') or len(set(before) & finished) < len(finished) * 0.8:
        return None
    todo = sum(t for sid, t in before.items() if sid not in finished)
    return timing['seconds'] * todo / total


def session_view(root, story_id, session, mine, state, now):
    """One run as the page shows it, with what a run still going (or
    stopped without closing its record) has not written yet worked out:
    elapsed time, model and Python time so far, its calls in flight."""
    t0 = parse_stamp(session.get('started')) or now
    s = dict(session)
    s['stages'] = [dict(st) for st in session.get('stages') or []]
    if 'seconds' in s:
        s['elapsed'] = s['seconds']
    elif state == 'running':
        s['elapsed'] = now - t0
    else:
        s['elapsed'] = last_activity(session, mine) - t0     # stopped: until it last did anything
    for st in s['stages']:
        if 'seconds' in st:
            continue
        if state == 'running':
            st['elapsed'] = now - (parse_stamp(st.get('started')) or now)
        else:
            st['outcome'] = 'stopped'
            st['seconds'] = max(0.0, last_activity(session, mine) - (parse_stamp(st.get('started')) or t0))
    running = []
    for call in (s.get('running') or []) if state == 'running' else []:
        call = dict(call)
        call['elapsed'] = now - (parse_stamp(call.get('started')) or now)
        log = os.path.join(root, story_id, call.get('log') or '')
        call['log_bytes'] = os.path.getsize(log) if call.get('log') and os.path.isfile(log) else 0
        running.append(call)
    s['running'] = running
    s['python_work'] = python_work_view(s.get('python_work'), now) if state == 'running' else None
    s['calls'] = s.get('calls', sum(1 for c in mine if c.get('seconds') is not None))
    if 'model_seconds' not in s:
        # so far (a stopped run: until it last did anything): finished calls and the
        # ones still in flight, overlaps counted once, for the run and each open stage
        end = now if state == 'running' else t0 + s['elapsed']
        intervals = [(parse_stamp(c.get('started')), parse_stamp(c.get('started')) + c.get('seconds', 0))
                     for c in mine if parse_stamp(c.get('started')) is not None]
        intervals += [(now - c['elapsed'], now) for c in running]
        s['model_seconds'] = busy_seconds(intervals, t0, end)
        s['python_seconds'] = max(0.0, s['elapsed'] - s['model_seconds'])
        for st in s['stages']:
            if 'model_seconds' in st:
                continue
            start = parse_stamp(st.get('started')) or t0
            span_end = now if state == 'running' else start + st['seconds']
            wall = st['elapsed'] if state == 'running' else st['seconds']
            st['model_seconds'] = busy_seconds(intervals, start, span_end)
            st['python_seconds'] = max(0.0, wall - st['model_seconds'])
            st['calls'] = sum(1 for a, _ in intervals if start - 0.001 <= a <= span_end)
    # and how long each stage, and the run, would have taken with nothing at the same time
    for st in s['stages']:
        start = parse_stamp(st.get('started')) or t0
        add_serial(st, mine, running, start, st.get('seconds', st.get('elapsed')) or 0, now)
    add_serial(s, mine, running, t0, s['elapsed'] or 0, now)
    return s


def story_list(root):
    """(the stories, newest first; the newest Claude usage reading any of
    their runs saved). The usage windows are the account's, not a story's."""
    stories, usage = [], None
    try:
        names = os.listdir(root)
    except OSError:
        return stories, usage
    for name in names:
        path = stats_path(root, name)
        if not path or not os.path.isfile(path):
            continue
        data = load(path) or {}
        sessions = data.get('sessions') or []
        session = sessions[-1] if sessions else None
        current = None
        for st in (session or {}).get('stages') or []:
            if st.get('depth', 0) == 0:
                current = st['stage']
        for s in sessions:
            reading = s.get('usage_limits')
            if reading and (usage is None or reading.get('at', '') > usage.get('at', '')):
                usage = reading
        stories.append({'story_id': name, 'updated': os.path.getmtime(path), 'state': state_of(session),
                        'stage': current, 'calls': len(data.get('calls') or [])})
    stories.sort(key=lambda s: -s['updated'])
    return stories, usage


def log_tail(root, story_id, name, size):
    """The last `size` bytes of one of a story's log or text files."""
    if not stats_path(root, story_id) or not SAFE_NAME.match(name or '') or not name.endswith(('.log', '.txt')):
        return None
    path = os.path.join(root, story_id, name)
    if not os.path.isfile(path):
        return None
    total = os.path.getsize(path)
    with open(path, 'rb') as f:
        f.seek(max(0, total - size))
        text = f.read().decode('utf-8', errors='replace')
    return {'name': name, 'bytes': total, 'text': text, 'truncated': total > size}


class Handler(BaseHTTPRequestHandler):
    root = DEFAULT_STORIES

    def send(self, code, body, kind='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.split('/') if p]
        query = parse_qs(url.query)
        if not parts:
            with open(PAGE, 'rb') as f:
                return self.send(200, f.read(), 'text/html; charset=utf-8')
        if parts == ['api', 'stories']:
            stories, usage = story_list(self.root)
            return self.send(200, {'root': self.root, 'stories': stories, 'claude_usage': usage, 'now': time.time()})
        if len(parts) == 3 and parts[:2] == ['api', 'story']:
            view = 'latest' if (query.get('view') or [''])[0] == 'latest' else 'all'
            detail = story_detail(self.root, parts[2], view)
            return self.send(200, detail) if detail else self.send(404, {'error': 'no such story'})
        if len(parts) == 5 and parts[:2] == ['api', 'story'] and parts[3] == 'log':
            try:
                size = min(int((query.get('tail') or [LOG_TAIL])[0]), 2_000_000)
            except ValueError:
                size = LOG_TAIL
            tail = log_tail(self.root, parts[2], parts[4], size)
            return self.send(200, tail) if tail else self.send(404, {'error': 'no such log'})
        self.send(404, {'error': 'not found'})

    def log_message(self, fmt, *args):
        pass        # the page polls every two seconds; keep the terminal quiet


def stop(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(description='Follow story generation runs in a browser.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='127.0.0.1',
                        help='address to listen on (default 127.0.0.1: this machine only)')
    parser.add_argument('--stories', default=DEFAULT_STORIES, help=f'stories directory (default {DEFAULT_STORIES})')
    args = parser.parse_args(argv)
    Handler.root = os.path.abspath(args.stories)
    # ctrl-c and kill stop the server even where it was started with SIGINT
    # ignored (some sandboxes and wrappers do that; Python then keeps ignoring it)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'dashboard for {Handler.root} at http://{args.host}:{args.port}/  (ctrl-c to stop)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    sys.exit(main())
