"""Drawing each pane onto a Surface. Every function takes the surface, its
Rect and what it shows, and returns what the app needs back (the menu's
row -> entry map for the mouse, the story's scroll limit)."""

from menukeys import KEYS

from . import text as T
from .layout import Rect

MEASURE = 88                  # the widest the story is set, however wide the pane: lines past this are hard to read
BOX = {'tl': '┌', 'tr': '┐', 'bl': '└', 'br': '┘', 'h': '─', 'v': '│'}
JOURNAL_STYLES = {'title': 'heading', 'chapter': 'title', 'current': 'current', 'summary': 'normal', 'choice': 'choice',
                  'section': 'heading', 'item': 'normal', 'ending': 'mark'}
HELP = [
    ('heading', 'Moving through the menu'),
    ('normal', '↑ ↓            choose'),
    ('normal', '→ or Enter     open, or do it'),
    ('normal', '← Backspace b  back up a level'),
    ('normal', '1-9, letters   pick an entry by its key'),
    ('heading', 'Time'),
    ('normal', 'u              unwind the last action'),
    ('normal', 'h              history: go back to any point'),
    ('normal', 's / l          save / load'),
    ('heading', 'Reading'),
    ('normal', 'j              journal: the story so far'),
    ('normal', 'PgUp PgDn      scroll the story; End: back to the latest'),
    ('normal', 'Tab            show or hide the side panel'),
    ('normal', 'mouse          click an entry; wheel scrolls'),
    ('heading', 'Marks'),
    ('normal', '•              not yet examined, asked or thought'),
    ('normal', '◆              a choice that changes the story'),
    ('normal', '…              opens a further menu'),
    ('heading', ''),
    ('muted', 'q quits (asks first). Esc closes this.'),
]


def box(surface, r, title=None, focused=False):
    style = 'title' if focused else 'border'
    surface.put(r.y, r.x, BOX['tl'] + BOX['h'] * (r.w - 2) + BOX['tr'], style)
    for y in range(r.y + 1, r.y + r.h - 1):
        surface.put(y, r.x, BOX['v'], style)
        surface.put(y, r.x + r.w - 1, BOX['v'], style)
    surface.put(r.y + r.h - 1, r.x, BOX['bl'] + BOX['h'] * (r.w - 2) + BOX['br'], style)
    if title:
        surface.put(r.y, r.x + 2, ' ' + T.ellipsize(title, r.w - 6) + ' ', 'title' if focused else 'heading')
    return Rect(r.y + 1, r.x + 2, r.h - 2, r.w - 4)


def header(surface, r, here):
    surface.fill(r.y, r.x, 1, r.w, 'header')
    right = f" turn {here['turn']} "
    parts = [here['title'], here['chapter'], cap(here['room'])]
    left = ' ' + ' · '.join(p for p in parts if p) + ' '
    surface.put(r.y, r.x, T.ellipsize(left, r.w - T.width(right) - 1), 'header')
    surface.put(r.y, r.x + r.w - T.width(right), right, 'header')


def cap(text):
    text = str(text or '')
    return text[:1].upper() + text[1:]


