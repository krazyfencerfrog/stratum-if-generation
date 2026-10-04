#!/usr/bin/env python3
"""Two outlines of the same kernel, side by side, for before/after reading.

Either side is a story id (stories/<id>/<id>_story.json), a path to a
*_story.json, or a reference outline (tests/kernels/reference/<id>_reference.json,
named as ref:<id>). Prints markdown: the premise against the premise (you,
the opposition, events, hidden truth, turns), the cast, then the main lines
beat by beat (paired by position along the line), the endings, and the
computed metrics where an eval exists.

    python sidebyside.py kernel35_f5 kernel35_b3 > ../stories/compare_35.md
    python sidebyside.py ref_monkeys_paw ref:ref_monkeys_paw
"""

import argparse
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES = os.path.join(THIS_DIR, '..', 'stories')
REFS = os.path.join(THIS_DIR, '..', 'tests', 'kernels', 'reference')


def load(spec):
    if spec.startswith('ref:'):
        path = os.path.join(REFS, f'{spec[4:]}_reference.json')
    elif spec.endswith('.json'):
        path = spec
    else:
        path = os.path.join(STORIES, spec, f'{spec}_story.json')
    with open(path, encoding='utf-8') as f:
        story = json.load(f)
    ev_path = path.replace('_story.json', '_eval.json')
    ev = None
    if ev_path != path and os.path.isfile(ev_path):
        with open(ev_path, encoding='utf-8') as f:
            ev = json.load(f)
    return story, ev


def main_line(story):
    order = story.get('line_order') or list(story.get('lines') or {})
    return (story.get('lines') or {}).get(order[0]) if order else None


def premise_rows(story):
    p = story.get('premise') or {}
    prot = p.get('protagonist') or {}
    opp = p.get('opposition') or {}
    rows = [('you', prot.get('who')), ('history', prot.get('history')), ('wants', prot.get('wants')),
            ('need', prot.get('need')), ('question', (p.get('mediation') or {}).get('question')),
            ('pressure', (p.get('pressure') or {}).get('description')),
            ('opposition', f"{opp.get('who_or_what')}: wants {opp.get('wants')}" if opp else None),
            ('hidden truth', (p.get('hidden_truth') or {}).get('truth') if isinstance(p.get('hidden_truth'), dict) else None)]
    for i, e in enumerate(p.get('events') or [], 1):
        rows.append((f'event {i}', e.get('what') if isinstance(e, dict) else e))
    for t in p.get('turns') or []:
        if isinstance(t, dict):
            rows.append((f"turn {t.get('id')} ({t.get('form')})", t.get('situation')))
    return rows


def cast_lines(story):
    out = []
    for c in (story.get('characters') or {}).values():
        name = f"{c.get('name')} ({c.get('label')})" if c.get('name') else c.get('label')
        bits = [f"wants {c.get('wants')}"]
        for k in ('edge', 'voice', 'breaking_point'):
            if c.get(k):
                bits.append(f'{k}: {c[k]}')
        out.append(f"- **{name}**{' [opposition]' if c.get('opposition') else ''}: " + '; '.join(bits))
    return out


def render(a_spec, b_spec):
    (a, aev), (b, bev) = load(a_spec), load(b_spec)
    a_spec, b_spec = (os.path.basename(x).replace('_story.json', '') for x in (a_spec, b_spec))
    out = [f'# {a_spec} | {b_spec}', '', f"Kernel: {a.get('kernel') or b.get('kernel')}", '', '## Premise', '']
    ra, rb = dict(premise_rows(a)), dict(premise_rows(b))
    for key in list(dict.fromkeys([k for k, _ in premise_rows(a)] + [k for k, _ in premise_rows(b)])):
        va, vb = ra.get(key), rb.get(key)
        if not va and not vb:
            continue
        out += [f'**{key}**', f'- A: {va or "-"}', f'- B: {vb or "-"}', '']
    out += ['## Cast', '', f'A ({a_spec}):'] + cast_lines(a) + ['', f'B ({b_spec}):'] + cast_lines(b) + ['']
    la, lb = main_line(a) or {}, main_line(b) or {}
    out += ['## Main line, beat by beat', '', f"- A: {la.get('title')}: {la.get('motivation')}",
            f"- B: {lb.get('title')}: {lb.get('motivation')}", '']
    pa, pb = la.get('path') or [], lb.get('path') or []
    na, nb = a.get('nodes') or {}, b.get('nodes') or {}
    for i in range(max(len(pa), len(pb))):
        out.append(f'### {i + 1}')
        for tag, path, nodes in (('A', pa, na), ('B', pb, nb)):
            if i < len(path):
                n = nodes.get(path[i]) or {}
                out.append(f"- {tag} {path[i]} [{n.get('beat')}] **{n.get('title')}**: {n.get('summary')} "
                           f"*Image: {n.get('image')}*")
            else:
                out.append(f'- {tag}: -')
        out.append('')
    out += ['## Endings', '']
    for tag, story in (('A', a), ('B', b)):
        for lid in story.get('line_order') or []:
            e = (story['lines'][lid].get('ending') or {})
            out.append(f"- {tag} {lid} **{e.get('title')}**: {e.get('summary')} (standing {e.get('standing')}; "
                       f"lost {e.get('lost')})")
    for tag, ev in (('A', aev), ('B', bev)):
        if ev and ev.get('judge'):
            scores = {k: v.get('score') for k, v in (ev['judge'].get('scores') or {}).items()}
            out += ['', f"Judge {tag}: {scores}; best: {ev['judge'].get('best_thing')}; worst: {ev['judge'].get('worst_thing')}"]
    return '\n'.join(out) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('a')
    ap.add_argument('b')
    args = ap.parse_args(argv)
    sys.stdout.write(render(args.a, args.b))
    return 0


if __name__ == '__main__':
    sys.exit(main())
