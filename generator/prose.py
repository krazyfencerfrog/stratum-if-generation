#!/usr/bin/env python3
"""The prose stage (docs/later_stages.md §6): an editing pass over the text
stages B and D already wrote, in one voice per story.

    python prose.py <story_id>     # on a directory with <id>_package_draft.json; writes <id>_package.json

1. 8a, the style sheet: the voice for THIS story (tradition, person and
   tense, register, rhythm, how each person speaks, recurring images, what
   to avoid, where length pays) ending in a sample paragraph every later
   call matches. Checked in Python and by one cheap call (8v); a sheet the
   check faults is written once more with its problems.
2. 8b, the edits, part by part: each scene in story order (with what the
   player has already read: openings so far and images spent), then each
   person, each location, then the endings, the opening and "you". Only
   text fields are sent and only text fields come back, by id, so the
   structure cannot change; the checks below cost one informed retry.
3. Names: every named person gets an `unnamed` label (the role, or the
   person call's description) and `known` when the protagonist already
   knows them (a relative, "your ..."); every literal name in text and
   labels becomes a code ({C02}) that the engine renders by what the player
   knows. A first conversation introduces a person (engine/runtime.py).
The result is validated by the engine and written beside the package.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import sys

import example_guard
import schemas
import checks
import stats
from errors import SoftReject

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(THIS_DIR, '..', 'engine')

TARGETS = {'room': 60, 'action': 50, 'opening': 90, 'ending': 150, 'other': 80, 'unnamed': 8, 'recap': 40, 'dialogue': 45}
CHUNK = 40                    # texts per call: a person with every state and subject is split
CODE = re.compile(r'\{([A-Za-z_]\w*)\}')
NAME_KEYS = ('text', 'label', 'detail_label', 'object_label', 'title')   # where a literal name becomes a code


def proper_name(name):
    """A name names.py gave a person, not a role kept in the name field
    ("the cat"): no leading article, and some word capitalized. On
    2026-10-06 "the cat" was taken for a first and last name and every
    "the" in kernel35's package became the cat's code."""
    words = str(name or '').split()
    return bool(words) and words[0].lower() not in ('the', 'a', 'an', 'your') and any(w[:1].isupper() for w in words)


def name_parts(name):
    """The first and last word of a proper name, where each could stand
    alone for the person: capitalized and longer than two letters."""
    bits = str(name).split()
    return [b for b in ((bits[0], bits[-1]) if len(bits) > 1 else ()) if b[:1].isupper() and len(b) > 2]
REPEAT_N = 5                  # a run of this many words shared with an earlier part is a repeat

GUIDANCE = {
    'scene': "THIS PART is one scene: its opening (the first thing read on arrival: put the player in the room and "
             "the moment, with who is here; it tells the world, never a deed the player did not choose), what each of its actions does (the response to choosing it), how its "
             "rooms read during it, the events that happen on their own, the nudges if the player idles, and its "
             "journal entry ('recap': what the scene put before the player, for the story-so-far page; describe the circumstance, dilemma, or situation found here—NEVER describe what the player chose or did (no 'You took...', 'You let...', 'You signed...'), because the journal records player choices separately beneath it).",
    'person': "THIS PART is one person: how they look (by their state), the line the room shows them by ('here': what "
              "they are doing or holding when found, never where they are, since each scene places them and the line "
              "is read in every room they turn up in), "
              "and what they say on each subject in conversation topics ('topics'). "
              "CRITICAL FOR DIALOGUE: The lines under 'topics' are spoken directly by this person. Revise their spoken lines strictly in "
              "this person's own voice, vocabulary, and rhythm (see 'voice' and 'breaking_point' in this part), NOT in the story narrator's voice. "
              "Preserve their distinctive idioms, sentence length, and attitude. "
              "'unnamed' is how the player sees them before learning their name: a short phrase, three to eight words, starting with 'the' or 'a', "
              "what you would notice first ('the old man in the captain's coat').",
    'place': "THIS PART is one location: each room's description (given on the first visit and on Look, so it is "
             "the room itself, not this moment), its state fragments, and the things in it as they read when "
             "examined.",
    'rest': "THIS PART is the story's frame: the opening of the story, how you see yourself and what you think "
            "about, and the endings with what becomes of each person. An ending shows the world left behind; it "
            "never sums up what it meant or what it cost.",
}


def as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def text_paths(node, path=()):
    """Every (path, text) for a string under a 'text' key (a list of
    alternatives gives one path per entry)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == 'text' and isinstance(v, str):
                yield path + (k,), v
            elif k == 'text' and isinstance(v, list) and all(isinstance(x, str) for x in v):
                for i, x in enumerate(v):
                    yield path + (k, i), x
            else:
                yield from text_paths(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from text_paths(v, path + (i,))


def get_at(node, path):
    for p in path:
        node = node[p]
    return node


def set_at(node, path, value):
    for p in path[:-1]:
        node = node[p]
    node[path[-1]] = value


def words(text):
    return re.findall(r"[a-z0-9']+", str(text).lower())


QUOTES = ("'", '"', '“', '”', '‘', '’')


def validate_dialogue_text(original, revised):
    """Checks character dialogue: returns list of soft issue strings, or empty list."""
    issues = []
    orig_stripped = (original or '').strip()
    rev_stripped = (revised or '').strip()
    if any(orig_stripped.startswith(q) or orig_stripped.endswith(q) for q in QUOTES) and not any(
        rev_stripped.startswith(q) or rev_stripped.endswith(q) for q in QUOTES
    ):
        issues.append("character dialogue should remain spoken dialogue in quotation marks, not indirect narration")
    inner = rev_stripped.strip("'\"“”‘’").strip()
    if re.match(r"^you\s+(?:ask|tell|look|say|nod|watch|listen|step|walk)\b", inner, re.I):
        issues.append("narrates player action instead of speaking the character's line; write what the character says aloud")
    return issues


class ProseWriter:
    def __init__(self, gen, package, story=None):
        self.gen = gen
        self.original = package
        self.pkg = copy.deepcopy(package)
        self.story = story or {}
        self.chars = self.pkg['world'].get('characters') or {}
        self.spent, self.openings, self.read_so_far = [], [], []
        self.findings = []

    # ------------------------------------------------------------ the people

    def people(self):
        out = []
        cast = {norm_role(c.get('label')): c for c in (self.story.get('characters') or {}).values()}
        seeds = {norm_role(s.get('role')): s for s in (self.story.get('premise', {}).get('cast_seeds') or []) if isinstance(s, dict)}
        for cid, c in self.chars.items():
            role_key = norm_role(c.get('role'))
            seed = cast.get(role_key) or seeds.get(role_key) or {}
            out.append({'code': cid, 'name': c.get('name'), 'role': c.get('role'),
                        'voice': seed.get('voice') or c.get('voice'),
                        'breaking_point': seed.get('breaking_point') or c.get('breaking_point'),
                        'edge': seed.get('edge') or c.get('edge'),
                        'known_to_you': bool(c.get('known') or not c.get('unnamed'))})
        return out

    def prepare_names(self):
        """A named person the protagonist does not already know goes by their
        role until introduced; a relative or a 'your ...' is known."""
        premise = (self.story.get('premise') or {}) if isinstance(self.story, dict) else {}
        prot = premise.get('protagonist') or {}
        prot_ties = {norm_role(t.get('who')) for t in (prot.get('ties') or []) if isinstance(t, dict)}
        seed_ties = {
            norm_role(s.get('role')): (s.get('tie') or '').lower()
            for s in (premise.get('cast_seeds') or []) if isinstance(s, dict)
        }

        for cid, c in self.chars.items():
            if not proper_name(c.get('name')) or c.get('unnamed'):
                continue
            role = str(c.get('role') or '').strip()
            role_norm = norm_role(role)
            name_norm = norm_role(c.get('name'))
            role_lower = role.lower()

            tie_text = seed_ties.get(role_norm, '')
            is_known = (
                bool(c.get('known'))
                or any(role_lower.startswith(p) for p in ('your ', 'tu ', 'su '))
                or role_norm in prot_ties
                or name_norm in prot_ties
                or any(w in tie_text for w in ('you', 'your', 'protagonist', 'tú', 'tu'))
            )
            if is_known:
                c['known'] = True
            c['unnamed'] = role or 'a stranger'

    def convert_names(self):
        """Every literal name in text and labels becomes the person's code:
        the full name, and the first or last name where no one else shares it."""
        named = {cid: c['name'] for cid, c in self.chars.items() if proper_name(c.get('name'))}
        parts = {}
        for cid, name in named.items():
            for b in name_parts(name):
                parts.setdefault(b, set()).add(cid)
        forms = []
        for cid, name in named.items():
            forms.append((name, cid))
            forms += [(b, cid) for b in name_parts(name) if len(parts[b]) == 1]
        forms.sort(key=lambda f: -len(f[0]))
        if not forms:
            return
        rx = re.compile(r"(?<![\w{])(" + '|'.join(re.escape(f) for f, _ in forms) + r")(?![\w}])")
        lookup = dict(forms)

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in NAME_KEYS and isinstance(v, str):
                        node[k] = rx.sub(lambda m: '{' + lookup[m.group(1)] + '}', v)
                    elif k in NAME_KEYS and isinstance(v, list) and all(isinstance(x, str) for x in v):
                        node[k] = [rx.sub(lambda m: '{' + lookup[m.group(1)] + '}', x) for x in v]
                    elif k != 'name':
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        for key in ('intro', 'protagonist', 'scenes', 'endings'):
            walk(self.pkg.get(key))
        for table in ('rooms', 'objects', 'characters'):
            walk(self.pkg['world'].get(table))

    # ------------------------------------------------------------ 8a: the voice

    def sample_text(self):
        first = next(iter(self.pkg['scenes'].values()), {})
        bits = [t for _, t in text_paths(first.get('opening'))][:1]
        bits += [it.get('text') for it in (first.get('interactions') or [])[:4] if isinstance(it.get('text'), str)]
        room = self.pkg['world']['rooms'].get(first.get('start_room')) or {}
        bits += [t for _, t in text_paths(room.get('description'))][:1]
        return '\n'.join(f'- {b}' for b in bits if b)

    def style(self):
        people = self.people()

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            missing = [k for k in ('person_tense', 'register', 'rhythm', 'sample') if not str(parsed.get(k) or '').strip()]
            if missing:
                raise ValueError(f'missing: {missing}')
            parsed['voices'] = [v for v in as_list(parsed.get('voices')) if isinstance(v, dict) and v.get('who')]
            for k in ('images', 'avoid'):
                parsed[k] = [str(x) for x in as_list(parsed.get(k)) if str(x).strip()]
            soft = []
            n = len(words(parsed['sample']))
            if not 60 <= n <= 220:
                soft.append(f'the sample is {n} words; write one paragraph of 80 to 160')
            # Person, tense, tone, and register delivery are verified semantically
            # by s8v_style_check.prompt, retiring brittle pronoun regex heuristics.
            said = ' '.join(str(v.get('who')) for v in parsed['voices']).lower()
            silent = [p['name'] or p['role'] for p in people if p['name'] and p['name'].split()[0].lower() not in said
                      and str(p['role']).lower() not in said]
            if silent:
                soft.append(f'no voice for {silent}')
            if soft:
                raise SoftReject('; '.join(soft))
        fields = {'$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PROMISES$$': self.gen.promises_block(),
                  '$$PEOPLE$$': json.dumps([{k: p[k] for k in ('name', 'role', 'voice')} for p in people], ensure_ascii=False),
                  '$$SAMPLE_TEXT$$': self.sample_text()}
        style = self.gen.run_prompt('s8a', 'style', fields, prompt_file='s8a_style.prompt', validator=validate,
                                    klass='build', schema=schemas.STYLE)
        check = self.gen.run_prompt('s8v', 'style_check', {
            '$$KERNEL$$': self.gen.kernel, '$$TONE$$': self.gen.tone_line(), '$$PROMISES$$': self.gen.promises_block(),
            '$$STYLE_JSON$$': json.dumps(style, ensure_ascii=False, indent=1)},
            prompt_file='s8v_style_check.prompt', validator=check_validator, klass='classify', schema=schemas.STYLE_CHECK)
        if check['problems'] and not check['delivers']:
            self.findings.append(f"8v: {'; '.join(check['problems'])}")
            fields['$$SAMPLE_TEXT$$'] += ('\n\nA first style sheet was checked and these problems found; write it '
                                          'again without them:\n' + '\n'.join(f'- {p}' for p in check['problems']))
            style = self.gen.run_prompt('s8a_r1', 'style', fields, prompt_file='s8a_style.prompt', validator=validate,
                                        klass='build', schema=schemas.STYLE)
        self.style_sheet = style
        return style

    # ------------------------------------------------------------ 8b: the parts

    def units(self):
        """(unit id, kind, title, [paths]) in reading order; every text path
        is in exactly one."""
        pkg = self.pkg
        seen = set()
        out = []

        def take(paths):
            got = [p for p in paths if p not in seen]
            seen.update(got)
            return got
        all_paths = [p for p, _ in text_paths(pkg)]
        for sid, sc in pkg['scenes'].items():
            out.append((sid, 'scene', sc.get('title') or sid, take([p for p in all_paths if p[:2] == ('scenes', sid)])))
        for cid in self.chars:
            out.append((cid, 'person', self.chars[cid].get('name') or self.chars[cid].get('role'),
                        take([p for p in all_paths if p[:3] == ('world', 'characters', cid)])))
        rooms = pkg['world']['rooms']
        objects = pkg['world'].get('objects') or {}
        by_loc = {}
        for rid, r in rooms.items():
            by_loc.setdefault(r.get('location') or rid, []).append(rid)
        for loc, rids in by_loc.items():
            oids = [o for o, ob in objects.items() if ob.get('location') in rids]
            paths = [p for p in all_paths if (p[:2] == ('world', 'rooms') and p[2] in rids)
                     or (p[:2] == ('world', 'objects') and p[2] in oids)]
            out.append((loc, 'place', ', '.join(rooms[r].get('name', r) for r in rids), take(paths)))
        out.append(('frame', 'rest', 'the opening, you, the endings', take(all_paths)))
        chunks = []
        for uid, kind, title, paths in out:
            for i in range(0, len(paths), CHUNK):
                chunks.append({'id': uid if i == 0 else f'{uid}_{i // CHUNK + 1}', 'of': uid, 'first': i == 0,
                               'kind': kind, 'title': title, 'paths': paths[i:i + CHUNK]})
        return [c for c in chunks if c['paths']]

    def kind_of(self, path):
        if path[0] == 'scenes':
            part = path[2]
            return {'opening': 'opening', 'interactions': 'action', 'room_text': 'room'}.get(part, 'other')
        if path[0] == 'world':
            if path[1] == 'rooms' and path[3] == 'description':
                return 'room'
            if path[1] == 'characters' and len(path) > 3 and path[3] == 'topics':
                return 'dialogue'
            return 'other'
        if path[0] == 'endings':
            return 'ending'
        if path[0] == 'intro':
            return 'opening'
        return 'other'

    def what(self, path):
        """What a text is, in a phrase, for the model."""
        p, pkg = path, self.pkg
        if p[0] == 'scenes':
            sc = pkg['scenes'][p[1]]
            if p[2] == 'opening':
                return 'the scene opening'
            if p[2] == 'interactions':
                it = sc['interactions'][p[3]]
                label = ' › '.join(str(x) for x in (it.get('verb'), it.get('object_label') or it.get('object'),
                                                    it.get('detail_label') or it.get('detail')) if x)
                return f'what the action "{label}" does'
            if p[2] == 'room_text':
                return f"how {pkg['world']['rooms'].get(p[3], {}).get('name', p[3])} reads during this scene"
            if p[2] == 'events':
                return 'something that happens on its own during the scene'
            if p[2] == 'nudges':
                return 'a nudge when the player idles'
            if p[2] == 'exits':
                return 'walking out of the scene'
            return f'scene text ({p[2]})'
        if p[0] == 'world':
            x = pkg['world'][p[1]][p[2]]
            name = '{' + p[2] + '}' if p[1] == 'characters' else (x.get('name') or p[2])
            if p[1] == 'characters':
                if p[3] == 'topics':
                    return f"what {name} says aloud when asked about {x['topics'][p[4]].get('label', p[4])}"
                return {'description': f'{name}, as seen', 'here': f'how the room shows {name}'}.get(p[3], f'{name} ({p[3]})')
            if p[1] == 'rooms':
                return {'description': f'{name}: the room', 'fragments': f'{name}: a detail by state',
                        'exits': f'{name}: walking out'}.get(p[3], f'{name} ({p[3]})')
            return f'{name}, examined' if p[3] == 'description' else f'{name} ({p[3]})'
        if p[0] == 'endings':
            end = pkg['endings'][p[1]]
            if 'text' == p[2]:
                return f"the ending \"{end.get('title', p[1])}\""
            return f"the ending \"{end.get('title', p[1])}\": what becomes of someone"
        if p[0] == 'intro':
            return 'the opening of the story'
        if p[0] == 'protagonist':
            return 'you: how you see yourself' if p[1] == 'description' else 'you: what you think about something'
        return '/'.join(str(x) for x in p)

    def edit(self, unit, codes):
        uid, kind, title, paths = unit['id'], unit['kind'], unit['title'], unit['paths']
        items, kinds, originals = [], {}, {}
        for i, path in enumerate(paths):
            tid = f't{i + 1}'
            holder = get_at(self.pkg, path[:-1] if path[-1] == 'text' else path[:-2])
            item = {'id': tid, 'what': self.what(path), 'text': get_at(self.pkg, path)}
            if isinstance(holder, dict) and holder.get('when') not in (None, 'true'):
                item['when'] = holder['when']
            items.append(item)
            kinds[tid], originals[tid] = self.kind_of(path), item['text']
        if kind == 'person' and unit['first']:
            c = self.chars[unit['of']]
            if c.get('name') and not c.get('known'):
                items.append({'id': 'unnamed', 'what': 'how the player sees them before learning their name',
                              'text': c.get('unnamed') or c.get('role') or ''})
                kinds['unnamed'], originals['unnamed'] = 'unnamed', items[-1]['text']
        if kind == 'scene' and unit['first']:
            sid = unit['of']
            node = (self.story.get('nodes') or {}).get(sid[2:] if sid.startswith('S_') else sid) or {}
            items.append({'id': 'recap', 'what': "the journal entry for this scene: the situation, dilemma, or "
                          "circumstance confronting the protagonist on arrival (who was there, what pressed), one or two "
                          "sentences; describe what was before you or found in the world, NEVER a player deed or choice (do NOT "
                          "write 'You took...', 'You let...', 'You signed...', 'You decided...'), which the journal lists separately beneath it",
                          'text': node.get('summary') or self.pkg['scenes'][sid].get('title') or ''})
            kinds['recap'], originals['recap'] = 'recap', items[-1]['text']
        ids = [x['id'] for x in items]
        earlier = ' ' + ' '.join(self.read_so_far) + ' ' if kind == 'scene' else ''
        # the last attempt that got as far as the soft checks, and the ids its
        # complaints named: a retry is told to change only those
        previous, flagged = {}, set()

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            texts = parsed.get('texts')
            if isinstance(texts, dict):      # the form this validator saves, read back on a resumed run
                got = {str(k): str(v or '').strip() for k, v in texts.items()}
            else:
                got = {str(t.get('id')): str(t.get('text') or '').strip() for t in as_list(texts) if isinstance(t, dict)}
            # a retry that drops a text nobody complained about keeps the
            # previous attempt's (s8b_S_N08 lost t26 fixing the recap, 2026-10-16)
            kept = [i for i in ids if not got.get(i) and previous.get(i) and i not in flagged]
            for i in kept:
                got[i] = previous[i]
            if kept:
                print(f'  kept {kept} from the previous attempt: the retry left them out')
            missing = [i for i in ids if not got.get(i)]
            if missing:
                raise ValueError(f'texts missing or empty: {missing[:12]}; return every id you were given, revised')
            bad = sorted({c for i in ids for c in CODE.findall(got[i])} - codes)
            if bad:
                raise ValueError(f'codes that name nobody: {bad}; a person is written as their code from the people list')
            parsed['texts'] = {i: got[i] for i in ids}
            parsed['images_used'] = [str(x) for x in as_list(parsed.get('images_used')) if str(x).strip()][:5]
            embodiment = (self.pkg.get('protagonist') or {}).get('embodiment') or (self.pkg.get('premise', {}).get('protagonist') or {}).get('embodiment')
            soft = []
            for i in ids:
                t, k = got[i], kinds[i]
                if k == 'unnamed':
                    if not 2 <= len(words(t)) <= 10 or CODE.search(t):
                        soft.append(f"unnamed: '{t}' should be a short phrase, three to eight words, no name or code")
                    continue
                if k == 'recap' and not 8 <= len(words(t)) <= 70:
                    soft.append(f'recap: {len(words(t))} words; one or two sentences')
                if k == 'dialogue':
                    for issue in validate_dialogue_text(originals[i], t):
                        soft.append(f'{i}: {issue}')
                for cid, c in self.chars.items():
                    unnamed = c.get('unnamed')
                    if unnamed and re.search(r'\b' + re.escape(unnamed) + r"['’]s\b", t, re.I):
                        soft.append(f"{i}: ungrammatical possessive on unintroduced handle ({unnamed!r}); use head noun or person code")
                # Semantic invariants (somatic embodiment discipline, resolution liveness
                # consistency, and fourth-wall/craft mechanics leakage) are evaluated across
                # complete context by semantic LLM judges (s8j_somatic, s8j_fate, s8j_craft)
                # during the post-edit pass (#49), retiring fragile regexes.
                n = len(words(t))
                if n > 2 * TARGETS[k] and n > 1.3 * len(words(originals[i])):
                    soft.append(f'{i}: {n} words, more than twice the {TARGETS[k]} this kind of text aims at')
            if self.gen and hasattr(self.gen, 'run_prompt'):
                try:
                    # a call of its own (timed, logged, on the dashboard), saved by what it judged:
                    # a retry's new texts are judged afresh, and a resumed run reads the verdict back
                    texts_json = json.dumps(got, ensure_ascii=False, indent=1)
                    digest = hashlib.sha1(json.dumps(got, sort_keys=True).encode('utf-8')).hexdigest()[:10]   # the texts, not their order
                    craft_parsed = self.gen.run_prompt(f's8j_{uid}', f'craft_{digest}', {'$$TEXTS_JSON$$': texts_json},
                                                       prompt_file='s8j_craft.prompt', klass='classify',
                                                       schema=schemas.CRAFT_JUDGE)
                    if craft_parsed and craft_parsed.get('verdict') == 'issues_found':
                        for v in craft_parsed.get('violations') or []:
                            soft.append(f"{v.get('text_id')}: {v.get('reason')} ({v.get('quote')})")
                except Exception:
                    pass
            if earlier:
                for i in ids:
                    w = words(CODE.sub(' ', got[i]))
                    given = ' ' + ' '.join(words(CODE.sub(' ', originals[i] or ''))) + ' '
                    for j in range(len(w) - REPEAT_N + 1):
                        run = ' '.join(w[j:j + REPEAT_N])
                        # a fact the text already had may recur; phrasing the revision brought may not
                        if f' {run} ' in earlier and f' {run} ' not in given and sum(len(x) > 3 for x in w[j:j + REPEAT_N]) >= 3:
                            soft.append(f'{i}: "{run}" was already read in an earlier part; find new words')
                            break
            previous.clear()
            previous.update(got)
            flagged.clear()
            flagged.update(s.split(':', 1)[0] for s in soft)
            if 'endings' in flagged:
                flagged.update(ending_res_ids)
            if soft:
                raise SoftReject('; '.join(soft[:12]))
        part = {'id': uid, 'kind': kind, 'title': title}
        if kind == 'scene':
            sid = unit['of']
            node = (self.story.get('nodes') or {}).get(sid[2:] if sid.startswith('S_') else sid) or {}
            part.update(happens=node.get('summary'),
                        people_here=['{' + c + '}' for c in sorted(self.pkg['scenes'][unit['of']].get('cast') or {})])
            if self.pkg['scenes'][sid].get('frame'):
                part['frame'] = self.pkg['scenes'][sid]['frame']
        elif kind == 'place':
            lid = unit['of']
            rf = {rid: r['frame'] for rid, r in self.pkg['world']['rooms'].items() if r.get('location') == lid and r.get('frame')}
            if rf:
                part['room_frames'] = rf
        elif kind == 'person':
            cid = unit['of']
            ch_info = next((p for p in self.people() if p['code'] == cid), {})
            part.update(
                character_code=cid,
                character_name=ch_info.get('name'),
                role=ch_info.get('role'),
                voice=ch_info.get('voice'),
                breaking_point=ch_info.get('breaking_point'),
                edge=ch_info.get('edge'),
            )
            if self.chars.get(cid, {}).get('portrait'):
                part['portrait'] = self.chars[cid]['portrait']
        answer = self.gen.run_prompt(f's8b_{uid}', 'edit', {
            '$$UNIT_GUIDANCE$$': GUIDANCE[kind],
            '$$STYLE_JSON$$': json.dumps(self.style_sheet, ensure_ascii=False, indent=1),
            '$$PEOPLE$$': json.dumps(self.people(), ensure_ascii=False),
            '$$ALREADY_READ$$': json.dumps({'openings': self.openings[-8:], 'images_spent': self.spent[-20:]}, ensure_ascii=False),
            '$$UNIT$$': json.dumps(part, ensure_ascii=False),
            '$$TEXTS_JSON$$': json.dumps(items, ensure_ascii=False, indent=1),
        }, prompt_file='s8b_edit.prompt', validator=validate, klass='edit', schema=schemas.PROSE_EDIT)
        texts = answer['texts'] if isinstance(answer['texts'], dict) else {t['id']: t['text'] for t in answer['texts']}
        for i, path in enumerate(paths):
            set_at(self.pkg, path, texts[f't{i + 1}'])
        if 'unnamed' in texts:
            self.chars[unit['of']]['unnamed'] = texts['unnamed']
        if 'recap' in texts:
            self.pkg['scenes'][unit['of']]['recap'] = [{'text': texts['recap']}]
        self.spent += [x for x in answer.get('images_used') or [] if x not in self.spent]
        self.read_so_far += [' '.join(words(CODE.sub(' ', texts[f't{i + 1}']))) for i in range(len(paths))]
        if kind == 'scene' and unit['first']:
            opening = [texts[f't{i + 1}'] for i, p in enumerate(paths) if p[2] == 'opening']
            if opening:
                self.openings.append(' '.join(opening[0].split()[:30]))

    def judge_somatic(self):
        """Step 8j2: Evaluates second-person texts for protagonist embodiment discipline."""
        if not self.gen or not hasattr(self.gen, 'run_prompt'):
            return None
        embodiment = (self.pkg.get('protagonist') or {}).get('embodiment') or \
                     (self.pkg.get('premise', {}).get('protagonist') or {}).get('embodiment')
        if not embodiment or embodiment not in checks.DISENBODIED_EMBODIMENTS:
            return None

        texts = {}
        if self.pkg.get('opening'):
            texts['opening'] = self.pkg['opening']
        you = self.pkg.get('you') or {}
        for idx, d in enumerate(you.get('description') or []):
            if isinstance(d, dict) and d.get('text'):
                texts[f'you_desc_{idx+1}'] = d['text']
        for idx, th in enumerate(you.get('think') or []):
            if isinstance(th, dict) and th.get('says'):
                for s_idx, s in enumerate(th['says']):
                    if isinstance(s, dict) and s.get('text'):
                        texts[f'you_think_{idx+1}_{s_idx+1}'] = s['text']
        for sid, scene in (self.pkg.get('scenes') or {}).items():
            if scene.get('opening'):
                texts[f'{sid}_opening'] = scene['opening']
            for r_idx, r in enumerate(scene.get('recap') or []):
                if isinstance(r, dict) and r.get('text'):
                    texts[f'{sid}_recap_{r_idx+1}'] = r['text']
        for eid, end in (self.pkg.get('endings') or {}).items():
            for t_idx, t in enumerate(end.get('text') or []):
                if isinstance(t, dict) and t.get('text'):
                    texts[f'{eid}_text_{t_idx+1}'] = t['text']

        if not texts:
            return None

        role = (self.pkg.get('protagonist') or {}).get('role') or 'the protagonist'
        emb_payload = {
            'embodiment': embodiment,
            'role': role,
            'guidance': 'Non-human or disembodied intelligence; must operate via telemetry, sensors, network buses, or mechanical effectors, never biological human anatomy.'
        }
        res = self.gen.run_prompt('s8j', 'somatic', {
            '$$PROTAGONIST_EMBODIMENT$$': json.dumps(emb_payload, ensure_ascii=False, indent=1),
            '$$TEXTS_JSON$$': json.dumps(texts, ensure_ascii=False, indent=1),
        }, prompt_file='s8j_somatic.prompt', klass='classify', schema=schemas.SOMATIC_JUDGE)

        if res and res.get('verdict') == 'drift_found':
            for v in res.get('violations') or []:
                msg = f"somatic drift in {v.get('text_id')}: {v.get('quote')} ({v.get('reason')})"
                self.findings.append(msg)
        return res

    def judge_fates(self):
        """Step 8j1: Evaluates character resolutions against ending narratives for contradictions."""
        if not self.gen or not hasattr(self.gen, 'run_prompt'):
            return None
        endings = self.pkg.get('endings') or {}
        if not endings:
            return None

        payload = []
        for eid, end in sorted(endings.items()):
            base_text = ' '.join(x.get('text', '') for x in (end.get('text') or []) if isinstance(x, dict) and x.get('text'))
            resolutions_payload = []
            for group in end.get('resolutions') or []:
                cid = group.get('about')
                char_info = (self.pkg.get('world') or {}).get('characters', {}).get(cid) or {}
                char_name = char_info.get('name') or cid
                for vi, v in enumerate(group.get('variants') or []):
                    vt = v.get('text', '')
                    if vt:
                        resolutions_payload.append({
                            'character_code': cid,
                            'character_name': char_name,
                            'variant_index': vi,
                            'resolution_text': vt
                        })
            if base_text and resolutions_payload:
                payload.append({
                    'ending_id': eid,
                    'ending_narrative': base_text,
                    'character_resolutions': resolutions_payload
                })

        if not payload:
            return None

        res = self.gen.run_prompt('s8j', 'fate', {
            '$$ENDINGS_AND_RESOLUTIONS$$': json.dumps(payload, ensure_ascii=False, indent=1),
        }, prompt_file='s8j_fate.prompt', klass='classify', schema=schemas.FATE_JUDGE)

        if res and res.get('verdict') == 'contradictions_found':
            for c in res.get('contradictions') or []:
                msg = f"fate contradiction in {c.get('ending_id')}: {c.get('character')} - {c.get('reason')}"
                self.findings.append(msg)
        return res

    def judge_craft(self):
        """Step 8j3: Evaluates rewritten narrative texts for fourth-wall breaks,
        game engine mechanics leakage, and meta-craft announcements (#49 Phase 3)."""
        if not self.gen or not hasattr(self.gen, 'run_prompt'):
            return None
        texts = {}
        if self.pkg.get('opening'):
            texts['opening'] = self.pkg['opening']
        for sid, scene in (self.pkg.get('scenes') or {}).items():
            if scene.get('opening'):
                texts[f'{sid}_opening'] = scene['opening']
            for r_idx, r in enumerate(scene.get('recap') or []):
                if isinstance(r, dict) and r.get('text'):
                    texts[f'{sid}_recap_{r_idx+1}'] = r['text']
            for a_idx, a in enumerate(scene.get('actions') or []):
                if isinstance(a, dict) and a.get('text'):
                    texts[f'{sid}_act_{a_idx+1}'] = a['text']
        for eid, end in (self.pkg.get('endings') or {}).items():
            for t_idx, t in enumerate(end.get('text') or []):
                if isinstance(t, dict) and t.get('text'):
                    texts[f'{eid}_text_{t_idx+1}'] = t['text']
        if not texts:
            return None
        res = self.gen.run_prompt('s8j', 'craft', {
            '$$TEXTS_JSON$$': json.dumps(texts, ensure_ascii=False, indent=1),
        }, prompt_file='s8j_craft.prompt', klass='classify', schema=schemas.CRAFT_JUDGE)
        if res and res.get('verdict') == 'issues_found':
            for v in res.get('violations') or []:
                msg = f"craft leakage ({v.get('issue_type')}) in {v.get('text_id')}: {v.get('quote')} ({v.get('reason')})"
                self.findings.append(msg)
        return res

    # ------------------------------------------------------------ the whole pass

    def run(self):
        dd_before = dialogue_distinctiveness(self.original)
        self.prepare_names()
        self.style()
        codes = set(self.chars)
        self.convert_names()            # the model is shown codes, never names, in the text it revises
        units = self.units()
        # "scene 5 of 15 · part 5 of 34" on the dashboard: a long unit's chunks count as one of its kind
        of_kind = {}
        for u in units:
            ids = of_kind.setdefault(u['kind'], [])
            if u['of'] not in ids:
                ids.append(u['of'])
        for i, unit in enumerate(units, 1):
            ids = of_kind[unit['kind']]
            label = 'the opening, you and the endings' if unit['kind'] == 'rest' else unit['kind']
            with stats.working_on(self.gen, label, ids.index(unit['of']) + 1, len(ids), part=(i, len(units))):
                self.edit(unit, codes)
        self.convert_names()            # any name a revision wrote anyway
        self.judge_somatic()
        self.judge_fates()
        self.judge_craft()
        if ENGINE not in sys.path:
            sys.path.insert(0, ENGINE)
        from story import Story, validate
        errors, _ = validate(Story(self.pkg))
        dd_after = dialogue_distinctiveness(self.pkg)
        self.dd_before = dd_before
        self.dd_after = dd_after
        if dd_before['pairs'] and dd_before['avg_distinctiveness'] > 0:
            if dd_after['avg_distinctiveness'] < dd_before['avg_distinctiveness'] * 0.8:
                self.findings.append(
                    f"character dialogue distinctiveness dropped from {dd_before['avg_distinctiveness']:.2f} to {dd_after['avg_distinctiveness']:.2f}"
                )
        return self.pkg, errors


def norm_role(text):
    return re.sub(r'^(the|a|an)\s+', '', str(text or '').strip().lower())


def check_validator(parsed):
    if not isinstance(parsed, dict):
        raise ValueError('expected a JSON object')
    parsed['delivers'] = str(parsed.get('delivers')).strip().lower() in ('true', 'yes', '1')
    parsed['problems'] = [str(x) for x in as_list(parsed.get('problems')) if str(x).strip()]


def report_markdown(story_id, style, findings, errors, before, after, dd=None):
    lines = [f'# {story_id}: the prose pass', '', '## Style sheet', '']
    for k in ('tradition', 'person_tense', 'register', 'rhythm', 'length'):
        if style.get(k):
            lines.append(f'- **{k}:** {style[k]}')
    lines += ['- **voices:**'] + [f"  - {v.get('who')}: {v.get('speech')}" for v in style.get('voices') or []]
    lines += [f"- **images:** {'; '.join(style.get('images') or [])}", f"- **avoid:** {'; '.join(style.get('avoid') or [])}",
              '', '### Sample', '', style.get('sample', ''), '', '## Size', '',
              f'{before[0]} texts, {before[1]} words before; {after[1]} words after', '', '## Findings', '']
    lines += [f'- {f}' for f in findings] or ['- none']
    lines += ['', '## Engine validator', ''] + ([f'- ERROR {e}' for e in errors] or ['- no errors'])
    if dd and dd.get('characters'):
        lines += ['', '## Character Dialogue Distinctiveness', '',
                  f"- **average pairwise distinctiveness:** {dd.get('avg_distinctiveness', 1.0):.2f}",
                  '']
        chars = dd.get('characters', {})
        if chars:
            lines += ['### Speakers', '']
            for cid, info in sorted(chars.items()):
                lines.append(f"- **{info.get('name', cid)}** ({cid}): {info.get('words', 0)} words, "
                             f"{info.get('unique', 0)} unique, TTR: {info.get('ttr', 0.0):.2f}")
            lines.append('')
        pairs = dd.get('pairs', [])
        if pairs:
            lines += ['### Pairwise distinctiveness', '']
            for p in pairs:
                p_names = ' vs '.join(p['pair'])
                lines.append(f"- **{p_names}:** distinctiveness {p['distinctiveness']:.2f} "
                             f"({p['overlap']} shared words)")
            lines.append('')
    return '\n'.join(lines) + '\n'


def size(pkg):
    texts = [t for _, t in text_paths(pkg)]
    return len(texts), sum(len(words(t)) for t in texts)


def dialogue_distinctiveness(pkg):
    """Calculates character-level word count, unique vocabulary, TTR, and
    pairwise Jaccard distinctiveness across all characters with dialogue."""
    chars = (pkg.get('world') or {}).get('characters') or {}
    profiles = {}
    for cid, c in chars.items():
        name = c.get('name') or cid
        texts = [t for _, t in text_paths(c.get('topics') or {})]
        word_list = [w for t in texts for w in words(CODE.sub(' ', t))]
        if not word_list:
            continue
        vocab = set(word_list)
        profiles[cid] = {
            'name': name,
            'words': len(word_list),
            'unique': len(vocab),
            'ttr': round(len(vocab) / len(word_list), 3) if word_list else 0.0,
            'vocab': vocab,
        }
    pairs = []
    cids = sorted(profiles.keys())
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            c1, c2 = cids[i], cids[j]
            v1, v2 = profiles[c1]['vocab'], profiles[c2]['vocab']
            union = v1 | v2
            inter = v1 & v2
            sim = len(inter) / len(union) if union else 0.0
            dist = round(1.0 - sim, 3)
            pairs.append({
                'pair': (profiles[c1]['name'], profiles[c2]['name']),
                'distinctiveness': dist,
                'overlap': len(inter),
            })
    avg_dist = round(sum(p['distinctiveness'] for p in pairs) / len(pairs), 3) if pairs else 1.0
    return {
        'characters': {cid: {k: v for k, v in p.items() if k != 'vocab'} for cid, p in profiles.items()},
        'pairs': pairs,
        'avg_distinctiveness': avg_dist,
    }


def write(gen, story=None):
    """Runs the pass for gen's story: needs <id>_package_draft.json."""
    base = gen.story_file_path('')
    with open(base + 'package_draft.json', encoding='utf-8') as f:
        package = json.load(f)
    if story is None and os.path.isfile(base + 'story.json'):
        with open(base + 'story.json', encoding='utf-8') as f:
            story = json.load(f)
    writer = ProseWriter(gen, package, story)
    pkg, errors = writer.run()
    gen.save_story_json('package.json', pkg)
    gen.save_story_json('prose_style.json', writer.style_sheet)
    gen.save_story_file('prose.md', report_markdown(gen.story_id, writer.style_sheet, writer.findings, errors,
                                                    size(package), size(pkg), getattr(writer, 'dd_after', None)))
    print(f'prose: {size(package)[1]} words -> {size(pkg)[1]}; validator {len(errors)} error(s)')
    for e in errors:
        print(f'  - {e}')
    return pkg, errors


def main(argv=None):
    from main import StoryGenerator
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('story_id')
    args = ap.parse_args(argv)
    gen = StoryGenerator(story_id=args.story_id)
    base = gen.story_file_path('')
    if not os.path.isfile(base + 'package_draft.json'):
        print('the prose pass needs <id>_package_draft.json (run --stage-d first)', file=sys.stderr)
        return 1
    for key, suffix in (('s3_brief', 's3_brief.json'), ('s3_4_promises', 's3_4_promises.json')):
        if os.path.isfile(base + suffix):
            with open(base + suffix, encoding='utf-8') as f:
                gen.analysis[key] = json.load(f)
    kernel = base + 's1_kernel.txt'
    gen.kernel = open(kernel, encoding='utf-8').read().strip() if os.path.isfile(kernel) else ''
    _, errors = write(gen)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
