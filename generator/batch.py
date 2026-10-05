#!/usr/bin/env python3
"""A batch queue for pipeline runs: one model job at a time, resumable.

The local model serves one request at a time, so two pipeline runs at once
time each other out. This runner keeps a queue file of jobs and runs them in
order, holding a GPU lock (a file lock shared by every copy of the code on
the machine) for each job, so a second runner, even from another checkout,
waits instead of colliding. Jobs can be added while it runs. A job left
"running" by a kill or a reboot goes back to "queued" and resumes from its
saved files (the pipeline replays what is on disk).

    cd generator
    python batch.py add  kernel38                      # stories/kernel38 from tests/kernels/kernel38.txt
    python batch.py add  reference/ref_canterville     # stories/ref_canterville from tests/kernels/reference/
    python batch.py add  kernel35 --variant b3 -- --branching=judge   # replay 3.4 on from stories/kernel35's phase 3
    python batch.py add  --set quick --variant plan                   # every kernel in EVAL_QUICK.txt
    python batch.py run                                # until the queue is empty (--wait: keep polling)
    python batch.py status
    python batch.py report                             # times, outcomes, metrics -> batch_report.md

Queue file: stories/batch_queue.json (--queue to choose another). Outcomes:
done (exit 0), halted (exit 2: a premise loop out of repair rounds), failed
(anything else; a transient error such as a model timeout is retried once).
"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(THIS_DIR)
STORIES = os.path.join(ROOT, 'stories')
KERNELS = os.path.join(ROOT, 'tests', 'kernels')
DEFAULT_QUEUE = os.path.join(STORIES, 'batch_queue.json')


def gpu_lock_path(root=ROOT):
    """The GPU lock every copy of the code shares: the outermost
    .stratum_gpu.lock above the checkout, so a copy nested in a comparison
    directory still locks the machine's one (not one beside itself); with
    none yet, the checkout's parent."""
    found, d = None, os.path.dirname(os.path.abspath(root))
    while True:
        if os.path.exists(os.path.join(d, '.stratum_gpu.lock')):
            found = os.path.join(d, '.stratum_gpu.lock')
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return found or os.path.join(os.path.dirname(os.path.abspath(root)), '.stratum_gpu.lock')


GPU_LOCK = os.environ.get('STRATUM_GPU_LOCK') or gpu_lock_path()
TRANSIENT = ('idle timeout', 'could not reach ollama', 'failed mid-stream', 'ended before the call finished',
             'an error was encountered while running the model')   # a ROCm library that failed to load, once
RETRIES = 1


# ---------------------------------------------------------------- queue file

