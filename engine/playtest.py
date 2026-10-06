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
  explore_scenes  the same, one scene at a time, for a story too big to
            explore whole (more than three scenes): each scene is explored
            from the states the scenes before it are left in (a spread of
            them, by arc state, when there are many), and the states it is
            left in become the next scenes' entries. STUCK means a state the
            scene cannot be left from.
  play      many runs of a simulated player: `random` picks uniformly among
            the options; `up` / `down` prefer options that move arc states
            that way (and avoid the opposite); `<state>:up` steers one
            state; `seek` plays the story (answers choices, heads for the
            way on), `seek:branch` heads for the line-changing way on. Reports endings and resolutions reached, actions taken,
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
from runtime import FREE, Engine, leaves
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


def behavioural_flags(story):
    """Flags read by conditions that change what can happen (what is offered,
    what fires, where exits lead, what is visible, which ending variant
    holds), as opposed to flags read only by text variants (a description
    that changes, a fragment that appears). Only these need to be part of an
    explored state."""
    flags = set()
    for t in behavioural_conditions(story):
        for node in ast.walk(parse(t)):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'flags':
                flags.add(node.attr)
    return flags


def relevant_objects(story):
    """Per scene, the objects whose whereabouts can change what happens in it:
    named by a condition that matters (anywhere: has() can be asked by an
    ending), needed at hand by one of its interactions, or moved by one of
    its effects. Picking up anything else changes nothing but what you
    carry. Returns {scene: objects}; key None holds the story-wide ones."""
    wide = set()
    for t in behavioural_conditions(story):
        for node in ast.walk(parse(t)):
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                    and getattr(node.func, 'id', None) in ('has', 'here'):
                wide.add(node.args[0].value)
    out = {None: {o for o in wide if o in story.objects}}
    for sid, sc in story.scenes.items():
        mine = set(out[None])
        for it in sc.get('interactions') or []:
            if it.get('reach') != 'any':
                mine |= {it.get('object'), it.get('detail')}
            for e in it.get('effects') or []:
                mine |= {e.get('give'), e.get('take'), e.get('place')}
        for ev in (sc.get('events') or []) + (sc.get('nudges') or []):
            for e in ev.get('effects') or []:
                mine |= {e.get('give'), e.get('take'), e.get('place')}
        out[sid] = {o for o in mine if o in story.objects}
    return out


def inert_interactions(story):
    """One-time interactions that do nothing but say something: having used
    one takes it off the menu and changes nothing else."""
    return {it['id'] for sc in story.scenes.values() for it in sc.get('interactions') or []
            if not it.get('effects') and not it.get('takes_time')}


def behavioural_conditions(story):
    """The conditions that can change what happens: interactions, events,
    nudges, exits, visibility, ending variants, and the topics and thoughts
    that have effects. A topic that only says something is offered or not
    by its condition, and nothing else follows from it: its condition (a
    seen(), a visited(), a done flag) does not make two states different."""
    texts = []
    for sc in story.scenes.values():
        for key in ('interactions', 'events', 'nudges', 'exits'):
            texts += [x.get('when', 'true') for x in sc.get(key) or []]
    for ch in story.characters.values():
        texts += [t.get('known_when', 'true') for t in (ch.get('topics') or {}).values() if t.get('effects')]
    texts += [t.get('known_when', 'true') for t in (story.protagonist.get('think') or {}).values() if t.get('effects')]
    for room in story.rooms.values():
        texts += [x.get('when', 'true') for x in room.get('exits') or []]
    texts += [o.get('when', 'true') for o in story.objects.values()]
    for end in story.endings.values():
        for group in ending_groups(end):
            texts += [v.get('when', 'true') for v in group.get('variants') or [] if isinstance(v, dict)]
    return texts


