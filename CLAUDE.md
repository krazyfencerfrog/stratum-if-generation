# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A story/content generator for the `stratum-if` interactive-fiction engine, which is room-based (rooms, fixtures, characters with topics; not a choose-your-own-adventure). A user supplies a short free-text story premise (a **kernel**), and a multi-step LLM pipeline analyzes it and expands it, with no further user involvement, into a second-person story.

What is built today ends at an **outline**: a story graph of **nodes** (one framework beat filled on one line: a short summary, where, who), **lines** (through-lines: a motivation, a strategy, an ending, a path of nodes), plain-language **branch triggers**, and rough **character and location registers**. The pipeline is: step 2 (rating filter + shape split), phase 3 (nine blind extractions + 3h cross-check + a computed constraint map and story brief), 3.5 premise (the dramatic engine, built in three calls, audited, repaired), 3.8 story form (a framework chosen from a computed shortlist), and step 4, the outline loop (main line, then one divergent line per iteration), which produces `stories/<id>/<id>_story.json` and `.md`. Everything after that (beat expansion, character and setting buildout, reconciliation, the per-node room build, prose) is unbuilt; `docs/later_stages.md` is the design sketch and `prompts/later/` + `generator/later/` hold the parked material.

`docs/outline_design.md` is the live design document. `docs/fable_response_4.md` explains why the pipeline has this shape and holds the first-live-run checklist. `docs/kernel1_target_outline.md` is a hand-written example of a right-sized outline (never paste it into a prompt). `docs/step4_design.md` and `docs/strategy.txt` are historical. The project has no test framework or linter; the prompts are the main thing being iterated on.

**Hard constraint: production inference is a local 27B-class thinking model via Ollama.** Nothing in the runtime path may assume a frontier model. The real limits are wall-clock time per call and trace size per call, and trace size is a function of what a call is given and asked to return, not of instructions about how to reason.

## Setup and running

```
python -m venv .env
pip install -e .
```

The LLM backend is a local Ollama server. `main.py` calls `dynamic_config.get_client()`, which must return an `LlmClient` subclass; create `generator/dynamic_config.py` locally (see README for a template); it is gitignored. `STRATUM_CLIENT=stub` selects `generator/stub_client.py` (a model-free client that answers every prompt with schema-valid canned JSON) and needs no `dynamic_config.py`.

All scripts use sibling-module imports, so **run from inside `generator/`** (the test script can be run from anywhere):

```
python tests/test_plumbing.py                                           # stub-driven plumbing tests, ~8 s; run before any model time
cd generator
python probe_ollama.py                                                  # what the local server supports (thinking, schemas, breakers, speed)
python main.py --story-id=kernel1 < ../tests/kernels/kernel1.txt      # one kernel, whole pipeline
python main.py --story-id=foo --rating=PG-13 --stop-after=3.5 < k.txt  # rating filter; stop after 2 | 3 | 3.5 | 3.75 | 3.8
python main.py --story-id=kernel1 --max-iterations=2 < ...            # cap the outline's lines (default 4)
python report.py kernel1 --baseline ../docs/baseline_kernel1_run_stats.json   # per-stage time and trace size against the archived run
./todo.sh                                                             # all 30 test kernels
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt
```

