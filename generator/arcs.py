"""Stage A: character arcs and node expansion (docs/later_stages.md §2).

The outline's lines carry the protagonist's arc; this stage maps every
other arc onto the node graph and expands it with minor nodes that let the
player influence, understand and complete those arcs.

    A0  arc cast: computed tiers (arc: the opposition, anyone whose
        standing differs between endings, and a companion with a breaking
        point who is in at least half the nodes; a breaking point alone is
        not enough, since the cast step gives one to every companion), plus
        one thinking-off call that sorts the rest into supporting and
        functional. The arc cast is closed here.
    A1  arc plan, one call: per arc character a named state (what moves it
        up and down), where the arc starts, its moments on the major nodes,
        and how it resolves on each line (by line, or by the state's
        direction); light arcs for supporting characters; the protagonist's
        arc per line; setup/payoff pairs; pattern shifts the story wants.
    A2  node expansion, one call per line: minor nodes (opportunity,
        revelation, demonstration, resolution) hung after the line's major
        nodes. A major node shared by several lines is expanded with the
        first line that reaches it; later lines see those minor nodes.

Python owns the structure (later_stages.md §2, "What Python does"): ids and
graph surgery, the state registry, all threshold math (a pattern shift's
condition is computed so that random play triggers it under 15% of the
time), the composed ending variants, every rule check, and a playtest of the
expanded graph (generator/playtest.py). Output: <id>_arcs.json and
<id>_arcs.md.
"""

import argparse
import json
import os
import re
import sys

import checks
from checks import as_list
import playtest
import schemas
from errors import SoftReject

norm = checks.norm

KINDS = ('opportunity', 'revelation', 'demonstration', 'resolution')
MOMENT_KINDS = ('turn', 'reveal', 'test', 'demonstration')
VISIBILITY = ('signposted', 'observed', 'hidden')
SHIFT_DOES = ('resolution', 'ending', 'line')
RANDOM_SHIFT_LIMIT = 0.15
SHIFT_MIN_MOVES = 3
SHIFT_SHARES = (0.75, 0.8, 0.9, 1.0)
RESOLUTION_SHARE = 0.6
SUMMARY_WORDS = (20, 70)
TELL_REACH = 2                  # a tell lands within this many nodes after its opportunity, or at the next major node
STATE_NAME = re.compile(r'^[a-z][a-z0-9_]{2,40}$')


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- threshold math

def random_pattern_rate(opps, at_least, share):
    """How often uniform random play satisfies a pattern: `opps` is one
    (p_toward, p_against) per opportunity on the path (the share of its
    options that move the state each way). Exact, by dynamic programming over
    (moves toward, moves against)."""
    dist = {(0, 0): 1.0}
    for p_to, p_against in opps:
        p_none = max(0.0, 1.0 - p_to - p_against)
        nxt = {}
        for (d, o), p in dist.items():
            for key, q in (((d + 1, o), p_to), ((d, o + 1), p_against), ((d, o), p_none)):
                if q:
                    nxt[key] = nxt.get(key, 0.0) + p * q
        dist = nxt
    return sum(p for (d, o), p in dist.items() if d + o >= at_least and d + o and d / (d + o) >= share)


def shift_threshold(opps, limit=RANDOM_SHIFT_LIMIT):
    """The least strict pattern (at least k moves, at least `share` of them
    toward) that a consistent player can reach and random play reaches under
    `limit` of the time. None when the path has too few opportunities."""
    reachable = sum(1 for p_to, _ in opps if p_to > 0)
    for k in range(SHIFT_MIN_MOVES, reachable + 1):
        for share in SHIFT_SHARES:
            rate = random_pattern_rate(opps, k, share)
            if rate < limit:
                return {'at_least': k, 'share': share, 'random_rate': round(rate, 3)}
    return None


def option_split(node, state, direction):
    """(p_toward, p_against) for one opportunity and one state."""
    options = node.get('options') or []
    if not options:
        return 0.0, 0.0
    other = 'down' if direction == 'up' else 'up'
    to = sum(1 for o in options if any(m['state'] == state and m['direction'] == direction for m in o.get('moves') or []))
    against = sum(1 for o in options if any(m['state'] == state and m['direction'] == other for m in o.get('moves') or []))
    return to / len(options), against / len(options)


def moves_state(node, state):
    return any(m['state'] == state for o in node.get('options') or [] for m in o.get('moves') or [])


def tell_in_reach(seq, own, target, is_major):
    """A tell must show soon: within TELL_REACH nodes of its opportunity, or at
    the first major node after it (minor nodes other lines hang after a
    shared node can push the next beat further away; the next beat still
    counts as soon)."""
    if target is None or target <= own:
        return False
    if target - own <= TELL_REACH:
        return True
    first_major = next((i for i in range(own + 1, len(seq)) if is_major(seq[i])), None)
    return target == first_major


def pattern_holds(up, down, direction, at_least, share):
    """The engine's pattern(): moved at least `at_least` times, at least
    `share` of the moves `direction` (engine/expressions.py)."""
    moves = up + down
    agree = down if direction == 'down' else up
    return moves >= at_least and moves > 0 and agree / moves >= share


def is_seesaw(node):
    """Every option trades one state up against another down: the player is
    asked "this person or that one" again (kernel35's first live run: 6 of 14
    opportunities, and no option good for both)."""
    sigs = [{(m['state'], m['direction']) for m in o.get('moves') or []} for o in node.get('options') or []]
    sigs = [x for x in sigs if x]
    return bool(sigs) and all(len({st for st, _ in x}) >= 2 and len({d for _, d in x}) == 2 for x in sigs)


def expr(state, direction, at_least, share):
    return f"pattern('{state}','{direction}',{at_least},{share})"


# ---------------------------------------------------------------- the stage

