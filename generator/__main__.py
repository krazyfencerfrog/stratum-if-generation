#!/usr/bin/env python3
"""Cross-platform entry point for the Stratum IF generation pipeline.

Run from the repository root:
    python -m generator --story-id=my_story tests/kernels/kernel35.txt
    python -m generator --story-id=my_story --no-prose tests/kernels/kernel1.txt
    STRATUM_CLIENT=stub python -m generator --story-id=stubtest tests/kernels/kernel1.txt

Handles sys.path and working directory setup so that generator/ sibling
imports work without the caller needing to cd into the directory.
"""

import os
import sys

_orig_cwd = os.getcwd()

_generator_dir = os.path.dirname(os.path.abspath(__file__))
if _generator_dir not in sys.path:
    sys.path.insert(0, _generator_dir)

# The generator's sibling imports and relative file paths (prompts/, stories/)
# expect the working directory to be generator/.
os.chdir(_generator_dir)

argv = list(sys.argv[1:])

# Handle --no-prose: if present, skip prose and run through Stage D.
no_prose = '--no-prose' in argv
if no_prose:
    argv.remove('--no-prose')

# Default to full-pipeline (--prose) unless:
# - --no-prose was explicitly passed
# - --stop-after was specified
# - specific stages were requested (--stage-a, --stage-b, --stage-d)
# - --prose was already specified
stage_flags = {'--stage-a', '--stage-b', '--stage-d'}
has_stop = any(a.startswith('--stop-after') for a in argv)
has_stage = any(a in stage_flags for a in argv)
has_prose = '--prose' in argv

if not no_prose and not has_stop and not has_stage and not has_prose:
    argv.append('--prose')
elif no_prose and not has_stop and not has_stage:
    # --no-prose means compile package up to Stage D without the prose pass
    argv.append('--stage-d')

# If any positional argument is a relative path to an existing file, resolve it
# relative to the caller's original cwd (since we chdir'd to generator/).
resolved_argv = []
for arg in argv:
    if not arg.startswith('-') and not os.path.isabs(arg):
        candidate = os.path.join(_orig_cwd, arg)
        if os.path.isfile(candidate):
            resolved_argv.append(candidate)
            continue
    resolved_argv.append(arg)

from main import main

if __name__ == '__main__':
    main(resolved_argv)