def counter_caps(story):
    """For each counter, a value past which no condition can tell two values
    apart: one more than the largest constant it is compared with."""
    caps = {'turns': 0, 'turns_in_scene': 0}
    uses_visited = False
    seen_subjects = set()
    answered = set()
    behavioural = set(behavioural_conditions(story))
    for text in expressions_in(story.data):
        tree = parse(text)
        for node in ast.walk(tree):
            if text not in behavioural and isinstance(node, ast.Call) \
                    and getattr(node.func, 'id', None) in ('visited', 'seen'):
                continue                # gates only what is said: not part of a state
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'visited':
                uses_visited = True
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'seen' and node.args \
                    and isinstance(node.args[0], ast.Constant):
                seen_subjects.add(node.args[0].value)
            if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'answered' and node.args \
                    and isinstance(node.args[0], ast.Constant):
                answered.add(node.args[0].value)
            if isinstance(node, ast.Compare):
                sides = [node.left] + list(node.comparators)
                names = [n.id for n in sides if isinstance(n, ast.Name) and n.id in caps]
                nums = [n.value for n in sides if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))]
                for name in names:
                    for num in nums:
                        caps[name] = max(caps[name], int(num) + 1)
    idle = {sid: max([n.get('after', 3) for n in sc.get('nudges') or []] or [0])
            for sid, sc in story.scenes.items()}
    lapses = {m['id']: (m.get('lapse') or {}).get('after', 4) if not m.get('required') else 0
              for sc in story.scenes.values() for m in sc.get('moments') or []}
    scoped = {}                     # scene -> ids that live and die with it (interactions, moments, events, nudges)
    for sid, sc in story.scenes.items():
        ids = {it['id'] for it in sc.get('interactions') or []}
        ids |= {m['id'] for m in sc.get('moments') or []}
        ids |= {e['id'] for e in list(sc.get('events') or []) + list(sc.get('nudges') or [])}
        scoped[sid] = ids - answered
    return caps, idle, uses_visited, seen_subjects, lapses, scoped


class Normalizer:
    def __init__(self, story):
        self.story = story
        self.caps, self.idle, self.uses_visited, self.seen_subjects, self.lapses, self.scoped = counter_caps(story)
        self.all_scoped = set().union(*self.scoped.values()) if self.scoped else set()
        self.live_flags = behavioural_flags(story)
        self.objects, self.inert = relevant_objects(story), inert_interactions(story)
        self.uses_known = 'known(' in json.dumps(story.data)    # names change only text unless a condition asks

    def __call__(self, st):
        st.turns = min(st.turns, self.caps['turns'])
        st.turns_in_scene = min(st.turns_in_scene, self.caps['turns_in_scene'])
        nudges = (self.story.scenes.get(st.scene) or {}).get('nudges') or []
        if all(n['id'] in st.fired for n in nudges):
            st.idle = 0                       # no nudge left to fire: idling changes nothing
        else:
            st.idle = min(st.idle, self.idle.get(st.scene, 0))
        st.seed = SEED
        st.actions = 0                        # nothing reads the action count
        st.heard = set()                      # what was read only marks the menu
        st.flags = {k: v for k, v in st.flags.items() if k in self.live_flags}
        # another scene's interactions, moments and events can never be offered or fire again
        stale = self.all_scoped - self.scoped.get(st.scene, set())
        st.used -= stale
        st.fired -= stale
        st.moments = {m: min(n, self.lapses.get(m, 0)) for m, n in st.moments.items()}
        return st

    def key(self, st):
        """What tells two states apart. Who you have seen and where you have
        been stay in the state (they decide which topics the menu offers)
        but count only where a condition that matters asks about them."""
        d = st.to_dict()
        d['seen'] = sorted(st.seen & self.seen_subjects)
        keep = self.objects.get(st.scene, self.objects[None])
        d['locations'] = {k: v for k, v in d['locations'].items() if k in keep}
        d['used'] = sorted(set(d['used']) - self.inert)
        if not self.uses_visited:
            d['visited'] = []
        if not self.uses_known:
            d['introduced'] = []
        return json.dumps(d, sort_keys=True)


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

MAX_CHOICES = 29          # entries one menu level can show: the keys the terminal player has (cli.KEYS)


def menu_problems(eng):
    """What a person at the menu cannot do that the explorer can: an option
    missing from the menu or in it twice, two entries one level shows alike,
    an entry with no label, a level with more entries than keys."""
    tree = eng.menu()
    found = Counter(i for _, i in leaves(tree))
    problems = []
    for o in eng.options():
        if found[o['id']] == 0:
            problems.append(f"option {o['id']} is not in the menu")
        elif found[o['id']] > 1:
            problems.append(f"option {o['id']} is in the menu {found[o['id']]} times")

    def walk(node, path):
        kids = node.get('children') or []
        where = ' › '.join(path) or 'the top level'
        if len(kids) > MAX_CHOICES:
            problems.append(f'{where} has more entries than the {MAX_CHOICES} a menu level can show')
        labels = Counter(str(c.get('label') or '').strip().lower() for c in kids)
        if labels.get(''):
            problems.append(f'{where} has an entry with no label')
        for label, n in labels.items():
            if label and n > 1:
                problems.append(f'{where} shows {label!r} {n} times')
        for c in kids:
            if 'children' in c:
                walk(c, path + [str(c.get('label') or '')])
    walk(tree, [])
    return problems


