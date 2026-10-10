"""Stages C and D: reconcile, then compile each scene for the engine
(docs/later_stages.md §4-§5).

Inputs: the outline, stage A (<id>_arcs.json: minor nodes, states, pattern
shifts, composed endings), B0 (<id>_scenes.json) and stage B
(<id>_world.json). One model call per scene (s7d_scene) writes the scene by
NAME: its opening, where people stand, each room's text in this scene, its
moments (one engine action per opportunity option, in stage A's order),
revelations and incidental actions, the action that takes each outgoing edge,
events and nudges, and any small props. Python owns everything mechanical:

  - effects: an option's state moves are stage A's, copied by position; the
    model never writes them;
  - which moments are required (a state that feeds an ending variant or a
    pattern shift) and that a required moment offers a neutral option;
  - the done flags stage B reads: entering a scene sets `done_<major>`,
    answering a moment or taking a revelation sets `done_<minor>`, and any
    done flag still unset is set on entering the scene that holds its node;
  - exits: pattern shifts first, then branch triggers, then the default edge,
    each a flag the leading action sets (`go_<scene>__<target>`);
  - ids, story verbs, the package, and the checks: stage C before compiling
    (every scene's rooms joined among themselves), every name resolving
    while compiling (a hard retry), and after assembly the engine's
    validator and the playtest simulator.
Output: <id>_package.json (stratum-story/1, playable with engine/cli.py) and
<id>_package.md (the report: findings and walkthroughs).
"""

import argparse
import io
import json
import os
import re
import sys

import checks
import schemas
from errors import SoftReject
import example_guard
from world import compile_variants, slug, as_list, compact

norm = checks.norm
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(THIS_DIR, '..', 'engine')
CORE_VERBS = ('look', 'examine', 'go', 'talk', 'take', 'give', 'show', 'use', 'think', 'wait', 'inventory')
LAPSE_AFTER = 4
WAY_THING = re.compile(r"\b(door|doors|gate|lane|path|road|track|trail|towpath|ladder|steps|stairs|gangway|hatch|"
                       r"bridge|street)\b", re.I)       # kernel40 left scenes by "Use › the school lane", "Take › the door"
ENGINE_VERBS = ('look', 'examine', 'wait', 'inventory', 'think')     # the engine makes these; a scene's own is a misuse


