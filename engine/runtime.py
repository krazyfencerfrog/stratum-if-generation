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
import re

from expressions import evaluate
from menukeys import KEYS
from state import GameState
from story import Story, ending_groups, pick_text

DETAIL_WORD = {'talk': 'about', 'give': 'to', 'show': 'to', 'use': 'on'}
NEWS = ('examine', 'talk', 'think')     # verbs whose options are marked new until taken
GROUP_AT = 8                            # an object with more options than this sorts its grouped ones into groups
GROUP_LABELS = {'person': 'people', 'place': 'places', 'object': 'things', 'event': 'what happened'}
FREE = ('look', 'inventory')          # meta actions: no turn passes, nothing fires
CHAIN_LIMIT = 10                      # scene changes or event rounds in one action
SAVE_FORMAT = 'stratum-save/1'
COLLAPSE_MODES = ('trivial', 'all')
ALONE = {'look': 'around'}             # an objectless option beside others, by verb ("Look › around"); else the verb
EXAMINE_GROUPS = (('people', 'people'), ('carried', 'things you carry'), ('here', 'things here'))
MORE = 'more…'
PARAPHRASE_SHARE = 0.8                 # ... or whose content words mostly were (a paraphrase of the opening)
REPEAT_SHARE = 0.6                     # a sentence whose phrases were mostly read already in this view is dropped
DOUBLED = re.compile(r"\b(the|a|an|of|to|in|on|at|and|for|with|by|from)\s+\1\b", re.I)
SENTENCE = re.compile(r'(?<=[.!?])\s+(?=[A-Z\'"‘“{])')
WORD = re.compile(r"[a-z0-9']+")


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
        st.introduced = {cid for cid, ch in s.characters.items() if ch.get('known') or not ch.get('unnamed')}
        for name in s.states:
            st.arcs[name] = {'up': 0, 'down': 0}
        st.locations = {oid: o.get('location') for oid, o in s.objects.items()}
        self.queue = []
        intro = s.data.get('intro')
        if intro:
            self.queue.append(pick_text(intro, st))
        self._enter_scene(s.start['scene'], room=s.start.get('room'))
        self._settle()
        self._note_seen()
        self.timeline = [st.clone()]
        view = self.view()
        self.history = [{'label': '(the beginning)', 'text': view['text'], 'turn': 0, 'scene': st.scene,
                         'scene_after': st.scene}]
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

        def add(into, oid, verb, obj=None, detail=None, obj_label=None, detail_label=None, source=None, weight=None,
                group=None):
            topics = (s.characters.get(obj) or {}).get('topics') or {}
            text_only = detail not in s.objects and detail not in s.characters and detail not in s.rooms \
                and detail not in topics
            free = detail is not None and bool(source) and source[0] == 'interaction' \
                and _is_action(detail_label, 2 if text_only else 3)
            into.append({'id': oid, 'verb': verb, 'object': obj, 'detail': detail, 'detail_free': free,
                         'object_label': s.render(obj_label, st, False) or (s.name_of(obj, st) if obj else None),
                         'detail_label': s.render(detail_label, st, False) or (s.name_of(detail, st) if detail else None),
                         'source': source, 'weight': weight, 'group': group,
                         'new': verb in NEWS and oid not in st.heard})

        add(built, 'look', 'look')
        for oid in self.visible_objects():
            add(built, f'examine:{oid}', 'examine', oid)
            obj = s.objects[oid]
            if obj.get('portable') and st.locations.get(oid) == st.room:
                add(built, f'take:{oid}', 'take', oid)
        you = s.protagonist
        if you.get('description'):
            add(built, 'examine:you', 'examine', 'you', obj_label='yourself', source=('self',))
        for tid, topic in (you.get('think') or {}).items():
            if f'think:{tid}' not in st.used and evaluate(topic.get('known_when', 'true'), st):
                add(built, f'think:{tid}', 'think', tid, obj_label=topic.get('label') or tid, source=('think', tid))
        for cid in self.present():
            add(built, f'examine:{cid}', 'examine', cid)
            for tid, topic in (s.characters[cid].get('topics') or {}).items():
                if f'talk:{cid}:{tid}' in st.used:
                    continue
                if evaluate(topic.get('known_when', 'true'), st):
                    add(built, f'talk:{cid}:{tid}', 'talk', cid, tid, detail_label=topic.get('label') or tid,
                        source=('topic', cid, tid), group=topic.get('group'))
        room = s.rooms.get(st.room) or {}
        for ex in room.get('exits') or []:
            if ex['to'] in self.open_rooms() and evaluate(ex.get('when', 'true'), st):
                add(built, f"go:{ex['to']}", 'go', ex['to'], obj_label=ex.get('label') or s.name_of(ex['to']),
                    source=('exit', ex))
        add(built, 'wait', 'wait')
        if any(loc == 'player' for loc in st.locations.values()):
            add(built, 'inventory', 'inventory')

        for it in self.scene().get('interactions') or []:
            if not self._available(it):
                continue
            detail_label = it.get('detail_label')
            if detail_label is None and it.get('object') in s.characters and it.get('detail'):
                topic = (s.characters[it['object']].get('topics') or {}).get(it['detail'])
                detail_label = (topic or {}).get('label')
            add(authored, it['id'], it['verb'], it.get('object'), it.get('detail'), it.get('object_label'),
                detail_label, source=('interaction', it), weight=it.get('weight'), group=it.get('group'))

        taken = {(o['verb'], o['object'], o['detail']) for o in authored}
        return [o for o in built if (o['verb'], o['object'], o['detail']) not in taken] + authored

    def _available(self, it):
        """An authored interaction can be offered now: in this room (or
        anywhere in the scene), not used up, its moment not yet answered, its
        object and detail at hand, its condition true."""
        st = self.state
        if it.get('room') not in (None, st.room) or it['id'] in st.used:
            return False
        moment = self.moment_of(it['id'])
        if moment and moment['id'] in st.used:
            return False
        if it.get('reach') != 'any' and not (self._reachable(it.get('object')) and self._reachable(it.get('detail'))):
            return False
        return bool(evaluate(it.get('when', 'true'), st))

    def moments(self):
        return self.scene().get('moments') or []

    def moment_of(self, interaction_id):
        for m in self.moments():
            if interaction_id in (m.get('options') or []):
                return m
        return None

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
            kinds = []                        # what each object node is, for grouping a long Examine
            for obj, opts in objects.items():
                if obj is None:
                    for o in opts:
                        vnode['children'].append(dict({'label': None, 'id': o['id']},
                                                      **({'weight': o['weight']} if o.get('weight') else {}),
                                                      **({'new': True} if o.get('new') else {})))
                        kinds.append(None)
                    continue
                onode = {'label': opts[0]['object_label'], 'children': []}
                groups = {}
                for o in opts:
                    leaf = {'label': None if o['detail'] is None else detail_text(verb, o['detail_label'], o.get('detail_free')),
                            'id': o['id']}
                    if o.get('weight'):
                        leaf['weight'] = o['weight']
                    if o.get('new'):
                        leaf['new'] = True
                    if o.get('group') and len(opts) > GROUP_AT:
                        if o['group'] not in groups:     # many options: the grouped ones go one level down
                            groups[o['group']] = {'label': GROUP_LABELS.get(o['group'], o['group']), 'children': []}
                        groups[o['group']]['children'].append(leaf)
                    else:
                        onode['children'].append(leaf)
                order = list(GROUP_LABELS)
                for g in sorted(groups, key=lambda g: (order.index(g) if g in order else len(order), g)):
                    onode['children'].append(groups[g])
                if len(onode['children']) > 1:           # the plain action beside detailed ones: "Take › the pen › take it"
                    for c in onode['children']:
                        if c.get('label') is None:
                            c['label'] = f"{vnode['label'].lower()} it"
                vnode['children'].append(onode)
                kinds.append(self._kind(obj))
            if len(vnode['children']) > 1:
                for c in vnode['children']:
                    if c.get('label') is None:
                        c['label'] = ALONE.get(verb, vnode['label'])
            if verb == 'examine' and len(vnode['children']) > GROUP_AT:
                vnode['children'] = _group_examine(vnode['children'], kinds)
            root['children'].append(vnode)
        root['children'] = [_fit(_mark_new(_collapse(c, collapse or self.collapse))) for c in root['children']]
        return _fit(root)

    def _kind(self, thing):
        """Where an examinable thing belongs in a long Examine menu."""
        if thing == 'you':
            return 'you'
        if thing in self.story.characters:
            return 'people'
        return 'carried' if self.state.locations.get(thing) == 'player' else 'here'

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
            return self.view(show_room=opt['verb'] == 'look', full=True)
        src = opt['source']
        answered = bool(src and src[0] == 'interaction' and self.moment_of(src[1]['id']))
        label = self.label_of(opt)
        moved_room, scene_before = self.perform(opt)
        self.timeline.append(st.clone())
        view = self.view(show_room=moved_room or st.scene != scene_before)
        text = view['text'] or ([_first_sentence(view['room']['text']) or _cap(view['room']['name']) + '.']
                                if view.get('room') else [])
        entry = {'label': label, 'text': text, 'turn': st.turns, 'scene': scene_before, 'scene_after': st.scene}
        if opt.get('weight'):
            entry['weight'] = opt['weight']
        if answered:
            entry['answered'] = True                  # the answer to a moment: a choice the journal keeps
        if st.ending:
            entry['ending'] = st.ending
        self.history.append(entry)
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
        changes_before = _changes(st)
        moved_room = False
        takes_time = None
        src = opt['source']
        if opt['verb'] in NEWS:
            st.heard.add(opt['id'])
        if opt['verb'] == 'talk' and opt.get('object') in s.characters:
            st.introduced.add(opt['object'])     # a first conversation is an introduction
        if src and src[0] == 'interaction':
            it = src[1]
            self.queue.append(pick_text(it.get('text'), st, it['id']))
            self._apply(it.get('effects'))
            if it.get('once'):
                st.used.add(it['id'])
            moment = self.moment_of(it['id'])
            if moment:                       # one answer closes the moment
                st.used.add(moment['id'])
                st.moments.pop(moment['id'], None)
            if 'takes_time' in it:
                takes_time = bool(it['takes_time'])
        elif src and src[0] == 'self':
            self.queue.append(pick_text(s.protagonist.get('description'), st, 'you'))
        elif src and src[0] == 'think':
            topic = s.protagonist['think'][src[1]]
            self.queue.append(pick_text(topic.get('says'), st, f'think.{src[1]}'))
            self._apply(topic.get('effects'))
            if topic.get('once'):
                st.used.add(f'think:{src[1]}')
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
                              or f'Nothing about {s.name_of(thing, st, short=False)} stands out.')
        elif opt['verb'] == 'take':
            obj = s.objects[opt['object']]
            st.locations[opt['object']] = 'player'
            self.queue.append(pick_text(obj.get('take_text'), st) or f"You take {obj.get('name', opt['object'])}.")
        elif opt['verb'] == 'wait':
            self.queue.append(pick_text(self.scene().get('wait_text'), st) or 'Time passes.')
        if takes_time is None:     # computed: time passes when something changed, you moved, or you waited
            takes_time = moved_room or opt['verb'] == 'wait' or _changes(st) != changes_before
        if takes_time:
            st.turns += 1
            st.turns_in_scene += 1
        st.actions = getattr(st, 'actions', 0) + 1
        scene_before = st.scene
        self._settle(progress_since=before)
        return moved_room, scene_before

    def label_of(self, opt):
        """An option as the menu path that names it: 'Talk › Lazlo Brandt › about the ledger'."""
        parts = [self.story.verbs.get(opt['verb'], opt['verb'])]
        if opt['object_label']:
            parts.append(opt['object_label'])
        if opt['detail_label']:
            parts.append(detail_text(opt['verb'], opt['detail_label'], opt.get('detail_free')))
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
            elif 'introduce' in eff:
                st.introduced.add(eff['introduce'])

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
                self._tick_moments()
            self._note_seen()
            target = self._exit_due()
            if target is None:
                return
            self._lapse_all()
            if target in self.story.endings:
                self._end(target)
                return
            self._enter_scene(target)
            self._note_seen()

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

    def _note_seen(self):
        """Who and what the player has now encountered: the people in the room
        and every object visible there."""
        st = self.state
        if st.ending or st.room is None:
            return
        st.seen.update(self.present())
        st.seen.update(self.visible_objects())

    def _offered(self, moment):
        by_id = {it['id']: it for it in self.scene().get('interactions') or []}
        return any(self._available(by_id[i]) for i in moment.get('options') or [] if i in by_id)

    def _tick_moments(self):
        """Count the actions since each open moment was first offered; an
        optional one lapses after its `after`."""
        st = self.state
        for m in self.moments():
            if m['id'] in st.used:
                continue
            if m['id'] in st.moments:
                st.moments[m['id']] += 1
            elif self._offered(m):
                st.moments[m['id']] = 0
            lapse = m.get('lapse')
            if not m.get('required') and lapse and st.moments.get(m['id'], -1) >= lapse.get('after', 4):
                self._lapse(m)

    def _lapse(self, m):
        st = self.state
        st.used.add(m['id'])
        st.moments.pop(m['id'], None)
        lapse = m.get('lapse') or {}
        if lapse.get('text'):
            self.queue.append(pick_text(lapse['text'], st, m['id']))
        self._apply(lapse.get('effects'))

    def _lapse_all(self):
        """Leaving a scene: every optional moment that was offered and never
        answered lapses. Only the first one's text is read: three closing
        lines about a scene the player has just left, before the next one
        opens, read as noise (kernel40, 2026-10-08)."""
        told = False
        for m in self.moments():
            if not m.get('required') and m['id'] not in self.state.used and m['id'] in self.state.moments:
                before = len(self.queue)
                self._lapse(m)
                if told:
                    del self.queue[before:]
                told = told or len(self.queue) > before

    def _exit_due(self):
        st = self.state
        if any(m.get('required') and m['id'] not in st.used for m in self.moments()):
            return None          # a required moment holds the scene until it is answered
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
                parts.append(self._named(text, group.get('about')))
        self.queue.extend(p for p in parts if p)

    def _named(self, text, cid):
        """A resolution line about a person that never says who ("He is gone,
        ..."): its opening pronoun becomes the person."""
        s = self.story
        if cid not in s.characters or f'{{{cid}}}' in text:
            return text
        names = [s.characters[cid].get('name'), s.characters[cid].get('unnamed')]
        if any(n and n.lower() in text.lower() for n in names):
            return text
        return re.sub(r'^(He|She|It)\b', '{' + cid + '}', text, count=1)

    # ------------------------------------------------------------ the view

    def describe(self, full=False):
        """The current room, layered: base description, the scene's layer,
        state fragments, then who and what is here. The base description is
        given the first time and on Look; after that, only what is particular
        to now."""
        s, st = self.story, self.state
        room = s.rooms.get(st.room) or {}
        full = full or f'room:{st.room}' not in st.heard
        st.heard.add(f'room:{st.room}')
        pre, post = [], []
        for frag in room.get('fragments') or []:
            if evaluate(frag.get('when', 'true'), st):
                (pre if frag.get('position') == 'pre' else post).append(frag['text'])
        scene_layer = pick_text((self.scene().get('room_text') or {}).get(st.room), st, f'{st.scene}.{st.room}')
        layers = pre + [self._still_true(pick_text(room.get('description'), st, st.room)) if full else '',
                        self._still_true(scene_layer)]
        layers += post
        plain = []
        for cid in self.present():
            if self._mentions(scene_layer, cid):
                continue                # the scene's own words for the room already place them, and know better
            line = self._here_line(cid)
            if line is None:
                plain.append(f'{{{cid}}}')
            else:
                layers.append(line)
        if plain:
            layers.append(f"{_join(plain)} {'is' if len(plain) == 1 else 'are'} here.")
        listed = [s.name_of(o) for o in self.visible_objects()
                  if st.locations.get(o) == st.room and s.objects[o].get('listed', s.objects[o].get('portable', False))]
        if listed:
            layers.append(f'You can see {_join(listed)}.')
        return {'name': room.get('name', st.room), 'text': s.render(' '.join(x for x in layers if x), st)}

    def _mentions(self, text, cid):
        """Whether text names this person: by code, name or unnamed label."""
        if not text:
            return False
        if f'{{{cid}}}' in text:
            return True
        ch = self.story.characters.get(cid) or {}
        low = text.lower()
        return any(n and re.search(r'\b' + re.escape(n.lower()) + r'\b', low)
                   for n in (ch.get('name'), ch.get('unnamed'), ch.get('unnamed_short')))

    def _here_line(self, cid):
        """How a present person appears in the room: the first `here` variant
        that holds and does not put them in another room (stage B writes these
        per person, by state, and some name a place: "the cat is asleep in the
        cabin", read on the deck); None when there is none (the room then says
        plainly who is here, in one sentence)."""
        s, st = self.story, self.state
        others = self._other_room_names()
        for v in s.characters[cid].get('here') or []:
            if isinstance(v, str):
                v = {'text': v}
            if not evaluate(v.get('when', 'true'), st):
                continue
            text = v.get('text', '')
            if isinstance(text, list):
                text = pick_text([v], st, cid)
            if text and not any(p.search(text.lower()) for p in others):
                return text
        return None

    def _other_room_names(self):
        """Patterns for the names of rooms other than this one ("the cabin"),
        leaving out any that are part of this room's own name."""
        s, st = self.story, self.state
        mine = str((s.rooms.get(st.room) or {}).get('name') or st.room).lower()
        out = []
        for rid, r in s.rooms.items():
            if rid == st.room:
                continue
            core = re.sub(r"^(the|a|an)\s+", '', str(r.get('name') or '').lower()).strip()
            if len(core) < 3 or core in mine:
                continue
            out.append(re.compile(r'\b(in|on|at|inside|into|by|from|near) (the |a |an )?' + re.escape(core) + r'\b'))
            head = core.split()[-1]         # "in the office" for the clean office, read in the square
            if len(head) >= 4 and head not in mine.split():
                out.append(re.compile(r"\b(in|inside|into) (the |a |an |his |her |their )?([\w']+ )?" + re.escape(head) + r'\b'))
        return out

    def _still_true(self, text):
        """Room text without the sentences about a portable thing that began
        in this room and has since gone (taken, given, moved): "The fountain
        pen lies on the desk" after you pocketed it."""
        if not text:
            return text
        s, st = self.story, self.state
        gone = []
        for oid, obj in s.objects.items():
            if obj.get('portable') and obj.get('location') == st.room and st.locations.get(oid) != st.room:
                core = re.sub(r"^(the|a|an|your|my)\s+", '', str(obj.get('name') or '').lower()).strip()
                if len(core) >= 3:
                    gone.append(re.compile(r'\b' + re.escape(core) + r'\b'))
        if not gone:
            return text
        kept = [x for x in SENTENCE.split(text) if not any(g.search(x.lower()) for g in gone)]
        return ' '.join(kept)

    def view(self, show_room=True, full=False):
        st = self.state
        out = {'text': [self.story.render(t, st) for t in self.queue if t], 'scene': st.scene, 'turns': st.turns,
               'ending': st.ending, 'room': None, 'menu': None}
        if st.ending:                     # one line per person: alike is not a repeat here, so only tidied
            out['text'] = [DOUBLED.sub(r'\1', t) for t in out['text']]
            out['ending_title'] = self.story.render(self.story.endings[st.ending].get('title'), st)
            return out
        out['room'] = self.describe(full) if show_room else None
        if out['room']:
            texts = _unrepeated(out['text'] + [out['room']['text']])
            out['text'], out['room'] = texts[:-1], dict(out['room'], text=texts[-1] if texts else '')
        else:
            out['text'] = _unrepeated(out['text'])
        out['text'] = [t for t in out['text'] if t]
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


