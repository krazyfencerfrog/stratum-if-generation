# kernel38 on Fable 5.1, 2026-10-28: the end-to-end run behind docs/fable_response_6.md

Command (from the repo root):

    STRATUM_CLIENT=claude STRATUM_CLAUDE_MODEL=fable STRATUM_PLAYTEST_JOBS=$(sysctl -n hw.ncpu) \
      python3 -m generator --story-id=kernel38_fable --stage-d --parallel 8 tests/kernels/kernel38.txt

What is here:
- `run/`: a mirror of `stories/kernel38_fable/` (gitignored), every artifact the pipeline wrote:
  `<prefix>_raw_input_prompt.txt` (exactly what was sent), `<prefix>_raw_output_response.txt`,
  the parsed `<prefix>_*.json`, one `<prefix>_<epoch>.log` per call attempt (the streamed answer and
  the timing line), `kernel38_fable_run_stats.json` (one record per call attempt), and the stage
  documents (`_s3_brief.json`, `_s3_5_premise_accepted.json`, `_story.json/.md`, `_arcs.json/.md`,
  `_world.json/.md`, `_package_draft.json`, `_package.md`).
  The Claude backend does not return thinking text, so `_raw_output_thinking.txt` holds only a token count.
- `run.log`: the pipeline's stdout/stderr for the whole run.
- `analysis/`: the blind target written before any constructive output was read, and the running notes.
- `sync.sh`: re-mirrors `stories/kernel38_fable/` into `run/`; run it after any later re-run.
