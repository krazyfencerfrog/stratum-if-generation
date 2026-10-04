#!/usr/bin/env python3
"""Playtest a story graph without a model: walk it the way players would.

Works on the outline as it stands today (nodes, edges with plain-language
triggers, lines, endings) and on the stage-A extensions sketched in
docs/later_stages.md §2, so the same tool checks both:

  today     every playthrough is enumerated by taking or declining each
            branch trigger; the checks report unreachable endings and nodes,
            dead ends, cycles, lines whose path cannot be walked, and branch
            points without a default. Walkthroughs print the decisions that
            lead to each ending.
  stage A   a node may carry `options` (each with `effects`: [{state,
            direction}]) and an edge may carry `condition` ({state,
            direction, at_least: count, share: fraction}, a pattern of
            play). Play styles choose options (always up, always down,
            random, ...) and the report says which endings and pattern
            shifts each style reaches; the checks add the rules from the
            design: a pattern shift needs at least three moves of its state,
            three quarters one way, and random play must not trigger it.

    python playtest.py kernel31                 # stories/kernel31/kernel31_story.json
    python playtest.py path/to/x_story.json --walkthroughs
"""

import argparse
import json
import os
import random
import sys
from collections import Counter

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
STORIES = os.path.join(THIS_DIR, '..', 'stories')

SHIFT_MIN_MOVES = 3
SHIFT_MIN_SHARE = 0.75


class Story:
    def __init__(self, story):
        self.story = story
        self.nodes = story.get('nodes') or {}
        self.lines = story.get('lines') or {}
        self.edges = story.get('edges') or []
        self.out = {}
        for e in self.edges:
            self.out.setdefault(e['from'], []).append(e)
        order = story.get('line_order') or list(self.lines)
        main = next((self.lines[l] for l in order if not self.lines[l].get('divergence')), None)
        path = (main or {}).get('path') or story.get('node_order') or list(self.nodes)
        self.start = path[0] if path else None
        self.endings = [n for n, v in self.nodes.items() if v.get('is_ending')]

    def title(self, nid):
        return (self.nodes.get(nid) or {}).get('title') or nid

    def choices(self, nid):
        """The ways out of a node: (edge, label, kind). The default edge is the
        'continue' one; a branch edge is taken when its trigger is."""
        out = []
        for e in self.out.get(nid, []):
            if e.get('kind') == 'branch':
                trig = e.get('trigger') or {}
                out.append((e, trig.get('text') or '(branch)', trig.get('kind') or 'act'))
            else:
                label = '; '.join(e.get('otherwise') or []) or None
                out.append((e, label, 'continue'))
        return out


# ---------------------------------------------------------------- play

def condition_met(cond, state):
    """A pattern-of-play condition: the state moved at least `at_least` times
    and at least `share` of those moves went `direction`."""
    if not cond:
        return True
    moves = state.get(cond.get('state'), [])
    want = cond.get('direction', 'up')
    agree = sum(1 for m in moves if m == want)
    return (len(moves) >= cond.get('at_least', SHIFT_MIN_MOVES)
            and moves and agree / len(moves) >= cond.get('share', SHIFT_MIN_SHARE))


def apply_options(node, style, state, rng):
    """Stage A: a node's options move states. The style picks one."""
    options = node.get('options') or []
    if not options:
        return None
    pick = style(options, rng) if callable(style) else options[0]
    for eff in pick.get('effects') or []:
        state.setdefault(eff.get('state'), []).append(eff.get('direction'))
    return pick


def styles():
    def toward(direction):
        def choose(options, rng):
            for o in options:
                if any(e.get('direction') == direction for e in o.get('effects') or []):
                    return o
            return options[0]
        return choose
    return {'always_up': toward('up'), 'always_down': toward('down'),
            'random': lambda options, rng: rng.choice(options)}


def playthroughs(st, style=None, rng=None, limit=5000):
    """Every playthrough from the start: at each branch point the player takes
    the default or one of the act triggers (both are tried); an accumulated
    trigger or a conditioned edge is taken only when its condition holds.
    Options (stage A) are chosen by `style`. Returns a list of dicts."""
    rng = rng or random.Random(0)
    found = []

    def walk(nid, nodes, decisions, state, seen):
        if len(found) >= limit:
            return
        node = st.nodes.get(nid) or {}
        state = {k: list(v) for k, v in state.items()}
        pick = apply_options(node, style, state, rng)
        if pick:
            decisions = decisions + [(nid, 'option', pick.get('do'))]
        nodes = nodes + [nid]
        if nid in seen:
            found.append({'ending': None, 'nodes': nodes, 'decisions': decisions, 'state': state, 'cycle': nid})
            return
        seen = seen | {nid}
        options = st.choices(nid)
        if not options:
            found.append({'ending': nid if node.get('is_ending') else None, 'nodes': nodes,
                          'decisions': decisions, 'state': state, 'dead_end': not node.get('is_ending')})
            return
        forced = [c for c in options if c[0].get('condition') and condition_met(c[0]['condition'], state)]
        if forced:   # a pattern shift that has come due takes the story with it
            e, label, kind = forced[0]
            walk(e['to'], nodes, decisions + [(nid, 'shift', label)], state, seen)
            return
        for e, label, kind in options:
            if e.get('condition'):
                continue                     # not due
            if kind == 'accumulated' and not e.get('condition'):
                # no formal condition yet (outline stage): try it as if the pattern held
                walk(e['to'], nodes, decisions + [(nid, 'accumulated', label)], state, seen)
            elif kind == 'continue':
                walk(e['to'], nodes, decisions + ([(nid, 'default', label)] if label else []), state, seen)
            else:
                walk(e['to'], nodes, decisions + [(nid, 'act', label)], state, seen)

    if st.start:
        walk(st.start, [], [], {}, frozenset())
    return found


