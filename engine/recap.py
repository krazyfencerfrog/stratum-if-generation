"""The story so far: a journal built from the engine's history, for any
front end (the terminal player prints it, the paned interface shows it).

    j = journal(engine)
    j['chapters']   # one per scene played, in order: title, summary, the choices that mattered, current
    j['people']     # everyone met: the name you know them by, whether you know it, whether they are here
    j['carrying']   # what you hold
    j['ending']     # the ending's title, once reached
    journal_lines(j) -> [(kind, text)]   kinds: title, chapter, current, summary, choice, section, item, ending

A chapter's summary is the scene's `recap` (written by the prose stage,
state-keyed like any text) when the package has one, else the first
sentence of its opening. The choices kept are the ones that mattered: a
moment's answer and anything marked major.
"""

import re

from story import pick_text

SUMMARY_WORDS = 45            # a fallback summary (an opening's first sentence) is cut to this


def first_sentence(text, limit=SUMMARY_WORDS):
    text = ' '.join(str(text or '').split())
    m = re.match(r'(.+?[.!?])(\s|$)', text)
    sentence = m.group(1) if m else text
    words = sentence.split()
    return sentence if len(words) <= limit else ' '.join(words[:limit]) + '…'


def journal(engine):
    s, st = engine.story, engine.state
    chapters, order = {}, []

    def chapter(sid):
        if sid not in chapters:
            sc = s.scenes.get(sid) or {}
            chapters[sid] = {'scene': sid, 'title': sc.get('title') or sid, 'summary': '', 'choices': [], 'current': False}
            order.append(sid)
        return chapters[sid]

    for i, h in enumerate(engine.history):
        sid = h.get('scene')
        if sid not in s.scenes:
            continue                                   # an entry from an old save: no scene recorded
        ch = chapter(sid)
        if i and (h.get('weight') == 'major' or h.get('answered')):
            ch['choices'].append(h['label'])
        after = h.get('scene_after')
        if after in s.scenes and after != sid:
            chapter(after)
    if st.scene in s.scenes:
        chapter(st.scene)
    for sid in order:
        sc = s.scenes.get(sid) or {}
        text = pick_text(sc.get('recap'), st, f'{sid}.recap') if sc.get('recap') else ''
        if not text:
            text = first_sentence(pick_text(sc.get('opening'), st, sid))
        chapters[sid]['summary'] = s.render(text, st)
        chapters[sid]['current'] = sid == st.scene and not st.ending
    here = set(engine.present())
    people = [{'id': cid, 'name': s.name_of(cid, st, short=False), 'known': s.known(cid, st), 'here': cid in here}
              for cid in s.characters if cid in st.seen]
    carrying = [s.name_of(o, st) for o, loc in st.locations.items() if loc == 'player']
    ending = s.render((s.endings.get(st.ending) or {}).get('title'), st) if st.ending else None
    return {'title': s.title, 'chapters': [chapters[sid] for sid in order], 'people': people,
            'carrying': carrying, 'ending': ending, 'turns': st.turns}


def journal_lines(j):
    out = [('title', j.get('title') or 'The story so far')]
    for n, ch in enumerate(j['chapters'], 1):
        out.append(('current' if ch['current'] else 'chapter', f"{n}. {ch['title']}" + ('  (now)' if ch['current'] else '')))
        if ch['summary']:
            out.append(('summary', ch['summary']))
        for c in ch['choices']:
            out.append(('choice', f'You chose: {c}'))
    if j.get('ending'):
        out.append(('ending', f"The end: {j['ending']}"))
    if j['people']:
        out.append(('section', 'People'))
        for p in j['people']:
            note = ' (here)' if p['here'] else ''
            out.append(('item', p['name'][:1].upper() + p['name'][1:] + note))
    out.append(('section', 'Carrying'))
    out.append(('item', ', '.join(j['carrying']) if j['carrying'] else 'nothing'))
    return out
