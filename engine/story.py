"""The story package: loading, text selection, and static validation.

A package is one JSON document (format "stratum-story/1", see
docs/engine_design.md §3-§5). It is read-only at play time. `validate`
checks everything that can be checked without playing: every id resolves,
every condition parses and names things that exist, every flag a condition
reads is set somewhere, every scene and ending is reachable from the start.
"""

import hashlib
import re
import json
import random

from expressions import ExpressionError, references

FORMAT = 'stratum-story/1'

CORE_VERBS = {
    'look': 'Look', 'examine': 'Examine', 'go': 'Go', 'talk': 'Talk', 'take': 'Take', 'give': 'Give',
    'show': 'Show', 'use': 'Use', 'think': 'Think', 'wait': 'Wait', 'inventory': 'Inventory',
}
VERB_ORDER = ('look', 'examine', 'go', 'talk', 'take', 'give', 'show', 'use', 'think', 'wait', 'inventory')
EFFECT_KEYS = ('set', 'clear', 'add', 'move', 'give', 'take', 'place', 'room', 'introduce')
CODE = re.compile(r'\{([A-Za-z_]\w*)\}')     # a person in text: {C02}, rendered by what the player knows
SHORT_CUT = re.compile(r"\s+(in|with|on|at|from|of|by|who|that|whose|near|under|beside)\s|,")


class StoryError(ValueError):
    pass


def pick_text(variants, state, salt=''):
    """The first variant whose `when` holds. A variant's text may be a list,
    one entry chosen deterministically from the state's seed (the same step
    always shows the same choice, so a rewind replays it)."""
    from expressions import evaluate
    if isinstance(variants, str):
        return variants
    for v in variants or []:
        if isinstance(v, str):
            return v
        if evaluate(v.get('when', 'true'), state):
            text = v.get('text', '')
            if isinstance(text, list):
                if not text:
                    return ''
                key = hashlib.md5(('|'.join(text) + salt).encode('utf-8')).hexdigest()
                return random.Random(f'{state.seed}|{key}').choice(text)
            return text
    return ''


class Story:
    def __init__(self, data):
        if data.get('format') != FORMAT:
            raise StoryError(f"not a {FORMAT} package (format is {data.get('format')!r})")
        self.data = data
        self.id = data.get('story_id', '')
        self.title = data.get('title', self.id)
        world = data.get('world') or {}
        self.rooms = world.get('rooms') or {}
        self.objects = world.get('objects') or {}
        self.characters = world.get('characters') or {}
        self.scenes = data.get('scenes') or {}
        self.endings = data.get('endings') or {}
        self.states = data.get('states') or {}
        self.start = data.get('start') or {}
        self.protagonist = data.get('protagonist') or {}
        self.verbs = dict(CORE_VERBS)
        for vid, v in (data.get('verbs') or {}).items():
            self.verbs[vid] = (v or {}).get('label') or vid.capitalize()
        self.hash = package_hash(data)

    @staticmethod
    def load(path):
        with open(path, encoding='utf-8') as f:
            return Story(json.load(f))

    def name_of(self, thing, state=None, short=True):
        """A thing's name. A character with an `unnamed` label goes by it
        (its short form in menus) until the player is introduced, when a
        state is given."""
        if thing == 'you':
            return 'yourself'
        if thing in self.characters and state is not None and not self.known(thing, state):
            ch = self.characters[thing]
            return self.short_unnamed(thing) if short else ch['unnamed']
        for table in (self.objects, self.characters, self.rooms):
            if thing in table:
                return table[thing].get('name') or thing
        return thing

    def short_unnamed(self, cid):
        """The short form of a person's unnamed label: `unnamed_short`, else
        the label cut before its first qualifying phrase ("the captain in the
        wet canvas coat" -> "the captain"), when that leaves a noun phrase."""
        ch = self.characters.get(cid) or {}
        if ch.get('unnamed_short'):
            return ch['unnamed_short']
        label = ch.get('unnamed') or ''
        m = SHORT_CUT.search(label)
        cut = label[:m.start()].strip() if m else label
        return cut if len(cut.split()) >= 2 else label

    def known(self, cid, state):
        """Whether the player knows this person's name: introduced in play,
        marked known from the start, or never given an unnamed label."""
        ch = self.characters.get(cid) or {}
        return cid in state.introduced or bool(ch.get('known')) or not ch.get('unnamed')

    def render(self, text, state, sentence=True):
        """Text with each {Cxx} replaced by the name the player knows the
        person by. An unnamed label is given in full the first time a text
        names the person and short after that, and short before "'s" ("the
        captain in the wet canvas coat" five times in one paragraph; "the wet
        lock-keeper with a wrench's papers"). A name opening a sentence is
        capitalised, unless `sentence` is False (a menu label: "about the
        captain")."""
        if not text or '{' not in text:
            return text
        told = set()

        def one(m):
            cid = m.group(1)
            if cid not in self.characters:
                return m.group(0)
            long_form = cid not in told and not text.startswith("'s", m.end())
            name = self.name_of(cid, state, short=not long_form)
            told.add(cid)
            before = text[:m.start()].rstrip(' \'"‘“')
            if sentence and (not before or before[-1] in '.!?:—'):
                name = name[:1].upper() + name[1:]
            return name
        return CODE.sub(one, text)

    def verb_rank(self, verb):
        return VERB_ORDER.index(verb) if verb in VERB_ORDER else VERB_ORDER.index('wait') - 0.5