def explore(story, max_states=50000):
    norm = Normalizer(story)
    eng = Engine(story)
    eng.start(seed=SEED)
    start = norm(eng.state.clone())
    states, index, parent, out = [start], {norm.key(start): 0}, {0: None}, [[]]
    offered, taken, fired, scenes, exits_taken = set(), set(), set(), set(), set()
    endings = {}                               # ending -> {combo: state index}
    truncated = False
    clipped = set()                            # states that lost a successor to the limit
    menus = {}                                 # (scene, problem) -> the first state it shows in
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
        for problem in menu_problems(eng):
            menus.setdefault((st.scene, problem), i)
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
                    clipped.add(i)
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
    if truncated:     # unexplored or clipped: unknown, so never reported as stuck
        can |= {i for i in range(len(states)) if (not out[i] and not states[i].ending) or i in clipped}
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
            'fired': fired, 'scenes': scenes, 'exits_taken': exits_taken, 'endings': endings, 'stuck': stuck,
            'menus': menus}


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
    # a truncated search has not tried every sequence: what it did not reach is unknown, not unreachable
    unreached = notes if result['truncated'] else errors
    for sid in story.scenes:
        if sid not in result['scenes']:
            unreached.append(f'scene {sid} is never reached by any sequence of actions'
                             + (' within the explored states' if result['truncated'] else ''))
    for eid in story.endings:
        if eid not in result['endings']:
            unreached.append(f'ending {eid} is never reached by any sequence of actions'
                             + (' within the explored states' if result['truncated'] else ''))
    by_scene = {}
    for i in result['stuck']:
        by_scene.setdefault(result['states'][i].scene, []).append(i)
    for sid, idxs in by_scene.items():
        first = min(idxs, key=lambda i: len(path_to(result, i)))
        errors.append(f'STUCK: {len(idxs)} state(s) in scene {sid} from which no ending can be reached; '
                      f"the first comes after: {' / '.join(path_to(result, first)) or '(the start)'}")
    for (sid, problem), i in result.get('menus', {}).items():
        errors.append(f"MENU: scene {sid}: {problem}; first after: {' / '.join(path_to(result, i)) or '(the start)'}")
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


# ---------------------------------------------------------------- one scene at a time

ENTRIES_PER_SCENE = 8     # entry states explored per scene, spread over the arc states they carry
SCENE_STATES = 20000      # states explored per scene


def scene_order(story):
    """Scenes in an order where a scene comes after every scene that can lead
    to it (as far as cycles allow): its entry states are all known when it is
    explored."""
    preds = {sid: set() for sid in story.scenes}
    for sid, sc in story.scenes.items():
        for ex in sc.get('exits') or []:
            if ex['to'] in preds and ex['to'] != sid:
                preds[ex['to']].add(sid)
    order, done = [], set()
    todo = list(story.scenes)
    while todo:
        ready = [s for s in todo if preds[s] <= done] or todo[:1]    # a cycle: take the first and go on
        for s in ready:
            order.append(s)
            done.add(s)
            todo.remove(s)
    return order


def entry_bucket(st):
    """What makes two entry states worth exploring separately: the arc counts
    (patterns and endings read them) and the flags set."""
    return (tuple(sorted((k, v.get('up', 0), v.get('down', 0)) for k, v in st.arcs.items())),
            tuple(sorted(k for k, v in st.flags.items() if v)))


def spread(items, k):
    """k items evenly spaced through a sorted list."""
    if len(items) <= k:
        return items
    step = len(items) / k
    return [items[int(i * step)] for i in range(k)]