@contextmanager
def locked(path):
    """Exclusive lock on the queue's own lock file while it is read or written."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + '.lock', 'w') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def load(path):
    if not os.path.exists(path):
        return {'jobs': []}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, q):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(q, f, indent=2)
    os.replace(tmp, path)


def update(path, fn):
    with locked(path):
        q = load(path)
        result = fn(q)
        save(path, q)
        return result


# ---------------------------------------------------------------- jobs

def kernel_ids(spec):
    if spec in ('eval', 'quick'):
        name = 'EVAL_SET.txt' if spec == 'eval' else 'EVAL_QUICK.txt'
        with open(os.path.join(KERNELS, name), encoding='utf-8') as f:
            return f.read().split()
    return [k.strip() for k in spec.split(',') if k.strip()]


def make_job(kernel, variant=None, flags=(), story_id=None):
    """A job runs the pipeline for one story. With a variant it replays 3.4 on
    from stories/<kernel>'s phase-3 files into stories/<kernel>_<variant>
    (the same as ab.py run); without, it runs the whole pipeline."""
    base = os.path.basename(kernel)      # 'reference/ref_canterville' -> ref_canterville
    sid = story_id or (f'{base}_{variant}' if variant else base)
    return {'story_id': sid, 'kernel': kernel, 'variant': variant, 'flags': list(flags),
            'status': 'queued', 'attempts': 0, 'added': time.strftime('%Y-%m-%d %H:%M'),
            'started': None, 'ended': None, 'minutes': None, 'exit': None, 'error': None}


def add(path, jobs):
    def fn(q):
        have = {j['story_id'] for j in q['jobs'] if j['status'] in ('queued', 'running')}
        added = [j for j in jobs if j['story_id'] not in have]
        q['jobs'].extend(added)
        return added
    return update(path, fn)


def next_job(path):
    """Claims the first queued job (marks it running). A job found 'running'
    when no runner holds the GPU lock was interrupted; it is re-queued first."""
    def fn(q):
        for j in q['jobs']:
            if j['status'] == 'queued':
                j['status'] = 'running'
                j['started'] = time.strftime('%Y-%m-%d %H:%M')
                j['attempts'] += 1
                return dict(j)
        return None
    return update(path, fn)


def requeue_interrupted(path):
    def fn(q):
        n = 0
        for j in q['jobs']:
            if j['status'] == 'running':
                j['status'], n = 'queued', n + 1
        return n
    return update(path, fn)


def finish(path, sid, **fields):
    def fn(q):
        for j in q['jobs']:
            if j['story_id'] == sid and j['status'] == 'running':
                j.update(fields)
                return j
    return update(path, fn)


def last_error(log_path):
    try:
        with open(log_path, encoding='utf-8', errors='replace') as f:
            lines = [l.strip() for l in f if l.strip()]
    except OSError:
        return None
    for l in reversed(lines[-40:]):
        if 'Error' in l or 'HALTED' in l or 'error' in l:
            return l[:300]
    return lines[-1][:300] if lines else None


def run_job(job, env=None):
    """Runs one job in the foreground; returns (exit code, log path)."""
    os.makedirs(os.path.join(STORIES, job['story_id']), exist_ok=True)
    log_path = os.path.join(STORIES, job['story_id'], f"{job['story_id']}_batch.log")
    if job.get('variant'):
        import ab
        sid = ab.prepare(job['kernel'], job['variant'])
        if not sid:
            return 3, log_path
    kernel_path = os.path.join(KERNELS, f"{job['kernel']}.txt")
    cmd = [sys.executable, '-u', 'main.py', f"--story-id={job['story_id']}", *job.get('flags', [])]
    with open(log_path, 'a', encoding='utf-8') as log:
        log.write(f"\n=== batch start {time.strftime('%Y-%m-%d %H:%M')}: {' '.join(cmd[2:])}\n")
        log.flush()
        stdin = open(kernel_path, 'rb') if os.path.isfile(kernel_path) else subprocess.DEVNULL
        try:
            proc = subprocess.run(cmd, cwd=THIS_DIR, stdin=stdin, stdout=log, stderr=subprocess.STDOUT, env=env)
        finally:
            if stdin is not subprocess.DEVNULL:
                stdin.close()
    return proc.returncode, log_path


@contextmanager
def gpu(lock_path=None, say=print):
    """Holds the machine-wide GPU lock for the length of one job."""
    lock_path = lock_path or GPU_LOCK      # read at call time, so it can be redirected (tests)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, 'a+') as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say(f'waiting for the GPU (another runner holds {lock_path})')
            fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)


def run(path, wait=False, poll=60, env=None, say=print):
    with gpu(say=say):
        n = requeue_interrupted(path)
    if n:
        say(f're-queued {n} interrupted job(s); they resume from their saved files')
    while True:
        job = next_job(path)
        if not job:
            if not wait:
                say('queue empty')
                return
            time.sleep(poll)
            continue
        say(f"=== {job['story_id']} start {time.strftime('%H:%M')} (attempt {job['attempts']})")
        started = time.time()
        with gpu(say=say):
            code, log_path = run_job(job, env)
        minutes = round((time.time() - started) / 60, 1)
        error = None if code == 0 else last_error(log_path)
        status = 'done' if code == 0 else ('halted' if code == 2 else 'failed')
        retry = status == 'failed' and job['attempts'] <= RETRIES and error and any(t in error.lower() for t in TRANSIENT)
        finish(path, job['story_id'], status='queued' if retry else status, ended=time.strftime('%Y-%m-%d %H:%M'),
               minutes=minutes, exit=code, error=error)
        say(f"=== {job['story_id']} {('retry queued' if retry else status)} after {minutes} min" + (f": {error}" if error else ''))


# ---------------------------------------------------------------- report

def metrics_for(sid):
    d = os.path.join(STORIES, sid)
    out = {}
    ev = os.path.join(d, f'{sid}_eval.json')
    if os.path.isfile(ev):
        with open(ev, encoding='utf-8') as f:
            e = json.load(f)
        m = e.get('metrics') or {}
        out.update({'lines': m.get('lines'), 'nodes': m.get('nodes'), 'forks': m.get('fork_positions'),
                    'early': m.get('forks_in_first_half'), 'worlds': f"{m.get('distinct_ending_worlds')}/{m.get('endings')}",
                    'judge': sum(v.get('score', 0) for v in ((e.get('judge') or {}).get('scores') or {}).values()) or None})
    story = os.path.join(d, f'{sid}_story.json')
    if os.path.isfile(story):
        try:
            import playtest
            with open(story, encoding='utf-8') as f:
                st = playtest.Story(json.load(f))
            plays = playtest.playthroughs(st)
            out['decisions'] = max((sum(1 for d in p['decisions'] if d[1] in ('act', 'accumulated', 'shift')) for p in plays), default=0)
            out['playtest_findings'] = len(playtest.check(st, plays))
        except Exception as e:              # a report never fails on one story
            out['playtest_findings'] = f'error: {e}'
    return out


def report(path):
    q = load(path)
    rows = ['| story | status | minutes | lines | nodes | forks | early | worlds | decisions | judge /30 | note |',
            '|---|---|---|---|---|---|---|---|---|---|---|']
    for j in q['jobs']:
        m = metrics_for(j['story_id']) if j['status'] == 'done' else {}
        rows.append(f"| {j['story_id']} | {j['status']} | {j.get('minutes') or ''} | {m.get('lines', '')} | {m.get('nodes', '')} | "
                    f"{m.get('forks', '')} | {m.get('early', '')} | {m.get('worlds', '')} | {m.get('decisions', '')} | "
                    f"{m.get('judge') or ''} | {(j.get('error') or '')[:80]} |")
    text = '\n'.join(rows)
    out = os.path.splitext(path)[0].replace('_queue', '') + '_report.md'
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f"# Batch report ({time.strftime('%Y-%m-%d %H:%M')})\n\n{text}\n")
    return text, out


def status(path):
    q = load(path)
    return '\n'.join(f"{j['status']:<8} {j['story_id']:<24} attempts {j['attempts']}  "
                     f"{('started ' + j['started']) if j.get('started') else ('added ' + j['added'])}"
                     + (f"  {j['minutes']} min" if j.get('minutes') else '') for j in q['jobs']) or '(empty)'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--queue', default=DEFAULT_QUEUE)
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add', help='queue jobs')
    a.add_argument('kernels', nargs='?', default='', help='comma-separated kernel ids')
    a.add_argument('--set', choices=['eval', 'quick'], help='every kernel in EVAL_SET.txt or EVAL_QUICK.txt')
    a.add_argument('--variant', help='replay 3.4 on from stories/<kernel> into stories/<kernel>_<variant>')
    a.add_argument('flags', nargs=argparse.REMAINDER, help='after --: flags for main.py')
    r = sub.add_parser('run', help='run the queue')
    r.add_argument('--wait', action='store_true', help='keep polling for new jobs when the queue is empty')
    sub.add_parser('status')
    sub.add_parser('report')
    args = ap.parse_args(argv)
    if args.cmd == 'add':
        flags = [f for f in args.flags if f != '--']
        ids = kernel_ids(args.set) if args.set else kernel_ids(args.kernels)
        added = add(args.queue, [make_job(k, args.variant, flags) for k in ids])
        print(f"queued {len(added)}: {', '.join(j['story_id'] for j in added) or '(all already queued)'}")
    elif args.cmd == 'run':
        run(args.queue, wait=args.wait)
    elif args.cmd == 'status':
        print(status(args.queue))
    elif args.cmd == 'report':
        text, out = report(args.queue)
        print(text)
        print(f'\nwritten to {out}')


if __name__ == '__main__':
    sys.exit(main())
