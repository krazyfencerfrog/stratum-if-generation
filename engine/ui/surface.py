"""Where the interface draws: a curses screen, or a grid in memory.

Widgets draw with put(y, x, text, style) in named styles, never curses
attributes, so the same drawing code runs in a terminal and in a test
(MemorySurface keeps every cell's character and style for assertions and
snapshots). Styles map to curses attributes and colour pairs in one table
(THEME), the place to change how it looks.
"""

from . import text as T

STYLES = ('normal', 'dim', 'bold', 'header', 'title', 'choice', 'mark', 'new', 'selected', 'border', 'muted',
          'warn', 'current', 'heading', 'key')

# style -> (foreground colour name or None, attribute names); colours fall back to attributes on a plain terminal
THEME = {
    'normal':   (None, ()),
    'dim':      (None, ('dim',)),
    'bold':     (None, ('bold',)),
    'header':   ('header', ('reverse', 'bold')),
    'title':    ('yellow', ('bold',)),
    'choice':   ('cyan', ()),
    'mark':     ('yellow', ('bold',)),
    'new':      (None, ('bold',)),
    'selected': ('selected', ('reverse',)),
    'border':   ('blue', ()),
    'muted':    (None, ('dim',)),
    'warn':     ('red', ('bold',)),
    'current':  ('green', ('bold',)),
    'heading':  ('magenta', ('bold',)),
    'key':      ('cyan', ('bold',)),
}


class Surface:
    def size(self):
        raise NotImplementedError

    def put(self, y, x, text, style='normal'):
        raise NotImplementedError

    def clear(self):
        raise NotImplementedError

    def refresh(self):
        pass

    def fill(self, y, x, h, w, style='normal'):
        for row in range(y, y + h):
            self.put(row, x, ' ' * w, style)


class MemorySurface(Surface):
    """A grid of (character, style): what a test reads back."""

    def __init__(self, height, width):
        self.h, self.w = height, width
        self.clear()

    def size(self):
        return self.h, self.w

    def clear(self):
        self.chars = [[' '] * self.w for _ in range(self.h)]
        self.styles = [['normal'] * self.w for _ in range(self.h)]

    def put(self, y, x, text, style='normal'):
        if not 0 <= y < self.h or x >= self.w:
            return
        for ch in str(text):
            cw = T.char_width(ch)
            if cw == 0:
                continue
            if x + cw > self.w:
                break
            if x >= 0:
                self.chars[y][x] = ch
                self.styles[y][x] = style
                if cw == 2 and x + 1 < self.w:
                    self.chars[y][x + 1] = ''
                    self.styles[y][x + 1] = style
            x += cw

    def lines(self):
        return [''.join(row).rstrip() for row in self.chars]

    def text(self):
        return '\n'.join(self.lines())

    def find(self, needle):
        """(y, x) of the first place `needle` is drawn, or None."""
        for y, line in enumerate(self.lines()):
            x = line.find(needle)
            if x >= 0:
                return y, x
        return None

    def style_at(self, y, x):
        return self.styles[y][x]


class CursesSurface(Surface):
    def __init__(self, stdscr):
        import curses
        self.curses = curses
        self.scr = stdscr
        self.attrs = {}
        colours = {}
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            named = {'red': curses.COLOR_RED, 'green': curses.COLOR_GREEN, 'yellow': curses.COLOR_YELLOW,
                     'blue': curses.COLOR_BLUE, 'magenta': curses.COLOR_MAGENTA, 'cyan': curses.COLOR_CYAN}
            pairs = dict(named)
            pairs['header'] = (curses.COLOR_BLACK, curses.COLOR_CYAN)
            pairs['selected'] = (curses.COLOR_BLACK, curses.COLOR_YELLOW)
            for n, (name, value) in enumerate(pairs.items(), 1):
                try:
                    fg, back = value if isinstance(value, tuple) else (value, bg)
                    curses.init_pair(n, fg, back)
                    colours[name] = curses.color_pair(n)
                except curses.error:
                    pass
        flags = {'bold': curses.A_BOLD, 'dim': curses.A_DIM, 'reverse': curses.A_REVERSE}
        for style, (colour, names) in THEME.items():
            attr = 0
            if colour in colours:
                attr |= colours[colour]
                names = tuple(n for n in names if n != 'reverse')     # a coloured background replaces reverse video
            for n in names:
                attr |= flags[n]
            self.attrs[style] = attr

    def size(self):
        return self.scr.getmaxyx()

    def clear(self):
        self.scr.erase()

    def put(self, y, x, text, style='normal'):
        h, w = self.size()
        if not 0 <= y < h or x >= w or x < 0:
            return
        text = T.clip(str(text), w - x - (1 if y == h - 1 else 0))     # the last cell of the screen cannot be written
        try:
            self.scr.addstr(y, x, text, self.attrs.get(style, 0))
        except self.curses.error:
            pass

    def refresh(self):
        self.scr.refresh()
