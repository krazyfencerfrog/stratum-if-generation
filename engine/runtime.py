"""The engine at play: scenes, the menu, actions, events, endings, rewind.

    eng = Engine(Story.load('story.json'))
    view = eng.start()            # {'text': [...], 'room': '...', 'menu': {...}, 'ending': None, ...}
    view = eng.act('S04.bail')    # a leaf id from the menu
    view = eng.rewind()

The menu is a tree built fresh for every view from what is available now:
the current scene's interactions (in the player's room or anywhere in the
scene, their `when` holding, not used up), plus the built-in ones (Look,
Examine what is here, Go through exits the scene opens, Talk to who is here
about the topics you know, Take what can be carried, Wait, Inventory). An
interaction the package writes for the same verb and object as a built-in
replaces it. See docs/engine_design.md §6-§7.
"""

import json

from expressions import evaluate
from state import GameState
from story import Story, ending_groups, pick_text

DETAIL_WORD = {'talk': 'about', 'give': 'to', 'show': 'to', 'use': 'on'}
FREE = ('look', 'inventory')          # meta actions: no turn passes, nothing fires
CHAIN_LIMIT = 10                      # scene changes or event rounds in one action
SAVE_FORMAT = 'stratum-save/1'
COLLAPSE_MODES = ('trivial', 'all')


class EngineError(ValueError):
    pass


class SaveMismatch(EngineError):
    pass