def explore_scene(story, sid, entries, norm, max_states=SCENE_STATES):
    """Breadth-first within one scene from its entry states [(state, path)].
    An action that leaves the scene (another scene, an ending) ends that
    branch; what it leaves to, and the state it leaves in, are kept by bucket
    for the next scene's entries."""
    eng = Engine(story)
    states, index, parent, out = [], {}, {}, []
    queue = deque()
    for st, path in entries:
        st = norm(st.clone())
        k = norm.key(st)
        if k in index:
            continue
        index[k] = len(states)
        parent[len(states)] = ('entry', path)
        states.append(st)
        out.append([])
        queue.append(len(states) - 1)
    leaving = {}                     # target -> {bucket: (state, path)}
    endings = {}                     # ending -> {combo: path}
    offered, taken, fired, menus = set(), set(), set(), {}
    leaves_from, clipped, truncated = set(), set(), False
    while queue:
        i = queue.popleft()
        st = states[i]
        fired |= st.fired
        eng.state = st.clone()
        for problem in menu_problems(eng):
            menus.setdefault(problem, i)
        for opt in time_taking(eng):
            offered.add(opt['id'])
            eng.state = st.clone()
            eng.queue = []
            eng.perform(opt, reseed=False)
            nxt = eng.state
            taken.add(opt['id'])
            if nxt.ending or nxt.scene != sid:
                leaves_from.add(i)
                fired |= nxt.fired
                label = eng.label_of(opt)
                if nxt.ending:
                    endings.setdefault(nxt.ending, {}).setdefault(
                        resolution_combo(story, nxt), lambda i=i, label=label: scene_path(result, i) + [label])
                else:
                    leaving.setdefault(nxt.scene, {}).setdefault(
                        entry_bucket(norm(nxt.clone())), (nxt.clone(), (i, label)))
                continue
            nxt = norm(nxt)
            k = norm.key(nxt)
            j = index.get(k)
            if j is None:
                if len(states) >= max_states:
                    truncated = True
                    clipped.add(i)
                    continue
                j = len(states)
                index[k] = j
                states.append(nxt)
                out.append([])
                parent[j] = (i, eng.label_of(opt))
                queue.append(j)
            out[i].append(j)
    can = set(leaves_from)
    if truncated:     # unexplored or clipped: unknown, so never reported as stuck
        can |= {i for i in range(len(states)) if (not out[i] and i not in leaves_from) or i in clipped}
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
    result = {'scene': sid, 'states': states, 'parent': parent, 'truncated': truncated, 'offered': offered,
              'taken': taken, 'fired': fired, 'menus': menus, 'stuck': [i for i in range(len(states)) if i not in can],
              'entries': len([p for p in parent.values() if p[0] == 'entry'])}
    # paths are built only for what is reported (a closure over the finished result)
    result['endings'] = {e: {c: f() for c, f in combos.items()} for e, combos in endings.items()}
    result['leaving'] = {t: {b: (st, scene_path(result, i) + [label]) for b, (st, (i, label)) in bs.items()}
                         for t, bs in leaving.items()}
    return result


def scene_path(result, i):
    """The labels from the story's start to state i of a scene's exploration."""
    labels = []
    while True:
        p = result['parent'][i]
        if p[0] == 'entry':
            return list(p[1]) + list(reversed(labels))
        i, label = p
        labels.append(label)


def explore_scenes(story, max_states=SCENE_STATES, per_scene=ENTRIES_PER_SCENE):
    """Every scene explored on its own, from entry states the scenes before it
    leave in (the start state for the first). Scales with the size of a
    scene, not of the story; the price is sampling: a scene reached in more
    distinct states than `per_scene` is explored from a spread of them."""
    norm = Normalizer(story)
    eng = Engine(story)
    eng.start(seed=SEED)
    arriving = {eng.state.scene: {entry_bucket(norm(eng.state.clone())): (eng.state.clone(), [])}}
    scenes, endings, sampled = {}, {}, set()
    for sid in scene_order(story):
        buckets = arriving.get(sid)
        if not buckets:
            continue
        keys = sorted(buckets)
        if len(keys) > per_scene:
            sampled.add(sid)
        res = explore_scene(story, sid, [buckets[k] for k in spread(keys, per_scene)], norm, max_states)
        scenes[sid] = res
        for target, bs in res['leaving'].items():
            arriving.setdefault(target, {}).update({b: v for b, v in bs.items() if b not in arriving.get(target, {})})
        for e, combos in res['endings'].items():
            for c, path in combos.items():
                if c not in endings.setdefault(e, {}) or len(path) < len(endings[e][c]):
                    endings[e][c] = path
    return {'scenes': scenes, 'endings': endings, 'sampled': sampled,
            'arrived': {s: len(b) for s, b in arriving.items()}}


