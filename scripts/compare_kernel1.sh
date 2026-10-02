#!/bin/bash
# Run kernel1 through the main line on two branches, reusing the archived
# run's phase 3, and print each run's report beside the archive baseline.
#
#   scripts/compare_kernel1.sh                      # opus vs combined
#   BRANCHES="request-4-combined outline-loop-fable-request-4" scripts/compare_kernel1.sh
#   DEST=~/cmp ITERATIONS=2 scripts/compare_kernel1.sh
#   EXTRA_ARGS="--craft-spine" scripts/compare_kernel1.sh   # passed to every run
#
# Each branch is exported (git archive, no worktree) into $DEST/<branch>.
# generator/dynamic_config.py is copied from this checkout. The runs go one
# after the other (one GPU). Expect roughly 1.5-3 hours per branch: the
# premise (3.5) and the main line run live; phase 3 is reused.
# STRATUM_CLIENT=stub in the environment runs the whole thing on the stub
# in seconds, to check the setup before spending model time.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-$REPO/../stratum-compare}"
BRANCHES="${BRANCHES:-request-4-outline-loop-opus request-4-combined}"
ITERATIONS="${ITERATIONS:-1}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
SID=kernel1_cmp

mkdir -p "$DEST"
ARCH="$DEST/archive"
if [ ! -d "$ARCH/kernel1" ]; then
    mkdir -p "$ARCH"
    tar -xf "$REPO/stories/current_output.tar" -C "$ARCH"
fi

if [ "${STRATUM_CLIENT:-}" != "stub" ] && [ ! -f "$REPO/generator/dynamic_config.py" ]; then
    echo "generator/dynamic_config.py not found in $REPO; create it first (see README)" >&2
    exit 1
fi

for BR in $BRANCHES; do
    REF="$BR"
    git -C "$REPO" rev-parse --verify -q "$REF" >/dev/null || REF="origin/$BR"
    OUT="$DEST/$BR"
    echo "=== $BR -> $OUT"
    if [ ! -d "$OUT/generator" ]; then
        mkdir -p "$OUT"
        git -C "$REPO" archive "$REF" | tar -x -C "$OUT"
    fi
    [ -f "$REPO/generator/dynamic_config.py" ] && cp "$REPO/generator/dynamic_config.py" "$OUT/generator/"
    S="$OUT/stories/$SID"
    if [ ! -d "$S" ]; then
        mkdir -p "$S"
        # the kernel, step 2 and phase 3 (all unchanged prompts), renamed to this story id
        for f in s1_kernel.txt s2_rating.txt s2_shape.json s2_kernel.txt \
                 s3_0a_interactive_question.json s3_0b_identity_epistemic.json \
                 s3_0c_consequence_failure_model.json s3b_affect.json s3c_theme.json \
                 s3d_viewpoint.json s3e_timeline.json s3f_setting.json s3g_complexity.json \
                 s3h_cross_check.json; do
            cp "$ARCH/kernel1/kernel1_$f" "$S/${SID}_$f"
        done
    fi
    ( cd "$OUT/generator" && python3 main.py --story-id=$SID --max-iterations="$ITERATIONS" $EXTRA_ARGS \
          < "$REPO/tests/kernels/kernel1.txt" ) || echo "!!! $BR stopped with an error; see $S"
done

echo
for BR in $BRANCHES; do
    OUT="$DEST/$BR"
    echo "=================== $BR"
    if [ -f "$OUT/generator/report.py" ]; then
        ( cd "$OUT/generator" && python3 report.py $SID --baseline ../docs/baseline_kernel1_run_stats.json ) || true
    else
        ( cd "$OUT/generator" && python3 run_report.py $SID --baseline "$ARCH/kernel1" --baseline-from-logs ) || true
    fi
    ls "$OUT/stories/$SID/"*story*.md 2>/dev/null | sed 's/^/outline: /'
done
echo
echo "Read the two outlines beside docs/kernel1_target_outline.md (combined) / docs/kernel1_outline_target.md (opus)."
