"""Text measured as a terminal shows it, and wrapped to a width.

Widths count terminal cells: a wide character (CJK, most emoji) takes two,
a combining mark none. Wrapping keeps paragraphs (a blank line between
them) and breaks overlong words rather than overflowing a pane.
"""

import unicodedata


def char_width(ch):
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


def width(text):
    return sum(char_width(c) for c in text)


def clip(text, cells):
    """The longest prefix of text that fits in `cells`."""
    out, used = [], 0
    for c in text:
        w = char_width(c)
        if used + w > cells:
            break
        out.append(c)
        used += w
    return ''.join(out)


def ellipsize(text, cells):
    if width(text) <= cells:
        return text
    return clip(text, max(0, cells - 1)) + '…' if cells > 0 else ''


def wrap(text, cells, indent=''):
    """Lines of at most `cells` cells. Paragraph breaks (newlines) are kept;
    a blank line in the source stays a blank line. `indent` prefixes
    continuation lines of a paragraph; a word too long for a line is broken."""
    cells = max(4, cells)
    room = max(1, cells - width(indent))
    lines = []
    for para in str(text or '').split('\n'):
        pieces = []
        for w in para.split():
            while width(w) > room:
                head = clip(w, room)
                pieces.append(head)
                w = w[len(head):]
            if w:
                pieces.append(w)
        if not pieces:
            lines.append('')
            continue
        line = pieces[0]
        for w in pieces[1:]:
            if width(line) + 1 + width(w) <= cells:
                line += ' ' + w
            else:
                lines.append(line)
                line = indent + w
        lines.append(line)
    return lines
