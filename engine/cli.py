#!/usr/bin/env python3
"""Play a story package in the terminal.

The menu stands in for the radial UI: the root shows the verbs; one key
press (1-9, then letters) drills down to objects and details. Keys that are
always there: u unwind one action, h history (what you did, and a way back
to any point), j journal (the story so far), s save, l load, q quit; b (or
backspace, esc) goes back a level. tui.py is the paned interface; this is
the plain one, and the one scripts and the playtest drive. At a real terminal a key acts at once; piped input reads lines.

    python cli.py examples/kernel35_demo.json
    python cli.py story.json --check              # validate only
    python cli.py story.json --script 3,1,2        # play scripted picks (menu numbers per level), then stop
    python cli.py story.json --collapse all        # merge every single-option level into its parent
"""

import argparse
import json
import os
import select
import sys
import textwrap

from menukeys import KEYS
from recap import journal, journal_lines
from runtime import Engine, EngineError, SaveMismatch
from story import Story, validate

WIDTH = 78
BACK_KEYS = ('b', '\x7f', '\x08', '\x1b')


def read_key(prompt, out):
    """One key press from a terminal, without enter. Arrow keys and other
    escape sequences are swallowed whole; a lone esc is esc."""
    import termios
    import tty
    print(prompt, end='', flush=True, file=out)
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        key = os.read(fd, 1).decode(errors='ignore')
        if key == '\x1b':
            while select.select([fd], [], [], 0.03)[0]:
                os.read(fd, 8)
                key = ''                                    # an arrow or function key: no choice at all
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    shown = {'\x1b': 'esc', '\x7f': 'back', '\x08': 'back', '\n': '', '\r': ''}.get(key, key)
    print(shown, file=out)
    return key


def wrap(text):
    return '\n'.join(textwrap.fill(p, WIDTH) for p in text.split('\n'))


def format_frame(frame, title="VISUAL FRAME"):
    comp = str(frame.get('composition') or '').strip()
    subs = ', '.join(frame.get('subjects') or []) if isinstance(frame.get('subjects'), list) else str(frame.get('subjects') or '')
    env = str(frame.get('environment') or '').strip()
    palette = str(frame.get('palette_mood') or '').strip()
    summary = str(frame.get('prompt_summary') or '').strip()

    hdr = f"┌─ [ {title.upper()} ] "
    hdr += "─" * max(0, WIDTH - len(hdr) - 1) + "┐"
    lines = [hdr]

    parts = []
    if comp:
        parts.append(f"Composition: {comp}")
    if subs:
        parts.append(f"Subjects: {subs}")
    if env:
        parts.append(f"Environment: {env}")
    if palette:
        parts.append(f"Palette/Mood: {palette}")
    if summary and not (comp or subs or env):
        parts.append(summary)

    for p in parts:
        for b in textwrap.fill(p, WIDTH - 4).split('\n'):
            lines.append(f"│ {b:<{WIDTH - 4}} │")
    lines.append("└" + "─" * (WIDTH - 2) + "┘")
    return '\n'.join(lines)


def show(view, out, show_frames=False):
    if show_frames and view.get('frame'):
        name = view.get('room', {}).get('name') if view.get('room') else 'Scene'
        print(format_frame(view['frame'], name) + '\n', file=out)
    for t in view['text']:
        print(wrap(t) + '\n', file=out)
    if view.get('ending'):
        print(f"*** {view.get('ending_title') or 'The End'} ***", file=out)
        return
    room = view.get('room')
    if room:
        print(f"[{room['name']}]", file=out)
        print(wrap(room['text']) + '\n', file=out)