class Engine:
    def __init__(self, story, collapse='trivial'):
        self.story = story if isinstance(story, Story) else Story(story)
        if collapse not in COLLAPSE_MODES:
            raise EngineError(f'collapse must be one of {COLLAPSE_MODES}')
        self.collapse = collapse
        self.state = None
        self.timeline = []                # a snapshot after every action (rewind)
        self.history = []                 # beside each snapshot: what was chosen and what it said
        self.queue = []

    # ------------------------------------------------------------ setup

    def start(self, seed=None):
        s, st = self.story, GameState()
        if seed is not None:
            st.seed = seed
        self.state = st
        st.flags = dict(s.data.get('initial_flags') or {})
        st.stats = dict(s.data.get('initial_stats') or {})
        for name in s.states:
            st.arcs[name] = {'up': 0, 'down': 0}
        st.locations = {oid: o.get('location') for oid, o in s.objects.items()}
        self.queue = []
        intro = s.data.get('intro')
        if intro:
            self.queue.append(pick_text(intro, st))
        self._enter_scene(s.start['scene'], room=s.start.get('room'))
        self._settle()
        self.timeline = [st.clone()]
        view = self.view()
        self.history = [{'label': '(the beginning)', 'text': view['text'], 'turn': 0}]
        return view

    # ------------------------------------------------------------ what can be done

    def scene(self):
        return self.story.scenes.get(self.state.scene) or {}

    def open_rooms(self):
        return set(self.scene().get('rooms') or [])

    def present(self):
        """Characters in the player's room."""
        return [c for c, r in self.state.placements.items() if r == self.state.room]

    def visible_objects(self):
        """Objects in the player's room, carried, or held by someone here,
        whose `when` (if any) holds."""
        st = self.state
        out = []
        holders = set(self.present())
        for oid, obj in self.story.objects.items():
            loc = st.locations.get(oid)
            if (loc in (st.room, 'player') or loc in holders) and evaluate(obj.get('when', 'true'), st):
                out.append(oid)
        return out

    def _reachable(self, thing):
        if thing is None or thing in self.story.rooms:
            return True
        if thing in self.story.characters:
            return thing in self.present()
        if thing in self.story.objects:
            return thing in self.visible_objects()
        return True                     # free-text object or detail

    def options(self):
        """Every action available now: a list of dicts with id, verb, object,
        detail and the labels the menu shows."""
        if self.state.ending:
            return []
        s, st = self.story, self.state
        built, authored = [], []

        def add(into, oid, verb, obj=None, detail=None, obj_label=None, detail_label=None, source=None):
            into.append({'id': oid, 'verb': verb, 'object': obj, 'detail': detail,
                         'object_label': obj_label or (s.name_of(obj) if obj else None),
                         'detail_label': detail_label or (s.name_of(detail) if detail else None),
                         'source': source})

        add(built, 'look', 'look')
        for oid in self.visible_objects():
            add(built, f'examine:{oid}', 'examine', oid)
            obj = s.objects[oid]
            if obj.get('portable') and st.locations.get(oid) == st.room:
                add(built, f'take:{oid}', 'take', oid)
        for cid in self.present():
            add(built, f'examine:{cid}', 'examine', cid)
            for tid, topic in (s.characters[cid].get('topics') or {}).items():
                if f'talk:{cid}:{tid}' in st.used:
                    continue
                if evaluate(topic.get('known_when', 'true'), st):
                    add(built, f'talk:{cid}:{tid}', 'talk', cid, tid, detail_label=topic.get('label') or tid,
                        source=('topic', cid, tid))
        room = s.rooms.get(st.room) or {}
        for ex in room.get('exits') or []:
            if ex['to'] in self.open_rooms() and evaluate(ex.get('when', 'true'), st):
                add(built, f"go:{ex['to']}", 'go', ex['to'], obj_label=ex.get('label') or s.name_of(ex['to']),
                    source=('exit', ex))
        add(built, 'wait', 'wait')
        if any(loc == 'player' for loc in st.locations.values()):
            add(built, 'inventory', 'inventory')

        for it in self.scene().get('interactions') or []:
            if it.get('room') not in (None, st.room) or it['id'] in st.used:
                continue
            if it.get('reach') != 'any' and not (self._reachable(it.get('object')) and self._reachable(it.get('detail'))):
                continue
            if not evaluate(it.get('when', 'true'), st):
                continue
            detail_label = it.get('detail_label')
            if detail_label is None and it.get('object') in s.characters and it.get('detail'):
                topic = (s.characters[it['object']].get('topics') or {}).get(it['detail'])
                detail_label = (topic or {}).get('label')
            add(authored, it['id'], it['verb'], it.get('object'), it.get('detail'), it.get('object_label'),
                detail_label, source=('interaction', it))

        taken = {(o['verb'], o['object'], o['detail']) for o in authored}
        return [o for o in built if (o['verb'], o['object'], o['detail']) not in taken] + authored

    def menu(self, collapse=None):
        """The options as a tree: verbs, then objects, then details. Leaves
        carry `id`. `collapse` (default: the engine's) decides which levels
        with a single option merge into their parent: 'trivial' merges only
        where there is nothing to choose (Wait, Look, an object with one way
        to act on it), so the menu keeps its shape and does not point at what
        matters; 'all' merges every single option ("Untie › the stern line"
        at the root)."""
        s = self.story
        verbs = {}
        for o in self.options():
            verbs.setdefault(o['verb'], []).append(o)
        root = {'label': None, 'children': []}
        for verb in sorted(verbs, key=s.verb_rank):
            vnode = {'label': s.verbs.get(verb, verb), 'children': []}
            objects = {}
            for o in verbs[verb]:
                objects.setdefault(o['object'], []).append(o)
            for obj, opts in objects.items():
                if obj is None:
                    for o in opts:
                        vnode['children'].append({'label': None, 'id': o['id']})
                    continue
                onode = {'label': opts[0]['object_label'], 'children': []}
                for o in opts:
                    if o['detail'] is None:
                        onode['children'].append({'label': None, 'id': o['id']})
                    else:
                        onode['children'].append({'label': detail_text(verb, o['detail_label']), 'id': o['id']})
                vnode['children'].append(onode)
            root['children'].append(vnode)
        root['children'] = [_collapse(c, collapse or self.collapse) for c in root['children']]
        return root

    # ------------------------------------------------------------ acting

    def act(self, option_id):
        st, s = self.state, self.story
        if st.ending:
            raise EngineError('the story has ended')
        opt = next((o for o in self.options() if o['id'] == option_id), None)
        if opt is None:
            raise EngineError(f'{option_id!r} is not available now')
        self.queue = []
        if opt['verb'] in FREE:
            self.queue.append(self._free_text(opt))
            return self.view(show_room=opt['verb'] == 'look')
        moved_room, scene_before = self.perform(opt)
        self.timeline.append(st.clone())
        view = self.view(show_room=moved_room or st.scene != scene_before)
        text = view['text'] or ([f"You are in {view['room']['name']}."] if view.get('room') else [])
        self.history.append({'label': self.label_of(opt), 'text': text, 'turn': st.turns})
        return view

    def perform(self, opt, reseed=True):
        """Carry out one (non-free) option from options(): text queued,
        effects, turns, events, nudges, scene exits. No snapshot and no view,
        so the playtest simulator can step through states cheaply. Returns
        (moved_room, scene_before)."""
        st, s = self.state, self.story
        if reseed:
            st.new_seed()
        before = _signature(st)
        moved_room = False
        src = opt['source']
        if src and src[0] == 'interaction':
            it = src[1]
            self.queue.append(pick_text(it.get('text'), st, it['id']))
            self._apply(it.get('effects'))
            if it.get('once'):
                st.used.add(it['id'])
        elif src and src[0] == 'topic':
            _, cid, tid = src
            topic = s.characters[cid]['topics'][tid]
            self.queue.append(pick_text(topic.get('says'), st, f'{cid}.{tid}'))
            self._apply(topic.get('effects'))
            if topic.get('once'):
                st.used.add(f'talk:{cid}:{tid}')
        elif opt['verb'] == 'go':
            ex = src[1]
            if ex.get('text'):
                self.queue.append(pick_text(ex['text'], st))
            st.room = ex['to']
            st.visited.add(st.room)
            moved_room = True
        elif opt['verb'] == 'examine':
            thing = opt['object']
            table = s.objects if thing in s.objects else s.characters
            self.queue.append(pick_text(table[thing].get('description'), st, thing)
                              or f'Nothing about {s.name_of(thing)} stands out.')
        elif opt['verb'] == 'take':
            obj = s.objects[opt['object']]
            st.locations[opt['object']] = 'player'
            self.queue.append(pick_text(obj.get('take_text'), st) or f"You take {obj.get('name', opt['object'])}.")
        elif opt['verb'] == 'wait':
            self.queue.append(pick_text(self.scene().get('wait_text'), st) or 'Time passes.')
        st.turns += 1
        st.turns_in_scene += 1
        scene_before = st.scene
        self._settle(progress_since=before)
        return moved_room, scene_before

    def label_of(self, opt):
        """An option as the menu path that names it: 'Talk › Lazlo Brandt › about the ledger'."""
        parts = [self.story.verbs.get(opt['verb'], opt['verb'])]
        if opt['object_label']:
            parts.append(opt['object_label'])
        if opt['detail_label']:
            parts.append(detail_text(opt['verb'], opt['detail_label']))
        return ' › '.join(parts)

    def _free_text(self, opt):
        if opt['verb'] == 'look':
            return ''
        names = [self.story.name_of(o) for o, loc in self.state.locations.items() if loc == 'player']
        return 'You are carrying ' + _join(names) + '.'

    def _apply(self, effects):
        st, s = self.state, self.story
        for eff in effects or []:
            if 'set' in eff:
                st.flags[eff['set']] = True
            elif 'clear' in eff:
                st.flags[eff['clear']] = False
            elif 'add' in eff:
                st.stats[eff['add']] = st.stats.get(eff['add'], 0) + eff.get('by', 1)
            elif 'move' in eff:
                st.move_arc(eff['move'], eff.get('dir', 'up'))
            elif 'give' in eff:
                st.locations[eff['give']] = 'player'
            elif 'take' in eff:
                st.locations[eff['take']] = None
            elif 'place' in eff:
                if eff['place'] in s.characters:
                    st.placements[eff['place']] = eff.get('to')
                else:
                    st.locations[eff['place']] = eff.get('to')
            elif 'room' in eff:
                st.room = eff['room']
                st.visited.add(st.room)

    def _fire_events(self):
        st = self.state
        for _ in range(CHAIN_LIMIT):
            fired = False
            for ev in self.scene().get('events') or []:
                once = ev.get('once', True)
                if once and ev['id'] in st.fired:
                    continue
                if evaluate(ev.get('when', 'true'), st):
                    st.fired.add(ev['id'])
                    if ev.get('text'):
                        self.queue.append(pick_text(ev['text'], st, ev['id']))
                    self._apply(ev.get('effects'))
                    fired = fired or once
            if not fired:
                return

    def _settle(self, progress_since=None):
        """After an action (or at the start): events, idle count and nudges,
        then scene exits, repeated while a scene change lands somewhere new."""
        st = self.state
        for _ in range(CHAIN_LIMIT):
            self._fire_events()
            if progress_since is not None:
                if _signature(st) != progress_since:
                    st.idle = 0
                else:
                    st.idle += 1
                    self._nudge()
                progress_since = None
            target = self._exit_due()
            if target is None:
                return
            if target in self.story.endings:
                self._end(target)
                return
            self._enter_scene(target)

    def _nudge(self):
        st = self.state
        for n in self.scene().get('nudges') or []:
            if n['id'] in st.fired or st.idle < n.get('after', 3):
                continue
            if not evaluate(n.get('when', 'true'), st):
                continue
            st.fired.add(n['id'])
            self.queue.append(pick_text(n.get('text'), st, n['id']))
            self._apply(n.get('effects'))
            return

    def _exit_due(self):
        for ex in self.scene().get('exits') or []:
            if evaluate(ex.get('when', 'true'), self.state):
                return ex['to']
        return None

    def _enter_scene(self, sid, room=None):
        st = self.state
        sc = self.story.scenes[sid]
        st.scene = sid
        st.turns_in_scene = 0
        st.idle = 0
        st.visited.add(sid)
        st.placements = dict(sc.get('cast') or {})
        rooms = sc.get('rooms') or []
        room = room or sc.get('start_room')
        if room:
            st.room = room
        elif st.room not in rooms and rooms:
            st.room = rooms[0]
        st.visited.add(st.room)
        if sc.get('opening'):
            self.queue.append(pick_text(sc['opening'], st, sid))

    def _end(self, eid):
        st = self.state
        end = self.story.endings[eid]
        st.ending = eid
        parts = [pick_text(end.get('text'), st, eid)]
        for group in ending_groups(end):
            text = pick_text(group.get('variants'), st, f"{eid}.{group.get('about')}")
            if text:
                parts.append(text)
        self.queue.extend(p for p in parts if p)

    # ------------------------------------------------------------ the view

    def describe(self):
        """The current room, layered: base description, the scene's layer,
        state fragments, then who and what is here."""
        s, st = self.story, self.state
        room = s.rooms.get(st.room) or {}
        pre, post = [], []
        for frag in room.get('fragments') or []:
            if evaluate(frag.get('when', 'true'), st):
                (pre if frag.get('position') == 'pre' else post).append(frag['text'])
        layers = pre + [pick_text(room.get('description'), st, st.room),
                        pick_text((self.scene().get('room_text') or {}).get(st.room), st, f'{st.scene}.{st.room}')]
        layers += post
        for cid in self.present():
            ch = s.characters[cid]
            here = pick_text(ch.get('here'), st, cid) or f"{ch.get('name', cid)} is here."
            layers.append(here)
        listed = [s.name_of(o) for o in self.visible_objects()
                  if st.locations.get(o) == st.room and s.objects[o].get('listed', s.objects[o].get('portable', False))]
        if listed:
            layers.append(f'You can see {_join(listed)}.')
        return {'name': room.get('name', st.room), 'text': ' '.join(x for x in layers if x)}

    def view(self, show_room=True):
        st = self.state
        out = {'text': [t for t in self.queue if t], 'scene': st.scene, 'turns': st.turns,
               'ending': st.ending, 'room': None, 'menu': None}
        if st.ending:
            out['ending_title'] = self.story.endings[st.ending].get('title')
            return out
        out['room'] = self.describe() if show_room else None
        out['menu'] = self.menu()
        return out

    # ------------------------------------------------------------ rewind, save, load

    def can_rewind(self):
        return len(self.timeline) > 1

    def rewind(self, steps=1):
        if not self.can_rewind():
            raise EngineError('nothing to rewind')
        steps = min(steps, len(self.timeline) - 1)
        del self.timeline[len(self.timeline) - steps:]
        del self.history[len(self.timeline):]
        self.state = self.timeline[-1].clone()
        self.queue = []
        return self.view()

    def rewind_to(self, index):
        """Back to history entry `index` (0 is the beginning): the state as
        it was right after that action."""
        if not 0 <= index < len(self.timeline):
            raise EngineError(f'no history entry {index}')
        if index == len(self.timeline) - 1:
            raise EngineError('that is where you are')
        return self.rewind(len(self.timeline) - 1 - index)

    def save(self, path):
        data = {'format': SAVE_FORMAT, 'story_id': self.story.id, 'package_hash': self.story.hash,
                'state': self.state.to_dict(), 'timeline': [t.to_dict() for t in self.timeline],
                'history': self.history}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def load(self, path):
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if data.get('format') != SAVE_FORMAT:
            raise SaveMismatch('that file is not a stratum save')
        if data.get('story_id') != self.story.id:
            raise SaveMismatch(f"that save belongs to a different story ({data.get('story_id')})")
        if data.get('package_hash') != self.story.hash:
            raise SaveMismatch('this story has been regenerated since that save was made; '
                               'the save cannot be loaded into the new version')
        self.state = GameState.from_dict(data['state'])
        self.timeline = [GameState.from_dict(t) for t in data.get('timeline') or [data['state']]]
        history = list(data.get('history') or [])
        history += [{'label': '(not recorded)', 'text': [], 'turn': None}] * (len(self.timeline) - len(history))
        self.history = history[:len(self.timeline)]
        self.queue = []
        return self.view()


