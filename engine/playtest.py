#!/usr/bin/env python3
"""Playtest a story package without a player: every state, then many plays.

Two methods, both driving the real engine (runtime.Engine.perform):

  explore   breadth-first over every game state reachable from the start,
            through every option the menu offers (Look and Inventory take no
            time and are skipped). Turn counters are capped at the largest
            threshold any condition compares them with, and the random seed
            is fixed, so equivalent states merge and the search ends. Finds:
            unreachable scenes and endings, STUCK states (no ending can be
            reached from them by any sequence of actions: the design's rule
            that a scene's way forward is findable from every state),
            interactions, topics, events, nudges and scene exits that never
            happen, and which combinations of ending resolutions occur.
            Walkthroughs are the shortest action sequence to each ending and
            resolution combination.
  play      many runs of a simulated player: `random` picks uniformly among
            the options; `up` / `down` prefer options that move arc states
            that way (and avoid the opposite); `<state>:up` steers one
            state. Reports endings and resolutions reached, actions taken,
            and for every scene exit whose condition is a pattern(), how
            often it fires: random play must trigger a pattern shift rarely
            (under 15%, later_stages.md §2), a consistent style must be able
            to.

    python playtest.py examples/kernel35_demo.json
    python playtest.py story.json --walkthroughs --runs 2000
"""

import argparse
import ast
import json
import random
import sys
from collections import Counter, deque

from expressions import evaluate, parse
from runtime import FREE, Engine
from story import Story, ending_groups, validate

RANDOM_SHIFT_LIMIT = 0.15
MISSED_OPPORTUNITY = 0.5
SEED = 0.5


# ---------------------------------------------------------------- state normalization

def expressions_in(data):
    """Every condition string in a package."""
    out = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ('when', 'known_when') and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return out


def counter_caps(story):
    """For each counter, a value past which no condition can tell two values
    apart: one more than the largest constant it is compared with."""
    caps = {'turns': 0, 'turns_in_scene': 0}
    uses_visited = False
    for text in expressions_in(story.data):
        tree = parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'visited':
                uses_visited = True
            if isinstance(node, ast.Compare):
                sides = [node.left] + list(node.comparators)
                names = [n.id for n in sides if isinstance(n, ast.Name) and n.id in caps]
                nums = [n.value for n in sides if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))]
                for name in names:
                    for num in nums:
                        caps[name] = max(caps[name], int(num) + 1)
    idle = {sid: max([n.get('after', 3) for n in sc.get('nudges') or []] or [0])
            for sid, sc in story.scenes.items()}
    return caps, idle, uses_visited


class Normalizer:
    def __init__(self, story):
        self.story = story
        self.caps, self.idle, self.uses_visited = counter_caps(story)

    def __call__(self, st):
        st.turns = min(st.turns, self.caps['turns'])
        st.turns_in_scene = min(st.turns_in_scene, self.caps['turns_in_scene'])
        nudges = (self.story.scenes.get(st.scene) or {}).get('nudges') or []
        if all(n['id'] in st.fired for n in nudges):
            st.idle = 0                       # no nudge left to fire: idling changes nothing
        else:
            st.idle = min(st.idle, self.idle.get(st.scene, 0))
        st.seed = SEED
        if not self.uses_visited:
            st.visited = set()
        return st

    @staticmethod
    def key(st):
        return json.dumps(st.to_dict(), sort_keys=True)


def resolution_combo(story, st):
    """For an ended state: per resolution group, the index of the variant that
    holds (None when none does)."""
    end = story.endings[st.ending]
    combo = []
    for group in ending_groups(end):
        pick = None
        for i, v in enumerate(group.get('variants') or []):
            if evaluate(v.get('when', 'true'), st):
                pick = i
                break
        combo.append(pick)
    return tuple(combo)


def combo_text(story, ending, combo):
    parts = []
    for group, pick in zip(ending_groups(story.endings[ending]), combo):
        who = group.get('about') or 'ending'
        if pick is None:
            parts.append(f'{who}: (none)')
        else:
            v = group['variants'][pick]
            parts.append(f"{who}: {v.get('when', 'true')}")
    return '; '.join(parts)


def time_taking(eng):
    return [o for o in eng.options() if o['verb'] not in FREE]


# ---------------------------------------------------------------- exhaustive exploration

