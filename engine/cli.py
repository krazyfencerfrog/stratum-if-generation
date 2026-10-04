#!/usr/bin/env python3
"""Play a story package in the terminal.

The menu stands in for the radial UI: the root shows the verbs; pick a
number to drill down to objects and details. Other keys: b back a level,
r rewind one action, h history (what you did, and a way back to any point),
s save, l load, q quit.

    python cli.py examples/kernel35_demo.json
    python cli.py story.json --check              # validate only
    python cli.py story.json --script 3,1,2        # play scripted picks (menu numbers per level), then stop
    python cli.py story.json --collapse all        # merge every single-option level into its parent
"""

import argparse
import os
import sys
import textwrap

from runtime import Engine, EngineError, SaveMismatch
from story import Story, validate

WIDTH = 78


def wrap(text):
    return '\n'.join(textwrap.fill(p, WIDTH) for p in text.split('\n'))


def show(view, out):
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
    for i, child in enumerate(node['children'], 1):
        more = '' if 'id' in child else ' …'
        mark = ' ◆' if child.get('weight') == 'major' else ''      # a line-changing choice (a front-end option)
        print(f'  {i}. {child["label"]}{more}{mark}', file=out)


def history(engine, ask, out):
    """List what has happened; offer to go back to any earlier point.
    Returns the new view if the player went back, else None."""
    entries = engine.history
    print('\n  History:', file=out)
    for i, h in enumerate(entries):
        first = next((t for t in h['text'] if t), '')
        gist = (first[:60] + '…') if len(first) > 60 else first
        here = '  <- you are here' if i == len(entries) - 1 else ''
        print(f"  {i:>3}. {h['label']}{here}", file=out)
        if gist:
            print(f'       {gist}', file=out)
    if len(entries) < 2:
        return None
    choice = ask('  go back to which point? (number, or enter to stay) ').strip()
    if not choice.isdigit() or not 0 <= int(choice) < len(entries) - 1:
        return None
    index = int(choice)
    view = engine.rewind_to(index)
    print(f"\n(back to {index}: {entries[index]['label'] if index < len(entries) else ''})\n", file=out)
    for t in engine.history[index]['text']:
        print(wrap(t) + '\n', file=out)
    show(dict(view, text=[]), out)
    return view


def play(engine, picks=None, out=sys.stdout, save_path='stratum.save'):
    """Run the loop. `picks` (a list of strings) replaces input when given."""
    feed = iter(picks) if picks is not None else None

    def ask(prompt):
        if feed is not None:
            try:
                choice = next(feed)
            except StopIteration:
                return 'q'
            print(f'{prompt}{choice}', file=out)
            return choice
        try:
            return input(prompt)
        except EOFError:
            return 'q'

    view = engine.start()
    show(view, out)
    while not view.get('ending'):
        stack = [(view['menu'], [])]
        while True:
            node, path = stack[-1]
            show_level(node, path, out)
            choice = ask('> ').strip().lower()
            if choice == 'q':
                return view
            if choice == 'b':
                if len(stack) > 1:
                    stack.pop()
                continue
            if choice == 'r':
                try:
                    view = engine.rewind()
                    print('(rewound)\n', file=out)
                    show(view, out)
                except EngineError as e:
                    print(f'({e})', file=out)
                break
            if choice == 'h':
                rewound = history(engine, ask, out)
                if rewound:
                    view = rewound
                    break
                continue
            if choice == 's':
                engine.save(save_path)
                print(f'(saved to {save_path})', file=out)
                continue
            if choice == 'l':
                try:
                    view = engine.load(save_path)
                    print('(loaded)\n', file=out)
                    show(view, out)
                except (OSError, SaveMismatch) as e:
                    print(f'({e})', file=out)
                break
            if not choice.isdigit() or not 1 <= int(choice) <= len(node['children']):
                print('  (pick a number, or b, r, h, s, l, q)', file=out)
                continue
            child = node['children'][int(choice) - 1]
            if 'id' in child:
                print(file=out)
                view = engine.act(child['id'])
                show(view, out)
                break
            stack.append((child, path + [child['label']]))
    return view


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('package')
    ap.add_argument('--check', action='store_true', help='validate the package and stop')
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
    print(f'== {story.title} ==\n')
    picks = args.script.split(',') if args.script else None
    play(Engine(story, collapse=args.collapse), picks, save_path=args.save)
    return 0


if __name__ == '__main__':
    sys.exit(main())