class SceneCompiler:
    def __init__(self, gen, story, arcs, plan, world):
        self.gen = gen
        self.story = story
        self.arcs = arcs
        self.plan = plan
        self.world = world['world']
        self.protagonist = world['protagonist']
        self.location_rooms = world.get('location_rooms') or {}
        self.nodes = dict(story['nodes'])
        self.minors = arcs.get('minor_nodes') or {}
        self.nodes.update(self.minors)
        self.states = set((arcs.get('states') or {}).keys())
        self.scenes = {sc['id']: sc for sc in plan['scenes']}
        self.scene_of = {n: sc['id'] for sc in plan['scenes'] for n in sc['nodes']}
        self.compiled = {}
        self.verbs = set()
        self.findings = []

    # ------------------------------------------------------------ lookups

    def names(self):
        """Every nameable thing: rooms, objects, characters, by normalized name."""
        out = {}
        for table in ('characters', 'rooms', 'objects'):
            for xid, x in self.world[table].items():
                out.setdefault(norm(x.get('name')), xid)
                if table == 'characters' and x.get('role'):
                    out.setdefault(norm(x['role']), xid)
                    first = norm(x.get('name')).split(' ')[0] if x.get('name') else None
                    if first:
                        out.setdefault(first, xid)
        return out

    def people(self):
        """Characters by name, role and first name: a placement means a person,
        whatever thing shares the name."""
        out = {}
        for cid, x in self.world['characters'].items():
            for key in (x.get('name'), x.get('role'), (x.get('name') or '').split(' ')[0]):
                if norm(key):
                    out.setdefault(norm(key), cid)
        return out

    def required_states(self):
        """States some ending variant or pattern shift reads."""
        found = set()
        for end in (self.arcs.get('endings') or {}).values():
            for g in end.get('groups') or []:
                for v in g.get('variants') or []:
                    found.update(re.findall(r"pattern\('(\w+)'", v.get('when') or ''))
        for sh in self.arcs.get('pattern_shifts') or []:
            found.add(sh.get('state'))
        return found

    def open_rooms(self, sc):
        """The rooms a scene opens: its locations' rooms, plus the connective
        rooms on the way between them."""
        rooms = []
        for lid in sc['where']:
            rooms += [r for r in self.location_rooms.get(lid, []) if r not in rooms]
        if len(sc['where']) > 1:
            connective = {rid for rid, r in self.world['rooms'].items() if r.get('location') is None}
            for rid in list(rooms):
                for e in self.world['rooms'][rid]['exits']:
                    if e['to'] in connective and e['to'] not in rooms:
                        rooms.append(e['to'])
        return rooms or list(self.world['rooms'])[:1]

    def out_edges(self, sc):
        """The outline's edges leaving a scene, as [{to, kind, trigger}], plus
        stage A's pattern-shift edges; the default ('continue') last."""
        major = sc['major']
        out = []
        for e in self.story.get('edges') or []:
            if e['from'] != major:
                continue
            to = self.scene_of.get(e['to'])
            trig = e.get('trigger') or {}
            out.append({'to': to, 'kind': 'branch' if e.get('kind') == 'branch' else 'default',
                        'trigger': trig.get('text') if isinstance(trig, dict) else None,
                        'instead': '; '.join(e.get('otherwise') or []) or None})
        if sc['ending']:
            out.append({'to': self.ending_id(sc), 'kind': 'ending', 'trigger': None, 'instead': None})
        out.sort(key=lambda x: {'branch': 0, 'ending': 1, 'default': 2}[x['kind']])
        return out

    def shifts_from(self, sc):
        return [sh for sh in self.arcs.get('pattern_shifts') or []
                if sh.get('does') == 'line' and sh.get('condition') and self.scene_of.get(sh.get('at')) == sc['id']]

    def ending_id(self, sc):
        return f"E_{sc['major']}"

    def tells_due(self, sc):
        out = []
        for mid, m in self.minors.items():
            tell = m.get('tell') or {}
            if tell.get('at') in sc['nodes']:
                moves = sorted({mv['state'] for o in m.get('options') or [] for mv in o.get('moves') or []})
                out.append({'from': mid, 'states': moves, 'how': tell.get('how')})
        return out

    # ------------------------------------------------------------ C: reconcile

    def reconcile(self):
        """Stage C's computed checks, before compiling: every scene's rooms are
        joined among themselves (rooms that are not get a way between them,
        so nothing a scene needs is out of reach), and every scene leads
        somewhere."""
        rooms = self.world['rooms']

        def joined(start, open_):
            seen, todo = set(), [start]
            while todo:
                r = todo.pop()
                if r in seen:
                    continue
                seen.add(r)
                todo += [e['to'] for e in rooms[r]['exits'] if e['to'] in open_]
            return seen
        for sc in self.plan['scenes']:
            open_ = self.open_rooms(sc)
            seen = joined(open_[0], open_)
            while len(seen) < len(open_):
                apart = next(r for r in open_ if r not in seen)
                near = next((r for r in seen if rooms[r].get('location') == rooms[apart].get('location')), open_[0])
                for a, b in ((near, apart), (apart, near)):
                    rooms[a]['exits'].append({'to': b, 'label': f"to {rooms[b]['name']}"})
                self.findings.append(f"C: scene {sc['id']}: {rooms[apart]['name']} ({apart}) was out of reach; "
                                     f"joined it to {rooms[near]['name']} ({near})")
                seen = joined(open_[0], open_)
            if not sc['ending'] and not self.out_edges(sc):
                self.findings.append(f"C: scene {sc['id']} leads nowhere")

    # ------------------------------------------------------------ D: one scene

    def packet(self, sc):
        required = self.required_states()
        nodes = []
        for nid in sc['nodes']:
            n = self.nodes[nid]
            entry = {'id': nid, 'kind': n.get('kind') or 'major', 'summary': n.get('summary'), 'image': n.get('image')}
            if n.get('kind') == 'opportunity':
                entry['options'] = [{'n': i + 1, 'do': o.get('do'), 'effect': o.get('effect'), 'active': o.get('active')}
                                    for i, o in enumerate(n.get('options') or [])]
                moved = {mv['state'] for o in n.get('options') or [] for mv in o.get('moves') or []}
                entry['required'] = bool(moved & required)
            if n.get('warns'):
                entry['warns'] = n['warns']
            nodes.append(entry)
        open_ = self.open_rooms(sc)
        rooms = [{'name': self.world['rooms'][r]['name'],
                  'objects': [o['name'] for o in self.world['objects'].values() if o.get('location') == r]}
                 for r in open_]
        cast = [c for c in sc['who'] if c in self.world['characters']]
        events = []
        if sc.get('event') is not None:
            ev = as_list((self.story.get('premise') or {}).get('events'))
            if 0 < sc['event'] <= len(ev):
                e = ev[sc['event'] - 1]
                events.append(e.get('what') if isinstance(e, dict) else e)
        return {'scene': {'id': sc['id'], 'title': sc['title'], 'beat': sc['beat'], 'lines': sc['lines']},
                'nodes': nodes, 'event_here': events, 'tells_due_here': self.tells_due(sc),
                'rooms': rooms,
                'people': [{'name': self.world['characters'][c]['name'], 'role': self.world['characters'][c].get('role'),
                            'topics': [t['label'] for t in self.world['characters'][c]['topics'].values()][:6]} for c in cast],
                'states': sorted(self.states), 'visibility': (self.arcs.get('plan') or {}).get('state_visibility'),
                'leaving': [{'to': e['to'], 'kind': e['kind'], 'trigger': e['trigger'], 'otherwise': e['instead']}
                            for e in self.out_edges(sc)]}

    def compile_scene(self, sc):
        packet = self.packet(sc)
        answer = self.gen.run_prompt(f's7d_{sc["id"]}', 'scene', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PACKET_JSON$$': compact(packet),
        }, prompt_file='s7d_scene.prompt', validator=self.validator(sc, packet), klass='build', schema=schemas.SCENE)
        self.compiled[sc['id']] = self.build(sc, answer)

    def validator(self, sc, packet):
        def validate(parsed):
            problems = []
            built = self.build(sc, parsed, problems)
            if problems:
                raise ValueError('; '.join(problems[:12]))
            soft = self.reading_problems(built['scene'], parsed, built['props'])
            if soft:
                raise SoftReject('; '.join(soft[:8]))
        return validate

    def reading_problems(self, scene, parsed, props):
        """What reads wrong to a player, found by playing kernel40 and kernel35
        (2026-10-08): one informed retry each, never the run."""
        out = []
        objects = dict(self.world['objects'], **props)
        for it in scene['interactions']:
            obj = objects.get(it.get('object'))
            label = it.get('object_label') or (obj or {}).get('name') or it.get('object')
            if it['verb'] == 'take' and obj is not None and not obj.get('portable'):
                out.append(f"take {label!r}: take picks up a thing that can be carried; {label!r} cannot be, so give "
                           f"this action a verb of its own (leave, sign, open, ...)")
            elif it['verb'] == 'take' and it.get('detail') in objects:
                out.append(f"take {label!r} with {objects[it['detail']].get('name')!r}: an action on two things is not "
                           f"a take; give it a verb of its own (sign, wrap, ...)")
            elif it['verb'] in ('use', 'take') and WAY_THING.search(str(label or '')) and any(
                    str(e.get('set', '')).startswith('go_') for e in it.get('effects') or []):
                out.append(f"{it['verb']} {label!r} leads on: a way on through a door, lane or ladder is a go (the menu "
                           f"where a player looks to leave), with a label saying how ('out the front door')")
            elif it['verb'] in ENGINE_VERBS:
                out.append(f"verb {it['verb']!r} on {label!r}: the engine makes {it['verb']} itself; give this action "
                           f"a verb of its own")
        opening = ' '.join(v.get('text', '') for v in scene.get('opening') or [])
        m = example_guard.player_deed(opening)
        if m:
            sentence = next((x for x in re.split(r'(?<=[.!?])\s+', opening) if m.group(0) in x), m.group(0))
            out.append(f'the opening narrates something the player does ("{sentence.strip()}"): the player acts only '
                       f'through the menu. Say what the place and the people are like now; a deed of the player\'s '
                       f'is an action')
        rooms = {r: self.world['rooms'][r]['name'] for r in scene['rooms']}
        for x in re.split(r'(?<=[.!?])\s+', opening):
            low = x.lower()
            said = [r for r, name in rooms.items()
                    if re.search(r'\b(in|at|inside|on) ' + re.escape(str(name).lower()) + r'\b', low)]
            for cid, placed in scene['cast'].items():
                ch = self.world['characters'].get(cid) or {}
                if len(said) == 1 and placed != said[0] and any(
                        n and n.lower() in low for n in (ch.get('name'), ch.get('role'))):
                    out.append(f"the opening puts {ch.get('name')} in {rooms[said[0]]} but placement puts them in "
                               f"{rooms[placed]}; make them agree")
        grams = example_guard.ngrams(opening)
        for k, ev in enumerate(as_list(parsed.get('events')), 1):
            g = example_guard.ngrams(str((ev or {}).get('text') or '')) if isinstance(ev, dict) else set()
            if len(g) >= 3 and len(g & grams) >= 0.5 * len(g):
                out.append(f'event {k} retells the opening; an event is something new that happens later')
        return out

    def resolve(self, name, names, open_rooms, extra=()):
        key = norm(name)
        if not key:
            return None
        if key in extra:
            return extra[key]
        return names.get(key)

    def build(self, sc, answer, problems=None):
        """The model's scene, by name, compiled to engine data. With
        `problems` given, collects what does not resolve (the validator)."""
        problems = problems if problems is not None else []
        names = self.names()
        open_ = self.open_rooms(sc)
        open_names = {norm(self.world['rooms'][r]['name']): r for r in open_}
        sid = sc['id']
        props = {}
        new_objects = {}
        taken = set(self.world['objects']) | set(self.world['rooms']) | set(self.world['characters'])
        for p in as_list(answer.get('props')):
            if isinstance(p, dict) and p.get('name'):
                room = open_names.get(norm(p.get('room')))
                if not room:
                    problems.append(f"prop {p['name']!r}: room {p.get('room')!r} is not open in this scene")
                    continue
                if norm(p['name']) in names:     # already in the world: the scene uses that one
                    props[norm(p['name'])] = names[norm(p['name'])]
                    continue
                oid = slug(p['name'], taken | set(new_objects))
                new_objects[oid] = {'name': p['name'], 'location': room, 'portable': bool(p.get('portable')),
                                    'listed': bool(p.get('portable')), 'description': [{'text': p.get('description') or p['name']}]}
                props[norm(p['name'])] = oid
        start = open_names.get(norm(answer.get('start_room'))) or open_[0]
        cast = {}
        for pl in as_list(answer.get('placement')):
            cid = self.resolve(pl.get('who'), names, open_, self.people())
            room = open_names.get(norm(pl.get('room')))
            if cid not in self.world['characters']:
                problems.append(f"placement: {pl.get('who')!r} is not a person in the world")
            elif not room:
                problems.append(f"placement: {pl.get('who')!r} is put in {pl.get('room')!r}, which this scene does not open")
            else:
                cast[cid] = room
        for c in sc['who']:
            if c in self.world['characters'] and c not in cast:
                cast[c] = start
        room_text = {}
        for rt in as_list(answer.get('room_text')):
            room = open_names.get(norm(rt.get('room')))
            if not room:
                problems.append(f"room_text for {rt.get('room')!r}, which this scene does not open")
                continue
            room_text[room] = compile_variants(rt.get('variants'), self.states, self.nodes, problems, f"room_text {rt.get('room')}")

        interactions, moments, keys = [], [], set()

        def interaction(a, iid, effects, where):
            verb = str(a.get('verb') or '').strip().lower().replace(' ', '_')
            if not re.fullmatch(r'[a-z_]{2,20}', verb):
                problems.append(f'{where}: verb {a.get("verb")!r} is not a verb')
                return None
            if not a.get('object') and a.get('detail'):   # "go" + "up the plank gangway": the detail is what it acts on
                a = dict(a, object=a['detail'], detail=None)
            elif not a.get('object') and a.get('label'):   # "go" + "out the lower doors": the label is what it acts on
                a = dict(a, object=a['label'], detail=None)
            obj = self.resolve(a.get('object'), names, open_, props) if a.get('object') else None
            free = None
            if a.get('object') and not obj:      # not a thing in the world ("salute the water"): the menu shows its words
                free = str(a['object']).strip()
                obj = slug(free) or 'it'
            room = open_names.get(norm(a.get('room'))) if a.get('room') else None
            if a.get('room') and not room:
                problems.append(f"{where}: room {a.get('room')!r} is not open in this scene")
            it = {'id': iid, 'verb': verb, 'text': str(a.get('text') or '').strip()}
            if obj:
                it['object'] = obj
            if free:
                it['object_label'] = free
            detail = a.get('detail')
            if detail:
                d = self.resolve(detail, names, open_, props)
                if d:
                    it['detail'] = d
                else:
                    it['detail'] = slug(detail)
                    it['detail_label'] = str(a.get('label') or detail)
            if room:
                it['room'] = room
            key = (verb, it.get('object'), it.get('detail'), room)
            if key in keys:
                problems.append(f"{where}: another action already has verb {verb!r} on {a.get('object')!r} "
                                f"{('with ' + repr(detail)) if detail else ''}; give it a different detail")
            keys.add(key)
            if not it['text']:
                problems.append(f'{where}: no text')
            if effects:
                it['effects'] = effects
            if verb not in CORE_VERBS:
                self.verbs.add(verb)
            return it

        nodes_here = {n: self.nodes[n] for n in sc['nodes']}
        required = self.required_states()
        given = {m.get('node'): m for m in as_list(answer.get('moments')) if isinstance(m, dict)}
        for nid, n in nodes_here.items():
            if n.get('kind') != 'opportunity':
                continue
            m = given.get(nid)
            if not m:
                problems.append(f'opportunity {nid} has no moment')
                continue
            a2 = n.get('options') or []
            opts = [o for o in as_list(m.get('options')) if isinstance(o, dict) and not o.get('neutral')]
            neutral = [o for o in as_list(m.get('options')) if isinstance(o, dict) and o.get('neutral')]
            if len(opts) != len(a2):
                problems.append(f'moment {nid}: {len(opts)} options for stage A\'s {len(a2)}; one engine action per '
                                f'option, in the same order (plus a neutral one if it is required)')
                continue
            moved = {mv['state'] for o in a2 for mv in o.get('moves') or []}
            is_required = bool(moved & required)
            if is_required and not neutral:
                problems.append(f'moment {nid} is required (its state decides how the story ends), so it needs a '
                                f'neutral option: something to do that takes no side')
            ids = []
            for i, (o, src) in enumerate(zip(opts, a2), 1):
                effects = [{'move': mv['state'], 'dir': mv['direction']} for mv in src.get('moves') or []]
                effects.append({'set': f'done_{nid}'})
                it = interaction(o, f'{sid}.{nid}.{i}', effects, f'moment {nid} option {i}')
                if it:
                    interactions.append(it)
                    ids.append(it['id'])
            neutral_id = None
            for o in neutral[:1]:
                it = interaction(o, f'{sid}.{nid}.n', [{'set': f'done_{nid}'}], f'moment {nid} neutral option')
                if it:
                    interactions.append(it)
                    ids.append(it['id'])
                    neutral_id = it['id']
            entry = {'id': f'{sid}.{nid}', 'options': ids, 'required': is_required}
            if is_required:
                entry['neutral'] = neutral_id
            else:
                lapse = m.get('lapse') or {}
                entry['lapse'] = {'after': int(lapse.get('after') or LAPSE_AFTER),
                                  'text': str(lapse.get('text') or '').strip(), 'effects': [{'set': f'done_{nid}'}]}
            moments.append(entry)

        exits = []
        for sh in self.shifts_from(sc):
            target = self.scene_of.get(sh['to'])
            if target:
                exits.append({'to': target, 'when': sh['when'], 'kind': 'accumulated'})
        leading = {e['to']: e for e in self.out_edges(sc)}
        led = set()
        for k, a in enumerate(as_list(answer.get('actions')), 1):
            if not isinstance(a, dict):
                continue
            effects = []
            to = a.get('leads_to')
            if to:
                if to not in leading:
                    problems.append(f"action {k}: leads_to {to!r} is not one of {sorted(leading)}")
                    continue
                effects.append({'set': f'go_{sid}__{to}'})
                led.add(to)
            for f in as_list(a.get('reveals')):
                if f in self.nodes:
                    effects.append({'set': f'done_{f}'})
            it = interaction(a, f'{sid}.a{k}', effects, f'action {k}')
            if it:
                if a.get('once') or to:
                    it['once'] = True
                if to and leading[to]['kind'] == 'branch':
                    it['weight'] = 'major'
                interactions.append(it)
        for to, e in leading.items():
            if to not in led:
                problems.append(f"no action leads to {to} ({e['kind']}{': ' + e['trigger'] if e.get('trigger') else ''})")
            exits.append({'to': to, 'when': f'flags.go_{sid}__{to}', 'kind': e['kind']})
        order = {'accumulated': 0, 'branch': 1, 'ending': 2, 'default': 3}
        exits.sort(key=lambda x: order.get(x['kind'], 3))
        things = set(self.world['objects']) | set(new_objects)
        for it in interactions:
            portable = (self.world['objects'].get(it.get('object')) or new_objects.get(it.get('object')) or {}).get('portable')
            if it['verb'] == 'take' and it.get('object') in things and portable \
                    and not any(e.get('give') == it['object'] for e in it.get('effects') or []):
                it.setdefault('effects', []).append({'give': it['object']})   # a take the scene writes still takes
                it['once'] = True
            if any(str(e.get('set', '')).startswith(f'go_{sid}__') for e in it.get('effects') or []):
                it['reach'] = 'any'     # a way on is findable from every state: never behind fetching a thing
        for m in moments:               # a moment is a choice, not a puzzle: its options never wait on fetching a thing,
            for it in interactions:     # and the neutral one, which lets a required moment pass, is there in any room
                if it['id'] in m['options']:
                    it['reach'] = 'any'
                    if it['id'] == m.get('neutral'):
                        it.pop('room', None)

        events = [{'id': f'{sid}.enter', 'when': 'true', 'effects': [{'set': f"done_{sc['major']}"}]}]
        for k, ev in enumerate(as_list(answer.get('events')), 1):
            if not isinstance(ev, dict) or not str(ev.get('text') or '').strip():
                continue
            parts = []
            if ev.get('after_turns'):
                parts.append(f"turns_in_scene >= {int(ev['after_turns'])}")
            if ev.get('after') in self.nodes:
                parts.append(f"flags.done_{ev['after']}")
            events.append({'id': f'{sid}.e{k}', 'when': ' and '.join(parts) or 'true', 'text': ev['text']})
        nudges = []
        for k, nd in enumerate(as_list(answer.get('nudges')), 1):
            if isinstance(nd, dict) and str(nd.get('text') or '').strip():
                nudges.append({'id': f'{sid}.n{k}', 'after': int(nd.get('after') or 4), 'text': nd['text']})
        if not nudges:
            problems.append('no nudge: give one or two, for a player who has done nothing for a while')
        return {'scene': {'beat': sc['major'], 'lines': sc['lines'], 'title': sc['title'],
                          'opening': [{'text': str(answer.get('opening') or '').strip()}] if answer.get('opening') else [],
                          'rooms': open_, 'start_room': start, 'cast': cast, 'room_text': room_text,
                          'interactions': interactions, 'moments': moments, 'events': events, 'nudges': nudges,
                          'exits': [{k: v for k, v in x.items() if k != 'kind'} for x in exits]},
                'props': new_objects}

    # ------------------------------------------------------------ assembly

    def endings(self):
        out = {}
        for l, e in (self.arcs.get('endings') or {}).items():
            sc = self.scene_of.get(e['node'])
            if not sc:
                continue
            end = (self.story['lines'][l].get('ending') or {})
            out[f"E_{e['node']}"] = {'title': e.get('title') or end.get('title'),
                                     'text': [{'text': end.get('summary') or ''}],
                                     'resolutions': [{'about': g['about'], 'variants': g['variants']} for g in e.get('groups') or []]}
        return out

    def package(self):
        objects = {k: {kk: vv for kk, vv in o.items() if kk != 'story'} for k, o in self.world['objects'].items()}
        scenes = {}
        for sid, c in self.compiled.items():
            scenes[sid] = c['scene']
            objects.update(c['props'])
        # every done flag something reads is set: unset ones on entering the scene that holds the node
        text = json.dumps({'w': self.world, 'p': self.protagonist, 's': scenes})
        read = set(re.findall(r'flags\.(done_\w+)', text))
        set_ = set(re.findall(r'"set": "(done_\w+)"', text))
        for flag in sorted(read - set_):
            node = flag[len('done_'):]
            sid = self.scene_of.get(node)
            if sid in scenes:
                scenes[sid]['events'][0]['effects'].append({'set': flag})
        main = self.story['lines'][(self.story.get('line_order') or ['T1'])[0]]
        first = self.scene_of.get(main['path'][0])
        prot = self.premise_protagonist()
        return {
            'format': 'stratum-story/1', 'story_id': self.story.get('story_id'),
            'title': main.get('title') or self.story.get('story_id'),
            'intro': [{'text': ' '.join(x for x in (prot.get('who'), prot.get('history')) if x)}],
            'protagonist': self.protagonist,
            'states': {k: {'meaning': v.get('meaning')} for k, v in (self.arcs.get('states') or {}).items()},
            'verbs': {v: {'label': v.replace('_', ' ').capitalize()} for v in sorted(self.verbs)},
            'world': {'rooms': self.world['rooms'], 'objects': objects, 'characters': self.world['characters']},
            'scenes': scenes,
            'start': {'scene': first, 'room': (scenes.get(first) or {}).get('start_room')},
            'endings': self.endings(),
        }

    def premise_protagonist(self):
        return (self.story.get('premise') or {}).get('protagonist') or {}

    def check(self, package, runs=None, max_states=None):
        """The engine's validator, then the playtest. STRATUM_PLAYTEST=quick
        (the plumbing tests) explores less and plays fewer runs."""
        quick = os.environ.get('STRATUM_PLAYTEST') == 'quick'
        runs = runs or (20 if quick else 200)
        max_states = max_states or (3000 if quick else 60000)
        import importlib.util
        if ENGINE not in sys.path:
            sys.path.insert(0, ENGINE)
        from story import Story, validate
        # the generator has its own playtest.py (the outline walker); load the engine's by path
        spec = importlib.util.spec_from_file_location('engine_playtest', os.path.join(ENGINE, 'playtest.py'))
        engine_playtest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine_playtest)
        story = Story(package)
        errors, notes = validate(story)
        report = {'errors': errors, 'notes': notes, 'playtest': None}
        if errors:
            return report
        out = io.StringIO()
        result = engine_playtest.run(story, runs=runs, max_states=max_states, walkthroughs=True, out=out,
                                     styled_runs=10 if quick else None, scene_states=1500 if quick else None)
        report['playtest'] = {'errors': result['errors'], 'notes': result['notes'], 'text': out.getvalue()}
        return report

    def run(self):
        """Reconcile and compile; returns the package (check it with check())."""
        self.reconcile()
        for sc in self.plan['scenes']:
            self.compile_scene(sc)
        return self.package()


