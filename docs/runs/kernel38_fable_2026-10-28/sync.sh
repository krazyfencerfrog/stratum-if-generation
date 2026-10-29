#!/bin/sh
# Mirror the live run directory (gitignored under stories/) into docs/runs so every
# intermediate artifact survives: raw prompts, raw responses, parsed JSON, per-call logs,
# run stats, the pipeline log. Re-run any time; it only adds and updates.
cd "$(dirname "$0")/../../.." || exit 1
rsync -a --exclude '__pycache__' stories/kernel38_fable/ docs/runs/kernel38_fable_2026-10-28/run/
cp stories/kernel38_fable_run.log docs/runs/kernel38_fable_2026-10-28/run.log
date > docs/runs/kernel38_fable_2026-10-28/last_sync.txt