def show_level(node, path, out):
    if path:
        print('  ' + ' › '.join(path), file=out)
    for key, child in zip(KEYS, node['children']):
        more = '' if 'id' in child else ' …'
        mark = ' ◆' if child.get('weight') == 'major' else ''      # a line-changing choice (a front-end option)
        new = ' •' if child.get('new') else ''                      # not yet examined, asked or thought
        way = ' →' if child.get('way') else ''                      # the way on, shown once you have idled a while
        print(f'  {key}. {child["label"]}{more}{new}{mark}{way}', file=out)
    print('  ' + ('[b] prev menu  ' if path else '') + '[u] unwind  [h] history  [j] journal  [s] save  [l] load  [q] quit',
          file=out)


def show_journal(engine, out):
    print(file=out)
    for kind, text in journal_lines(journal(engine)):
        if kind in ('title', 'section'):
            print(f'  == {text} ==' if kind == 'title' else f'\n  {text}', file=out)
        elif kind in ('chapter', 'current', 'ending'):
            print(f'\n  {text}', file=out)
        else:
            print(textwrap.fill(text, WIDTH, initial_indent='     ', subsequent_indent='     '), file=out)
    print(file=out)


def history(engine, ask, out):
    """List what has happened; offer to go back to any earlier point.
    Returns the new view if the player went back, else None."""
    entries = engine.history
    keys = '0' + KEYS
    start = max(0, len(entries) - len(keys))               # the most recent points, if there are more than keys
    print('\n  History:', file=out)
    for key, i in zip(keys, range(start, len(entries))):
        h = entries[i]
        first = next((t for t in h['text'] if t), '')
        gist = (first[:60] + '…') if len(first) > 60 else first
        here = '  <- you are here' if i == len(entries) - 1 else ''
        print(f"  {key}. {h['label']}{here}", file=out)
        if gist:
            print(f'       {gist}', file=out)
    if len(entries) < 2:
        return None
    choice = ask('  go back to which point? (its key, or anything else to stay) ').strip().lower()
    if not choice or choice not in keys or start + keys.index(choice) >= len(entries) - 1:
        return None
    choice = str(start + keys.index(choice))
    index = int(choice)
    view = engine.rewind_to(index)
    print(f"\n(back to {index}: {entries[index]['label'] if index < len(entries) else ''})\n", file=out)
    for t in engine.history[index]['text']:
        print(wrap(t) + '\n', file=out)
    show(dict(view, text=[]), out)
    return view


def play(engine, picks=None, out=sys.stdout, save_path='stratum.save', keys=None, show_frames=False):
    """Run the loop. `picks` (a list of strings) replaces input when given.
    `keys`: one press per choice; by default, when stdin is a terminal."""
    feed = iter(picks) if picks is not None else None
    if keys is None:
        keys = feed is None and sys.stdin.isatty()

    def ask(prompt):
        if feed is not None:
            try:
                choice = next(feed)
            except StopIteration:
                return 'q'
            print(f'{prompt}{choice}', file=out)
            return choice
        try:
            return read_key(prompt, out) if keys else input(prompt)
        except (EOFError, KeyboardInterrupt):
            return 'q'

    view = engine.start()
    show(view, out, show_frames=show_frames)
    while not view.get('ending'):
        stack = [(view['menu'], [])]
        while True:
            node, path = stack[-1]
            show_level(node, path, out)
            raw = ask('> ')
            choice = raw if raw in BACK_KEYS else raw.strip().lower()
            if choice == 'q':
                return view
            if choice in BACK_KEYS:
                if len(stack) > 1:
                    stack.pop()
                continue
            if choice == 'u':
                try:
                    view = engine.rewind()
                    print('(unwound)\n', file=out)
                    show(view, out, show_frames=show_frames)
                except EngineError as e:
                    print(f'({e})', file=out)
                break
            if choice == 'h':
                rewound = history(engine, ask, out)
                if rewound:
                    view = rewound
                    break
                continue
            if choice == 'j':
                show_journal(engine, out)
                continue
            if choice == 's':
                engine.save(save_path)
                print(f'(saved to {save_path})', file=out)
                continue
            if choice == 'l':
                try:
                    view = engine.load(save_path)
                    print('(loaded)\n', file=out)
                    show(view, out, show_frames=show_frames)
                except (OSError, SaveMismatch) as e:
                    print(f'({e})', file=out)
                break
            if not choice:
                continue
            if choice not in KEYS[:len(node['children'])]:
                print('  (pick an option\'s key, or b, u, h, j, s, l, q)', file=out)
                continue
            child = node['children'][KEYS.index(choice)]
            if 'id' in child:
                print(file=out)
                view = engine.act(child['id'])
                show(view, out, show_frames=show_frames)
                break
            stack.append((child, path + [child['label']]))
    return view


