#!/usr/bin/env python3
"""The prose stage (docs/later_stages.md §6): an editing pass over the text
stages B and D already wrote, in one voice per story.

    python prose.py <story_id>     # on a directory with <id>_package.json; writes <id>_package_prose.json

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
import json
import os
import re
import sys

import schemas
from errors import SoftReject

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(THIS_DIR, '..', 'engine')

TARGETS = {'room': 60, 'action': 50, 'opening': 90, 'ending': 150, 'other': 80, 'unnamed': 8, 'recap': 40}
CHUNK = 40                    # texts per call: a person with every state and subject is split
MECHANICS = re.compile(r"\b(menus?|nodes?|variants?|the player|playthroughs?)\b", re.I)   # never ordinary English
ALTERNATIVES = re.compile(r"\bif\b[^.!?]*[;,]\s*(?:and |but |or )?if\b", re.I)
ANNOUNCED = re.compile(r"\b(the cost (?:is|was)|it (?:has|had) cost|the price|pays? off)\b", re.I)
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
             "the moment, with who is here), what each of its actions does (the response to choosing it), how its "
             "rooms read during it, the events that happen on their own, the nudges if the player idles, and its "
             "journal entry ('recap': what the scene put before the player, for the story-so-far page).",
    'person': "THIS PART is one person: how they look (by their state), the line the room shows them by ('here'), "
              "and what they say on each subject, in their own voice. 'unnamed' is how the player sees them before "
              "learning their name: a short phrase, three to eight words, starting with 'the' or 'a', what you would "
              "notice first ('the old man in the captain's coat').",
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
        for cid, c in self.chars.items():
            seed = cast.get(norm_role(c.get('role'))) or {}
            out.append({'code': cid, 'name': c.get('name'), 'role': c.get('role'),
                        'voice': seed.get('voice') or c.get('voice'),
                        'known_to_you': bool(c.get('known') or not c.get('unnamed'))})
        return out

    def prepare_names(self):
        """A named person the protagonist does not already know goes by their
        role until introduced; a relative or a "your ..." is known."""
        from main import KIN
        for cid, c in self.chars.items():
            if not proper_name(c.get('name')) or c.get('unnamed'):
                continue
            role = str(c.get('role') or '').strip()
            if role.lower().startswith('your ') or KIN.search(role):
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
            if 'second' in str(parsed['person_tense']).lower() and not re.search(r'\byou(r)?\b', parsed['sample'], re.I):
                soft.append('the sample is not in the second person: the player is "you"')
            if MECHANICS.search(parsed['sample']):
                soft.append(f"the sample uses a game word ({MECHANICS.search(parsed['sample']).group(0)})")
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
            return 'room' if path[1] == 'rooms' and path[3] == 'description' else 'other'
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
                    return f"{name}, asked about {x['topics'][p[4]].get('label', p[4])}"
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
            items.append({'id': 'recap', 'what': "the journal entry for this scene: what it put before the player, as "
                          "they will remember it afterwards (who was there, what pressed), one or two sentences, past "
                          "tense, second person; never what they chose, which the journal lists on its own",
                          'text': node.get('summary') or self.pkg['scenes'][sid].get('title') or ''})
            kinds['recap'], originals['recap'] = 'recap', items[-1]['text']
        ids = [x['id'] for x in items]
        earlier = ' ' + ' '.join(self.read_so_far) + ' ' if kind == 'scene' else ''

        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            got = {str(t.get('id')): str(t.get('text') or '').strip() for t in as_list(parsed.get('texts')) if isinstance(t, dict)}
            missing = [i for i in ids if not got.get(i)]
            if missing:
                raise ValueError(f'texts missing or empty: {missing[:12]}; return every id you were given, revised')
            bad = sorted({c for i in ids for c in CODE.findall(got[i])} - codes)
            if bad:
                raise ValueError(f'codes that name nobody: {bad}; a person is written as their code from the people list')
            parsed['texts'] = {i: got[i] for i in ids}
            parsed['images_used'] = [str(x) for x in as_list(parsed.get('images_used')) if str(x).strip()][:5]
            soft = []
            for i in ids:
                t, k = got[i], kinds[i]
                if k == 'unnamed':
                    if not 2 <= len(words(t)) <= 10 or CODE.search(t):
                        soft.append(f"unnamed: '{t}' should be a short phrase, three to eight words, no name or code")
                    continue
                if k == 'recap' and not 8 <= len(words(t)) <= 70:
                    soft.append(f'recap: {len(words(t))} words; one or two sentences')
                if ALTERNATIVES.search(t):
                    soft.append(f'{i}: narrates alternatives ("{ALTERNATIVES.search(t).group(0)}"); say what happens')
                if MECHANICS.search(t):
                    soft.append(f'{i}: a game word ("{MECHANICS.search(t).group(0)}")')
                if ANNOUNCED.search(t) and not ANNOUNCED.search(originals[i] or '') or (k == 'ending' and ANNOUNCED.search(t)):
                    soft.append(f'{i}: names the craft ("{ANNOUNCED.search(t).group(0)}"); show what is lost instead')
                n = len(words(t))
                if n > 2 * TARGETS[k] and n > 1.3 * len(words(originals[i])):
                    soft.append(f'{i}: {n} words, more than twice the {TARGETS[k]} this kind of text aims at')
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
            if soft:
                raise SoftReject('; '.join(soft[:12]))
        part = {'id': uid, 'kind': kind, 'title': title}
        if kind == 'scene':
            sid = unit['of']
            node = (self.story.get('nodes') or {}).get(sid[2:] if sid.startswith('S_') else sid) or {}
            part.update(happens=node.get('summary'),
                        people_here=['{' + c + '}' for c in sorted(self.pkg['scenes'][unit['of']].get('cast') or {})])
        answer = self.gen.run_prompt(f's8b_{uid}', 'edit', {
            '$$UNIT_GUIDANCE$$': GUIDANCE[kind],
            '$$STYLE_JSON$$': json.dumps(self.style_sheet, ensure_ascii=False, indent=1),
            '$$PEOPLE$$': json.dumps(self.people(), ensure_ascii=False),
            '$$ALREADY_READ$$': json.dumps({'openings': self.openings[-8:], 'images_spent': self.spent[-20:]}, ensure_ascii=False),
            '$$UNIT$$': json.dumps(part, ensure_ascii=False),
            '$$TEXTS_JSON$$': json.dumps(items, ensure_ascii=False, indent=1),
        }, prompt_file='s8b_edit.prompt', validator=validate, klass='build', schema=schemas.PROSE_EDIT)
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

    # ------------------------------------------------------------ the whole pass

    def run(self):
        self.prepare_names()
        self.style()
        codes = set(self.chars)
        self.convert_names()            # the model is shown codes, never names, in the text it revises
        for unit in self.units():
            self.edit(unit, codes)
        self.convert_names()            # any name a revision wrote anyway
        if ENGINE not in sys.path:
            sys.path.insert(0, ENGINE)
        from story import Story, validate
        errors, _ = validate(Story(self.pkg))
        return self.pkg, errors


def norm_role(text):
    return re.sub(r'^(the|a|an)\s+', '', str(text or '').strip().lower())


def check_validator(parsed):
    if not isinstance(parsed, dict):
        raise ValueError('expected a JSON object')
    parsed['delivers'] = str(parsed.get('delivers')).strip().lower() in ('true', 'yes', '1')
    parsed['problems'] = [str(x) for x in as_list(parsed.get('problems')) if str(x).strip()]


def report_markdown(story_id, style, findings, errors, before, after):
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
    return '\n'.join(lines) + '\n'


def size(pkg):
    texts = [t for _, t in text_paths(pkg)]
    return len(texts), sum(len(words(t)) for t in texts)


def write(gen, story=None):
    """Runs the pass for gen's story: needs <id>_package.json."""
    base = gen.story_file_path('')
    with open(base + 'package.json', encoding='utf-8') as f:
        package = json.load(f)
    if story is None and os.path.isfile(base + 'story.json'):
        with open(base + 'story.json', encoding='utf-8') as f:
            story = json.load(f)
    writer = ProseWriter(gen, package, story)
    pkg, errors = writer.run()
    gen.save_story_json('package_prose.json', pkg)
    gen.save_story_json('prose_style.json', writer.style_sheet)
    gen.save_story_file('prose.md', report_markdown(gen.story_id, writer.style_sheet, writer.findings, errors,
                                                    size(package), size(pkg)))
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
    if not os.path.isfile(base + 'package.json'):
        print('the prose pass needs <id>_package.json (run --stage-d first)', file=sys.stderr)
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
