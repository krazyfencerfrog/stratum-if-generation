#!/usr/bin/env python3
"""Where do thinking traces spend their bytes? (backlog: thinking budget, step 1)

For every saved model call in the given story directories, reads the prompt,
the thinking trace and the answer, and measures:

  settle    how far into the trace (as a share of its length) the answer's
            own content has appeared: the positions by which 50% and 80% of
            the answer's distinctive phrases (content-word trigrams found in
            the answer and not in the prompt) are first written in the
            trace. Early settling means the rest of the trace was checking;
            settling at the very end of a forced trace means the cut came
            mid-decision.
  in_trace  the share of the answer's distinctive phrases that appear in the
            trace at all. Low means the answer was composed after the
            reasoning stopped (a forced answer writing what the trace never
            reached).
  profile   for each tenth of the trace, what its lines do: restate the
            prompt, draft the answer, deliberate (could, maybe, option, or),
            or check (check, ensure, good, verify, need ensure).

and, across all calls, whether forced answers (cut at the thinking limit)
are rejected by their validator more often than answers that finished.

    python trace_analysis.py ../../stratum-compare/fable5/stories/*_f5
    python trace_analysis.py DIR [DIR ...] --steps s4a,s4c,s3_5a --json out.json
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

STOP = set("""a an the and or but of to in on at by for with from as is are was were be been being it its this that these
those he she they them his her their you your we our i me my not no so if then than there here what which who whom whose
when where why how all any each every some such one two into out up down over under again further once only own same too
very can will just do does did done have has had having would should could may might must shall about above below between
through during before after while because until also more most other""".split())
CHECK = re.compile(r'\b(check|checking|ensure|verify|verified|good\b|ok\b|okay|fine\b|confirm|double-check|make sure|'
                   r'validate|satisf|allowed|complies|meets|correct\b|valid\b)', re.I)
DELIB = re.compile(r'(\?|\b(could|maybe|perhaps|option|alternatively|or should|what if|hmm|wait|actually|instead|'
                   r'consider|another way|either|whether|which one|might|unless|but then)\b)', re.I)
PLAN = re.compile(r'^\s*[-*]?\s*(\d+[.)]?\s+\w+|[a-z_]+\s*:\s|turn\s*\d|t\d|n\d)', re.I)


def words(text):
    return [w for w in re.findall(r"[a-z][a-z'\-]+", text.lower()) if w not in STOP and len(w) > 2]


def trigrams(ws):
    return {tuple(ws[i:i + 3]) for i in range(len(ws) - 2)}


def first_positions(trace, phrases):
    """For each phrase, the char position (as a share of the trace) of its
    first appearance as consecutive content words."""
    pos = {}
    tokens = [(m.start(), m.group(0)) for m in re.finditer(r"[a-z][a-z'\-]+", trace.lower())]
    content = [(p, w) for p, w in tokens if w not in STOP and len(w) > 2]
    n = max(1, len(trace))
    for i in range(len(content) - 2):
        g = (content[i][1], content[i + 1][1], content[i + 2][1])
        if g in phrases and g not in pos:
            pos[g] = content[i][0] / n
    return pos


def classify_line(line, prompt_grams, answer_grams):
    """One sentence (or short line): restate, draft, deliberate, check, plan or other."""
    ws = words(line)
    grams = trigrams(ws)
    if grams:
        in_answer = len(grams & answer_grams) / len(grams)
        in_prompt = len(grams & prompt_grams) / len(grams)
        if in_answer >= 0.5 and in_answer > in_prompt:
            return 'draft'
        if in_prompt >= 0.5:
            return 'restate'
    if DELIB.search(line):
        return 'deliberate'
    if CHECK.search(line):
        return 'check'
    if PLAN.match(line) and len(line) < 160:
        return 'plan'
    return 'other'


def sentences(trace):
    """(position, sentence) pieces: lines, split further at sentence ends."""
    at = 0
    for line in trace.split('\n'):
        start = 0
        for m in re.finditer(r'(?<=[.?!])\s+', line):
            yield at + start, line[start:m.start() + 1]
            start = m.end()
        if line[start:].strip():
            yield at + start, line[start:]
        at += len(line) + 1


def analyze(prompt, trace, answer):
    pg = trigrams(words(prompt))
    ag_all = trigrams(words(answer))
    ag = ag_all - pg
    pos = first_positions(trace, ag)
    seen = sorted(pos.values())
    out = {'trace_kb': round(len(trace.encode('utf-8')) / 1024, 1), 'answer_phrases': len(ag),
           'in_trace': round(len(seen) / len(ag), 2) if ag else None,
           'settle50': round(seen[int(len(seen) * 0.5)], 2) if seen else None,
           'settle80': round(seen[min(len(seen) - 1, int(len(seen) * 0.8))], 2) if seen else None}
    profile = [defaultdict(int) for _ in range(10)]
    n = max(1, len(trace))
    for at, piece in sentences(trace):
        if piece.strip():
            profile[min(9, int(at / n * 10))][classify_line(piece, pg, ag_all)] += len(piece)
    shares = []
    for bucket in profile:
        total = sum(bucket.values()) or 1
        shares.append({k: round(v / total, 2) for k, v in bucket.items()})
    out['profile'] = shares
    totals = defaultdict(int)
    for bucket in profile:
        for k, v in bucket.items():
            totals[k] += v
    grand = sum(totals.values()) or 1
    out['overall'] = {k: round(v / grand, 2) for k, v in sorted(totals.items())}
    return out


def step_of(prefix):
    m = re.match(r'(s\d+(?:_\d+)?[a-z]*\d?)', prefix)
    s = m.group(1) if m else prefix
    return re.sub(r'_i\d+.*$', '', prefix) if prefix.startswith('s4') else s


def calls_in(story_dir):
    sid = os.path.basename(story_dir.rstrip('/'))
    stats = os.path.join(story_dir, f'{sid}_run_stats.json')
    if not os.path.isfile(stats):
        return
    with open(stats, encoding='utf-8') as f:
        records = json.load(f).get('calls') or []
    last = {}
    for r in records:
        last[r.get('prefix')] = r          # the accepted (last) attempt per prefix
    attempts = defaultdict(list)
    for r in records:
        attempts[r.get('prefix')].append(r)
    for prefix, r in last.items():
        base = os.path.join(story_dir, f'{sid}_{prefix}')
        paths = [base + '_raw_input_prompt.txt', base + '_raw_output_thinking.txt', base + '_raw_output_response.txt']
        if not all(os.path.isfile(p) for p in paths):
            continue
        texts = [open(p, encoding='utf-8', errors='replace').read() for p in paths]
        if len(texts[1]) < 2000:
            continue
        yield sid, prefix, r, attempts[prefix], texts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('dirs', nargs='+')
    ap.add_argument('--steps', default='', help='comma-separated step prefixes to include (default: all)')
    ap.add_argument('--json', default='', help='write every row to this file')
    args = ap.parse_args(argv)
    want = [s for s in args.steps.split(',') if s]
    rows = []
    for d in sorted({p for pattern in args.dirs for p in glob.glob(pattern)}):
        for sid, prefix, rec, tries, (prompt, trace, answer) in calls_in(d):
            if want and not any(prefix.startswith(w) for w in want):
                continue
            row = {'story': sid, 'prefix': prefix, 'step': step_of(prefix), 'klass': rec.get('klass'),
                   'forced': bool(rec.get('forced_answer')), 'attempts': len(tries),
                   'first_forced': bool(tries[0].get('forced_answer')),
                   'first_rejected': len(tries) > 1, 'prompt_kb': round(len(prompt) / 1024, 1)}
            row.update(analyze(prompt, trace, answer))
            rows.append(row)
    if not rows:
        print('no traces found')
        return 1
    by_step = defaultdict(list)
    for r in rows:
        by_step[r['step']].append(r)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(sum(xs) / len(xs), 2) if xs else None

    print(f'{len(rows)} traced calls in {len({r["story"] for r in rows})} stories\n')
    print(f'{"step":<10} {"n":>3} {"forced":>6} {"KB":>5} {"in_trace":>8} {"settle50":>8} {"settle80":>8}  '
          f'{"restate":>7} {"deliberate":>10} {"check":>5} {"plan":>5} {"draft":>5} {"other":>5}')
    for step in sorted(by_step):
        rs = by_step[step]
        ov = lambda k: mean([r['overall'].get(k, 0) for r in rs])
        print(f'{step:<10} {len(rs):>3} {sum(r["forced"] for r in rs):>6} {mean([r["trace_kb"] for r in rs]):>5} '
              f'{mean([r["in_trace"] for r in rs]):>8} {mean([r["settle50"] for r in rs]):>8} '
              f'{mean([r["settle80"] for r in rs]):>8}  {ov("restate"):>7} {ov("deliberate"):>10} {ov("check"):>5} '
              f'{ov("plan"):>5} {ov("draft"):>5} {ov("other"):>5}')
    print('\nby tenth of the trace, construction calls that were forced (share deliberate / check / plan+draft):')
    construction = [r for r in rows if r['forced'] and r['klass'] == 'build']
    if construction:
        cells = []
        for t in range(10):
            d = mean([r['profile'][t].get('deliberate', 0) for r in construction])
            c = mean([r['profile'][t].get('check', 0) for r in construction])
            w = mean([r['profile'][t].get('plan', 0) + r['profile'][t].get('draft', 0) for r in construction])
            cells.append(f'{t + 1}: {d}/{c}/{w}')
        print('  ' + '  '.join(cells))
    unforced = [r for r in rows if not r['forced'] and r['klass'] == 'extract']
    if unforced:
        cells = []
        for t in range(10):
            d = mean([r['profile'][t].get('deliberate', 0) for r in unforced])
            c = mean([r['profile'][t].get('check', 0) for r in unforced])
            w = mean([r['profile'][t].get('plan', 0) + r['profile'][t].get('draft', 0) for r in unforced])
            cells.append(f'{t + 1}: {d}/{c}/{w}')
        print('phase 3 extractions, finished on their own, for comparison:')
        print('  ' + '  '.join(cells))
    print('\nlast tenth of forced traces vs. finished traces (share of lines by kind):')
    for label, group in (('forced', [r for r in rows if r['forced']]), ('finished', [r for r in rows if not r['forced']])):
        if group:
            last = defaultdict(list)
            for r in group:
                for k, v in r['profile'][9].items():
                    last[k].append(v)
            print(f'  {label:<9} n={len(group):<3} ' + ', '.join(f'{k} {round(sum(v) / len(group), 2)}'
                                                          for k, v in sorted(last.items())))
    print('\nfirst attempts rejected by their validator:')
    for label, cond in (('forced', True), ('finished', False)):
        group = [r for r in rows if r['first_forced'] == cond and r['klass'] in ('build', 'audit', 'judge')]
        if group:
            rej = sum(r['first_rejected'] for r in group)
            print(f'  {label:<9} {rej}/{len(group)} ({rej / len(group):.0%})')
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