def _changes(st):
    """What makes an action take time: a change to facts, counts, arcs or where
    things are (walking and waiting are counted separately)."""
    return (tuple(sorted(st.flags.items())), tuple(sorted(st.stats.items())),
            tuple(sorted((k, v['up'], v['down']) for k, v in st.arcs.items())),
            tuple(sorted((k, str(v)) for k, v in st.locations.items())))


def _signature(st):
    """What counts as progress: any change to facts, counts, arcs, where
    things are, or what has been used up. Walking about does not."""
    return (tuple(sorted(st.flags.items())), tuple(sorted(st.stats.items())),
            tuple(sorted((k, v['up'], v['down']) for k, v in st.arcs.items())),
            tuple(sorted((k, str(v)) for k, v in st.locations.items())), tuple(sorted(st.used)), st.scene)


NOUN_START = re.compile(r"^((the|a|an|your|my|his|her|their|its|our|this|that|these|those|some|one|two|what|who|whom|"
                        r"whose|why|how|where|when|whether|if)\b|[A-Z{'\"‘“])")


def _is_action(label, min_words=3):
    """An authored detail label that is an action in words ("step into the
    yard and hold the chain", "let the cat hold it"), not a thing or a
    subject ("the yard", "Viola", "what a nuisance costs"): such a label
    takes no preposition in the menu."""
    label = str(label or '').strip()
    return len(label.split()) >= min_words and not NOUN_START.match(label)