Other flags: `--max-repairs` (3.5 repair rounds, default 2), `--framework=<id>` (skip the 3.8 choice), `--no-think-steps` / `--think-steps` (comma-separated prefixes, steps or step_names to run with thinking off / on, overriding the call's class), `--no-breakers`, `--no-force-answer` (skip budget forcing), `--craft-spine` (run the optional 3.75 craft spine). Environment: `STRATUM_SAMPLER=model` (send no sampler options), `STRATUM_PRESENCE_PENALTY`. Output goes to `stories/<story_id>/`. `stories/` is not gitignored; `*.log` is.

## Pipeline architecture

`generator/main.py` — `StoryGenerator`. `run_prompt(prefix, name, replacements, prompt_file=None, validator=None, klass='extract', schema=None)` is the one model call: it loads `prompts/<prompt_file or prefix_name>.prompt`, substitutes `$$PLACEHOLDER$$`s by plain string replace (a leftover placeholder raises), calls the client, saves `<prefix>_raw_input_prompt.txt`, `<prefix>_raw_output_thinking.txt`, `<prefix>_raw_output_response.txt` and the parsed `<prefix>_<name>.json`, appends a record to `<id>_run_stats.json`, and returns the parsed value. A `validator` can reject an answer; the call is retried once **with the complaint and the previous answer appended**. A saved file that fails the validator is reported as stale and named. JSON goes through `lenient_json_loads`.

**Call classes** (`generator/stats.py`): every call is `extract` (phase 3: untouched, no breaker), `classify` (thinking off, a rationale field first in the schema), `judge`, `audit` (3.5v) or `build` (thinking on, with a target and a circuit breaker on thinking bytes and wall clock; a call over its thinking limit first gets its answer forced from the partial thinking; if that fails, or another breaker tripped, it re-runs once with thinking off; reasoning the client sees looping is cut at once and first re-run from a new seed, thinking on). Decide a new call's class before writing its prompt. `generator/schemas.py` holds the JSON schema for each new prompt (Ollama structured outputs); the client sends it on thinking-off calls by default.

Order: `s1 → s2 (rating filter, shape split) → run_phase3()` (`s3_0a, s3_0b, s3_0c, s3b, s3c, s3d, s3e, s3f(←3d), s3g(←3-0a,3-0c), s3h(←bundle)`, then `build_constraint_map()` and `build_story_brief()`), then `run_premise_expansion()`, `run_story_form()`, `run_outline()`.

**The content kernel.** Step 2 splits the kernel into `s2_kernel.txt` (content, verbatim minus shape clauses) and `s2_shape.json` (ending-count tier, linearity, choice density, length). Every later step reads the content kernel; the shape reaches only step 4, as advisory targets computed by `brief.shape_targets`. A stated ending number decides the tier by lookup.

**The brief.** `generator/brief.py` computes `s3_brief.json` (each phase-3 field's value and binding class). Every prompt after 3h receives the brief, never the raw bundle, usually as `brief_lines()` (one line per field) or `brief_lite()`. Keep it that way: trace length scales with input size.

**Blind execution** is the default for phase 3; three steps are chained only because their field is undefined without the other's output. Never chain for agreement — that is 3h's job. Do not weaken phase 3.

**3.5 is the dramatic engine**, built in three calls: `s3_5a_engine` (protagonist with `cannot_do`, arena, pressure, opposition, mediation), `s3_5b_turns` (3–5 turns, each a different form, each with `ways_through` and costs), `s3_5c_cast` (one rough sketch per role the turns name; every crowd has a representative). `premise_computed_findings()` checks what is a count or a lookup (including `example_guard.copied_phrases`, which flags output copied from a prompt's calibration example; the step-4 validators run the same check); `s3_5v_premise_check` answers a fixed list of yes/no questions (Kernel clauses, constraints, engine checks, mechanics); any failure sends the finding list to `s3_5r<n>_premise_repair`, which returns **only the sections it changed**; up to `--max-repairs` rounds, then `PipelineHalt` (exit 2). Files: `s3_5_premise.json` (as built), `s3_5_premise_accepted.json` (what downstream reads), `s3_5_loop.json`.

**3.8 story form.** `config/frameworks.json` is the framework library (beats with jobs); `generator/frameworks.py` scores it against the brief and returns a shortlist of three and the modifiers the brief licenses; `s3_8_story_form` picks. The framework scaffolds beats only: it never drives how many lines or endings are built.

**Step 4** (`generator/outline.py`, `OutlineBuilder`): iteration 1 runs `s4a_main_line` (the through-line and one entry per beat: `beat`, `turn`, `way`, `adapted`); iteration n runs `s4c_divergence` on the previous judge's seed (where it leaves, the plain-language trigger, the new beats, its ending or `rejoins_at`); every iteration then runs `s4b_line_nodes` (title, summary, where, who; registers grow as needed), the computed checks (`generator/checks.py`), and `s4d_next_line` (is another line worth building, and its seed). Structural rules are enforced by each call's validator; `check_story` reports broken invariants (should be none) and notes. Prefixes: `s4a_i1`, `s4c_i<n>`, `s4b_i<n>`, `s4d_i<n>`. State is rebuilt by replaying the driver over saved files, so a rerun makes no model calls.

**Re-running a step**: delete its saved output file(s). For the 3.5 loop, delete every `s3_5*` file. Downstream outputs are not invalidated automatically — delete them too when an input changed. Each story directory carries `<id>_pipeline.json` (schema version 4); a directory from an older schema stops the run and prints what to delete (phase-3 outputs may be kept).

## Prompts

`prompts/s*.prompt` are the real product. Each demands JSON-only output with a fixed key shape. Extraction prompts carry `evidence_basis` from the five-tier set `explicit → strong_inference → genre_association → mixed → no_signal`; construction prompts carry `serves`. Every prompt that takes an optional upstream JSON tolerates the literal string `none`. The phase-3 prompts end with a REASONING DISCIPLINE block; it has no measurable effect on this model and the newer prompts do not carry one.

**Read `docs/step3_consolidated_design_lessons.md` before drafting or editing any prompt** (§6a–§6d carry the pipeline-level patterns), and `docs/outline_design.md` §6 for the JSON shapes `outline.py` depends on — changing a step-4 prompt's schema means changing `schemas.py`, the validator, the stub, and usually `checks.py`.

Rules that apply pipeline-wide: **generation and verification never share a prompt**; **repair is a separate call that receives the violation list and returns only what it changed**; **a prompt receives the brief or a packet, never the bundle**; **the question is not the verb** (a story decision is reached through play, never offered as a menu); **counts, lookups and structural checks are computed**; **calibration examples are domain-separated from the test kernels in judgment shape, not just nouns, and obey their own prompt's rules** (kernel1 is never an example).

Iteration workflow: run `tests/test_plumbing.py` → draft or edit the prompt → run against real kernels → read the full thinking trace and `report.py`, not just the JSON → make the narrowest fix → re-test only the affected kernels. `docs/fable_response_4.md` §9 lists what has never been run against a live model.

## Other files

- `tests/test_plumbing.py` — stub-driven tests: every stub scenario, the graph invariants, the Ollama client against a fake server. Keep `generator/stub_client.py` in sync with any schema change; the test fails if a prompt in `prompts/` is exercised by no scenario.
- `tests/kernels/kernel1..30.txt` — the test kernel batch (input fixtures, not automated tests); 28–30 are adversarial kernels for 3.5 and the 3d retrofit; 17 is the linear-shape case.
- `generator/report.py`, `generator/probe_ollama.py` — run statistics against a baseline; capability probe of the local server.
- `stories/current_output.tar` — the archived kernel1 run on the 2026-09-29 pipeline (the one this outline loop replaced): through 3.5–3.7 and about two step-4 iterations of node builds, 31.7 hours, with full thinking traces. `docs/baseline_kernel1_run_stats.json` is its per-call timing, rebuilt from its log timestamps.
- `prompts/later/`, `generator/later/` — parked later-stage material (craft spine, cast, world, node build, review). Not loaded or imported. See `prompts/later/README.md`.
- `docs/fable_strategy_review.md`, `docs/fable_request_2..4.txt`, `docs/fable_response_3.md` — the external review and the requests and responses of earlier passes.
