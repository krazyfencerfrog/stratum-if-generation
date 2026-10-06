"""The interface's state, without curses: what the player has read, where
the cursor is in the menu, which overlay is open.

    s = Session(Engine(story))
    s.start()
    s.move(1); s.enter()          # down one, then open it (or do it, at a leaf)
    s.back(); s.unwind(); s.rewind_to(3)
    s.open_overlay('journal')

`pages` runs beside the engine's history: page i is everything read after
history entry i (the choice, the text, the room when it changed), so an
unwind or a rewind trims it to match. A free action (Look, Inventory) adds
to the current page. The menu is a stack of levels, each remembering its
selected entry, so going back up lands where you were.
"""

from menukeys import KEYS
from recap import journal, journal_lines
from runtime import EngineError, SaveMismatch

OVERLAYS = ('journal', 'history', 'help', 'quit')


class Session:
    def __init__(self, engine, save_path='stratum.save'):
        self.engine = engine
        self.save_path = save_path
        self.pages = []
        self.view = None
        self.stack = []
        self.message = ''
        self.warn = False               # the message reports something that failed
        self.scroll = 0                 # lines scrolled back from the end of the story
        self.fresh = False              # something new to read: the story pane opens at its start
        self.overlay = None             # {'kind', 'index', 'scroll'}

    # ------------------------------------------------------------ life

    def start(self, seed=None):
        view = self.engine.start(seed=seed)
        self.pages = [[self._chapter(self.engine.state.scene, 1)] + self._entries(view, None)]
        self._set_view(view)
        self.note('')
        return view

    def _chapter(self, sid, number):
        title = (self.engine.story.scenes.get(sid) or {}).get('title') or sid
        return {'kind': 'chapter', 'text': self.engine.story.render(title, self.engine.state), 'number': number}

    def _chapters_so_far(self):
        return sum(1 for page in self.pages for e in page if e['kind'] == 'chapter')

    def _entries(self, view, label):
        out = [{'kind': 'choice', 'text': label}] if label else []
        out += [{'kind': 'text', 'text': t} for t in view.get('text') or [] if t]
        room = view.get('room')
        if room:
            out.append({'kind': 'room', 'title': room['name'], 'text': room['text']})
        if view.get('ending'):
            out.append({'kind': 'ending', 'text': view.get('ending_title') or 'The End'})
        return out

    def note(self, message, warn=False):
        self.message, self.warn = message, warn

    def _set_view(self, view):
        self.view = view
        self.stack = [{'node': view['menu'], 'index': 0}] if view.get('menu') else []
        self.scroll = 0
        self.fresh = True

    @property
    def ended(self):
        return bool(self.view and self.view.get('ending'))

    # ------------------------------------------------------------ the menu

    def level(self):
        return self.stack[-1] if self.stack else None

    def items(self):
        lvl = self.level()
        return lvl['node']['children'] if lvl else []

    def path(self):
        return [lvl['node']['label'] for lvl in self.stack[1:]]

    def selected(self):
        items = self.items()
        return items[self.level()['index']] if items else None

    def preview(self):
        """The full path of what Enter would do now."""
        sel = self.selected()
        return ' › '.join(self.path() + ([sel['label']] if sel and sel.get('label') else []))

    def move(self, delta):
        items = self.items()
        if items:
            lvl = self.level()
            lvl['index'] = (lvl['index'] + delta) % len(items)

    def select(self, index):
        if 0 <= index < len(self.items()):
            self.level()['index'] = index

    def back(self):
        if len(self.stack) > 1:
            self.stack.pop()
            return True
        return False

    def enter(self):
        """Open the selected entry, or do it if it is an action."""
        sel = self.selected()
        if sel is None:
            return None
        if 'id' in sel:
            return self.act(sel['id'], self.preview())
        self.stack.append({'node': sel, 'index': 0})
        return None

    def pick_key(self, key):
        """A menu key (1-9, letters): select that entry and enter it."""
        if key in KEYS and KEYS.index(key) < len(self.items()):
            self.select(KEYS.index(key))
            self.enter()
            return True
        return False

    # ------------------------------------------------------------ acting and time

    def act(self, option_id, label=None):
        before = len(self.engine.history)
        try:
            view = self.engine.act(option_id)
        except EngineError as e:
            self.note(str(e), warn=True)
            return None
        if len(self.engine.history) > before:
            h = self.engine.history[-1]
            page = self._entries(view, h['label'])
            if h.get('scene_after') != h.get('scene') and h.get('scene_after') in self.engine.story.scenes:
                at = 1 if page and page[0]['kind'] == 'choice' else 0     # the card comes after the choice that led there
                page.insert(at, self._chapter(h['scene_after'], self._chapters_so_far() + 1))
            self.pages.append(page)
        else:                                           # Look, Inventory: no time passes
            self.pages[-1].extend(self._entries(view, label))
        self._set_view(view)
        self.note('')
        return view

    def _trim(self, view):
        self.pages = self.pages[:len(self.engine.history)]
        if view.get('room') and self.pages:
            self.pages[-1] = [e for e in self.pages[-1] if e['kind'] != 'room'] + self._entries(dict(view, text=[]), None)
        self._set_view(view)

    def unwind(self):
        undone = self.engine.history[-1]['label'] if len(self.engine.history) > 1 else None
        try:
            view = self.engine.rewind()
        except EngineError as e:
            self.note(str(e), warn=True)
            return None
        self._trim(view)
        self.note(f'Unwound: {undone}' if undone else 'Unwound')
        return view

    def rewind_to(self, index):
        try:
            view = self.engine.rewind_to(index)
        except EngineError as e:
            self.note(str(e), warn=True)
            return None
        self._trim(view)
        self.note(f"Back to: {self.engine.history[index]['label']}")
        return view

    def save(self):
        try:
            self.engine.save(self.save_path)
            self.note(f'Saved to {self.save_path}')
        except OSError as e:
            self.note(f'Could not save: {e}', warn=True)

    def load(self):
        try:
            view = self.engine.load(self.save_path)
        except (OSError, SaveMismatch, ValueError) as e:
            self.note(f'Could not load: {e}', warn=True)
            return None
        self.pages = []
        for i, h in enumerate(self.engine.history):
            page = [{'kind': 'choice', 'text': h['label']}] if i else []
            new_scene = h.get('scene_after') if i == 0 or h.get('scene_after') != h.get('scene') else None
            if new_scene in self.engine.story.scenes:
                page.append(self._chapter(new_scene, self._chapters_so_far() + 1))
            self.pages.append(page + [{'kind': 'text', 'text': t} for t in h.get('text') or [] if t])
        self._trim(view)
        self.note(f'Loaded {self.save_path}')
        return view

    # ------------------------------------------------------------ what is around you

    def here(self):
        e, s = self.engine, self.engine.story
        st = e.state
        room = s.rooms.get(st.room) or {}
        scene = s.scenes.get(st.scene) or {}
        carried = [o for o, loc in st.locations.items() if loc == 'player']
        things = [o for o in e.visible_objects() if st.locations.get(o) == st.room
                  and s.objects[o].get('listed', s.objects[o].get('portable', False))]
        return {'title': s.title, 'chapter': scene.get('title') or st.scene, 'room': room.get('name') or st.room,
                'people': [s.name_of(c, st) for c in e.present()], 'things': [s.name_of(o, st) for o in things],
                'carrying': [s.name_of(o, st) for o in carried], 'turn': st.turns,
                'ending': self.view.get('ending_title') if self.ended else None}

    def journal(self):
        return journal_lines(journal(self.engine))

    def history_items(self):
        out = []
        last = len(self.engine.history) - 1
        for i, h in enumerate(self.engine.history):
            first = next((t for t in h.get('text') or [] if t), '')
            out.append({'index': i, 'label': h['label'], 'gist': first, 'current': i == last,
                        'major': h.get('weight') == 'major' or bool(h.get('answered'))})
        return out

    # ------------------------------------------------------------ overlays

    def open_overlay(self, kind):
        index = len(self.engine.history) - 1 if kind == 'history' else 0
        self.overlay = {'kind': kind, 'index': index, 'scroll': 0}

    def close_overlay(self):
        self.overlay = None