def scene_findings(story, result):
    errors, notes = [], []
    scenes = result['scenes']
    partial = bool(result['sampled']) or any(r['truncated'] for r in scenes.values())
    for sid in sorted(result['sampled']):
        notes.append(f"scene {sid} is entered in {result['arrived'][sid]} distinct states; explored from "
                     f'{ENTRIES_PER_SCENE} of them, spread over their arc states')
    for sid, r in scenes.items():
        if r['truncated']:
            notes.append(f"scene {sid}: exploration stopped at {len(r['states'])} states; its findings cover only those")
    # a sampled or truncated search has not tried everything: what it did not reach is unknown, not unreachable
    unreached = notes if partial else errors
    for sid in story.scenes:
        if sid not in scenes:
            unreached.append(f'scene {sid} is never reached by any sequence of actions'
                             + (' (within the states explored)' if partial else ''))
    for eid in story.endings:
        if eid not in result['endings']:
            unreached.append(f'ending {eid} is never reached by any sequence of actions'
                             + (' (within the states explored)' if partial else ''))
    for sid, r in scenes.items():
        if r['stuck']:
            first = min(r['stuck'], key=lambda i: len(scene_path(r, i)))
            errors.append(f"STUCK: {len(r['stuck'])} state(s) in scene {sid} from which the scene cannot be left; "
                          f"the first comes after: {' / '.join(scene_path(r, first)) or '(the start)'}")
        sc = story.scenes[sid]
        for it in sc.get('interactions') or []:
            if it['id'] not in r['offered']:
                notes.append(f"interaction {it['id']} is never offered")
        for ev in (sc.get('events') or []) + (sc.get('nudges') or []):
            if ev['id'] not in r['fired']:
                notes.append(f"{'nudge' if ev in (sc.get('nudges') or []) else 'event'} {ev['id']} never fires")
        for ex in sc.get('exits') or []:
            if ex['to'] not in r['leaving'] and ex['to'] not in r['endings']:
                notes.append(f"scene {sid}: the exit to {ex['to']} ({ex.get('when', 'true')}) is never taken")
    menus = {}                  # the same problem in many scenes (a topic everyone shares) is one finding
    for sid, r in scenes.items():
        for problem, i in r['menus'].items():
            menus.setdefault(problem, []).append((sid, scene_path(r, i)))
    for problem, where in menus.items():
        first = min(where, key=lambda w: len(w[1]))
        also = f" (and in {len(where) - 1} more scene{'s' if len(where) > 2 else ''})" if len(where) > 1 else ''
        errors.append(f"MENU: scene {first[0]}{also}: {problem}; first after: {' / '.join(first[1]) or '(the start)'}")
    for eid, combos in result['endings'].items():
        for gi, group in enumerate(ending_groups(story.endings[eid])):
            used = {c[gi] for c in combos}
            for vi, v in enumerate(group.get('variants') or []):
                if vi not in used:
                    notes.append(f"ending {eid}: the variant {v.get('when', 'true')} of "
                                 f"{group.get('about') or 'its text'} is never chosen")
    return errors, notes


# ---------------------------------------------------------------- simulated players

CURIOSITY = 0.7     # a styled player tries something new this often, when it can
SEEK_CHOICE = 0.6   # a seeker answers an offered choice this often
SEEK_WAY = 0.5      # takes the way on, when it is here, this often
SEEK_WALK = 0.7     # otherwise walks toward it this often (else looks around)
SEEK_FINISH = 0.8   # seekers who finish, at least
STYLE_SEEK = 0.5    # a styled player with nothing its way plays on like a seeker this often


def chooser(story, style):
    """A function (options, rng, tried) -> option for a play style. Styled
    players are also curious: among options that move nothing, they prefer
    ones they have not tried (people open conversations and drawers; a
    uniform random walker mostly walks)."""
    if style == 'random':
        return lambda opts, rng, tried, eng=None: rng.choice(opts)
    if style.startswith('seek'):
        return seeker(story, branch=style == 'seek:branch')
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

    seek = seeker(story)

    def choose(opts, rng, tried, eng=None):
        toward = [o for o in opts if any(d == direction for _, d in moves(o))]
        if toward:
            return rng.choice(toward)
        neutral = [o for o in opts if not moves(o)] or opts
        if eng is not None and rng.random() < STYLE_SEEK:   # nothing pulls its way: get on with the story
            return seek(neutral, rng, tried, eng)
        fresh = [o for o in neutral if o['id'] not in tried]
        if fresh and rng.random() < CURIOSITY:
            return rng.choice(fresh)
        return rng.choice(neutral)
    return choose