def _first_sentence(text):
    return SENTENCE.split(text or '')[0].strip()


def _cap(text):
    return text[:1].upper() + text[1:] if text else text


def _ngrams(text, n=4):
    w = WORD.findall(text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


STOP = set("""the a an and or but of to in on at by for with from into onto over under as is are was were be been
his her their its your you he she they it him them this that these those not no than then there here what
who which while when where so if all one has have had does do did said says just only still yet""".split())


def _content(text):
    """A sentence's content words, roughly stemmed ("comes" and "come" match)."""
    return {w.rstrip('s') for w in WORD.findall(text.lower()) if len(w) > 2 and w not in STOP}


def _unrepeated(texts):
    """The paragraphs of one view with each sentence that mostly repeats what
    was already read in this view dropped (a scene's opening, its first event
    and the room's scene layer often say the same thing three times), and
    doubled small words ("the the") made single. Keeps the list's length;
    a paragraph emptied becomes ''."""
    seen, words, out = set(), set(), []
    for text in texts:
        kept = []
        for sentence in SENTENCE.split(DOUBLED.sub(r'\1', text or '')):
            grams, content = _ngrams(sentence), _content(sentence)
            if len(grams) >= 3 and len(grams & seen) >= REPEAT_SHARE * len(grams):
                continue
            if len(content) >= 8 and len(content & words) >= PARAPHRASE_SHARE * len(content):
                continue                  # the same thing again in other words
            seen |= grams
            words |= content
            kept.append(sentence)
        out.append(' '.join(kept))
    return out


def detail_text(verb, label, free=False):
    """A detail as the menu shows it: 'about the ledger', 'on the crack',
    "say 'Boat held, sir'". A free-text detail that is not a quoted line is
    an action in its own words ("set the saddle between them") and takes no
    preposition ("on set the saddle..." before 2026-10-08)."""
    word = 'say' if label[:1] in '\'"‘“' else (None if free else DETAIL_WORD.get(verb))
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


def _group_examine(children, kinds):
    """A long Examine: yourself first, then people, things you carry and
    things here, each a submenu (a group of one stays a plain entry)."""
    out = [c for c, k in zip(children, kinds) if k in (None, 'you')]
    for kind, label in EXAMINE_GROUPS:
        members = [c for c, k in zip(children, kinds) if k == kind]
        if len(members) == 1:
            out.append(members[0])
        elif members:
            out.append({'label': label, 'children': members})
    return out


def _fit(node, limit=len(KEYS)):
    """A level with more entries than there are keys to pick them with ends
    in a 'more…' entry holding the rest (a front end shows only what it can
    key; the plain player dropped the 29th entry and on before 2026-10-08)."""
    if 'children' not in node:
        return node
    kids = [_fit(c, limit) for c in node['children']]
    if len(kids) > limit:
        rest = {'label': MORE, 'children': kids[limit - 1:]}
        if any(c.get('new') for c in rest['children']):
            rest['new'] = True
        kids = kids[:limit - 1] + [_fit(rest, limit)]
    return dict(node, children=kids)


def _mark_new(node):
    """A menu node is new when anything under it is."""
    if 'children' in node:
        node['children'] = [_mark_new(c) for c in node['children']]
        if any(c.get('new') for c in node['children']):
            node['new'] = True
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