def package_hash(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------- validation

def validate(story):
    """(errors, notes). Errors make the package unplayable or wrong; notes
    are craft warnings (a story verb used once, an object with nothing to say
    when examined, a flag set but never read)."""
    errors, notes = [], []
    s = story
    flags_set, flags_read = set(), set()
    moment_ids = set()           # (moment id, where) read by answered()
    declared_moments = set()
    verb_uses = {}

    def check_expr(where, text):
        try:
            refs = references(text)
        except ExpressionError as e:
            errors.append(f'{where}: {e}')
            return
        flags_read.update((f, where) for f in refs['flags'])
        for name in refs['states']:
            if name not in s.states:
                errors.append(f'{where}: pattern on undeclared state {name!r}')
        for stat in refs['stats']:
            base = stat.rsplit('_', 1)[0]
            if stat.endswith(('_up', '_down')) and base not in s.states:
                errors.append(f'{where}: stat {stat!r} looks like an arc state but {base!r} is not declared')
        for kind, table in (('objects', s.objects), ('rooms', s.rooms), ('chars', s.characters), ('scenes', s.scenes)):
            for x in refs[kind]:
                if x not in table:
                    errors.append(f'{where}: names unknown {kind[:-1]} {x!r}')
        for x in refs['visited']:
            if x not in s.rooms and x not in s.scenes:
                errors.append(f'{where}: visited() names neither a room nor a scene: {x!r}')
        for x in refs['seen']:
            if x not in s.characters and x not in s.objects:
                errors.append(f'{where}: seen() names neither a character nor an object: {x!r}')
        moment_ids.update((x, where) for x in refs['moments'])

    def check_variants(where, variants):
        if isinstance(variants, str):
            return
        for i, v in enumerate(variants or []):
            if isinstance(v, dict) and 'when' in v:
                check_expr(f'{where}[{i}]', v['when'])

    def check_effects(where, effects):
        for eff in effects or []:
            keys = [k for k in EFFECT_KEYS if k in eff]
            if len(keys) != 1:
                errors.append(f'{where}: an effect needs exactly one of {", ".join(EFFECT_KEYS)}: {eff}')
                continue
            k = keys[0]
            v = eff[k]
            if k == 'set':
                flags_set.add(v)
            elif k == 'move':
                if v not in s.states:
                    errors.append(f'{where}: moves undeclared state {v!r}')
                if eff.get('dir') not in ('up', 'down'):
                    errors.append(f"{where}: move needs dir 'up' or 'down'")
            elif k == 'add' and not isinstance(eff.get('by', 1), (int, float)):
                errors.append(f'{where}: add needs a number in by')
            elif k == 'place' and v not in s.objects and v not in s.characters:
                errors.append(f'{where}: place names unknown object or character {v!r}')
            elif k in ('give', 'take') and v not in s.objects:
                errors.append(f'{where}: {k} names unknown object {v!r}')
            elif k == 'place' and eff.get('to') not in (None, 'player', *s.rooms, *s.characters):
                errors.append(f"{where}: place to unknown location {eff.get('to')!r}")
            elif k == 'room' and v not in s.rooms:
                errors.append(f'{where}: moves the player to unknown room {v!r}')
            elif k == 'introduce' and v not in s.characters:
                errors.append(f'{where}: introduces unknown character {v!r}')

    # people in text are codes that name characters
    def codes(x):
        if isinstance(x, str):
            yield from CODE.findall(x)
        elif isinstance(x, dict):
            for v in x.values():
                yield from codes(v)
        elif isinstance(x, list):
            for v in x:
                yield from codes(v)
    for code in sorted(set(codes(s.data)) - set(s.characters)):
        errors.append(f'text names {{{code}}}, which is not a character')

    # start
    if s.start.get('scene') not in s.scenes:
        errors.append(f"start scene {s.start.get('scene')!r} does not exist")
    if s.start.get('room') and s.start['room'] not in s.rooms:
        errors.append(f"start room {s.start.get('room')!r} does not exist")

    # you
    you = s.protagonist
    check_variants('protagonist description', you.get('description'))
    for tid, topic in (you.get('think') or {}).items():
        check_expr(f'think {tid}', topic.get('known_when', 'true'))
        check_variants(f'think {tid} says', topic.get('says'))
        check_effects(f'think {tid}', topic.get('effects'))
        if not topic.get('says'):
            errors.append(f'think {tid}: says nothing')
    if 'you' in s.objects or 'you' in s.characters:
        errors.append('"you" is reserved for the player; no object or character may use it as an id')

    for name, st in s.states.items():
        if not isinstance(st, dict) or not st.get('meaning'):
            notes.append(f'state {name}: no meaning given')

    # world
    for rid, room in s.rooms.items():
        check_variants(f'room {rid} description', room.get('description'))
        if not room.get('description'):
            notes.append(f'room {rid}: no description')
        for i, frag in enumerate(room.get('fragments') or []):
            check_expr(f'room {rid} fragment {i}', frag.get('when', 'true'))
        for ex in room.get('exits') or []:
            if ex.get('to') not in s.rooms:
                errors.append(f"room {rid}: exit to unknown room {ex.get('to')!r}")
            if 'when' in ex:
                check_expr(f"room {rid} exit to {ex.get('to')}", ex['when'])
    for oid, obj in s.objects.items():
        loc = obj.get('location')
        if loc not in (None, 'player', *s.rooms, *s.characters):
            errors.append(f'object {oid}: location {loc!r} is not a room, character or the player')
        check_variants(f'object {oid} description', obj.get('description'))
        if 'when' in obj:
            check_expr(f'object {oid} visibility', obj['when'])
        if not obj.get('description'):
            notes.append(f'object {oid}: nothing to say when examined')
        if oid in s.rooms or oid in s.characters:
            errors.append(f'object {oid}: id also used by a room or character')
    for cid, ch in s.characters.items():
        for key in ('unnamed', 'unnamed_short'):
            if key in ch and not (isinstance(ch[key], str) and ch[key].strip()):
                errors.append(f'character {cid}: {key} must be a non-empty string')
        if 'unnamed_short' in ch and 'unnamed' not in ch:
            errors.append(f'character {cid}: unnamed_short without unnamed')
        check_variants(f'character {cid} description', ch.get('description'))
        check_variants(f'character {cid} here', ch.get('here'))
        if not ch.get('description'):
            notes.append(f'character {cid}: nothing to say when examined')
        if cid in s.rooms:
            errors.append(f'character {cid}: id also used by a room')
        for tid, topic in (ch.get('topics') or {}).items():
            check_expr(f'character {cid} topic {tid}', topic.get('known_when', 'true'))
            check_variants(f'character {cid} topic {tid} says', topic.get('says'))
            check_effects(f'character {cid} topic {tid}', topic.get('effects'))
            if not topic.get('says'):
                errors.append(f'character {cid} topic {tid}: says nothing')

    # scenes
    ids = set()
    graph = {}
    for sid, sc in s.scenes.items():
        where = f'scene {sid}'
        rooms = sc.get('rooms') or []
        if not rooms:
            errors.append(f'{where}: opens no rooms')
        for r in rooms:
            if r not in s.rooms:
                errors.append(f'{where}: unknown room {r!r}')
        if sc.get('start_room') and sc['start_room'] not in rooms:
            errors.append(f"{where}: start_room {sc['start_room']!r} is not one of its rooms")
        for cid, r in (sc.get('cast') or {}).items():
            if cid not in s.characters:
                errors.append(f'{where}: cast names unknown character {cid!r}')
            if r not in rooms:
                errors.append(f'{where}: places {cid} in {r!r}, not one of its rooms')
        check_variants(f'{where} opening', sc.get('opening'))
        check_variants(f'{where} recap', sc.get('recap'))
        for r, variants in (sc.get('room_text') or {}).items():
            if r not in rooms:
                errors.append(f'{where}: room_text for {r!r}, not one of its rooms')
            check_variants(f'{where} room_text {r}', variants)
        for it in sc.get('interactions') or []:
            iid = it.get('id')
            iw = f'{where} interaction {iid}'
            if not iid:
                errors.append(f'{where}: an interaction has no id ({it.get("verb")} {it.get("object")})')
            elif iid in ids:
                errors.append(f'{iw}: duplicate id')
            ids.add(iid)
            verb = it.get('verb')
            if verb not in s.verbs:
                errors.append(f'{iw}: verb {verb!r} is neither core nor declared in verbs')
            verb_uses.setdefault(verb, []).append(iid)
            for part in ('object', 'detail'):
                x = it.get(part)
                if x is not None and x not in s.objects and x not in s.characters and x not in s.rooms \
                        and not (part == 'detail' and it.get('object') in s.characters
                                 and x in (s.characters[it['object']].get('topics') or {})):
                    if not (isinstance(it.get(part + '_label'), str)):
                        errors.append(f'{iw}: {part} {x!r} is not an object, character, room or topic '
                                      f'(give a {part}_label to use free text)')
            if it.get('room') is not None and it['room'] not in rooms:
                errors.append(f"{iw}: room {it['room']!r} is not one of the scene's rooms")
            if it.get('object') is None and it.get('detail') is not None:
                errors.append(f'{iw}: a detail without an object')
            check_expr(iw, it.get('when', 'true'))
            check_effects(iw, it.get('effects'))
            if it.get('weight') not in (None, 'major'):
                errors.append(f"{iw}: weight must be 'major' or absent, not {it.get('weight')!r}")
            if 'takes_time' in it and not isinstance(it['takes_time'], bool):
                errors.append(f'{iw}: takes_time must be true or false')
            if not it.get('text'):
                errors.append(f'{iw}: no text')
        for ev in list(sc.get('events') or []) + list(sc.get('nudges') or []):
            ew = f"{where} event {ev.get('id')}"
            if not ev.get('id'):
                errors.append(f'{where}: an event or nudge has no id')
            elif ev['id'] in ids:
                errors.append(f'{ew}: duplicate id')
            ids.add(ev.get('id'))
            if 'when' in ev:
                check_expr(ew, ev['when'])
            elif 'after' not in ev:
                errors.append(f'{ew}: needs when (an event) or after (a nudge)')
            check_effects(ew, ev.get('effects'))
        own = {it.get('id') for it in sc.get('interactions') or []}
        in_moment = {}
        for m in sc.get('moments') or []:
            mw = f"{where} moment {m.get('id')}"
            if not m.get('id'):
                errors.append(f'{where}: a moment has no id')
                continue
            if m['id'] in ids:
                errors.append(f'{mw}: duplicate id')
            ids.add(m['id'])
            declared_moments.add(m['id'])
            options = m.get('options') or []
            if len(options) < 2:
                errors.append(f'{mw}: a moment offers at least two options')
            for o in options:
                if o not in own:
                    errors.append(f'{mw}: option {o!r} is not an interaction of this scene')
                if o in in_moment:
                    errors.append(f'{mw}: option {o!r} is already in moment {in_moment[o]}')
                in_moment[o] = m['id']
            if m.get('required'):
                if m.get('neutral') not in options:
                    errors.append(f'{mw}: a required moment names a neutral option among its options, so the choice '
                                  f'is offered and never forced one way')
                if m.get('lapse'):
                    errors.append(f'{mw}: a required moment cannot lapse')
            else:
                lapse = m.get('lapse')
                if not isinstance(lapse, dict) or not isinstance(lapse.get('after', 4), int):
                    errors.append(f'{mw}: an optional moment needs a lapse ({{after, text, effects}}): walking away '
                                  f'is its own answer')
                else:
                    check_effects(f'{mw} lapse', lapse.get('effects'))
        exits = sc.get('exits') or []
        graph[sid] = []
        for ex in exits:
            to = ex.get('to')
            if to not in s.scenes and to not in s.endings:
                errors.append(f'{where}: exit to unknown scene or ending {to!r}')
            check_expr(f'{where} exit to {to}', ex.get('when', 'true'))
            graph[sid].append(to)
        if not exits:
            errors.append(f'{where}: no exits (only endings may end the story)')
    for eid, end in s.endings.items():
        if eid in s.scenes:
            errors.append(f'ending {eid}: id also used by a scene')
        check_variants(f'ending {eid} text', end.get('text'))
        for gi, group in enumerate(ending_groups(end)):
            check_variants(f'ending {eid} resolution {gi}', group.get('variants'))
        if not end.get('text'):
            errors.append(f'ending {eid}: no text')

    for m, where in sorted(moment_ids):
        if m not in declared_moments:
            errors.append(f'{where}: answered() names unknown moment {m!r}')

    # every flag read is set somewhere
    for flag, where in sorted(flags_read):
        if flag not in flags_set and flag not in (s.data.get('initial_flags') or {}):
            errors.append(f'{where}: reads flag {flag!r}, which nothing sets')
    read = {f for f, _ in flags_read}
    for flag in sorted(flags_set - read):
        notes.append(f'flag {flag!r} is set but nothing reads it')

    # reachability over scene exits
    start = s.start.get('scene')
    seen, todo = set(), [start]
    while todo:
        x = todo.pop()
        if x in seen or x is None:
            continue
        seen.add(x)
        todo.extend(graph.get(x, []))
    for sid in s.scenes:
        if sid not in seen:
            errors.append(f'scene {sid}: not reachable from the start')
    for eid in s.endings:
        if eid not in seen:
            errors.append(f'ending {eid}: not reachable from the start')

    # people named by the world's own text before anything has introduced them
    notes.extend(unintroduced(s))

    # story verbs used once point at the solution
    for verb, uses in verb_uses.items():
        if verb not in CORE_VERBS and len(uses) == 1:
            notes.append(f'story verb {verb!r} is used by one interaction only ({uses[0]}): it may point at the solution')
    for vid in s.verbs:
        if vid not in CORE_VERBS and vid not in verb_uses:
            notes.append(f'story verb {vid!r} is declared but never used')
    return errors, notes


TITLES = {'Captain', 'Doctor', 'Lady', 'Lord', 'Master', 'Mister', 'Miss', 'Sister', 'Brother', 'Father', 'Mother'}


def texts_of(variants):
    if isinstance(variants, str):
        return [variants]
    out = []
    for v in variants or []:
        t = v if isinstance(v, str) else v.get('text', '')
        out.extend(t if isinstance(t, list) else [t])
    return out


def unintroduced(s):
    """Notes for event and nudge text that names a character no earlier text
    has introduced: the intro, or the opening of this scene or of a scene
    before it (breadth-first from the start). An event fires wherever the
    player is, so 'Pell's shouting grows louder' means nothing to a player
    who has not been told who Pell is."""
    import re
    parts = {}
    for cid, ch in s.characters.items():
        words = [w for w in re.findall(r"[A-Z][a-z']+", ch.get('name', '')) if w not in TITLES and len(w) > 2]
        parts[cid] = set(words)

    def named(text):
        found = set(re.findall(r"[A-Z][a-z']+", text))
        return {cid for cid, ws in parts.items() if ws & found}

    known = set()
    for t in texts_of(s.data.get('intro')):
        known |= named(t)
    order, seen, todo = [], set(), [s.start.get('scene')]
    while todo:
        x = todo.pop(0)
        if x in seen or x not in s.scenes:
            continue
        seen.add(x)
        order.append(x)
        todo.extend(ex.get('to') for ex in s.scenes[x].get('exits') or [])
    notes = []
    for sid in order:
        sc = s.scenes[sid]
        for t in texts_of(sc.get('opening')):
            known |= named(t)
        for ev in list(sc.get('events') or []) + list(sc.get('nudges') or []):
            for t in texts_of(ev.get('text')):
                for cid in sorted(named(t) - known):
                    notes.append(f"scene {sid} event {ev.get('id')}: names {s.characters[cid].get('name', cid)}, "
                                 f'whom nothing has introduced yet (the intro or a scene opening should)')
    return notes


def ending_groups(end):
    """An ending's resolution groups: [{'about': who, 'variants': [...]}].
    A bare `variants` list is one group."""
    groups = list(end.get('resolutions') or [])
    if end.get('variants'):
        groups.insert(0, {'about': None, 'variants': end['variants']})
    return groups
