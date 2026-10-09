#!/usr/bin/env python3
"""Per-call run statistics for a story, and a comparison against a baseline.

    cd generator
    python report.py kernel1                       # stories/kernel1/kernel1_run_stats.json
    python report.py kernel1 --baseline ../docs/baseline_kernel1_run_stats.json
    python report.py kernel1 --calls               # every call, not just the stage totals
    python report.py --from-logs DIR --story-id kernel1 [--write out.json]

main.py appends one record per call attempt to <id>_run_stats.json:
prefix, mode (think / no_think), prompt characters, thinking bytes,
response bytes, seconds, whether the answer was accepted, and any circuit
breaker that fired. This script totals them by stage, flags the calls that
went over their class's target (stats.CALL_CLASSES), and, given a
baseline, shows the difference stage by stage.

--from-logs rebuilds the same records for a story directory that has no
run_stats.json (anything run before this script existed) from what is on
disk: each call's .log file is named with its start time in milliseconds
and was last written when the call ended, and the saved thinking and
response files give the sizes. docs/baseline_kernel1_run_stats.json was
made that way from stories/current_output.tar.
"""

import argparse
import json
import os
import re
import sys

from stats import call_profile, step_of

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# (label, regex over the step id). First match wins.
STAGES = [
    ('step 2: shape split / rating', r'^s2$'),
    ('phase 3: extraction + cross-check', r'^s3(_0[abc]|[b-h])$'),
    ('3.4 genre promises', r'^s3_4$'),
    ('3.5 premise: build', r'^s3_5[abc]?$'),
    ('3.5 premise: verify', r'^s3_5[vk]$'),
    ('3.5 premise: repair', r'^s3_5r$'),
    ('3.6 / 3.7 cast and world (now stage B)', r'^s3_[67]$'),
    ('3.75 craft spine (now stage A)', r'^s3_75[vr]?$'),
    ('3.8 story form', r'^s3_8$'),
    ('4a / 4c line plans', r'^s4[ac]$'),
    ('4b node fill (baseline: node build)', r'^s4b$'),
    ('4p branch plan', r'^s4p$'),
    ('4d next-line judge (baseline: review)', r'^s4d$'),
    ('4e outline judge', r'^s4e$'),
]

OLD_CLASS = [(r'^s2$', 'extract'), (r'^s3(_0[abc]|[b-h])$', 'extract'), (r'^s4d$', 'build')]


def stage_of(step):
    for label, pattern in STAGES:
        if re.match(pattern, step):
            return label
    return 'other'


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def from_logs(directory, story_id):
    """Rebuild call records from <id>_<prefix>_<ms>.log files and the saved
    raw outputs."""
    pat = re.compile(rf'^{re.escape(story_id)}_(.+)_(\d{{13}})\.log$')
    logs = []
    for name in os.listdir(directory):
        m = pat.match(name)
        if m:
            path = os.path.join(directory, name)
            logs.append((int(m.group(2)) / 1000.0, m.group(1), path))
    logs.sort()
    last_for_prefix = {}
    for start, prefix, path in logs:
        last_for_prefix[prefix] = path
    calls = []
    attempts = {}
    for start, prefix, path in logs:
        attempts[prefix] = attempts.get(prefix, 0) + 1
        seconds = max(0.0, os.path.getmtime(path) - start)
        log_bytes = os.path.getsize(path)
        thinking = response = None
        if last_for_prefix[prefix] == path:
            for kind in ('thinking', 'response'):
                f = os.path.join(directory, f'{story_id}_{prefix}_raw_output_{kind}.txt')
                if os.path.isfile(f):
                    if kind == 'thinking':
                        thinking = os.path.getsize(f)
                    else:
                        response = os.path.getsize(f)
        step = step_of(prefix)
        klass = next((k for p, k in OLD_CLASS if re.match(p, step)), 'build')
        calls.append({
            'prefix': prefix, 'name': '', 'step': step, 'klass': klass, 'mode': 'think',
            'attempt': attempts[prefix], 'prompt_chars': None,
            'thinking_bytes': thinking if thinking is not None else log_bytes,
            'response_bytes': response if response is not None else 0,
            'seconds': round(seconds, 1),
            'ok': thinking is not None and (response or 0) > 0,
            'breaker': None, 'error': None if thinking is not None else 'no saved output (crashed or stopped)',
            'reconstructed_from_logs': True,
        })
    return {'story_id': story_id, 'calls': calls, 'reconstructed_from_logs': True}


def over_target(c):
    profile = call_profile(c.get('klass'))
    flags = []
    if c.get('mode') != 'no_think' and (c.get('thinking_bytes') or 0) > profile['target_thinking_bytes'] > 0:
        flags.append('thinking')
    if (c.get('seconds') or 0) > profile['target_seconds']:
        flags.append('time')
    if c.get('mode') == 'no_think' and (c.get('thinking_bytes') or 0) > 200:
        flags.append('think:false ignored')
    return flags


def totals(calls):
    out = {}
    for c in calls:
        s = out.setdefault(stage_of(c.get('step') or step_of(c['prefix'])),
                           {'calls': 0, 'seconds': 0.0, 'thinking': 0, 'response': 0, 'over': 0, 'rejected': 0, 'breakers': 0})
        s['calls'] += 1
        s['seconds'] += c.get('seconds') or 0
        s['thinking'] += c.get('thinking_bytes') or 0
        s['response'] += c.get('response_bytes') or 0
        s['over'] += 1 if over_target(c) else 0
        s['rejected'] += 0 if c.get('ok') else 1
        s['breakers'] += 1 if c.get('breaker') else 0
    return out


