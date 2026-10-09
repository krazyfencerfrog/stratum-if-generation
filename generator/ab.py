#!/usr/bin/env python3
"""A/B harness: replay the pipeline from saved phase-3 outputs under named
variants, and compare the outlines by the computed metrics.

Phase 3 is half the run and does not change between prompt variants, so a
variant run starts from a story directory that already holds phase 3
(stories/<kernel>/, from any earlier full run) and re-runs 3.4 onward into
a new directory stories/<kernel>_<variant>/.

    cd generator
    python ab.py run --variant plan   --kernels eval  -- --branching=plan
    python ab.py run --variant judge  --kernels eval  -- --branching=judge --no-promises
    python ab.py run --variant nopromise --kernels kernel31,kernel32 -- --no-promises
    python ab.py compare --variants plan,judge --kernels eval
    python ab.py eval kernel31_plan                 # recompute the metrics of one story, no model
    python ab.py prepare --variant x --kernels kernel31   # just make the directory

Everything after `--` is passed to main.py as flags. `--kernels eval` is
the fixed evaluation set in tests/kernels/EVAL_SET.txt; a kernel whose
source directory has no phase-3 output is skipped with a message (run
`python main.py --story-id=<kernel> --stop-after=3 < ../tests/kernels/<kernel>.txt`
first). Variants of one kernel share the same brief, so every difference
in the table is the premise and outline steps.

The table (per kernel, variants side by side) shows: lines, nodes, where
the earliest fork sits on the main line (share of its length), how many
lines leave in the first half, the share of distinct ending worlds,
promise coverage, events placed, repeated phrases, retold situations, the
share of summaries in the 45-75 word range, the 4e judge total (out of
30) and the minutes the variant took from 3.4 on. The metrics are in
generator/evaluate.py.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

import evaluate
from stats import SCHEMA_VERSION

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES = os.path.join(THIS_DIR, '..', 'stories')
KERNELS = os.path.join(THIS_DIR, '..', 'tests', 'kernels')

# files a variant inherits: the kernel, step 2, and phase 3 (3-0a..3h); nothing after
PHASE3_RE = re.compile(r'_(s1_kernel\.txt|s2_rating\.txt|s2_kernel\.txt|s2_shape\.json|s2_rated_kernel\.txt|'
                       r's3_0[abc]_[a-z_]+\.json|s3[b-h]_[a-z_]+\.json|s3h_constraint_map\.json|s3_brief\.json)$')


def eval_set():
    with open(os.path.join(KERNELS, 'EVAL_SET.txt'), encoding='utf-8') as f:
        return f.read().split()


def kernel_list(spec):
    if spec in ('eval', 'EVAL_SET'):
        return eval_set()
    if spec in ('quick', 'EVAL_QUICK'):
        with open(os.path.join(KERNELS, 'EVAL_QUICK.txt'), encoding='utf-8') as f:
            return f.read().split()
    return [k.strip() for k in spec.split(',') if k.strip()]


def variant_id(kernel, variant):
    return f'{kernel}_{variant}'


def prepare(kernel, variant, source_dir=None, fresh=False):
    """Copy the kernel's phase-3 outputs into stories/<kernel>_<variant>/
    under the new id. Returns the new story id, or None when the source has
    no phase-3 output."""
    src = source_dir or os.path.join(STORIES, kernel)
    if not os.path.isdir(src):
        print(f'{kernel}: no source directory {src}', file=sys.stderr)
        return None
    files = [n for n in os.listdir(src) if n.startswith(kernel + '_') and PHASE3_RE.search(n)]
    if not any('_s3h_cross_check' in n for n in files):
        print(f'{kernel}: {src} holds no phase-3 output (run main.py --stop-after=3 first)', file=sys.stderr)
        return None
    sid = variant_id(kernel, variant)
    dst = os.path.join(STORIES, sid)
    if os.path.isdir(dst) and fresh:
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)
    for n in files:
        target = os.path.join(dst, sid + n[len(kernel):])
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(src, n), target)
    stamp = os.path.join(dst, f'{sid}_pipeline.json')
    if not os.path.exists(stamp):
        with open(stamp, 'w', encoding='utf-8') as f:
            json.dump({'schema_version': SCHEMA_VERSION, 'variant': variant, 'source': os.path.abspath(src)}, f, indent=2)
    return sid


def run(kernel, variant, flags, source_dir=None, fresh=False):
    sid = prepare(kernel, variant, source_dir, fresh)
    if not sid:
        return None
    kernel_path = os.path.join(KERNELS, f'{kernel}.txt')
    stdin = open(kernel_path, 'rb') if os.path.isfile(kernel_path) else subprocess.DEVNULL
    cmd = [sys.executable, 'main.py', f'--story-id={sid}', *flags]
    print(f'== {sid}: {" ".join(cmd[2:])}')
    proc = subprocess.run(cmd, cwd=THIS_DIR, stdin=stdin)
    if stdin is not subprocess.DEVNULL:
        stdin.close()
    return proc.returncode


def load_result(sid):
    d = os.path.join(STORIES, sid)
    out = {'metrics': {}, 'judge': None, 'minutes': '-'}
    ev = os.path.join(d, f'{sid}_eval.json')
    if os.path.isfile(ev):
        with open(ev, encoding='utf-8') as f:
            out.update(json.load(f))
    else:
        story = os.path.join(d, f'{sid}_story.json')
        if os.path.isfile(story):
            with open(story, encoding='utf-8') as f:
                s = json.load(f)
            out['metrics'] = evaluate.metrics(s, s.get('promises'))
    stats = os.path.join(d, f'{sid}_run_stats.json')
    if os.path.isfile(stats):
        with open(stats, encoding='utf-8') as f:
            calls = (json.load(f) or {}).get('calls') or []
        out['minutes'] = round(sum(c.get('seconds') or 0 for c in calls) / 60, 1)
        out['calls'] = len(calls)
    return out


def compare(kernels, variants):
    means = {v: [] for v in variants}
    for kernel in kernels:
        results = {}
        for v in variants:
            sid = variant_id(kernel, v)
            if os.path.isdir(os.path.join(STORIES, sid)):
                results[v] = load_result(sid)
        if not results:
            print(f'{kernel}: no variant directories yet')
            continue
        print(f'\n### {kernel}')
        print(evaluate.table(results))
        for v, r in results.items():
            j = r.get('judge') or {}
            if j:
                print(f"  {v}: best: {j.get('best_thing')}")
                print(f"  {v}: worst: {j.get('worst_thing')}")
            m = r.get('metrics') or {}
            if m.get('repeated_phrases'):
                print(f"  {v}: tics: {'; '.join(m['repeated_phrases'][:3])}")
            means[v].append(r)
    print('\n### means over kernels')
    rows = {}
    for v, rs in means.items():
        if not rs:
            continue
        agg = {}
        for key, _ in evaluate.KEY_COLUMNS:
            vals = [(r.get('metrics') or {}).get(key) for r in rs]
            vals = [x for x in vals if isinstance(x, (int, float))]
            agg[key] = round(sum(vals) / len(vals), 2) if vals else None
        facts = [(r.get('judge') or {}).get('facts') for r in rs if (r.get('judge') or {}).get('facts')]
        mean = {}
        if facts:
            mean['loss'] = f"{sum(1 for f in facts if f['loss'] not in (None, 'feeling'))}/{len(facts)} concrete"
            for key in ('plants_paid', 'errands', 'abstractions', 'announced'):
                mean[key] = round(sum(f[key] for f in facts) / len(facts), 1)
            for key in ('opposition_at_work', 'reversal'):
                mean[key] = f"{sum(1 for f in facts if f[key])}/{len(facts)}"
        mins = [r.get('minutes') for r in rs if isinstance(r.get('minutes'), (int, float))]
        rows[f'{v} (n={len(rs)})'] = {'metrics': agg, 'judge': {'facts': mean} if facts else None,
                                      'minutes': round(sum(mins) / len(mins), 1) if mins else '-'}
    if rows:
        print(evaluate.table(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    for name in ('prepare', 'run'):
        p = sub.add_parser(name)
        p.add_argument('--variant', required=True, help='a short name; the story id becomes <kernel>_<variant>')
        p.add_argument('--kernels', required=True, help='comma-separated kernel ids, "eval" (tests/kernels/EVAL_SET.txt, the full set) or "quick" (EVAL_QUICK.txt)')
        p.add_argument('--source-dir', default='', help='take phase 3 from this directory instead of stories/<kernel>')
        p.add_argument('--fresh', action='store_true', help='delete an existing variant directory first')
        p.add_argument('flags', nargs=argparse.REMAINDER, help='after --: flags for main.py')
    p = sub.add_parser('compare')
    p.add_argument('--variants', required=True)
    p.add_argument('--kernels', required=True)
    p = sub.add_parser('eval')
    p.add_argument('story_id')
    args = parser.parse_args()

    if args.cmd in ('prepare', 'run'):
        flags = [f for f in args.flags if f != '--']
        codes = []
        for kernel in kernel_list(args.kernels):
            if args.cmd == 'prepare':
                sid = prepare(kernel, args.variant, args.source_dir or None, args.fresh)
                print(f'{kernel}: {"prepared " + sid if sid else "skipped"}')
            else:
                codes.append(run(kernel, args.variant, flags, args.source_dir or None, args.fresh))
        bad = [c for c in codes if c]
        return 1 if bad else 0
    if args.cmd == 'compare':
        compare(kernel_list(args.kernels), [v.strip() for v in args.variants.split(',') if v.strip()])
        return 0
    if args.cmd == 'eval':
        r = load_result(args.story_id)
        for line in evaluate.summary_lines(r):
            print(line)
        print(json.dumps(r.get('metrics'), indent=1))
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