def report_markdown(story_id, findings, report):
    out = [f'# {story_id}: the compiled package', '']
    out += ['## Stage C'] + ([f'- {f}' for f in findings] or ['- no findings']) + ['']
    out += ['## Engine validator'] + ([f'- ERROR {e}' for e in report['errors']] or ['- no errors'])
    out += [f'- note {n}' for n in report['notes']] + ['']
    if report.get('playtest'):
        out += ['## Playtest', '```', report['playtest']['text'].rstrip(), '```']
    return '\n'.join(out) + '\n'


def main(argv=None):
    """python compile_scenes.py <story_id>: stages C and D on a directory with
    the outline, stage A and stage B. Writes <id>_package.json and .md; play
    it with python ../engine/cli.py ../stories/<id>/<id>_package.json"""
    from main import StoryGenerator
    import scenes
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument('story_id')
    args = ap.parse_args(argv)
    gen = StoryGenerator(story_id=args.story_id)
    base = gen.story_file_path('')
    load = lambda suffix: json.load(open(base + suffix, encoding='utf-8')) if os.path.isfile(base + suffix) else None
    story, arcs, world = load('story.json'), load('arcs.json'), load('world.json')
    if not (story and arcs and world):
        print('stages C and D need <id>_story.json, <id>_arcs.json and <id>_world.json', file=sys.stderr)
        return 1
    gen.kernel = story.get('kernel') or ''
    for key, suffix in (('s3_brief', 's3_brief.json'), ('s3_4_promises', 's3_4_promises.json')):
        if load(suffix) is not None:
            gen.analysis[key] = load(suffix)
    plan = load('scenes.json') or scenes.plan(story, arcs, gen.analysis.get('s3_brief'))
    comp = SceneCompiler(gen, story, arcs, plan, world)
    package = comp.run()
    gen.save_story_json('package.json', package)
    report = comp.check(package)
    gen.save_story_file('package.md', report_markdown(args.story_id, comp.findings, report))
    print(f"package: {len(package['scenes'])} scenes; validator {len(report['errors'])} error(s); playtest "
          f"{len((report.get('playtest') or {}).get('errors') or [])} error(s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
