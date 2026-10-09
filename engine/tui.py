#!/usr/bin/env python3
"""Play a story package in a paned terminal interface.

    python tui.py examples/kernel35_demo.json
    python tui.py story.json --keys down,enter,j,esc,q     # play key names instead of the keyboard

The story scrolls on the left, the menu sits on the right (below the story
on a narrow terminal) with a panel of who and what is here. Arrow keys move
through the menu (→ or Enter opens or does, ← goes back), or press an
entry's key. u unwinds, h goes back to any point, j shows the story so
far, s and l save and load, ? is help, q quits. The mouse clicks entries
and the wheel scrolls. cli.py is the plain interface (a pipe, a script, a
terminal without curses).
"""

import argparse
import os
import sys

from runtime import Engine
from story import Story, validate
from ui.app import run
from ui.session import Session


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('package')
    ap.add_argument('--save', default=os.path.join(os.getcwd(), 'stratum.save'))
    ap.add_argument('--collapse', choices=('trivial', 'all'), default='trivial')
    ap.add_argument('--keys', help='comma-separated key names to play (up, down, left, right, enter, esc, pgup, '
                                   'pgdn, tab, or a character), then stop')
    ap.add_argument('--no-mouse', action='store_true')
    args = ap.parse_args(argv)
    story = Story.load(args.package)
    errors, _ = validate(story)
    if errors:
        for e in errors:
            print(f'ERROR: {e}', file=sys.stderr)
        return 1
    if not sys.stdout.isatty() and args.keys is None:
        print('tui.py needs a terminal; use cli.py for pipes and scripts', file=sys.stderr)
        return 1
    session = Session(Engine(story, collapse=args.collapse), save_path=args.save)
    session.start()
    keys = [k.replace('comma', ',') for k in args.keys.split(',')] if args.keys is not None else None
    run(session, keys=keys, mouse=not args.no_mouse)
    return 0


if __name__ == '__main__':
    sys.exit(main())
