"""The paned interface: keys in, panes out.

App.handle(key) takes a key NAME ('up', 'enter', 'pgdn', 'esc', 'tab',
'resize', a character, or ('mouse', y, x, what)), so the same logic runs
under curses, from a script (tui.py --keys) and in tests. run() is the
curses loop: it translates what curses reads into those names.
"""

from . import widgets as W
from .layout import layout
from .surface import CursesSurface

BACK = ('left', 'backspace', 'b')


class App:
    def __init__(self, session, surface):
        self.s = session
        self.surface = surface
        self.sidebar = True
        self.running = True
        self.rects = None
        self.menu_hits = {}
        self.overlay_lines = 0

    # ------------------------------------------------------------ drawing

    def draw(self):
        sf, s = self.surface, self.s
        sf.clear()
        h, w = sf.size()
        rects = layout(h, w, self.sidebar)
        self.rects = rects
        if rects['too_small']:
            W.too_small(sf, h, w)
            sf.refresh()
            return
        here = s.here()
        W.header(sf, rects['header'], here)
        W.story(sf, rects['story'], s)
        self.menu_hits = W.menu(sf, rects['menu'], s)
        if rects['side']:
            W.side(sf, rects['side'], here)
        W.status(sf, rects['status'], s)
        W.footer(sf, rects['footer'], s)
        if s.overlay:
            self.overlay_lines = W.overlay(sf, rects['overlay'], s)
        sf.refresh()

    # ------------------------------------------------------------ keys

    def page(self):
        r = (self.rects or {}).get('story')
        return max(1, (r.h - 4) if r else 10)

    def handle(self, key):
        """One key. Returns False when the app should stop."""
        s = self.s
        if isinstance(key, tuple) and key and key[0] == 'mouse':
            self.mouse(*key[1:])
            return self.running
        if key == 'resize':
            return self.running
        s.note('')                          # a message lasts until the next key
        if s.overlay:
            self.overlay_key(key)
            return self.running
        if key in ('pgup', 'pgdn', 'home', 'end'):
            s.scroll = {'pgup': s.scroll + self.page(), 'pgdn': max(0, s.scroll - self.page()),
                        'home': 10 ** 9, 'end': 0}[key]
            return self.running
        if key == 'q':
            s.open_overlay('quit')
        elif key == '?':
            s.open_overlay('help')
        elif key == 'j':
            s.open_overlay('journal')
        elif key == 'h':
            s.open_overlay('history')
        elif key == 'u':
            s.unwind()
        elif key == 's':
            s.save()
        elif key == 'l':
            s.load()
        elif key == 'tab':
            self.sidebar = not self.sidebar
        elif s.ended:
            if key == 'n':
                s.start()
        elif key == 'up':
            s.move(-1)
        elif key == 'down':
            s.move(1)
        elif key in ('right', 'enter'):
            s.enter()
        elif key in BACK or key == 'esc':
            s.back()
        elif isinstance(key, str) and len(key) == 1:
            if not s.pick_key(key.lower()):
                s.note(f"'{key}' is not a choice here (? for help)", warn=True)
        return self.running

    def overlay_key(self, key):
        s, ov = self.s, self.s.overlay
        kind = ov['kind']
        if kind == 'quit':
            if key in ('y', 'Y', 'q'):
                self.running = False
            else:
                s.close_overlay()
            return
        closers = {'journal': 'j', 'history': 'h', 'help': '?'}
        if key in ('esc', 'left', 'backspace') or key == closers.get(kind) or key == 'q':
            s.close_overlay()
            return
        if kind == 'history':
            last = len(s.engine.history) - 1
            if key in ('up', 'k'):
                ov['index'] = max(0, ov['index'] - 1)
            elif key in ('down',):
                ov['index'] = min(last, ov['index'] + 1)
            elif key in ('pgup', 'home'):
                ov['index'] = 0 if key == 'home' else max(0, ov['index'] - 10)
            elif key in ('pgdn', 'end'):
                ov['index'] = last if key == 'end' else min(last, ov['index'] + 10)
            elif key in ('enter', 'right'):
                if ov['index'] < last:
                    s.rewind_to(ov['index'])
                s.close_overlay()
            return
        step = {'up': -1, 'down': 1, 'pgup': -10, 'pgdn': 10, 'home': -10 ** 9, 'end': 10 ** 9}.get(key)
        if step is not None:
            ov['scroll'] = max(0, ov['scroll'] + step)

    def mouse(self, y, x, what):
        s = self.s
        if s.overlay:
            if what in ('wheel_up', 'wheel_down'):
                self.overlay_key('up' if what == 'wheel_up' else 'down')
            return
        r = self.rects or {}
        story = r.get('story')
        if what in ('wheel_up', 'wheel_down'):
            if story and story.y <= y < story.y + story.h and story.x <= x < story.x + story.w:
                s.scroll = s.scroll + 3 if what == 'wheel_up' else max(0, s.scroll - 3)
            else:
                s.move(-1 if what == 'wheel_up' else 1)
            return
        if what == 'click' and y in self.menu_hits:
            menu = r.get('menu')
            if menu and menu.x <= x < menu.x + menu.w:
                index = self.menu_hits[y]
                if s.level() and s.level()['index'] == index:
                    s.enter()                       # a click on the selected entry does it
                else:
                    s.select(index)