class ArcBuilder:
    def __init__(self, gen, story):
        self.gen = gen
        self.story = story
        self.nodes = story['nodes']
        self.lines = story['lines']
        self.order = story.get('line_order') or list(self.lines)
        self.chars = story.get('characters') or {}
        self.premise = story.get('premise') or {}
        self.tiers = {}
        self.plan = None
        self.minors = {}            # minor id -> minor node
        self.after = {}             # major id -> [minor ids] in order
        self.new_functional = []    # people A2 named who are not in the register

    # ------------------------------------------------------------ lookups

    def resolve(self, name):
        """A character id for a name or label the model wrote, or None."""
        text = re.sub(r'\(.*?\)', ' ', str(name or '')).strip()
        want = norm(text)
        if not want:
            return None
        for cid, c in self.chars.items():
            if want in (norm(c.get('label')), norm(c.get('name'))) or want == cid.lower():
                return cid
        hits = [cid for cid, c in self.chars.items()
                if c.get('name') and want in set(norm(c['name']).split()) - {'of', 'son', 'daughter', 'de', 'van'}]
        if len(hits) == 1:
            return hits[0]
        for cid, c in self.chars.items():           # "Lazlo Brandt, your brother-in-law"
            if c.get('name') and norm(c['name']) in want:
                return cid
        return None

    def who(self, cid):
        c = self.chars.get(cid) or {}
        return f"{c['name']} ({c.get('label')})" if c.get('name') else str(c.get('label') or cid)

    def lines_through(self, node_id):
        return [l for l in self.order if node_id in self.lines[l]['path']]

    def char_lines(self, cid):
        nodes = set((self.chars.get(cid) or {}).get('nodes') or [])
        return [l for l in self.order if nodes & set(self.lines[l]['path'])]

    def expanded_path(self, line_id):
        out = []
        for nid in self.lines[line_id]['path']:
            out.append(nid)
            out.extend(self.after.get(nid, []))
        return out

    def ending_of(self, line_id):
        return self.lines[line_id].get('ending') or {}

    # ------------------------------------------------------------ A0

    def a0_tiers(self):
        """Arc, supporting or functional for every character. Computed where it
        can be; one thinking-off call sorts the rest."""
        cast = list(self.chars.values())
        varies = set()
        for c in cast:
            label = norm(c.get('label'))
            standings = []
            for l in self.order:
                end = self.ending_of(l)
                if label in checks.people_only(end.get('standing'), cast):
                    standings.append('standing')
                elif label in checks.people_only(end.get('lost'), cast):
                    standings.append('lost')
                else:
                    standings.append('absent')
            if len(set(standings) - {'absent'}) > 1:
                varies.add(c['id'])
        undecided = []
        for cid, c in self.chars.items():
            if c.get('kind') == 'crowd':
                self.tiers[cid] = {'tier': 'functional', 'why': 'a crowd: its representative carries any arc'}
            elif c.get('opposition'):
                self.tiers[cid] = {'tier': 'arc', 'why': 'the opposition'}
            elif c.get('breaking_point') and len(c.get('nodes') or []) * 2 >= len(self.nodes):
                self.tiers[cid] = {'tier': 'arc', 'why': 'a companion with a breaking point, present in at least half '
                                                         'the nodes'}
            elif cid in varies:
                self.tiers[cid] = {'tier': 'arc', 'why': 'their standing differs between endings'
                                   + (' (and they have a breaking point)' if c.get('breaking_point') else '')}
            elif len(c.get('nodes') or []) <= 1:
                self.tiers[cid] = {'tier': 'functional', 'why': 'appears in one node'}
            else:
                undecided.append(cid)
        if undecided:
            answer = self.gen.run_prompt('s5a0', 'arc_cast', {
                '$$KERNEL$$': self.gen.kernel,
                '$$ARC_CAST$$': '\n'.join(f' - {self.who(c)}: {self.chars[c].get("wants")}'
                                          for c, t in self.tiers.items() if t['tier'] == 'arc') or ' (none)',
                '$$CANDIDATES_JSON$$': compact([{'who': self.who(c), 'wants': self.chars[c].get('wants'),
                                                 'tie': self.chars[c].get('tie'),
                                                 'nodes': len(self.chars[c].get('nodes') or [])} for c in undecided]),
            }, prompt_file='s5a0_arc_cast.prompt', validator=self.a0_validator(undecided), klass='classify',
                schema=schemas.ARC_CAST)
            for entry in answer['cast']:
                cid = self.resolve(entry['who'])
                self.tiers[cid] = {'tier': entry['tier'], 'why': entry.get('note') or ''}
        return self.tiers

    def a0_validator(self, undecided):
        def validate(parsed):
            got = {}
            for entry in as_list(parsed.get('cast')):
                cid = self.resolve(entry.get('who'))
                if cid not in undecided:
                    raise ValueError(f"cast entry {entry.get('who')!r} is not one of the candidates "
                                     f"{[self.who(c) for c in undecided]}")
                tier = str(entry.get('tier') or '').strip().lower()
                if tier not in ('supporting', 'functional'):
                    raise ValueError(f"{entry.get('who')}: tier must be supporting or functional, not {tier!r}")
                entry['tier'] = tier
                got[cid] = entry
            missing = [self.who(c) for c in undecided if c not in got]
            if missing:
                raise ValueError(f'no entry for {missing}; give one per candidate')
        return validate

    # ------------------------------------------------------------ A1

    def arc_cast(self, tier):
        return [c for c, t in self.tiers.items() if t['tier'] == tier]

    def a1_packet(self):
        p = self.premise
        prot = p.get('protagonist') or {}
        return {
            'protagonist': {k: prot.get(k) for k in ('name', 'who', 'history', 'wants', 'need', 'ties', 'open')
                            if prot.get(k)},
            'hidden_truth': p.get('hidden_truth'),
            'events': [e.get('what') if isinstance(e, dict) else e for e in as_list(p.get('events'))],
            'lines': [{'id': l, 'title': self.lines[l].get('title'), 'motivation': self.lines[l].get('motivation'),
                       'turning_point': self.lines[l].get('turning_point'), 'path': self.lines[l]['path'],
                       'ending': {k: self.ending_of(l).get(k) for k in ('title', 'answer', 'standing', 'lost', 'changed')}}
                      for l in self.order],
            'nodes': [{'id': n, 'title': self.nodes[n].get('title'), 'lines': self.lines_through(n),
                       'who': self.nodes[n].get('who'), 'summary': self.nodes[n].get('summary')}
                      for n in self.story.get('node_order') or self.nodes],
            'arc_cast': [{'who': self.who(c), 'wants': self.chars[c].get('wants'), 'edge': self.chars[c].get('edge'),
                          'tie': self.chars[c].get('tie'), 'voice': self.chars[c].get('voice'),
                          'breaking_point': self.chars[c].get('breaking_point'), 'lines': self.char_lines(c)}
                         for c in self.arc_cast('arc')],
            'supporting_cast': [{'who': self.who(c), 'wants': self.chars[c].get('wants'), 'tie': self.chars[c].get('tie'),
                                 'lines': self.char_lines(c)} for c in self.arc_cast('supporting')],
        }

    def a1_plan(self):
        self.plan = self.gen.run_prompt('s5a1', 'arc_plan', {
            '$$KERNEL$$': self.gen.kernel,
            '$$TONE$$': self.gen.tone_line(),
            '$$PACKET_JSON$$': compact(self.a1_packet()),
        }, prompt_file='s5a1_arc_plan.prompt', validator=self.a1_validate, klass='build', schema=schemas.ARC_PLAN)
        return self.plan

    def a1_validate(self, parsed):
        problems, soft = [], []
        vis = str(parsed.get('state_visibility') or '').strip().lower()
        if vis not in VISIBILITY:
            problems.append(f"state_visibility must be one of {VISIBILITY}, not {vis!r}")
        parsed['state_visibility'] = vis
        arc_ids = set(self.arc_cast('arc'))
        seen, states = {}, {}
        for a in as_list(parsed.get('arcs')):
            cid = self.resolve(a.get('who'))
            if cid not in arc_ids:
                problems.append(f"arcs: {a.get('who')!r} is not in the arc cast {[self.who(c) for c in arc_ids]}")
                continue
            if cid in seen:
                problems.append(f'arcs: {self.who(cid)} appears twice')
            seen[cid] = a
            a['id'] = cid
            st = a.get('state') or {}
            name = str(st.get('name') or '').strip().lower()
            if not STATE_NAME.match(name):
                problems.append(f'{self.who(cid)}: state name {name!r} must be snake_case, like lazlo_nerve')
            elif name in states:
                problems.append(f'{self.who(cid)}: state {name!r} is already used by {self.who(states[name])}')
            states[name] = cid
            st['name'] = name
            for k in ('meaning', 'up_when', 'down_when'):
                if not str(st.get(k) or '').strip():
                    problems.append(f'{self.who(cid)}: state.{k} is empty')
            lines = self.char_lines(cid)
            for m in as_list(a.get('moments')):
                if m.get('node') not in self.nodes:
                    problems.append(f"{self.who(cid)}: moment at unknown node {m.get('node')!r}")
                m['kind'] = str(m.get('kind') or '').strip().lower()
                if m['kind'] not in MOMENT_KINDS:
                    problems.append(f"{self.who(cid)}: moment kind must be one of {MOMENT_KINDS}, not {m['kind']!r}")
            moment_lines = {l for m in as_list(a.get('moments')) if m.get('node') in self.nodes
                            for l in self.lines_through(m['node'])}
            for l in lines:
                if l not in moment_lines:
                    soft.append(f'{self.who(cid)} appears on {l} but has no moment on a node of {l}')
            res_lines = {}
            for r in as_list(a.get('resolutions')):
                r['lines'] = [str(x) for x in as_list(r.get('lines'))]
                d = r.get('direction')
                r['direction'] = str(d).strip().lower() if d not in (None, '', 'null', 'none') else None
                if r['direction'] not in (None, 'up', 'down'):
                    problems.append(f"{self.who(cid)}: resolution direction must be up, down or null")
                for l in r['lines']:
                    if l not in self.lines:
                        problems.append(f'{self.who(cid)}: resolution on unknown line {l!r}')
                    res_lines.setdefault(l, []).append(r)
            for l in lines:
                if l not in res_lines:
                    problems.append(f'{self.who(cid)}: no resolution for line {l}, where they appear')
                    continue
                dirs = [r['direction'] for r in res_lines[l]]
                if len(res_lines[l]) > 1 and None in dirs and len([d for d in dirs if d]) == 0:
                    problems.append(f'{self.who(cid)}: line {l} has several resolutions but none says which state '
                                    f'direction leads to it')
                if len(set(d for d in dirs if d)) < len([d for d in dirs if d]):
                    problems.append(f'{self.who(cid)}: line {l} has two resolutions for the same direction')
                end = self.ending_of(l)
                label = norm(self.chars[cid].get('label'))
                cast = list(self.chars.values())
                standing = label in checks.people_only(end.get('standing'), cast)
                lost = label in checks.people_only(end.get('lost'), cast)
                if standing and lost:
                    continue    # the outline lists them both ways; nothing to agree with
                for r in res_lines[l]:
                    with_you = r.get('stands_with_you')
                    if r['direction'] is None and isinstance(with_you, bool) and (standing and not with_you
                                                                                  or lost and with_you):
                        soft.append(f"{self.who(cid)} on {l}: the resolution says stands_with_you={with_you}, but the "
                                    f"line's ending lists them as {'standing' if standing else 'lost'}")
        for cid in arc_ids - set(seen):
            problems.append(f'arcs: no entry for {self.who(cid)}')
        support = set(self.arc_cast('supporting'))
        light = {self.resolve(x.get('who')) for x in as_list(parsed.get('light_arcs'))}
        for x in as_list(parsed.get('light_arcs')):
            x['id'] = self.resolve(x.get('who'))
            for m in as_list(x.get('moments')):
                if m.get('node') not in self.nodes:
                    problems.append(f"light arc {x.get('who')}: moment at unknown node {m.get('node')!r}")
        for cid in support - light:
            soft.append(f'supporting character {self.who(cid)} has no light arc')
        for prot_line in self.order:
            if prot_line not in (parsed.get('protagonist') or {}):
                soft.append(f'protagonist: no arc for line {prot_line}')
        kept = []                 # a pair no player can see in order is dropped (one retry to mend it), never the run
        for s in as_list(parsed.get('setups')):
            if not isinstance(s, dict):
                continue
            a, b = s.get('setup'), s.get('payoff')
            if a not in self.nodes or b not in self.nodes:
                soft.append(f'setup/payoff names an unknown node: {a!r} -> {b!r}')
            elif not any(a in self.lines[l]['path'] and b in self.lines[l]['path']
                         and self.lines[l]['path'].index(a) < self.lines[l]['path'].index(b) for l in self.order):
                soft.append(f'setup {a} does not come before payoff {b} on any line (a line that pays it must pass '
                            f'through the setup first)')
            else:
                kept.append(s)
        parsed['setups'] = kept
        for sh in as_list(parsed.get('pattern_shifts')):
            sh['state'] = str(sh.get('state') or '').strip().lower()
            sh['direction'] = str(sh.get('direction') or '').strip().lower()
            sh['does'] = str(sh.get('does') or '').strip().lower()
            if sh['state'] not in states:
                problems.append(f"pattern shift on undeclared state {sh['state']!r} (declared: {sorted(states)})")
            if sh['direction'] not in ('up', 'down'):
                problems.append('pattern shift direction must be up or down')
            if sh['does'] not in SHIFT_DOES:
                problems.append(f"pattern shift does must be one of {SHIFT_DOES}")
            if sh.get('at') not in self.nodes:
                problems.append(f"pattern shift at unknown node {sh.get('at')!r}")
            if sh['does'] == 'line' and sh.get('to') not in self.nodes:
                problems.append(f"a line shift must name the node it jumps to, not {sh.get('to')!r}")
            if sh['does'] == 'line' and sh.get('to') in self.nodes and sh.get('at') in self.nodes:
                if set(self.lines_through(sh['to'])) >= set(self.lines_through(sh['at'])):
                    problems.append(f"line shift {sh['at']} -> {sh['to']}: every line through {sh['at']} already "
                                    f"reaches {sh['to']}")
        if problems:
            raise ValueError('; '.join(problems))
        if soft:
            raise SoftReject('; '.join(soft))

    def states(self):
        return {a['state']['name']: dict(a['state'], who=a['id']) for a in self.plan.get('arcs') or []}

    # ------------------------------------------------------------ A2

    def a2_packet(self, line_id):
        states = self.states()
        path = self.lines[line_id]['path']
        arcs = []
        for a in self.plan.get('arcs') or []:
            if line_id not in self.char_lines(a['id']):
                continue
            arcs.append({'who': self.who(a['id']), 'state': a['state'],
                         'moments': [m for m in a.get('moments') or [] if m.get('node') in path],
                         'resolutions': [r for r in a.get('resolutions') or [] if line_id in r['lines']]})
        light = [{'who': self.who(x['id']) if x.get('id') else x.get('who'),
                  'moments': [m for m in x.get('moments') or [] if m.get('node') in path], 'ends': x.get('ends')}
                 for x in self.plan.get('light_arcs') or []]
        major = []
        for nid in path:
            n = self.nodes[nid]
            entry = {'id': nid, 'title': n.get('title'), 'lines': self.lines_through(nid), 'summary': n.get('summary'),
                     'who': n.get('who'), 'where': n.get('where')}
            additions = [a for a in as_list(n.get('additions')) if a]
            if additions:
                entry['must_contain'] = additions
            done = [{'id': m, 'kind': self.minors[m]['kind'], 'summary': self.minors[m]['summary'],
                     'moves': sorted({mv['state'] + ' ' + mv['direction'] for o in self.minors[m].get('options') or []
                                      for mv in o.get('moves') or []})}
                    for m in self.after.get(nid, [])]
            if done:
                entry['already_expanded'] = done
            if self.nodes[nid].get('is_ending'):
                entry['ending'] = True
            major.append(entry)
        shifts = [sh for sh in self.plan.get('pattern_shifts') or [] if sh.get('at') in path]
        return {'line': {'id': line_id, 'title': self.lines[line_id].get('title'),
                         'motivation': self.lines[line_id].get('motivation'),
                         'protagonist_arc': (self.plan.get('protagonist') or {}).get(line_id),
                         'ending': self.ending_of(line_id).get('summary')},
                'state_visibility': self.plan.get('state_visibility'),
                'states': [{'name': k, 'who': self.who(v['who']), 'up_when': v.get('up_when'),
                            'down_when': v.get('down_when')} for k, v in states.items()],
                'arcs': arcs, 'light_arcs': [x for x in light if x['moments']], 'path': major,
                'pattern_shifts': [{'state': s['state'], 'direction': s['direction'], 'at': s['at'],
                                    'does': s['does']} for s in shifts]}

    def a2_line(self, line_id, n):
        packet = self.a2_packet(line_id)
        result = self.gen.run_prompt(f's5a2_{line_id}', 'line_expansion', {
            '$$KERNEL$$': self.gen.kernel,
            '$$TONE$$': self.gen.tone_line(),
            '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s5a2_line_expansion.prompt', validator=self.a2_validator(line_id), klass='build',
            schema=schemas.LINE_EXPANSION)
        self.insert(line_id, result['minor_nodes'])
        return result

    def a2_validator(self, line_id):
        states = self.states()
        path = self.lines[line_id]['path']

        def validate(parsed):
            problems, soft = [], []
            got = [x for x in as_list(parsed.get('minor_nodes')) if isinstance(x, dict)]
            if not got:
                problems.append('minor_nodes is empty; every line needs opportunities for its arcs')
            for i, x in enumerate(got, 1):
                where = f"minor node {i} (after {x.get('after')})"
                x['kind'] = str(x.get('kind') or '').strip().lower()
                if x['kind'] not in KINDS:
                    problems.append(f"{where}: kind must be one of {KINDS}, not {x['kind']!r}")
                if x.get('after') not in path:
                    problems.append(f"{where}: after must be a major node on {line_id}: {path}")
                elif self.nodes[x['after']].get('is_ending') and x['kind'] != 'resolution':
                    problems.append(f"{where}: only a resolution may follow the ending node {x['after']}")
                for k in ('title', 'summary', 'image'):
                    if not str(x.get(k) or '').strip():
                        problems.append(f'{where}: {k} is empty')
                words = len(str(x.get('summary') or '').split())
                if words and not SUMMARY_WORDS[0] <= words <= SUMMARY_WORDS[1]:
                    soft.append(f'{where}: summary is {words} words; keep it to 30-50')
                x['serves'] = [self.resolve(s) or s for s in as_list(x.get('serves'))]
                unknown = [s for s in x['serves'] if s not in self.chars]
                if unknown:
                    problems.append(f'{where}: serves names {unknown}, who are not in the cast')
                x['who'] = [str(w).strip() for w in as_list(x.get('who')) if str(w).strip()
                            and norm(w) not in ('you', 'yourself', 'the protagonist', 'protagonist')]
                options = as_list(x.get('options'))
                if x['kind'] == 'opportunity':
                    if not 2 <= len(options) <= 3:
                        problems.append(f'{where}: an opportunity has two or three options, not {len(options)}')
                    moved = False
                    for o in options:
                        if not str(o.get('do') or '').strip():
                            problems.append(f'{where}: an option has no "do"')
                        o['active'] = bool(o.get('active')) and str(o.get('active')).lower() != 'false'
                        clean = []
                        for m in as_list(o.get('moves')):
                            st = str((m or {}).get('state') or '').strip().lower()
                            d = str((m or {}).get('direction') or '').strip().lower()
                            if st not in states:
                                problems.append(f'{where}: option {o.get("do")!r} moves undeclared state {st!r} '
                                                f'(declared: {sorted(states)})')
                            elif d not in ('up', 'down'):
                                problems.append(f'{where}: option {o.get("do")!r}: direction must be up or down')
                            else:
                                clean.append({'state': st, 'direction': d})
                        o['moves'] = clean
                        moved = moved or bool(clean)
                    if options and not moved:
                        problems.append(f'{where}: no option moves a state; an opportunity moves an arc')
                    tell = x.get('tell') or {}
                    if not str(tell.get('how') or '').strip():
                        soft.append(f'{where}: no tell (how and where the player sees the effect, within two nodes)')
                elif options:
                    x['options'] = []
            if problems:
                raise ValueError('; '.join(problems))
            # line-level rules, on the line as it would be with these nodes in
            trial = self.trial_path(line_id, got)
            opps = [(i, x) for i, x in enumerate(got) if x['kind'] == 'opportunity']
            for i, x in opps:
                tell_at = (x.get('tell') or {}).get('at')
                through = self.lines_through(x['after'])
                missed = []
                for l in through:     # a node after a shared major node is on every line through it
                    seq = self.trial_path(l, got)
                    own = seq.index(('new', i))
                    target = None
                    if isinstance(tell_at, str) and tell_at in seq:
                        target = seq.index(tell_at)
                    elif isinstance(tell_at, str) and re.fullmatch(r'm\d+', tell_at or ''):
                        k = int(tell_at[1:]) - 1
                        target = seq.index(('new', k)) if ('new', k) in seq else None
                    if not tell_in_reach(seq, own, target, lambda t: isinstance(t, str) and t in self.nodes):
                        missed.append(l)
                if missed:
                    shared = f' (it follows {x["after"]}, which lines {", ".join(through)} share, so its tell must ' \
                             f'land on all of them)' if len(through) > 1 else ''
                    soft.append(f"minor node {i + 1} (after {x['after']}): its tell at {tell_at!r} does not land at "
                                f"the next major node or within {TELL_REACH} nodes on {', '.join(missed)}{shared}; "
                                f"use a major node id or m<k> for the k-th minor node of this answer")
            existing = [self.minors[m] for m in self.expanded_path(line_id) if m in self.minors]
            all_opps = [x for x in existing if x['kind'] == 'opportunity'] + [x for _, x in opps]
            if len(states) >= 2 and len(all_opps) >= 3:
                seesaws = [x for x in all_opps if is_seesaw(x)]
                if len(seesaws) > max(1, len(all_opps) // 3):
                    soft.append(f'{len(seesaws)} of {len(all_opps)} opportunities on {line_id} trade one person against '
                                f'another in every option (one up, the other down): the player is asked "this one or '
                                f'that one" again and again, and cannot do right by both. At most a third may; most '
                                f'options move ONE person\'s state, at a cost in the world (time, a thing, a risk), and '
                                f'somewhere on the line there is a way to do right, or wrong, by both')
            if len(all_opps) >= 2:
                active = sum(1 for x in all_opps if any(o.get('active') for o in x.get('options') or []))
                if active == 0:
                    soft.append(f'no opportunity on {line_id} offers an active attempt (a physical try that can '
                                f'succeed, fail or be stopped); about one in three should')
                elif active > max(1, round(len(all_opps) * 2 / 3)):
                    soft.append(f'{active} of {len(all_opps)} opportunities on {line_id} offer active attempts; '
                                f'about one in three should')
            for a in self.plan.get('arcs') or []:
                st = a['state']['name']
                forks = [r for r in a.get('resolutions') or [] if line_id in r['lines'] and r['direction']]
                count = sum(1 for x in all_opps if moves_state(x, st))
                if forks and count < 2:
                    soft.append(f'{self.who(a["id"])}: how they end on {line_id} depends on {st}, which '
                                f'{count} opportunit{"y" if count == 1 else "ies"} on the line move; it needs at '
                                f'least two (an aggregate, never one choice)')
            for sh in self.plan.get('pattern_shifts') or []:
                if sh.get('at') not in path:
                    continue
                before = trial[:trial.index(sh['at'])]
                nodes_before = [got[t[1]] if isinstance(t, tuple) else self.minors.get(t) for t in before]
                count = sum(1 for x in nodes_before if x and x['kind'] == 'opportunity' and moves_state(x, sh['state']))
                if count < SHIFT_MIN_MOVES:
                    soft.append(f"the pattern shift on {sh['state']} at {sh['at']} needs at least {SHIFT_MIN_MOVES} "
                                f"opportunities moving {sh['state']} before {sh['at']} on {line_id}; there are {count}")
                owner = states.get(sh['state'], {}).get('who')
                warned = any(x and x['kind'] == 'demonstration' and (x.get('warns') == sh['state'] or owner in x['serves'])
                             for x in nodes_before)
                if not warned:
                    soft.append(f"the pattern shift on {sh['state']} at {sh['at']} needs a warning first: a "
                                f"demonstration before {sh['at']} where {self.who(owner)} visibly nears the edge "
                                f"(set its warns to {sh['state']})")
            if soft:
                raise SoftReject('; '.join(soft))
        return validate

    def trial_path(self, line_id, got):
        """A line's node sequence with the proposed minor nodes in: major ids,
        existing minor ids, and ('new', i) for proposed node i (any line through
        the node a proposed minor follows gets it too)."""
        out = []
        for nid in self.lines[line_id]['path']:
            out.append(nid)
            out.extend(self.after.get(nid, []))
            out.extend(('new', i) for i, x in enumerate(got) if x.get('after') == nid)
        return out

    def insert(self, line_id, got):
        """Graph surgery: ids (the major id plus a letter), order, tell targets."""
        made = []
        for x in got:
            group = self.after.setdefault(x['after'], [])
            mid = x['after'] + 'abcdefghijklmnopqrstuvwxyz'[len(group)]
            group.append(mid)
            x['id'] = mid
            x['lines'] = self.lines_through(x['after'])
            x['built_on'] = line_id
            for w in x['who']:
                if not self.resolve(w) and w not in self.new_functional:
                    self.new_functional.append(w)
            self.minors[mid] = x
            made.append(mid)
        for x in got:
            tell = x.get('tell') or {}
            at = tell.get('at')
            if isinstance(at, str) and re.fullmatch(r'm\d+', at) and int(at[1:]) <= len(made):
                tell['at'] = made[int(at[1:]) - 1]
        return made

    # ------------------------------------------------------------ composition

    def path_to(self, line_id, node_id):
        p = self.expanded_path(line_id)
        return p[:p.index(node_id)] if node_id in p else p

    def compose_shifts(self):
        """Each pattern shift's condition, computed from the opportunities on
        every line through its node; the strictest line decides."""
        out = []
        for sh in self.plan.get('pattern_shifts') or []:
            per_line, worst = {}, None
            for l in self.lines_through(sh['at']):
                opps = [option_split(self.minors[m], sh['state'], sh['direction'])
                        for m in self.path_to(l, sh['at']) if m in self.minors
                        and self.minors[m]['kind'] == 'opportunity' and moves_state(self.minors[m], sh['state'])]
                th = shift_threshold(opps)
                per_line[l] = {'opportunities': len(opps), 'threshold': th}
                if th is None:
                    worst = None
                    break
                if worst is None or (th['at_least'], th['share']) > (worst['at_least'], worst['share']):
                    worst = dict(th)
            entry = dict(sh, per_line=per_line, threshold=worst)
            if worst:
                entry['condition'] = {'state': sh['state'], 'direction': sh['direction'],
                                      'at_least': worst['at_least'], 'share': worst['share']}
                entry['when'] = expr(sh['state'], sh['direction'], worst['at_least'], worst['share'])
            out.append(entry)
        return out

    def compose_endings(self, shifts=()):
        """For each line's ending: per arc character, the variants of how they
        end, each with its condition (a state pattern, or always), in order;
        and how many combinations the player can produce. A resolution or
        ending pattern shift through the line comes first in its group."""
        out = {}
        states = self.states()
        for l in self.order:
            end_node = self.lines[l]['path'][-1]
            groups = []
            for a in self.plan.get('arcs') or []:
                res = [r for r in a.get('resolutions') or [] if l in r['lines']]
                if not res:
                    continue
                st = a['state']['name']
                opps = [self.minors[m] for m in self.expanded_path(l)
                        if m in self.minors and self.minors[m]['kind'] == 'opportunity' and moves_state(self.minors[m], st)]
                k = max(1, min(2, len(opps)))
                variants = []
                for r in sorted(res, key=lambda r: r['direction'] is None):
                    when = expr(st, r['direction'], k, RESOLUTION_SHARE) if r['direction'] else 'true'
                    variants.append({'when': when, 'text': r.get('becomes') or r.get('state') or ''})
                if variants[-1]['when'] != 'true':
                    variants[-1] = dict(variants[-1], when='true', note='fallback: the last variant holds otherwise')
                for sh in shifts:
                    if (sh.get('does') == 'resolution' and sh.get('when') and sh['state'] == st
                            and l in self.lines_through(sh['at'])):
                        same = next((r for r in res if r['direction'] == sh['direction']), None)
                        variants.insert(0, {'when': sh['when'], 'text': (same or {}).get('becomes') or sh.get('why') or '',
                                            'note': 'pattern shift'})
                groups.append({'about': a['id'], 'who': self.who(a['id']), 'variants': variants})
            for sh in shifts:
                if sh.get('does') == 'ending' and sh.get('when') and l in self.lines_through(sh['at']):
                    groups.insert(0, {'about': 'ending', 'who': 'the ending', 'variants': [
                        {'when': sh['when'], 'text': sh.get('why') or '', 'note': 'pattern shift'},
                        {'when': 'true', 'text': self.ending_of(l).get('summary') or ''}]})
            combos = 1
            for g in groups:
                combos *= len(g['variants'])
            out[l] = {'node': end_node, 'title': self.ending_of(l).get('title'), 'groups': groups, 'combinations': combos}
        return out

    def expanded_graph(self, shifts):
        """The outline's graph with minor nodes in and pattern-shift edges added,
        in the form generator/playtest.py reads (nodes with options and effects,
        edges with conditions)."""
        last = {n: (self.after.get(n) or [n])[-1] for n in self.nodes}
        nodes = {}
        for nid, n in self.nodes.items():
            nodes[nid] = {'title': n.get('title'), 'is_ending': n.get('is_ending'), 'major': True}
            group = self.after.get(nid, [])
            if group and n.get('is_ending'):
                nodes[nid]['is_ending'] = False
                nodes[group[-1]] = None          # filled below; the last resolution ends the line
        for mid, m in self.minors.items():
            nodes[mid] = {'title': m.get('title'), 'kind': m['kind'], 'major': False,
                          'is_ending': bool(self.nodes[m['after']].get('is_ending')) and self.after[m['after']][-1] == mid,
                          'options': [{'do': o.get('do'), 'effects': o.get('moves') or []} for o in m.get('options') or []]}
        edges = []
        for nid, group in self.after.items():
            chain = [nid] + group
            for a, b in zip(chain, chain[1:]):
                edges.append({'from': a, 'to': b, 'lines': self.lines_through(nid), 'kind': 'continue', 'trigger': None})
        for e in self.story.get('edges') or []:
            edges.append(dict(e, **{'from': last.get(e['from'], e['from'])}))
        for sh in shifts:
            if sh.get('does') == 'line' and sh.get('condition'):
                edges.append({'from': last[sh['at']], 'to': sh['to'], 'lines': [], 'kind': 'branch',
                              'trigger': {'kind': 'accumulated', 'text': f"pattern: {sh['state']} {sh['direction']}"},
                              'condition': sh['condition']})
        lines = {l: dict(self.lines[l], path=self.expanded_path(l)) for l in self.order}
        order = []
        for nid in self.story.get('node_order') or self.nodes:
            order.append(nid)
            order.extend(self.after.get(nid, []))
        return {'nodes': nodes, 'edges': edges, 'lines': lines, 'line_order': self.order, 'node_order': order}

    def reachable_combinations(self, line_id, endings, limit=20000):
        """Which of the composed ending's variant combinations some sequence of
        option choices along the line can reach: every combination of
        choices, the states counted as the engine would."""
        end = endings.get(line_id) or {}
        groups = end.get('groups') or []
        if not groups:
            return set(), set()
        opps = [self.minors[m] for m in self.expanded_path(line_id)
                if m in self.minors and self.minors[m]['kind'] == 'opportunity']
        choices = [o.get('options') or [{}] for o in opps]
        total = 1
        for c in choices:
            total *= len(c)
        if total > limit:
            return None, None
        from itertools import product
        possible = set(product(*[range(len(g['variants'])) for g in groups]))
        reached = set()
        for pick in product(*choices):
            arcs_ = {}
            for o in pick:
                for mv in o.get('moves') or []:
                    a = arcs_.setdefault(mv['state'], {'up': 0, 'down': 0})
                    a[mv['direction']] += 1
            combo = []
            for g in groups:
                for i, v in enumerate(g['variants']):
                    m = re.match(r"pattern\('(\w+)','(\w+)',(\d+),([\d.]+)\)", v.get('when') or '')
                    if not m:
                        combo.append(i)
                        break
                    st, d, k, share = m.group(1), m.group(2), int(m.group(3)), float(m.group(4))
                    a = arcs_.get(st, {'up': 0, 'down': 0})
                    if pattern_holds(a['up'], a['down'], d, k, share):
                        combo.append(i)
                        break
                else:
                    combo.append(None)
            reached.add(tuple(combo))
        return possible, reached

    def final_checks(self, shifts, endings):
        findings = []
        for l in self.order:
            possible, reached = self.reachable_combinations(l, endings)
            if possible is None:
                continue
            groups = (endings.get(l) or {}).get('groups') or []
            for combo in sorted(possible - reached):
                what = '; '.join(f"{g['who']}: {g['variants'][i]['when']}" for g, i in zip(groups, combo))
                findings.append(f'on {l} no sequence of choices reaches the ending combination ({what})')
        for sh in shifts:
            if not sh.get('threshold'):
                counts = {l: v['opportunities'] for l, v in sh['per_line'].items()}
                findings.append(f"pattern shift on {sh['state']} at {sh['at']} cannot be made clear: opportunities "
                                f"moving it per line {counts}; random play would trigger any reachable pattern "
                                f"{RANDOM_SHIFT_LIMIT:.0%} of the time or more")
        for l in self.order:
            path = self.expanded_path(l)
            opps = [self.minors[m] for m in path if m in self.minors and self.minors[m]['kind'] == 'opportunity']
            if not opps:
                findings.append(f'line {l} has no opportunities')
            for a in self.plan.get('arcs') or []:
                if l in self.char_lines(a['id']) and not any(
                        a['id'] in (self.minors[m].get('serves') or []) for m in path if m in self.minors):
                    findings.append(f'{self.who(a["id"])}: no minor node on {l} serves their arc')
            for m in path:
                x = self.minors.get(m)
                if x and x['kind'] == 'opportunity':
                    at = (x.get('tell') or {}).get('at')
                    if not tell_in_reach(path, path.index(m), path.index(at) if at in path else None,
                                         lambda t: t in self.nodes):
                        findings.append(f"{m}: its tell ({at}) does not land by the next major node on {l}")
        return findings

    # ------------------------------------------------------------ driver

    def run(self):
        self.a0_tiers()
        self.a1_plan()
        built = set()
        for n, l in enumerate(self.order, 1):
            self.a2_line(l, n)
            built.add(l)
        shifts = self.compose_shifts()
        endings = self.compose_endings(shifts)
        graph = self.expanded_graph(shifts)
        findings = self.final_checks(shifts, endings)
        st = playtest.Story(graph)
        plays = playtest.playthroughs(st)
        play_findings = playtest.check(st, plays)
        more, report = playtest.shift_checks(st)
        result = {
            'story_id': self.story.get('story_id'), 'stage': 'arcs',
            'tiers': self.tiers, 'plan': self.plan, 'states': self.states(),
            'minor_nodes': self.minors, 'new_functional': self.new_functional,
            'pattern_shifts': shifts, 'endings': endings, 'graph': graph,
            'checks': findings,
            'playtest': {'summary': playtest.summarize(st, plays), 'findings': play_findings + more,
                         'shift_report': {k: dict(v) if hasattr(v, 'items') else v for k, v in report.items()}},
        }
        return result


# ---------------------------------------------------------------- report

def arcs_markdown(result, story):
    nodes, chars = story['nodes'], story.get('characters') or {}
    minors = result['minor_nodes']

    def who(cid):
        c = chars.get(cid) or {}
        return c.get('name') or c.get('label') or cid

    out = [f"# {result['story_id']}: arcs and node expansion", '']
    plan = result['plan']
    out += [f"State visibility: **{plan.get('state_visibility')}**. {plan.get('visibility_note') or ''}", '',
            '## Cast tiers']
    for cid, t in result['tiers'].items():
        out.append(f"- {who(cid)} ({(chars.get(cid) or {}).get('label')}): **{t['tier']}**, {t['why']}")
    out += ['', '## Arcs']
    for a in plan.get('arcs') or []:
        st = a['state']
        out += [f"### {who(a['id'])}: `{st['name']}`", f"- meaning: {st.get('meaning')}",
                f"- up when: {st.get('up_when')}", f"- down when: {st.get('down_when')}", f"- starts: {a.get('starts')}"]
        for m in a.get('moments') or []:
            out.append(f"- {m['node']} ({m['kind']}): {m.get('change')}")
        for r in a.get('resolutions') or []:
            cond = f"if {st['name']} {r['direction']}" if r['direction'] else 'always'
            out.append(f"- ends on {', '.join(r['lines'])}, {cond}: {r.get('becomes')}")
        out.append('')
    if plan.get('light_arcs'):
        out.append('## Light arcs')
        for x in plan['light_arcs']:
            moments = '; '.join(f"{m.get('node')}: {m.get('change')}" for m in x.get('moments') or [])
            out.append(f"- {who(x.get('id')) if x.get('id') else x.get('who')}: starts {x.get('starts')}; {moments}; "
                       f"ends {x.get('ends')}")
        out.append('')
    prot = plan.get('protagonist') or {}
    if prot:
        out.append('## You, by line')
        for l, v in prot.items():
            out.append(f"- {l}: {v.get('arc') if isinstance(v, dict) else v}")
        out.append('')
    for l, line in result['graph']['lines'].items():
        out += [f"## Line {l}: {line.get('title')}", '']
        for nid in line['path']:
            if nid in nodes:
                out.append(f"**{nid} {nodes[nid].get('title')}** (major)")
                continue
            m = minors[nid]
            out.append(f"- **{nid} {m.get('title')}** [{m['kind']}; serves {', '.join(who(s) for s in m['serves'])}]: "
                       f"{m.get('summary')} *Image: {m.get('image')}*")
            for o in m.get('options') or []:
                moves = ', '.join(f"{mv['state']} {mv['direction']}" for mv in o.get('moves') or []) or 'no state'
                out.append(f"    - {'(active) ' if o.get('active') else ''}{o.get('do')} -> {o.get('effect')} "
                           f"[{moves}]")
            if m.get('tell'):
                out.append(f"    - tell at {m['tell'].get('at')}: {m['tell'].get('how')}")
        out.append('')
    if result['pattern_shifts']:
        out.append('## Pattern shifts')
        for sh in result['pattern_shifts']:
            th = sh.get('threshold')
            out.append(f"- {sh['state']} {sh['direction']} at {sh['at']} -> {sh['does']} {sh.get('to') or ''}: "
                       + (f"`{sh['when']}` (random play {th['random_rate']:.0%})" if th else 'NO CLEAR THRESHOLD')
                       + f". {sh.get('why') or ''}")
        out.append('')
    out.append('## Endings, composed')
    for l, e in result['endings'].items():
        out.append(f"- {l} {e['node']} {e.get('title')}: {e['combinations']} combination(s)")
        for g in e['groups']:
            for v in g['variants']:
                out.append(f"    - {g['who']} `{v['when']}`: {v['text']}")
    out += ['', '## Checks']
    out += [f'- {f}' for f in result['checks'] + result['playtest']['findings']] or ['- none']
    s = result['playtest']['summary']
    out += ['', f"Playtest: {s['playthroughs']} playthrough(s) from {s['start']}; endings "
            + ', '.join(f"{e} ({v['ways']} ways)" for e, v in s['endings'].items())]
    if result['new_functional']:
        out.append(f"New functional characters named in minor nodes: {', '.join(result['new_functional'])}")
    return '\n'.join(out) + '\n'


def main(argv=None):
    """Run stage A alone on a finished outline directory, without replaying
    (and re-validating) the steps before it: for outlines made by older code.

        python arcs.py kernel35_f5            # stories/kernel35_f5/kernel35_f5_story.json
    """
    from main import StoryGenerator
    from errors import PipelineHalt
    ap = argparse.ArgumentParser(description=main.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('story_id')
    args = ap.parse_args(argv)
    gen = StoryGenerator(story_id=args.story_id)
    path = gen.story_file_path('story.json')
    if not os.path.isfile(path):
        print(f'no outline at {path}', file=sys.stderr)
        return 1
    with open(path, encoding='utf-8') as f:
        story = json.load(f)
    gen.kernel = story.get('kernel') or ''
    for key, suffix in (('s3_brief', 's3_brief.json'), ('s3_4_promises', 's3_4_promises.json')):
        p = gen.story_file_path(suffix)
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as f:
                gen.analysis[key] = json.load(f)
    try:
        gen.run_arcs(story)
    except PipelineHalt as halt:
        print(f'\nPIPELINE HALTED: {halt}', file=sys.stderr)
        return 2
    finally:
        for line in gen.stats.summary_lines():
            print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())