def show_info(story, out=sys.stdout):
    sep = '=' * WIDTH
    print(sep, file=out)
    print(story.title, file=out)
    sub = []
    if story.author:
        sub.append(f'by {story.author}')
    if story.rating:
        desc = f": {','.join(story.rating_descriptors)}" if story.rating_descriptors else ""
        sub.append(f'[{story.rating}{desc}]')
    if sub:
        print(' '.join(sub), file=out)
    if story.tagline:
        print(f'"{story.tagline}"', file=out)
    print('-' * WIDTH, file=out)
    if story.rating_advisory:
        print(f'Rating Advisory : {story.rating_advisory}', file=out)
    if story.model:
        print(f'Model           : {story.model}', file=out)
    print(f'Scenes          : {len(story.scenes)}', file=out)
    print(f'Rooms           : {len(story.rooms)}', file=out)
    print(f'Endings         : {len(story.endings)}', file=out)
    print(f'Characters      : {len(story.characters)}', file=out)
    print(f'Objects         : {len(story.objects)}', file=out)
    print(sep, file=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('package')
    ap.add_argument('--check', action='store_true', help='validate the package and stop')
    ap.add_argument('--info', action='store_true', help='display story package metadata, overview, and statistics, then stop')
    ap.add_argument('--frames', action='store_true', help='render visual keyframe descriptions on scene/room arrival')
    ap.add_argument('--export-frames', help='export all visual keyframes across the story to a JSON file and stop')
    ap.add_argument('--script', help='comma-separated menu picks to play instead of reading input')
    ap.add_argument('--save', default=os.path.join(os.getcwd(), 'stratum.save'))
    ap.add_argument('--collapse', choices=('trivial', 'all'), default='trivial',
                    help="merge single-option menu levels: only where there is no choice (trivial), or always (all)")
    args = ap.parse_args(argv)
    story = Story.load(args.package)
    errors, notes = validate(story)
    for n in notes:
        print(f'note: {n}')
    for e in errors:
        print(f'ERROR: {e}')
    if errors or args.check:
        return 1 if errors else 0
    if args.info:
        show_info(story, out=sys.stdout)
        return 0
    if args.export_frames:
        frames = story.export_frames()
        with open(args.export_frames, 'w', encoding='utf-8') as f:
            json.dump(frames, f, ensure_ascii=False, indent=2)
        count = sum(len(v) for k, v in frames.items() if isinstance(v, dict))
        print(f'Exported {count} frames to {args.export_frames}')
        return 0
    print(f'== {story.title} ==')
    sub = []
    if story.author and story.author != 'Anonymous':
        sub.append(f'by {story.author}')
    if story.rating:
        desc = f": {','.join(story.rating_descriptors)}" if story.rating_descriptors else ""
        sub.append(f'[{story.rating}{desc}]')
    if sub:
        print(' '.join(sub))
    if story.tagline:
        print(f'"{story.tagline}"')
    if story.rating_advisory:
        print(f'({story.rating_advisory})')
    print()
    picks = args.script.split(',') if args.script else None
    play(Engine(story, collapse=args.collapse), picks, save_path=args.save, show_frames=args.frames)
    return 0


if __name__ == '__main__':
    sys.exit(main())
