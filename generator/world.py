"""Stage B: the world (docs/later_stages.md §3).

Builds what the engine's world needs, from the outline, stage A (arcs and
minor nodes) and B0 (scenes, subjects, the room target):

    B1   characters: one call per arc or supporting character (curated topics,
         description and presence by state, a history for arc characters),
         one batch call for the functional ones.
    B2   places: one call per location (rooms with permanent base text,
         exits inside the location, objects: what the moments need plus
         examinable things), then one map call (which locations adjoin, and
         the connective places between them).
    B1c  conversation: one call per character over every subject (people,
         places, events, notable objects): what they would say about it, in
         their voice, by state for arc characters.
    B3   you: self-description, what you carry, THINK topics.

The model writes content; Python assigns ids, compiles state-keyed text to
engine conditions, and checks. Conventions shared with stage D:
  - every node sets the flag `done_<node id>` when it plays (D sets it), so
    "known after N04a" compiles to `flags.done_N04a`;
  - a variant is {state, direction, after, text}: state+direction compile to
    a pattern (moved at least once, mostly that way), after to the done
    flag, both to their conjunction; a variant with neither holds always and
    goes last;
  - talk about an encountered person or object is gated by `seen(id)`, about
    a place by `visited` of one of its rooms, about an event by the done flag
    of the node where it lands.
Output: <id>_world.json (engine-ready rooms, objects, characters with
topics, the protagonist block) and <id>_world.md.
"""

import argparse
import json
import os
import re
import sys

import checks
import example_guard
import schemas
from errors import SoftReject

norm = checks.norm

VARIANT_SHARE = 0.6
EXAMINABLE_PER_ROOM = (4, 8)
ID_RE = re.compile(r'[^a-z0-9]+')


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


def slug(text, taken=()):
    base = ID_RE.sub('_', norm(text)).strip('_')[:32] or 'thing'
    sid, n = base, 2
    while sid in taken:
        sid, n = f'{base}_{n}', n + 1
    return sid


# ---------------------------------------------------------------- variants

def compile_variants(variants, states, nodes, problems, where):
    """[{state, direction, after, text}] -> engine text variants, conditional
    ones first, the unconditional last. Unknown states or nodes are
    problems."""
    out, always = [], []
    for v in as_list(variants):
        if not isinstance(v, dict) or not str(v.get('text') or '').strip():
            continue
        parts = []
        st, d, after = v.get('state'), v.get('direction'), v.get('after')
        if st not in (None, '', 'null'):
            st = str(st).strip().lower()
            d = str(d or '').strip().lower()
            if st not in states:
                problems.append(f'{where}: state {st!r} is not one of {sorted(states)}')
                continue
            if d not in ('up', 'down'):
                problems.append(f'{where}: a variant on {st} needs direction up or down')
                continue
            parts.append(f"pattern('{st}','{d}',1,{VARIANT_SHARE})")
        if after not in (None, '', 'null'):
            if after not in nodes:
                problems.append(f'{where}: after {after!r} is not a node of the story')
                continue
            parts.append(f'flags.done_{after}')
        entry = {'text': str(v['text']).strip()}
        if parts:
            entry['when'] = ' and '.join(parts)
            out.append(entry)
        else:
            always.append(entry)
    return out + always[:1]


def done_flags(world):
    """Every done_<node> flag the world reads (stage D must set them)."""
    found = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ('when', 'known_when') and isinstance(v, str):
                    found.update(re.findall(r'flags\.(done_\w+)', v))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(world)
    return sorted(found)


# ---------------------------------------------------------------- the stage

