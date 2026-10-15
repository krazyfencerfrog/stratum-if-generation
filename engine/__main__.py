#!/usr/bin/env python3
"""Cross-platform entry point for the Stratum IF engine.

Run from the repository root:
    python -m engine examples/kernel35_the_mooring_line.json          # TUI (default)
    python -m engine --cli examples/kernel35_the_mooring_line.json    # plain terminal
    python -m engine --check examples/kernel35_the_mooring_line.json  # validate only
    python -m engine --playtest examples/kernel35_the_mooring_line.json  # automated solver
"""

import os
import sys

# Resolve the engine directory relative to this file, not cwd.
_engine_dir = os.path.dirname(os.path.abspath(__file__))
if _engine_dir not in sys.path:
    sys.path.insert(0, _engine_dir)

# Pre-parse to detect mode flags, then delegate to the appropriate module.
mode = 'tui'
argv = sys.argv[1:]

# Extract mode flags before passing the rest to the target module.
if '--cli' in argv:
    mode = 'cli'
    argv.remove('--cli')
elif '--playtest' in argv:
    mode = 'playtest'
    argv.remove('--playtest')
elif '--check' in argv:
    # --check is handled by cli.py
    mode = 'cli'

if mode == 'tui':
    from tui import main
elif mode == 'cli':
    from cli import main
elif mode == 'playtest':
    from playtest import main

sys.exit(main(argv) or 0)
