#!/usr/bin/env python3
"""One step, many saved cases: is a check right, measured in minutes.

    python steptest.py                              # every premise-audit case, once
    python steptest.py --cases king_contract_price,lady_clean --runs 3
    python steptest.py --no-think --tag nothink     # the same cases with the audit's thinking off
    python steptest.py --kernel-only --runs 3       # only the 3.5k Kernel-clause call (a few minutes a case)

A case (tests/steps/premise_audit/<name>/) is the content kernel, the brief
and a premise, saved from a real run or changed on purpose, with case.json
saying what the audit must find there ("present") and what it must not
("absent"): a finding matches when its source is the one named and its
where and quote contain the words given. The audit is run exactly as the
pipeline runs it (StoryGenerator.verify_premise: the computed checks, the
3.5k and 3.5v calls, the quote check), so a prompt change is measured
here before a full run. A verified Kernel-clause finding is the one that
halts a run, so one that no "present" expectation names counts as a false
alarm in every case. The false alarms are the halts and repair rounds of past runs
(2026-10-06); the true positives keep a change from passing by making the
audit blind.

Each run goes into stories/_steps/<tag>/<case>_r<n>/ (the prompt, the
thinking, the answer), and the summary into stories/_steps/<tag>/summary.json.
Holds the GPU lock unless --no-lock (when the caller holds it).
"""

import argparse
import contextlib
import json
import os
import re
import sys
import time

import main as gen_main
from main import StoryGenerator

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(THIS_DIR, '..', 'tests', 'steps', 'premise_audit')
OUT = os.path.join(THIS_DIR, '..', 'stories', '_steps')


def plain(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text or '').lower()).strip()


def matches(expectation, finding):
    return (finding.get('source') == expectation['source']
            and plain(expectation.get('where')) in plain(finding.get('where'))
            and plain(expectation.get('quote')) in plain(finding.get('quote')))


def case_names():
    return sorted(n for n in os.listdir(CASES) if os.path.isfile(os.path.join(CASES, n, 'case.json')))


def load_case(name):
    d = os.path.join(CASES, name)
    with open(os.path.join(d, 'kernel.txt'), encoding='utf-8') as f:
        kernel = f.read().strip()
    out = {'name': name, 'kernel': kernel}
    for key in ('brief', 'premise', 'case'):
        with open(os.path.join(d, f'{key}.json'), encoding='utf-8') as f:
            out[key] = json.load(f)
    return out


def audit(case, run_dir, no_think=False, kernel_only=False):
    """The findings verify_premise returns for this case's premise, round 0
    (with kernel_only, only the 3.5k call's)."""
    root, sid = os.path.split(run_dir)
    gen = StoryGenerator(sid, stories_root=root, no_think_steps={'s3_5v', 's3_5k'} if no_think else ())
    gen.kernel = gen.kernel_full = case['kernel']
    gen.analysis['s3_brief'] = case['brief']
    if kernel_only:
        return gen.check_kernel_clauses(case['premise'], 0, gen_main.kernel_clauses(case['kernel']))
    return gen.verify_premise(case['premise'], 0)


def score(case, findings, kernel_only=False):
    """Each expectation with whether it held, and the findings it matched."""
    out = []
    for e in case['case']['expect']:
        if kernel_only and e['source'] != 'kernel clause':
            continue
        hit = [f for f in findings if matches(e, f)]
        out.append(dict(e, held=bool(hit) == (e['want'] == 'present'),
                        matched=[{k: f.get(k) for k in ('source', 'where', 'problem', 'quote', 'verified')} for f in hit]))
    wanted = [e for e in case['case']['expect'] if e['want'] == 'present' and e['source'] == 'kernel clause']
    stray = [f for f in findings if f.get('source') == 'kernel clause' and f.get('verified') is not False
             and not any(matches(e, f) for e in wanted)]
    out.append({'want': 'absent', 'source': 'kernel clause', 'where': '(any other clause)', 'quote': '',
                'why': 'an unexpected verified Kernel contradiction halts a run', 'held': not stray,
                'matched': [{k: f.get(k) for k in ('source', 'where', 'problem', 'quote', 'verified')} for f in stray]})
    return out


def summary_lines(results):
    lines = []
    for name, runs in results.items():
        marks = ' '.join('ok' if all(e['held'] for e in r['score']) else 'FAIL' for r in runs)
        lines.append(f"{name:28} {marks}")
        for r in runs:
            for e in r['score']:
                if not e['held']:
                    what = 'missed' if e['want'] == 'present' else 'raised'
                    got = '; '.join(f"{m['problem'][:110]}" for m in e['matched'])
                    lines.append(f"    r{r['run']} {what} [{e['source']} {e['where']}]{': ' + got if got else ''}")
    held = sum(e['held'] for runs in results.values() for r in runs for e in r['score'])
    total = sum(len(r['score']) for runs in results.values() for r in runs)
    fp = [e for runs in results.values() for r in runs for e in r['score'] if e['want'] == 'absent']
    tp = [e for runs in results.values() for r in runs for e in r['score'] if e['want'] == 'present']
    lines.append(f"{held}/{total} expectations held; false alarms {sum(not e['held'] for e in fp)}/{len(fp)}, "
                 f"misses {sum(not e['held'] for e in tp)}/{len(tp)}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cases', help='comma-separated case names (default: all)')
    ap.add_argument('--runs', type=int, default=1, help='runs per case (the audit samples; repeats show how steady it is)')
    ap.add_argument('--no-think', action='store_true', help='run the audit with thinking off')
    ap.add_argument('--kernel-only', action='store_true', help='run only the 3.5k Kernel-clause call')
    ap.add_argument('--tag', default=None, help='output folder under stories/_steps (default: a timestamp)')
    ap.add_argument('--no-lock', action='store_true', help='do not take the GPU lock (the caller holds it)')
    ap.add_argument('--out', default=OUT, help='where the runs go (default: stories/_steps)')
    args = ap.parse_args(argv)
    names = args.cases.split(',') if args.cases else case_names()
    tag = args.tag or time.strftime('%Y%m%d_%H%M') + ('_nothink' if args.no_think else '')
    out_dir = os.path.join(args.out, tag)
    os.makedirs(out_dir, exist_ok=True)
    lock = contextlib.nullcontext()
    if not args.no_lock and os.environ.get('STRATUM_CLIENT') != 'stub':
        import batch
        lock = batch.gpu()
    results = {}
    with lock:
        for name in names:
            case = load_case(name)
            for n in range(1, args.runs + 1):
                run_dir = os.path.join(out_dir, f'{name}_r{n}')
                if os.path.isdir(run_dir):           # a rerun under the same tag starts the run again
                    for f in os.listdir(run_dir):
                        os.remove(os.path.join(run_dir, f))
                started = time.time()
                findings = audit(case, run_dir, args.no_think, args.kernel_only)
                results.setdefault(name, []).append({'run': n, 'seconds': round(time.time() - started),
                                                     'findings': findings, 'score': score(case, findings, args.kernel_only)})
                print(f"{name} r{n}: {'ok' if all(e['held'] for e in results[name][-1]['score']) else 'FAIL'} "
                      f"({len(findings)} findings, {results[name][-1]['seconds']}s)", flush=True)
                with open(os.path.join(out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
                    json.dump({'tag': tag, 'no_think': args.no_think, 'results': results}, f, indent=1, ensure_ascii=False)
    lines = summary_lines(results)
    print('\n'.join(lines))
    with open(os.path.join(out_dir, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