class WorldBuilder:
    def __init__(self, gen, story, arcs, plan):
        self.gen = gen
        self.story = story
        self.arcs = arcs or {}
        self.plan = plan
        self.chars = story.get('characters') or {}
        self.locations = story.get('locations') or {}
        self.premise = story.get('premise') or {}
        self.nodes = dict(story.get('nodes') or {})
        self.nodes.update(self.arcs.get('minor_nodes') or {})
        self.states = set((self.arcs.get('states') or {}).keys())
        self.tiers = {cid: t.get('tier') for cid, t in (self.arcs.get('tiers') or {}).items()}
        self.world = {'rooms': {}, 'objects': {}, 'characters': {}}
        self.protagonist = {}
        self.location_rooms = {}        # location id -> [room ids]

    # ------------------------------------------------------------ packets

    def who(self, cid):
        c = self.chars.get(cid) or {}
        return f"{c['name']} ({c.get('label')})" if c.get('name') else str(c.get('label') or cid)

    def scenes_with(self, cid=None, location=None):
        out = []
        for sc in self.plan['scenes']:
            if (cid and cid in sc['who']) or (location and location in sc['where']):
                out.append({'scene': sc['id'], 'title': sc['title'], 'lines': sc['lines'],
                            'nodes': [{'id': n, 'kind': (self.nodes[n].get('kind') or 'major'),
                                       'summary': self.nodes[n].get('summary')} for n in sc['nodes']]})
        return out

    def arc_of(self, cid):
        plan = self.arcs.get('plan') or {}
        for a in plan.get('arcs') or []:
            if a.get('id') == cid:
                return {'state': a.get('state'), 'starts': a.get('starts'), 'moments': a.get('moments'),
                        'resolutions': a.get('resolutions')}
        for a in plan.get('light_arcs') or []:
            if a.get('id') == cid:
                return {'starts': a.get('starts'), 'moments': a.get('moments'), 'ends': a.get('ends')}
        return None

    def knows_truth(self, cid):
        truth = self.premise.get('hidden_truth') or {}
        if not isinstance(truth, dict) or not truth.get('truth'):
            return False
        c = self.chars.get(cid) or {}
        knowers = norm(truth.get('who_knows'))
        return any(k and k in knowers for k in (norm(c.get('label')), norm(c.get('name'))))

    def character_packet(self, cid):
        c = self.chars[cid]
        packet = {'who': self.who(cid), 'tier': self.tiers.get(cid) or 'supporting',
                  'sketch': {k: c.get(k) for k in ('wants', 'holds', 'edge', 'tie', 'voice', 'breaking_point') if c.get(k)},
                  'arc': self.arc_of(cid), 'states': sorted(self.states), 'scenes': self.scenes_with(cid=cid)}
        if self.knows_truth(cid):
            packet['hidden_truth'] = self.premise['hidden_truth']
        return packet

    # ------------------------------------------------------------ B1

    def b1_character(self, cid):
        packet = self.character_packet(cid)
        answer = self.gen.run_prompt(f's6b1_{cid}', 'character', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s6b1_character.prompt', validator=self.b1_validator(cid), klass='build',
            schema=schemas.WORLD_CHARACTER)
        self.add_character(cid, answer)

    def b1_validator(self, cid):
        def validate(parsed):
            problems, soft = [], []
            topics = [t for t in as_list(parsed.get('topics')) if isinstance(t, dict) and t.get('label')]
            want = (3, 8) if self.tiers.get(cid) == 'arc' else (2, 5)
            if not want[0] <= len(topics) <= want[1]:
                problems.append(f'{len(topics)} topics; give {want[0]} to {want[1]}')
            for t in topics:
                compile_variants(t.get('says'), self.states, self.nodes, problems, f"topic {t['label']!r}")
                if t.get('known_after') not in (None, '', 'null') and t['known_after'] not in self.nodes:
                    problems.append(f"topic {t['label']!r}: known_after {t['known_after']!r} is not a node")
                if not as_list(t.get('says')):
                    problems.append(f"topic {t['label']!r} says nothing")
            for key in ('description', 'here'):
                if not compile_variants(parsed.get(key), self.states, self.nodes, problems, key):
                    problems.append(f'{key} needs at least one variant')
            if self.tiers.get(cid) == 'arc' and not str(parsed.get('history') or '').strip():
                problems.append('an arc character needs a history')
            if problems:
                raise ValueError('; '.join(problems))
            if not self.knows_truth(cid):
                truth = (self.premise.get('hidden_truth') or {}).get('truth') if isinstance(self.premise.get('hidden_truth'), dict) else None
                if truth:
                    leaked = example_guard.ngrams(truth) & example_guard.ngrams(json.dumps(topics))
                    if len(leaked) >= 2:
                        soft.append(f'{self.who(cid)} does not know the hidden truth, but their topics say it '
                                    f'({len(leaked)} of its phrases); they may suspect, never state')
            if self.states and self.tiers.get(cid) == 'arc':
                own = (self.arc_of(cid) or {}).get('state') or {}
                if own.get('name') and own['name'] not in json.dumps(parsed):
                    soft.append(f"nothing varies with {own['name']}, this person's own arc state: let at least the "
                                f"description or a topic change as it moves")
            if soft:
                raise SoftReject('; '.join(soft))
        return validate

    def add_character(self, cid, answer):
        problems = []
        topics = {}
        for t in as_list(answer.get('topics')):
            if not isinstance(t, dict) or not t.get('label'):
                continue
            tid = slug(t['label'], topics)
            topic = {'label': t['label'], 'says': compile_variants(t.get('says'), self.states, self.nodes, problems, tid)}
            if t.get('known_after') not in (None, '', 'null'):
                topic['known_when'] = f"flags.done_{t['known_after']}"
            moves = [m for m in as_list(t.get('moves')) if isinstance(m, dict) and m.get('state') in self.states]
            if moves:
                topic['effects'] = [{'move': m['state'], 'dir': m.get('direction', 'up')} for m in moves]
                topic['once'] = True
            topics[tid] = topic
        c = self.chars[cid]
        self.world['characters'][cid] = {
            'name': c.get('name') or c.get('label'), 'role': c.get('label'), 'gender': c.get('gender'),
            'arc_tier': self.tiers.get(cid),
            'description': compile_variants(answer.get('description'), self.states, self.nodes, problems, 'description'),
            'here': compile_variants(answer.get('here'), self.states, self.nodes, problems, 'here'),
            'topics': topics, 'history': answer.get('history')}

    def b1_functional(self, cids):
        if not cids:
            return
        packet = [{'who': self.who(c), 'sketch': {k: self.chars[c].get(k) for k in ('wants', 'holds', 'voice') if self.chars[c].get(k)},
                   'scenes': [s['title'] for s in self.scenes_with(cid=c)]} for c in cids]

        def validate(parsed):
            got = {self.resolve(x.get('who')): x for x in as_list(parsed.get('people')) if isinstance(x, dict)}
            missing = [self.who(c) for c in cids if c not in got]
            if missing:
                raise ValueError(f'no entry for {missing}')
        answer = self.gen.run_prompt('s6b1_functional', 'functional', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PEOPLE_JSON$$': compact(packet),
        }, prompt_file='s6b1f_functional.prompt', validator=validate, klass='classify', schema=schemas.WORLD_FUNCTIONAL)
        for x in as_list(answer.get('people')):
            cid = self.resolve(x.get('who'))
            if cid:
                self.add_character(cid, {'description': [{'text': x.get('description')}], 'here': [{'text': x.get('here')}],
                                         'topics': [{'label': t.get('label'), 'says': [{'text': t.get('says')}]}
                                                    for t in as_list(x.get('topics')) if isinstance(t, dict)]})

    def resolve(self, name):
        key = norm(re.sub(r'\(.*?\)', '', str(name or '')))
        for cid, c in self.chars.items():
            if key in (norm(c.get('name')), norm(c.get('label'))) or key == cid.lower():
                return cid
        for cid, c in self.chars.items():
            if c.get('name') and norm(c['name']) in norm(name):
                return cid
        return None

    # ------------------------------------------------------------ B2

    def room_budget(self, lid):
        """Rooms for one location: the target spread by how many scenes use it."""
        uses = {l: sum(1 for sc in self.plan['scenes'] if l in sc['where']) for l in self.locations}
        total = sum(uses.values()) or 1
        target = (self.plan['rooms']['min'] + self.plan['rooms']['max']) // 2
        share = max(1, round(target * uses.get(lid, 0) / total))
        return max(1, min(4, share))

    def b2_place(self, lid):
        loc = self.locations[lid]
        others = [l.get('name') for k, l in self.locations.items() if k != lid and l.get('name')]
        built = [r['name'] for r in self.world['rooms'].values()]
        packet = {'location': {'name': loc.get('name'), 'kind': loc.get('kind'), 'why': loc.get('why')},
                  'rooms_wanted': self.room_budget(lid), 'other_locations': others, 'rooms_already_built': built,
                  'scenes': self.scenes_with(location=lid),
                  'people_here': sorted({self.who(c) for sc in self.plan['scenes'] if lid in sc['where']
                                         for c in sc['who'] if c in self.chars})}
        answer = self.gen.run_prompt(f's6b2_{lid}', 'place', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s6b2_place.prompt', validator=self.b2_validator(others + built), klass='build', schema=schemas.WORLD_PLACE)
        self.add_place(lid, answer)

    def b2_validator(self, elsewhere=()):
        elsewhere = {norm(n) for n in elsewhere}

        def validate(parsed):
            problems, soft = [], []
            rooms = [r for r in as_list(parsed.get('rooms')) if isinstance(r, dict) and r.get('name')]
            if not 1 <= len(rooms) <= 4:
                problems.append(f'{len(rooms)} rooms; a location is one to four rooms')
            names = [norm(r['name']) for r in rooms]
            if len(set(names)) != len(names):
                problems.append('two rooms share a name')
            clash = [r['name'] for r in rooms if norm(r['name']) in elsewhere]
            if clash:
                problems.append(f'rooms {clash} are another location or a room already built; build only this '
                                f'location, and if it is one room-sized space, make it one room')
            for r in rooms:
                if len(str(r.get('description') or '').split()) < 15:
                    problems.append(f"room {r['name']!r}: the description is too thin; give it specific details")
            things = [o for o in as_list(parsed.get('objects')) if isinstance(o, dict) and o.get('name')]
            for o in things:
                if norm(o.get('room')) not in names:
                    problems.append(f"object {o['name']!r}: room {o.get('room')!r} is not one of this location's rooms")
                if not str(o.get('description') or '').strip():
                    problems.append(f"object {o['name']!r} has nothing to say when examined")
            for e in as_list(parsed.get('exits')):
                if norm(e.get('from')) not in names or norm(e.get('to')) not in names:
                    problems.append(f"exit {e.get('from')!r} -> {e.get('to')!r} names a room this location does not have")
            if problems:
                raise ValueError('; '.join(problems))
            for r in rooms:
                n = sum(1 for o in things if norm(o.get('room')) == norm(r['name']))
                if not EXAMINABLE_PER_ROOM[0] <= n <= EXAMINABLE_PER_ROOM[1]:
                    soft.append(f"room {r['name']!r} has {n} examinable things; give {EXAMINABLE_PER_ROOM[0]} to "
                                f"{EXAMINABLE_PER_ROOM[1]}, two or three that matter to the story and the rest saying "
                                f"something about a person or the place's history")
            if len(rooms) > 1:
                linked = {norm(e.get('from')) for e in as_list(parsed.get('exits'))} | {norm(e.get('to')) for e in as_list(parsed.get('exits'))}
                lonely = [r['name'] for r in rooms if norm(r['name']) not in linked]
                if lonely:
                    soft.append(f'rooms with no exit inside the location: {lonely}')
            if soft:
                raise SoftReject('; '.join(soft))
        return validate

    def add_place(self, lid, answer, location_name=None):
        taken = set(self.world['rooms']) | set(self.world['objects']) | set(self.chars)
        by_name = {}
        existing = {norm(v['name']): k for k, v in self.world['rooms'].items()}
        for r in as_list(answer.get('rooms')):
            if not isinstance(r, dict) or not r.get('name'):
                continue
            if norm(r['name']) in existing:  # never two rooms with one name: its things go to the one built
                by_name[norm(r['name'])] = existing[norm(r['name'])]
                continue
            rid = slug(r['name'], taken)
            taken.add(rid)
            by_name[norm(r['name'])] = rid
            self.world['rooms'][rid] = {'name': r['name'], 'location': lid, 'description': [{'text': r.get('description')}],
                                        'exits': []}
        for e in as_list(answer.get('exits')):
            a, b = by_name.get(norm(e.get('from'))), by_name.get(norm(e.get('to')))
            if a and b:
                self.link(a, b, e.get('label'), e.get('back_label'))
        for o in as_list(answer.get('objects')):
            if not isinstance(o, dict) or not o.get('name'):
                continue
            oid = slug(o['name'], taken)
            taken.add(oid)
            self.world['objects'][oid] = {
                'name': o['name'], 'location': by_name.get(norm(o.get('room'))), 'portable': bool(o.get('portable')),
                'listed': bool(o.get('portable')), 'description': [{'text': o.get('description')}],
                'story': bool(o.get('story'))}
        self.location_rooms[lid] = list(dict.fromkeys(by_name.values()))

    def link(self, a, b, label=None, back=None):
        rooms = self.world['rooms']
        if not any(x['to'] == b for x in rooms[a]['exits']):
            rooms[a]['exits'].append({'to': b, 'label': label or f"to {rooms[b]['name']}"})
        if not any(x['to'] == a for x in rooms[b]['exits']):
            rooms[b]['exits'].append({'to': a, 'label': back or f"to {rooms[a]['name']}"})

    def b2_map(self):
        """Which locations adjoin, and the connective places between them."""
        packet = {'locations': [{'name': self.locations[l].get('name'), 'kind': self.locations[l].get('kind'),
                                 'rooms': [self.world['rooms'][r]['name'] for r in self.location_rooms.get(l, [])]}
                                for l in self.locations],
                  'scene_order': [[self.locations[l].get('name') for l in sc['where'] if l in self.locations]
                                  for sc in self.plan['scenes']],
                  'rooms_target': self.plan['rooms'], 'rooms_so_far': len(self.world['rooms'])}
        room_names = {norm(r['name']): rid for rid, r in self.world['rooms'].items()}

        def validate(parsed):
            problems = []
            for a in as_list(parsed.get('adjacent')):
                for k in ('from_room', 'to_room'):
                    if norm(a.get(k)) not in room_names and not any(
                            norm(a.get(k)) == norm(c.get('name')) for c in as_list(parsed.get('connective'))):
                        problems.append(f"adjacent: {k} {a.get(k)!r} is neither a room nor a connective place")
            for c in as_list(parsed.get('connective')):
                if len(str(c.get('description') or '').split()) < 15 or not as_list(c.get('examinable')):
                    problems.append(f"connective place {c.get('name')!r} is a skeleton: give it specific details and "
                                    f"something worth examining that contributes to the story's feel")
            if problems:
                raise ValueError('; '.join(problems))
        answer = self.gen.run_prompt('s6b2_map', 'map', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s6b2m_map.prompt', validator=validate, klass='build', schema=schemas.WORLD_MAP)
        for c in as_list(answer.get('connective')):
            self.add_place(None, {'rooms': [{'name': c['name'], 'description': c.get('description')}],
                                  'objects': [{'name': x.get('name'), 'room': c['name'], 'description': x.get('description')}
                                              for x in as_list(c.get('examinable')) if isinstance(x, dict)]})
        room_names = {norm(r['name']): rid for rid, r in self.world['rooms'].items()}
        for a in as_list(answer.get('adjacent')):
            x, y = room_names.get(norm(a.get('from_room'))), room_names.get(norm(a.get('to_room')))
            if x and y and x != y:
                self.link(x, y, a.get('label'), a.get('back_label'))

    # ------------------------------------------------------------ B1c

    def subject_list(self):
        out = []
        for s in self.plan['subjects']:
            if s['kind'] == 'person' and s.get('id') in self.world['characters']:
                out.append({'subject': s['name'], 'kind': 'person', 'gate': f"seen('{s['id']}')"})
            elif s['kind'] == 'place' and self.location_rooms.get(s.get('id')):
                rooms = self.location_rooms[s['id']]
                out.append({'subject': s['name'], 'kind': 'place',
                            'gate': ' or '.join(f"visited('{r}')" for r in rooms)})
            elif s['kind'] == 'event':
                node = next((sc['major'] for sc in self.plan['scenes'] if sc['id'] == s.get('first_scene')), None)
                if node:
                    out.append({'subject': s['name'], 'kind': 'event', 'gate': f'flags.done_{node}'})
        for oid, o in self.world['objects'].items():
            if o.get('story'):
                out.append({'subject': o['name'], 'kind': 'object', 'gate': f"seen('{oid}')"})
        return out

    def b1c_conversation(self, cid):
        subjects = [s for s in self.subject_list() if s['subject'] not in (self.world['characters'][cid]['name'],)]
        packet = {'who': self.who(cid), 'voice': self.chars[cid].get('voice'), 'tie': self.chars[cid].get('tie'),
                  'tier': self.tiers.get(cid), 'arc': self.arc_of(cid), 'states': sorted(self.states),
                  'already_topics': [t['label'] for t in self.world['characters'][cid]['topics'].values()],
                  'subjects': [{'subject': s['subject'], 'kind': s['kind']} for s in subjects]}
        names = {norm(s['subject']): s for s in subjects}

        def validate(parsed):
            problems = []
            lines = [x for x in as_list(parsed.get('lines')) if isinstance(x, dict)]
            for x in lines:
                if norm(x.get('subject')) not in names:
                    problems.append(f"subject {x.get('subject')!r} is not in the list")
                compile_variants(x.get('says'), self.states, self.nodes, problems, f"subject {x.get('subject')!r}")
            if len(lines) < max(1, len(subjects) // 2):
                problems.append(f'{len(lines)} subjects answered of {len(subjects)}; say something about most of them '
                                f'(a person who would not know says so, in character)')
            if problems:
                raise ValueError('; '.join(problems))
        answer = self.gen.run_prompt(f's6b1c_{cid}', 'conversation', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s6b1c_conversation.prompt', validator=validate, klass='build', schema=schemas.WORLD_CONVERSATION)
        topics = self.world['characters'][cid]['topics']
        for x in as_list(answer.get('lines')):
            s = names.get(norm(x.get('subject')))
            if not s:
                continue
            tid = slug('about ' + s['subject'], topics)
            topics[tid] = {'label': s['subject'], 'known_when': s['gate'],
                           'says': compile_variants(x.get('says'), self.states, self.nodes, [], tid)}

    # ------------------------------------------------------------ B3

    def b3_you(self):
        prot = self.premise.get('protagonist') or {}
        plan = self.arcs.get('plan') or {}
        packet = {'you': {k: prot.get(k) for k in ('name', 'who', 'history', 'wants', 'need', 'ties', 'open', 'gender') if prot.get(k)},
                  'your_arc_by_line': plan.get('protagonist'), 'states': sorted(self.states),
                  'lines': [{'id': l, 'title': self.story['lines'][l].get('title'), 'path': self.story['lines'][l].get('path')}
                            for l in self.story.get('line_order') or []]}

        def validate(parsed):
            problems = []
            if not compile_variants(parsed.get('description'), self.states, self.nodes, problems, 'description'):
                problems.append('description needs at least one variant')
            thinks = [t for t in as_list(parsed.get('think')) if isinstance(t, dict) and t.get('label')]
            if len(thinks) < 3:
                problems.append(f'{len(thinks)} think topics; give at least three (your history, a tie, your need)')
            for t in thinks:
                compile_variants(t.get('says'), self.states, self.nodes, problems, f"think {t['label']!r}")
                if t.get('known_after') not in (None, '', 'null') and t['known_after'] not in self.nodes:
                    problems.append(f"think {t['label']!r}: known_after is not a node")
            if problems:
                raise ValueError('; '.join(problems))
        answer = self.gen.run_prompt('s6b3', 'you', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s6b3_you.prompt', validator=validate, klass='build', schema=schemas.WORLD_YOU)
        problems = []
        think = {}
        for t in as_list(answer.get('think')):
            if isinstance(t, dict) and t.get('label'):
                tid = slug(t['label'], think)
                think[tid] = {'label': t['label'], 'says': compile_variants(t.get('says'), self.states, self.nodes, problems, tid)}
                if t.get('known_after') not in (None, '', 'null'):
                    think[tid]['known_when'] = f"flags.done_{t['known_after']}"
        self.protagonist = {'name': prot.get('name'), 'pronoun': 'you', 'gender': prot.get('gender'),
                            'description': compile_variants(answer.get('description'), self.states, self.nodes, problems, 'you'),
                            'think': think}
        taken = set(self.world['objects']) | set(self.world['rooms']) | set(self.chars)
        for o in as_list(answer.get('carrying')):
            if isinstance(o, dict) and o.get('name'):
                oid = slug(o['name'], taken)
                taken.add(oid)
                self.world['objects'][oid] = {'name': o['name'], 'location': 'player', 'portable': True, 'listed': True,
                                              'description': [{'text': o.get('description')}], 'story': True}

    # ------------------------------------------------------------ driver

    def checks(self):
        findings = []
        rooms = self.world['rooms']
        if rooms:
            start = next(iter(rooms))
            seen, todo = set(), [start]
            while todo:
                r = todo.pop()
                if r in seen:
                    continue
                seen.add(r)
                todo += [e['to'] for e in rooms[r]['exits']]
            lost = [rooms[r]['name'] for r in rooms if r not in seen]
            if lost:
                findings.append(f'rooms no exit reaches: {lost}')
        target = self.plan['rooms']
        if not target['min'] <= len(rooms) <= target['max']:
            findings.append(f"{len(rooms)} rooms against a target of {target['min']}-{target['max']}")
        for cid in self.chars:
            if self.chars[cid].get('kind') != 'crowd' and cid not in self.world['characters']:
                findings.append(f'{self.who(cid)} was not built')
        return findings

    def run(self):
        people = [c for c, ch in self.chars.items() if ch.get('kind') != 'crowd']
        major = [c for c in people if self.tiers.get(c) in ('arc', 'supporting')]
        for cid in major:
            self.b1_character(cid)
        self.b1_functional([c for c in people if c not in major])
        for lid in self.locations:
            self.b2_place(lid)
        self.b2_map()
        for cid in self.world['characters']:
            self.b1c_conversation(cid)
        self.b3_you()
        return {'story_id': self.story.get('story_id'), 'stage': 'world', 'world': self.world,
                'protagonist': self.protagonist, 'done_flags': done_flags({'w': self.world, 'p': self.protagonist}),
                'location_rooms': self.location_rooms, 'checks': self.checks()}


def world_markdown(result):
    w = result['world']
    out = [f"# {result['story_id']}: the world", '', f"{len(w['rooms'])} rooms, {len(w['objects'])} objects, "
           f"{len(w['characters'])} people. Checks: {'; '.join(result['checks']) or 'none'}", '', '## Rooms']
    for rid, r in w['rooms'].items():
        out.append(f"### {r['name']} ({rid})")
        out.append(r['description'][0]['text'] if r['description'] else '')
        out.append('Exits: ' + ', '.join(f"{e['label']} -> {e['to']}" for e in r['exits']))
        things = [o for o in w['objects'].values() if o.get('location') == rid]
        for o in things:
            out.append(f"- {'**' if o.get('story') else ''}{o['name']}{'**' if o.get('story') else ''}: {o['description'][0]['text']}")
        out.append('')
    out.append('## People')
    for cid, c in w['characters'].items():
        out.append(f"### {c['name']} ({c.get('role')}, {c.get('arc_tier')})")
        if c.get('history'):
            out.append(f"History: {c['history']}")
        for v in c['description']:
            out.append(f"- looks{' [' + v['when'] + ']' if v.get('when') else ''}: {v['text']}")
        for tid, t in c['topics'].items():
            gate = f" (when {t['known_when']})" if t.get('known_when') else ''
            out.append(f"- about **{t['label']}**{gate}: " + ' / '.join(
                (f"[{v['when']}] " if v.get('when') else '') + v['text'] for v in t['says']))
        out.append('')
    p = result['protagonist']
    out.append('## You')
    for v in p.get('description') or []:
        out.append(f"- {('[' + v['when'] + '] ') if v.get('when') else ''}{v['text']}")
    for tid, t in (p.get('think') or {}).items():
        out.append(f"- think about **{t['label']}**: " + ' / '.join(v['text'] for v in t['says']))
    return '\n'.join(out) + '\n'


def main(argv=None):
    """python world.py <story_id>: stage B on a directory with the outline,
    stage A (<id>_arcs.json) and B0 (<id>_scenes.json, made here if missing)."""
    from main import StoryGenerator
    import scenes
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument('story_id')
    args = ap.parse_args(argv)
    gen = StoryGenerator(story_id=args.story_id)
    base = gen.story_file_path('')
    load = lambda suffix: json.load(open(base + suffix, encoding='utf-8')) if os.path.isfile(base + suffix) else None
    story, arcs = load('story.json'), load('arcs.json')
    if not story or not arcs:
        print('stage B needs <id>_story.json and <id>_arcs.json', file=sys.stderr)
        return 1
    gen.kernel = story.get('kernel') or ''
    for key, suffix in (('s3_brief', 's3_brief.json'), ('s3_4_promises', 's3_4_promises.json')):
        if load(suffix) is not None:
            gen.analysis[key] = load(suffix)
    plan = load('scenes.json') or scenes.plan(story, arcs, gen.analysis.get('s3_brief'), gen.analysis.get('s3_4_promises'))
    result = WorldBuilder(gen, story, arcs, plan).run()
    gen.save_story_json('world.json', result)
    gen.save_story_file('world.md', world_markdown(result))
    print(f"stage B: {len(result['world']['rooms'])} rooms, {len(result['world']['objects'])} objects, "
          f"{len(result['world']['characters'])} people; findings: {result['checks'] or 'none'}")
    for line in gen.stats.summary_lines():
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