def _signature(st):
    """What counts as progress: any change to facts, counts, arcs, where
    things are, or what has been used up. Walking about does not."""
    return (tuple(sorted(st.flags.items())), tuple(sorted(st.stats.items())),
            tuple(sorted((k, v['up'], v['down']) for k, v in st.arcs.items())),
            tuple(sorted((k, str(v)) for k, v in st.locations.items())), tuple(sorted(st.used)), st.scene)


def detail_text(verb, label):
    """A detail as the menu shows it: 'about the ledger', 'on the crack',
    "say 'Boat held, sir'"."""
    word = 'say' if label[:1] in '\'"‘“' else DETAIL_WORD.get(verb)
    if word and not label.startswith(word + ' '):
        return f'{word} {label}'
    return label


def _collapse(node, mode):
    if 'children' not in node:
        return node
    node = dict(node, children=[_collapse(c, mode) for c in node['children']])
    # an unlabelled child is no choice at all (Wait, or an object with one way
    # to act on it): it always merges; a labelled only child merges under 'all'
    if len(node['children']) == 1 and (node['children'][0]['label'] is None or mode == 'all'):
        child = node['children'][0]
        label = node['label'] if not child['label'] else f"{node['label']} › {child['label']}"
        merged = dict(child, label=label)
        return merged
    for c in node['children']:
        if c['label'] is None:
            c['label'] = node['label']      # an objectless option beside others: its verb's own name
    return node


def _join(names):
    names = list(names)
    if len(names) <= 1:
        return ''.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def leaves(tree, path=()):
    """Every leaf of a menu tree as (path of labels, id)."""
    if 'id' in tree:
        yield path + ((tree['label'],) if tree['label'] else ()), tree['id']
        return
    for c in tree['children']:
        yield from leaves(c, path + ((tree['label'],) if tree['label'] else ()))