def explore(story, max_states=50000):
    norm = Normalizer(story)
    eng = Engine(story)
    eng.start(seed=SEED)
    start = norm(eng.state.clone())
    states, index, parent, out = [start], {norm.key(start): 0}, {0: None}, [[]]
    offered, taken, fired, scenes, exits_taken = set(), set(), set(), set(), set()
    endings = {}                               # ending -> {combo: state index}
    truncated = False
    queue = deque([0])
    while queue:
        i = queue.popleft()
        st = states[i]
        scenes.add(st.scene)
        fired |= st.fired
        if st.ending:
            endings.setdefault(st.ending, {}).setdefault(resolution_combo(story, st), i)
            continue
        eng.state = st.clone()
        for opt in time_taking(eng):
            offered.add(opt['id'])
            eng.state = st.clone()
            eng.queue = []
            eng.perform(opt, reseed=False)
            nxt = norm(eng.state)
            taken.add(opt['id'])
            if nxt.scene != st.scene or nxt.ending:
                exits_taken.add((st.scene, nxt.ending or nxt.scene))
            k = norm.key(nxt)
            j = index.get(k)
            if j is None:
                if len(states) >= max_states:
                    truncated = True
                    continue
                j = len(states)
                index[k] = j
                states.append(nxt)
                out.append([])
                parent[j] = (i, eng.label_of(opt))
                queue.append(j)
            out[i].append(j)
    # which states can still reach an ending (frontier states count as able, when truncated)
    can = set(i for i, st in enumerate(states) if st.ending)
    if truncated:
        can |= {i for i in range(len(states)) if not out[i] and not states[i].ending}
    back = [[] for _ in states]
    for i, js in enumerate(out):
        for j in js:
            back[j].append(i)
    todo = deque(can)
    while todo:
        j = todo.popleft()
        for i in back[j]:
            if i not in can:
                can.add(i)
                todo.append(i)
    stuck = [i for i in range(len(states)) if i not in can]
    return {'states': states, 'parent': parent, 'truncated': truncated, 'offered': offered, 'taken': taken,
            'fired': fired, 'scenes': scenes, 'exits_taken': exits_taken, 'endings': endings, 'stuck': stuck}


def path_to(result, i):
    labels = []
    while result['parent'].get(i):
        i, label = result['parent'][i]
        labels.append(label)
    return list(reversed(labels))


def explore_findings(story, result):
    errors, notes = [], []
    if result['truncated']:
        notes.append(f"exploration stopped at {len(result['states'])} states: findings below cover only those")
    for sid in story.scenes:
        if sid not in result['scenes']:
            errors.append(f'scene {sid} is never reached by any sequence of actions')
    for eid in story.endings:
        if eid not in result['endings']:
            errors.append(f'ending {eid} is never reached by any sequence of actions')
    by_scene = {}
    for i in result['stuck']:
        by_scene.setdefault(result['states'][i].scene, []).append(i)
    for sid, idxs in by_scene.items():
        first = min(idxs, key=lambda i: len(path_to(result, i)))
        errors.append(f'STUCK: {len(idxs)} state(s) in scene {sid} from which no ending can be reached; '
                      f"the first comes after: {' / '.join(path_to(result, first)) or '(the start)'}")
    for sid, sc in story.scenes.items():
        if sid not in result['scenes']:
            continue
        for it in sc.get('interactions') or []:
            if it['id'] not in result['offered']:
                notes.append(f"interaction {it['id']} is never offered")
        for ev in sc.get('events') or []:
            if ev['id'] not in result['fired']:
                notes.append(f"event {ev['id']} never fires")
        for n in sc.get('nudges') or []:
            if n['id'] not in result['fired']:
                notes.append(f"nudge {n['id']} never fires")
        for ex in sc.get('exits') or []:
            if (sid, ex['to']) not in result['exits_taken']:
                notes.append(f"scene {sid}: the exit to {ex['to']} ({ex.get('when', 'true')}) is never taken")
    for cid, ch in story.characters.items():
        for tid in ch.get('topics') or {}:
            if f'talk:{cid}:{tid}' not in result['offered']:
                notes.append(f'topic {cid}.{tid} is never offered')
    for eid, combos in result['endings'].items():
        for gi, group in enumerate(ending_groups(story.endings[eid])):
            used = {c[gi] for c in combos}
            for vi, v in enumerate(group.get('variants') or []):
                if vi not in used:
                    notes.append(f"ending {eid}: the {group.get('about') or 'ending'} resolution "
                                 f"'{v.get('when', 'true')}' is never composed")
    return errors, notes