def fmt_min(seconds):
    return f'{seconds / 60:7.1f}'


def print_calls(calls):
    print(f"{'call':34s} {'mode':8s} {'prompt':>7s} {'think KB':>9s} {'resp KB':>8s} {'min':>7s} {'B/s':>5s}  flags")
    for c in calls:
        out_bytes = (c.get('thinking_bytes') or 0) + (c.get('response_bytes') or 0)
        rate = out_bytes / c['seconds'] if c.get('seconds') else 0
        flags = over_target(c)
        if c.get('breaker'):
            flags.append(f"breaker:{c['breaker']}")
        if not c.get('ok'):
            flags.append('rejected' if not c.get('breaker') else 'cut')
        label = c['prefix'] + (f"_{c['name']}" if c.get('name') else '') + (f" #{c['attempt']}" if c.get('attempt', 1) > 1 else '')
        prompt = f"{c['prompt_chars']:7d}" if c.get('prompt_chars') else '      -'
        print(f"{label[:34]:34s} {c.get('mode', ''):8s} {prompt} {(c.get('thinking_bytes') or 0) / 1000:9.1f} "
              f"{(c.get('response_bytes') or 0) / 1000:8.1f} {fmt_min(c.get('seconds') or 0)} {rate:5.0f}  {', '.join(flags)}")


def print_stages(stats, baseline=None):
    mine = totals(stats['calls'])
    base = totals(baseline['calls']) if baseline else {}
    labels = [l for l, _ in STAGES] + ['other']
    head = f"{'stage':40s} {'calls':>5s} {'min':>7s} {'think KB':>9s} {'over':>4s} {'cut':>3s} {'rej':>3s}"
    if baseline:
        head += f"   | {'base calls':>10s} {'base min':>8s} {'base KB':>8s} {'min delta':>9s}"
    print(head)
    for label in labels:
        m, b = mine.get(label), base.get(label)
        if not m and not b:
            continue
        m = m or {'calls': 0, 'seconds': 0.0, 'thinking': 0, 'over': 0, 'breakers': 0, 'rejected': 0}
        line = (f"{label:40s} {m['calls']:5d} {fmt_min(m['seconds'])} {m['thinking'] / 1000:9.1f} "
                f"{m['over']:4d} {m['breakers']:3d} {m['rejected']:3d}")
        if baseline:
            b = b or {'calls': 0, 'seconds': 0.0, 'thinking': 0}
            line += (f"   | {b['calls']:10d} {b['seconds'] / 60:8.1f} {b['thinking'] / 1000:8.1f} "
                     f"{(m['seconds'] - b['seconds']) / 60:+9.1f}")
        print(line)
    total_s = sum(s['seconds'] for s in mine.values())
    total_t = sum(s['thinking'] for s in mine.values())
    line = f"{'TOTAL':40s} {len(stats['calls']):5d} {fmt_min(total_s)} {total_t / 1000:9.1f}"
    if baseline:
        bs = sum(s['seconds'] for s in base.values())
        bt = sum(s['thinking'] for s in base.values())
        line += f"{'':13s}   | {len(baseline['calls']):10d} {bs / 60:8.1f} {bt / 1000:8.1f} {(total_s - bs) / 60:+9.1f}"
    print(line)
    print(f"  = {total_s / 3600:.1f} hours" + (f" against {bs / 3600:.1f} in the baseline" if baseline else ''))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('story_id', nargs='?', default='')
    parser.add_argument('--baseline', default='', help='another run_stats.json to compare against')
    parser.add_argument('--calls', action='store_true', help='list every call attempt')
    parser.add_argument('--from-logs', default='', help='rebuild stats from the .log files in this directory')
    parser.add_argument('--story-id', dest='story_id_opt', default='', help='story id for --from-logs')
    parser.add_argument('--write', default='', help='with --from-logs: save the rebuilt stats to this file')
    args = parser.parse_args()

    story_id = args.story_id or args.story_id_opt
    if args.from_logs:
        if not story_id:
            parser.error('--from-logs needs a story id')
        stats = from_logs(args.from_logs, story_id)
        if args.write:
            with open(args.write, 'w', encoding='utf-8') as f:
                json.dump(stats, f, indent=1)
    else:
        if not story_id:
            parser.error('give a story id')
        path = os.path.join(THIS_DIR, '..', 'stories', story_id, f'{story_id}_run_stats.json')
        if not os.path.isfile(path):
            print(f'{path} not found. For a run made before run stats existed, use --from-logs.', file=sys.stderr)
            return 1
        stats = load(path)
    baseline = load(args.baseline) if args.baseline else None

    print(f"story {stats.get('story_id')}: {len(stats['calls'])} call attempt(s)"
          + (' (rebuilt from log timestamps)' if stats.get('reconstructed_from_logs') else ''))
    print()
    print_stages(stats, baseline)
    over = [c for c in stats['calls'] if over_target(c) or c.get('breaker') or not c.get('ok')]
    if args.calls:
        print()
        print_calls(stats['calls'])
    elif over:
        print()
        print('calls over their target, cut off, or rejected (use --calls for all):')
        print_calls(over)
    else:
        print()
        print('every call was inside its target.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