def leads_on(it, sid):
    return any(str(e.get('set', '')).startswith(f'go_{sid}__') for e in it.get('effects') or [])


def step_toward(story, eng, room):
    """The Go option that is the first step of a shortest walk to `room`
    through the scene's rooms, or None."""
    open_ = eng.open_rooms()
    first, todo = {eng.state.room: None}, deque([eng.state.room])
    while todo:
        r = todo.popleft()
        if r == room:
            break
        for ex in (story.rooms.get(r) or {}).get('exits') or []:
            if ex['to'] in open_ and ex['to'] not in first and evaluate(ex.get('when', 'true'), eng.state):
                first[ex['to']] = first[r] or ex['to']
                todo.append(ex['to'])
    return f'go:{first[room]}' if first.get(room) else None


def seeker(story, branch=False):
    """A player who plays the story rather than the menu: answers the scene's
    choices when they are offered, takes the way on when it is there, and
    otherwise walks toward the room where it is (or a choice that is still
    open), looking around on the way. `branch` heads for the line-changing
    way on (weight major) when a scene has one."""
    def choose(opts, rng, tried, eng):
        st, sid = eng.state, eng.state.scene
        by_id = {o['id']: o for o in opts}
        moment = [o for o in opts if eng.moment_of(o['id'])]
        if moment and rng.random() < SEEK_CHOICE:
            return rng.choice(moment)
        sc = story.scenes[sid]
        ways = [it for it in sc.get('interactions') or [] if it['id'] not in st.used and leads_on(it, sid)]
        major = [it for it in ways if it.get('weight') == 'major']
        goals = major if branch and major else ([it for it in ways if not it.get('weight')] or ways)
        open_choices = [it for m in eng.moments() if m.get('required') and m['id'] not in st.used
                        for it in sc.get('interactions') or [] if it['id'] in (m.get('options') or [])]
        here = [by_id[g['id']] for g in goals if g['id'] in by_id]
        if here and rng.random() < SEEK_WAY:
            return rng.choice(here)
        rooms = [g['room'] for g in open_choices + goals if g.get('room') and g['room'] != st.room]
        if rooms and rng.random() < SEEK_WALK:
            step = step_toward(story, eng, rooms[0])
            if step in by_id:
                return by_id[step]
        fresh = [o for o in opts if o['id'] not in tried]
        return rng.choice(fresh if fresh and rng.random() < CURIOSITY else opts)
    return choose


def opportunities(story):
    """Option ids that move an arc state: the choices the story is built on.
    Options grouped in a moment are measured by the moment (offered when any
    of its options is), not one by one."""
    out = []
    for sc in story.scenes.values():
        grouped = {o for m in sc.get('moments') or [] for o in m.get('options') or []}
        for it in sc.get('interactions') or []:
            if any('move' in e for e in it.get('effects') or []) and it['id'] not in grouped:
                out.append(it['id'])
    for cid, ch in story.characters.items():
        for tid, topic in (ch.get('topics') or {}).items():
            if any('move' in e for e in topic.get('effects') or []):
                out.append(f'talk:{cid}:{tid}')
    return out


def optional_ids(story):
    """Opportunities a player may miss by design: marked `optional`, or in a
    moment that lapses."""
    out = {it['id'] for sc in story.scenes.values() for it in sc.get('interactions') or [] if it.get('optional')}
    out |= {o for sc in story.scenes.values() for m in sc.get('moments') or [] if not m.get('required')
            for o in m.get('options') or []}
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
            opt = pick(opts, rng, tried, eng)
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
    seek = next((p for p in plays if p['style'] == 'seek'), None)
    if seek and seek['unfinished'] > seek['runs'] * (1 - SEEK_FINISH):
        errors.append(f"{seek['unfinished']} of {seek['runs']} plays that look for the way forward did not finish in "
                      f'the step limit: the way on is hard to find even for a player seeking it')
    reached = set().union(*(p['endings'] for p in plays)) if plays else set()
    for eid in story.endings:
        if plays and eid not in reached:
            notes.append(f'ending {eid} is reached by none of the simulated players')
    if random_play and random_play['unfinished']:
        notes.append(f"{random_play['unfinished']} of {random_play['runs']} random plays did not finish "
                     f'in the step limit (wandering is allowed; a high share may mean the way forward is hard to find)')
    return errors, notes