def story_lines(pages, cells):
    """(text, style) lines for the story, the newest page bright and earlier
    ones muted, and the line where the newest page begins."""
    out = []
    last = len(pages) - 1
    newest = 0
    for i, page in enumerate(pages):
        fresh = i == last
        if fresh:
            newest = len(out)
        for e in page:
            if e['kind'] == 'choice':
                out += [(l, 'choice') for l in T.wrap('› ' + e['text'], cells, '  ')]
            elif e['kind'] == 'room':
                out.append((T.ellipsize(cap(e['title']), cells), 'title' if fresh else 'muted'))
                out += [(l, 'normal' if fresh else 'muted') for l in T.wrap(e['text'], cells)]
            elif e['kind'] == 'chapter':
                card = f"— Chapter {e.get('number', '')}: {e['text']} —"
                out.append((' ' * max(0, (cells - T.width(card)) // 2) + T.ellipsize(card, cells), 'heading' if fresh else 'muted'))
            elif e['kind'] == 'ending':
                out.append(('', 'normal'))
                title = f"*** {e['text']} ***"
                out.append((' ' * max(0, (cells - T.width(title)) // 2) + title, 'mark'))
            else:
                out += [(l, 'new' if fresh else 'muted') for l in T.wrap(e['text'], cells)]
            out.append(('', 'normal'))
    while out and not out[-1][0]:
        out.pop()
    return out, newest


def story(surface, r, session):
    inner = box(surface, r, 'Story')
    if inner.w > MEASURE:
        inner = inner._replace(x=inner.x + (inner.w - MEASURE) // 2, w=MEASURE)
    lines, newest = story_lines(session.pages, inner.w)
    limit = max(0, len(lines) - inner.h)
    if session.fresh:                      # just acted: open at the start of what is new, if it does not all fit
        session.scroll = max(0, len(lines) - inner.h - newest)
        session.fresh = False
    session.scroll = max(0, min(session.scroll, limit))
    start = max(0, len(lines) - inner.h - session.scroll)
    for row, (line, style) in enumerate(lines[start:start + inner.h]):
        surface.put(inner.y + row, inner.x, line, style)
    if start > 0:
        surface.put(r.y, r.x + r.w - 12, ' ↑ PgUp ', 'muted')
    if session.scroll > 0:
        surface.put(r.y + r.h - 1, r.x + r.w - 15, ' ↓ more: PgDn ', 'mark')
    return limit


def menu(surface, r, session, keys=KEYS):
    """The current menu level. Returns {screen row: entry index}."""
    if session.ended:
        inner = box(surface, r, 'The end', focused=True)
        lines = [('mark', session.view.get('ending_title') or 'The End'), ('normal', ''),
                 ('key', 'n  play again'), ('key', 'u  unwind the last action'), ('key', 'h  go back to any point'),
                 ('key', 'j  the story so far'), ('key', 'q  quit')]
        for row, (style, line) in enumerate(lines[:inner.h]):
            surface.put(inner.y + row, inner.x, T.ellipsize(line, inner.w), style)
        return {}
    path = session.path()
    inner = box(surface, r, ' › '.join(path) if path else 'What do you do?', focused=True)
    items = session.items()
    rows = max(1, inner.h - 2)
    index = session.level()['index'] if items else 0
    top = 0 if index < rows else index - rows + 1
    hits = {}
    for row, i in enumerate(range(top, min(len(items), top + rows))):
        child = items[i]
        key = keys[i] if i < len(keys) else ' '
        marks = (' …' if 'id' not in child else '') + (' •' if child.get('new') else '') + \
                (' ◆' if child.get('weight') == 'major' else '')
        label = child.get('label') or ''
        y = inner.y + row
        selected = i == index
        style = 'selected' if selected else 'normal'
        if selected:
            surface.fill(y, inner.x - 1, 1, inner.w + 2, 'selected')
        surface.put(y, inner.x, key, style if selected else 'key')
        surface.put(y, inner.x + 2, T.ellipsize(label, inner.w - 2 - T.width(marks)), style)
        surface.put(y, inner.x + 2 + min(T.width(label), inner.w - 2 - T.width(marks)), marks, style if selected else 'mark')
        hits[y] = i
    if top > 0:
        surface.put(r.y, r.x + r.w - 6, ' ↑ ', 'muted')
    if top + rows < len(items):
        surface.put(r.y + r.h - 1, r.x + r.w - 6, ' ↓ ', 'muted')
    if inner.h >= 3:
        surface.put(inner.y + inner.h - 1, inner.x, T.ellipsize('⏎ ' + session.preview(), inner.w), 'muted')
    return hits


def side(surface, r, here):
    inner = box(surface, r, 'Here')
    lines = [('title', cap(here['room']))]
    for label, names in (('People', here['people']), ('Things', here['things']), ('Carrying', here['carrying'])):
        lines += [('normal', l) for l in T.wrap(f"{label}: {', '.join(names) if names else '—'}", inner.w, '  ')]
    for row, (style, line) in enumerate(lines[:inner.h]):
        surface.put(inner.y + row, inner.x, line, style)


def status(surface, r, session):
    if session.message:
        surface.put(r.y, r.x + 1, T.ellipsize(session.message, r.w - 2), 'warn' if session.warn else 'current')


FOOTER_MAIN = [('↑↓', 'choose'), ('→⏎', 'open'), ('←', 'back'), ('u', 'unwind'), ('j', 'journal'), ('h', 'history'),
               ('s', 'save'), ('l', 'load'), ('?', 'help'), ('q', 'quit')]
FOOTER_OVERLAY = {'journal': [('↑↓ PgUp PgDn', 'scroll'), ('Esc j', 'close')],
                  'history': [('↑↓', 'choose'), ('⏎', 'go back to it'), ('Esc h', 'close')],
                  'help': [('Esc ?', 'close')], 'quit': [('y', 'quit'), ('n Esc', 'stay')]}


FOOTER_END = [('n', 'play again'), ('u', 'unwind'), ('h', 'history'), ('j', 'journal'), ('s', 'save'), ('q', 'quit')]


def footer(surface, r, session):
    hints = FOOTER_OVERLAY.get((session.overlay or {}).get('kind'), FOOTER_END if session.ended else FOOTER_MAIN)
    x = r.x + 1
    for key, word in hints:
        need = T.width(key) + T.width(word) + 3
        if x + need > r.x + r.w:
            break
        surface.put(r.y, x, key, 'key')
        surface.put(r.y, x + T.width(key) + 1, word, 'muted')
        x += need


def overlay(surface, r, session):
    """The open overlay. Returns the number of content lines (for scrolling)."""
    ov = session.overlay
    kind = ov['kind']
    if kind == 'quit':
        q = Rect(r.y + r.h // 2 - 2, r.x + r.w // 2 - 15, 5, 30)
        surface.fill(q.y, q.x, q.h, q.w)
        inner = box(surface, q, 'Quit?', focused=True)
        surface.put(inner.y + 1, inner.x, 'Quit the story? (y/n)', 'normal')
        return 0
    surface.fill(r.y, r.x, r.h, r.w)
    title = {'journal': 'The story so far', 'history': 'History: go back to any point', 'help': 'Help'}[kind]
    inner = box(surface, r, title, focused=True)
    if kind == 'history':
        items = session.history_items()
        rows = []
        for it in items:
            mark = ' ◆' if it['major'] else ''
            now = '   ← now' if it['current'] else ''
            rows.append((it['index'], f"{it['index']:>3}. {it['label']}{mark}{now}", it['gist']))
        per = 2
        visible = max(1, inner.h // per)
        top = min(max(0, ov['index'] - visible + 1), max(0, len(rows) - visible))
        for n, (i, line, gist) in enumerate(rows[top:top + visible]):
            y = inner.y + n * per
            sel = i == ov['index']
            if sel:
                surface.fill(y, inner.x - 1, 1, inner.w + 2, 'selected')
            surface.put(y, inner.x, T.ellipsize(line, inner.w), 'selected' if sel else 'normal')
            if gist:
                surface.put(y + 1, inner.x + 5, T.ellipsize(gist, inner.w - 5), 'muted')
        return len(rows)
    source = session.journal() if kind == 'journal' else HELP
    lines = []
    for k, text in source:
        style = JOURNAL_STYLES.get(k, k)
        if k in ('chapter', 'current', 'section', 'ending', 'heading') and lines:
            lines.append(('', 'normal'))
        indent = '   ' if k in ('summary', 'choice', 'item') else ''
        lines += [(indent + l, style) for l in T.wrap(text, inner.w - len(indent))]
    ov['scroll'] = max(0, min(ov['scroll'], len(lines) - inner.h))
    for row, (line, style) in enumerate(lines[ov['scroll']:ov['scroll'] + inner.h]):
        surface.put(inner.y + row, inner.x, line, style)
    return len(lines)


def too_small(surface, h, w):
    surface.put(h // 2, 0, T.ellipsize(f'The window is {w}×{h}; make it at least 48×14.', w), 'warn')