# ---------------------------------------------------------------- simulated players

CURIOSITY = 0.7     # a styled player tries something new this often, when it can


def chooser(story, style):
    """A function (options, rng, tried) -> option for a play style. Styled
    players are also curious: among options that move nothing, they prefer
    ones they have not tried (people open conversations and drawers; a
    uniform random walker mostly walks)."""
    if style == 'random':
        return lambda opts, rng, tried: rng.choice(opts)
    target, _, direction = style.rpartition(':') if ':' in style else ('', '', style)

    def moves(opt):
        src = opt.get('source')
        if src and src[0] == 'interaction':
            effects = src[1].get('effects') or []
        elif src and src[0] == 'topic':
            effects = story.characters[src[1]]['topics'][src[2]].get('effects') or []
        else:
            effects = []
        return [(e['move'], e.get('dir')) for e in effects if 'move' in e and (not target or e['move'] == target)]

    def choose(opts, rng, tried):
        toward = [o for o in opts if any(d == direction for _, d in moves(o))]
        if toward:
            return rng.choice(toward)
        neutral = [o for o in opts if not moves(o)] or opts
        fresh = [o for o in neutral if o['id'] not in tried]
        if fresh and rng.random() < CURIOSITY:
            return rng.choice(fresh)
        return rng.choice(neutral)
    return choose


def opportunities(story):
    """Option ids that move an arc state: the choices the story is built on."""
    out = []
    for sc in story.scenes.values():
        for it in sc.get('interactions') or []:
            if any('move' in e for e in it.get('effects') or []):
                out.append(it['id'])
    for cid, ch in story.characters.items():
        for tid, topic in (ch.get('topics') or {}).items():
            if any('move' in e for e in topic.get('effects') or []):
                out.append(f'talk:{cid}:{tid}')
    return out


def optional_ids(story):
    """Opportunities marked `optional`: discoveries a player may miss by design."""
    out = {it['id'] for sc in story.scenes.values() for it in sc.get('interactions') or [] if it.get('optional')}
    out |= {f'talk:{cid}:{tid}' for cid, ch in story.characters.items()
            for tid, topic in (ch.get('topics') or {}).items() if topic.get('optional')}
    return out


def pattern_exits(story):
    return [(sid, ex['to'], ex['when']) for sid, sc in story.scenes.items() for ex in sc.get('exits') or []
            if 'pattern(' in ex.get('when', '')]


def play(story, style='random', runs=500, max_steps=400, seed=0):
    rng = random.Random(seed)
    pick = chooser(story, style)
    endings, combos, steps, unfinished = Counter(), Counter(), [], 0
    reached, shifted = Counter(), Counter()
    shifts = pattern_exits(story)
    opps = set(opportunities(story))
    seen = Counter()
    for run in range(runs):
        eng = Engine(story)
        eng.start(seed=rng.random())
        seen_scenes = {eng.state.scene}
        tried, offered = set(), set()
        n = 0
        while not eng.state.ending and n < max_steps:
            before = eng.state.scene
            opts = time_taking(eng)
            offered.update(o['id'] for o in opts if o['id'] in opps)
            opt = pick(opts, rng, tried)
            tried.add(opt['id'])
            eng.perform(opt)
            after = eng.state.ending or eng.state.scene
            if after != before:
                for sid, to, _ in shifts:
                    if sid == before and to == after:
                        shifted[(sid, to)] += 1
                seen_scenes.add(eng.state.scene)
            n += 1
        for sid, to, _ in shifts:
            if sid in seen_scenes:
                reached[(sid, to)] += 1
        seen.update(offered)
        if eng.state.ending:
            endings[eng.state.ending] += 1
            combos[(eng.state.ending, resolution_combo(story, eng.state))] += 1
            steps.append(n)
        else:
            unfinished += 1
    return {'style': style, 'runs': runs, 'endings': endings, 'combos': combos, 'unfinished': unfinished,
            'mean_actions': round(sum(steps) / len(steps), 1) if steps else None,
            'opportunities_seen': {o: round(seen[o] / runs, 2) for o in sorted(opps)},
            'shift_rates': {k: round(shifted[k] / reached[k], 3) if reached[k] else None
                            for k in [(s, t) for s, t, _ in shifts]}}


