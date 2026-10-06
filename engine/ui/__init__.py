"""The paned terminal interface (tui.py). Layers, from the bottom:

    text      display width and wrapping
    surface   where it draws: curses, or a grid in memory (tests)
    session   the state: what has been read, the menu cursor, overlays (no curses)
    layout    which pane goes where for a terminal size
    widgets   drawing each pane
    app       keys in (as names), panes out; the curses loop

cli.py stays the plain interface, the fallback and the one scripts and the
playtest drive.
"""