# ---------------------------------------------------------------- the curses loop

def translate(curses, stdscr, ch):
    """What curses read, as a key name."""
    if isinstance(ch, str):
        return {'\n': 'enter', '\r': 'enter', '\x1b': 'esc', '\x7f': 'backspace', '\x08': 'backspace',
                '\t': 'tab'}.get(ch, ch)
    names = {curses.KEY_UP: 'up', curses.KEY_DOWN: 'down', curses.KEY_LEFT: 'left', curses.KEY_RIGHT: 'right',
             curses.KEY_ENTER: 'enter', curses.KEY_BACKSPACE: 'backspace', curses.KEY_PPAGE: 'pgup',
             curses.KEY_NPAGE: 'pgdn', curses.KEY_HOME: 'home', curses.KEY_END: 'end', curses.KEY_RESIZE: 'resize',
             curses.KEY_BTAB: 'tab'}
    if ch == curses.KEY_MOUSE:
        try:
            _, x, y, _, state = curses.getmouse()
        except curses.error:
            return None
        if state & getattr(curses, 'BUTTON4_PRESSED', 0):
            return ('mouse', y, x, 'wheel_up')
        if state & getattr(curses, 'BUTTON5_PRESSED', 1 << 21):
            return ('mouse', y, x, 'wheel_down')
        if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED | curses.BUTTON1_RELEASED):
            return ('mouse', y, x, 'click') if state & (curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED) else None
        return None
    return names.get(ch)


def run(session, keys=None, mouse=True):
    """Play in the terminal until quit. `keys`: key names to play instead of
    reading the keyboard (the screen is still drawn); the loop ends when
    they run out."""
    import curses
    import locale
    locale.setlocale(locale.LC_ALL, '')

    def main(stdscr):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        if hasattr(curses, 'set_escdelay'):
            curses.set_escdelay(25)
        stdscr.keypad(True)
        if mouse:
            curses.mousemask(curses.ALL_MOUSE_EVENTS)
            curses.mouseinterval(0)
        app = App(session, CursesSurface(stdscr))
        feed = iter(keys) if keys is not None else None
        while app.running:
            app.draw()
            if feed is not None:
                key = next(feed, None)
                if key is None:
                    break
            else:
                try:
                    key = translate(curses, stdscr, stdscr.get_wch())
                except curses.error:
                    continue
                except KeyboardInterrupt:
                    break
            if key is not None:
                app.handle(key)
        return app
    return curses.wrapper(main)