def play_findings(story, plays):
    errors, notes = [], []
    random_play = next((p for p in plays if p['style'] == 'random'), None)
    for sid, to, when in pattern_exits(story):
        if random_play:
            rate = random_play['shift_rates'].get((sid, to))
            if rate is not None and rate > RANDOM_SHIFT_LIMIT:
                errors.append(f'pattern shift {sid} -> {to} ({when}) fires on {rate:.0%} of random plays that reach '
                              f'{sid}: over {RANDOM_SHIFT_LIMIT:.0%}, so the pattern is not clear enough')
        if not any((p['shift_rates'].get((sid, to)) or 0) > 0 for p in plays if p['style'] != 'random'):
            notes.append(f'pattern shift {sid} -> {to} ({when}) never fires for any consistent play style')
    curious = next((p for p in plays if p['style'] == 'up'), None)
    if curious:
        optional = optional_ids(story)
        for opp, share in curious['opportunities_seen'].items():
            if share < MISSED_OPPORTUNITY and opp not in optional:
                notes.append(f'opportunity {opp} is offered in only {share:.0%} of curious plays: '
                             f'most players never get the choice (gate the way forward behind it, move it onto the path, '
                             f'or mark it optional)')
    if random_play and random_play['unfinished']:
        notes.append(f"{random_play['unfinished']} of {random_play['runs']} random plays did not finish "
                     f'in the step limit (wandering is allowed; a high share may mean the way forward is hard to find)')
    return errors, notes


# ---------------------------------------------------------------- report

def styles_for(story):
    out = ['random', 'up', 'down']
    for name in story.states:
        out += [f'{name}:up', f'{name}:down']
    return out


def run(story, runs=500, max_states=50000, walkthroughs=False, out=sys.stdout):
    result = explore(story, max_states=max_states)
    errors, notes = explore_findings(story, result)
    plays = [play(story, style, runs=runs if style == 'random' else max(50, runs // 5)) for style in styles_for(story)]
    e2, n2 = play_findings(story, plays)
    errors += e2
    notes += n2

    print(f"{story.title}: {len(result['states'])} states explored"
          f"{' (stopped at the limit)' if result['truncated'] else ''}", file=out)
    for eid, combos in result['endings'].items():
        shortest = min(len(path_to(result, i)) for i in combos.values())
        print(f"  ending {eid} ({story.endings[eid].get('title', '')}): {len(combos)} resolution combination(s), "
              f'shortest in {shortest} actions', file=out)
    print('play styles:', file=out)
    for p in plays:
        ends = ', '.join(f'{e} {c}' for e, c in p['endings'].most_common()) or 'none'
        line = f"  {p['style']:<22} {p['runs']} runs: {ends}; mean {p['mean_actions']} actions"
        if p['unfinished']:
            line += f"; {p['unfinished']} unfinished"
        print(line, file=out)
        if p['style'] == 'up' and p['opportunities_seen']:
            print('      opportunities offered (curious play): ' + ', '.join(
                f'{o} {v:.0%}' for o, v in p['opportunities_seen'].items()), file=out)
        for (eid, combo), c in sorted(p['combos'].items(), key=lambda x: -x[1])[:4]:
            print(f'      {c:>4} x {combo_text(story, eid, combo)}', file=out)
        for (sid, to), rate in p['shift_rates'].items():
            if rate is not None:
                print(f'      shift {sid} -> {to}: {rate:.0%}', file=out)
    print('findings:' if errors or notes else 'findings: none', file=out)
    for e in errors:
        print(f'  ERROR {e}', file=out)
    for n in notes:
        print(f'  note  {n}', file=out)
    if walkthroughs:
        for eid, combos in result['endings'].items():
            for combo, i in combos.items():
                print(f'\nWalkthrough to {eid}, {combo_text(story, eid, combo)}:', file=out)
                for k, label in enumerate(path_to(result, i), 1):
                    print(f'  {k:>2}. {label}', file=out)
    return {'errors': errors, 'notes': notes, 'explore': result, 'plays': plays}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('package')
    ap.add_argument('--walkthroughs', action='store_true', help='print the shortest route to each ending combination')
    ap.add_argument('--runs', type=int, default=500, help='random plays (styled plays get a fifth, at least 50)')
    ap.add_argument('--max-states', type=int, default=50000)
    args = ap.parse_args(argv)
    story = Story.load(args.package)
    errors, _ = validate(story)
    if errors:
        print('the package does not validate; run cli.py --check')
        return 1
    report = run(story, runs=args.runs, max_states=args.max_states, walkthroughs=args.walkthroughs)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