# ---------------------------------------------------------------- checks

def check(st, plays):
    findings = []
    reached_end = {p['ending'] for p in plays if p.get('ending')}
    reached = {n for p in plays for n in p['nodes']}
    for n in st.endings:
        if n not in reached_end:
            findings.append(f'ending {n} ({st.title(n)}) is reached by no playthrough')
    for n in st.nodes:
        if n not in reached:
            findings.append(f'node {n} ({st.title(n)}) is reached by no playthrough')
    for p in plays:
        if p.get('dead_end'):
            findings.append(f"dead end at {p['nodes'][-1]} ({st.title(p['nodes'][-1])}): not an ending, no way out")
        if p.get('cycle'):
            findings.append(f"cycle back to {p['cycle']}")
    for lid, line in st.lines.items():
        path = line.get('path') or []
        for a, b in zip(path, path[1:]):
            if not any(e['to'] == b and lid in (e.get('lines') or []) for e in st.out.get(a, [])):
                findings.append(f'line {lid} cannot be walked: no edge {a} -> {b} for it')
    for nid, outs in st.out.items():
        kinds = [e.get('kind') for e in outs]
        if 'branch' in kinds and kinds.count('continue') != 1:
            findings.append(f'branch point {nid} has {kinds.count("continue")} default ways out (needs exactly one)')
    return sorted(set(findings))


def shift_checks(st, rng_seed=0, random_runs=200):
    """Stage A: every conditioned edge (a pattern shift) needs a state moved by
    enough options on the paths to it, must fire for a consistent style, and
    must not fire for random play more than rarely."""
    findings, report = [], {}
    shifts = [e for e in st.edges if e.get('condition')]
    if not shifts:
        return findings, report
    sty = styles()
    for name in ('always_up', 'always_down'):
        plays = playthroughs(st, sty[name], random.Random(rng_seed))
        report[name] = Counter(p.get('ending') for p in plays)
        for e in shifts:
            fired = any((e['from'], 'shift') in [(d[0], d[1]) for d in p['decisions']] and e['to'] in p['nodes'] for p in plays)
            if e['condition'].get('direction') == name.split('_')[1] and not fired:
                findings.append(f"shift {e['from']} -> {e['to']} never fires for {name} play, though its pattern is {e['condition'].get('direction')}")
    rng = random.Random(rng_seed)
    fired = Counter()
    for _ in range(random_runs):
        for p in playthroughs(st, sty['random'], random.Random(rng.random()), limit=50):
            for d in p['decisions']:
                if d[1] == 'shift':
                    fired[d[0]] += 1
    runs = random_runs
    for e in shifts:
        rate = fired[e['from']] / max(1, runs)
        if rate > 0.2:
            findings.append(f"shift {e['from']} -> {e['to']} fires on {rate:.0%} of random playthroughs: the pattern is not clear enough")
    report['random_shift_rate'] = {e['from']: round(fired[e['from']] / max(1, runs), 2) for e in shifts}
    return findings, report


# ---------------------------------------------------------------- report

def summarize(st, plays):
    by_end = {}
    for p in plays:
        if p.get('ending'):
            by_end.setdefault(p['ending'], []).append(p)
    return {
        'start': st.start,
        'playthroughs': len(plays),
        'endings': {e: {'title': st.title(e), 'ways': len(ps),
                        'fewest_decisions': min(sum(1 for d in p['decisions'] if d[1] in ('act', 'accumulated', 'shift')) for p in ps),
                        'shortest_path': min(len(p['nodes']) for p in ps)} for e, ps in by_end.items()},
    }


def walkthrough(st, play):
    out = []
    decisions = {}
    for at, kind, label in play['decisions']:
        decisions.setdefault(at, []).append((kind, label))
    for nid in play['nodes']:
        out.append(f"  {nid} {st.title(nid)}")
        for kind, label in decisions.get(nid, []):
            mark = {'act': 'you chose to act', 'default': 'otherwise', 'accumulated': 'by pattern',
                    'shift': 'PATTERN SHIFT', 'option': 'option'}.get(kind, kind)
            out.append(f"      [{mark}] {label}")
    return '\n'.join(out)


def load(arg):
    path = arg if arg.endswith('.json') else os.path.join(STORIES, arg, f'{arg}_story.json')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('story', help='a story id (stories/<id>/<id>_story.json) or a path to a *_story.json')
    ap.add_argument('--walkthroughs', action='store_true', help='print one playthrough per ending')
    args = ap.parse_args(argv)
    st = Story(load(args.story))
    plays = playthroughs(st)
    summary = summarize(st, plays)
    print(f"{summary['playthroughs']} playthrough(s) from {summary['start']}")
    for e, info in summary['endings'].items():
        print(f"  ending {e} {info['title']}: {info['ways']} way(s), at least {info['fewest_decisions']} decision(s), "
              f"{info['shortest_path']} nodes")
    findings = check(st, plays)
    more, report = shift_checks(st)
    findings += more
    if report:
        print('pattern shifts:', json.dumps(report, default=dict))
    print('findings:' if findings else 'findings: none')
    for f in findings:
        print('  - ' + f)
    if args.walkthroughs:
        shown = set()
        for p in plays:
            if p.get('ending') and p['ending'] not in shown:
                shown.add(p['ending'])
                print(f"\nWalkthrough to {p['ending']} ({st.title(p['ending'])}):")
                print(walkthrough(st, p))
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