# ---------------------------------------------------------------- report

def styles_for(story):
    out = ['random', 'seek', 'seek:branch', 'up', 'down']
    for name in story.states:
        out += [f'{name}:up', f'{name}:down']
    return out


WHOLE_STORY_SCENES = 3    # stories with more scenes are explored one scene at a time


def run(story, runs=500, max_states=50000, walkthroughs=False, out=sys.stdout, styled_runs=None, scene_states=None,
        by_scene=None):
    """Explore (the whole story when it is small, else scene by scene), play
    every style, report. `by_scene` forces the method; `scene_states` caps
    each scene's exploration."""
    if by_scene is None:
        by_scene = len(story.scenes) > WHOLE_STORY_SCENES
    if by_scene:
        return run_by_scene(story, runs, scene_states or SCENE_STATES, walkthroughs, out, styled_runs)
    result = explore(story, max_states=max_states)
    errors, notes = explore_findings(story, result)
    styled_runs = styled_runs or max(50, runs // 5)
    plays = [play(story, style, runs=runs if style == 'random' else styled_runs) for style in styles_for(story)]
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


def print_plays(plays, story, out):
    print('play styles:', file=out)
    for p in plays:
        ends = ', '.join(f'{e} {c}' for e, c in p['endings'].most_common()) or 'none'
        line = f"  {p['style']:<22} {p['runs']} runs: {ends}; mean {p['mean_actions']} actions"
        if p['unfinished']:
            line += f"; {p['unfinished']} unfinished"
        print(line, file=out)
        for (sid, to), rate in p['shift_rates'].items():
            if rate is not None:
                print(f'      shift {sid} -> {to}: {rate:.0%}', file=out)


def run_by_scene(story, runs, scene_states, walkthroughs, out, styled_runs):
    result = explore_scenes(story, max_states=scene_states)
    errors, notes = scene_findings(story, result)
    styled_runs = styled_runs or max(50, runs // 5)
    plays = [play(story, style, runs=runs if style == 'random' else styled_runs) for style in styles_for(story)]
    e2, n2 = play_findings(story, plays)
    errors += e2
    notes += n2
    total = sum(len(r['states']) for r in result['scenes'].values())
    print(f"{story.title}: explored scene by scene, {total} states over {len(result['scenes'])} of "
          f"{len(story.scenes)} scenes", file=out)
    for sid, r in result['scenes'].items():
        print(f"  {sid:<12} {len(r['states']):>6} states from {r['entries']} entry state(s)"
              f"{' (stopped at the limit)' if r['truncated'] else ''}; leads to "
              f"{', '.join(sorted(r['leaving']) + sorted(r['endings'])) or 'nothing'}", file=out)
    for eid, combos in result['endings'].items():
        shortest = min(len(p) for p in combos.values())
        print(f"  ending {eid} ({story.endings[eid].get('title', '')}): {len(combos)} resolution combination(s), "
              f'shortest in {shortest} actions', file=out)
    print_plays(plays, story, out)
    print('findings:' if errors or notes else 'findings: none', file=out)
    for e in errors:
        print(f'  ERROR {e}', file=out)
    for n in notes:
        print(f'  note  {n}', file=out)
    if walkthroughs:
        for eid, combos in result['endings'].items():
            combo, path = min(combos.items(), key=lambda x: len(x[1]))
            print(f'\nWalkthrough to {eid}, {combo_text(story, eid, combo)}:', file=out)
            for k, label in enumerate(path, 1):
                print(f'  {k:>2}. {label}', file=out)
    return {'errors': errors, 'notes': notes, 'explore': result, 'plays': plays}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('package')
    ap.add_argument('--walkthroughs', action='store_true', help='print the shortest route to each ending combination')
    ap.add_argument('--runs', type=int, default=500, help='random plays (styled plays get a fifth, at least 50)')
    ap.add_argument('--max-states', type=int, default=50000)
    ap.add_argument('--by-scene', action='store_true', help='explore scene by scene even for a small story')
    args = ap.parse_args(argv)
    story = Story.load(args.package)
    errors, _ = validate(story)
    if errors:
        print('the package does not validate; run cli.py --check')
        return 1
    report = run(story, runs=args.runs, max_states=args.max_states, walkthroughs=args.walkthroughs,
                 by_scene=True if args.by_scene else None)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
