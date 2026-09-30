# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A story/content generator for the `stratum-if` interactive-fiction engine, which is room-based (rooms, fixtures, characters with topics; not a choose-your-own-adventure). A user supplies a short free-text story premise (a **kernel**), and a multi-step LLM pipeline progressively analyzes and expands it into a second-person story made of **nodes** (sections of play in a subset of rooms, with exits reached through what the player did) along several **through-lines** (each a different motivation or strategy for the protagonist, with its own ending). The pipeline is: step 2 (rating filter + shape split), phase 3 (nine blind extractions + 3h cross-check + a computed constraint map and story brief), 3.5 premise (the dramatic engine), 3.75 craft spine, 3.6 cast, 3.7 world, and step 4, an iterative story-line build-out (main line, then one divergent line per iteration, each node built and reviewed) that produces `stories/<id>/<id>_s4_story.json`. Everything after that (prose per node) is unbuilt.

`docs/step4_design.md` is the live design document for step 2's shape split and everything from 3.5 onward. `docs/fable_response_3.md` explains why the pipeline has this shape. `docs/strategy.txt` is the original numbered plan; its header says which parts are historical. The project has no test framework or linter; the prompts are the main thing being iterated on.

## Setup and running

```
python -m venv .env
pip install -e .
```

The LLM backend is a local Ollama server (default `http://localhost:11434`, override with `OLLAMA_HOST`). `generator/ollama_client.py` streams from `/api/generate`; it collects the model's reasoning from the server's separate `thinking` field (Ollama ≥ 0.9) or from `<think>` tags in the response (older servers) and returns `(thinking, response)`. It accepts `options={"num_ctx": N}` (the later prompts need 16k+ tokens of context or the server truncates silently) and `think=False` per call.

**`dynamic_config` is required but not in the repo.** `main.py` does `import dynamic_config` and calls `dynamic_config.get_client()`, which must return an `LlmClient` subclass. Create `generator/dynamic_config.py` locally (see README for a template); don't commit it. `generator/stub_client.py` is a model-free client that answers every prompt with schema-valid canned JSON; select it with `STRATUM_CLIENT=stub` (if your `dynamic_config` honors it) to test plumbing in seconds.

All scripts use sibling-module imports, so **run from inside `generator/`**:

```
cd generator
python main.py --story-id=kernel1 < ../tests/kernels/kernel1.txt      # one kernel, whole pipeline
python main.py --story-id=foo --rating=PG-13 --stop-after=3.5 < k.txt  # rating filter; stop after 3.5 (2 | 3 | 3.5 | 3.75 | 3.7)
python main.py --story-id=kernel1 --max-iterations=2 < ...            # cap step-4 story lines (default 4)
./todo.sh                                                             # all 30 test kernels
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt
```

Other flags: `--max-repairs` (repair rounds per verify loop, default 2), `--repair-on-soft` (also repair 3.5v soft_issues), `--max-repair-nodes` (nodes rebuilt per review, default 4), `--no-think-steps` (comma-separated call prefixes to run with the model's thinking disabled; off by default). Output goes to `stories/<story_id>/`. `stories/` is not gitignored; `*.log` is.

## Pipeline architecture

`generator/main.py` — `StoryGenerator`. `run_prompt(prefix, name, replacements, prompt_file=None, validator=None)` is the one model call: it loads `prompts/<prompt_file or prefix_name>.prompt`, substitutes `$$PLACEHOLDER$$`s by plain string replace (a leftover placeholder raises), calls the client, saves `<prefix>_raw_output_thinking.txt`, `<prefix>_raw_output_response.txt` and the parsed `<prefix>_<name>.json`, and returns the parsed value. A `validator` can reject a wrong shape; the call is retried once. A saved file that fails the validator is reported as stale and named. JSON goes through `lenient_json_loads`.

Order: `s1 → s2 (rating filter, then shape split) → run_phase3()` (`s3_0a, s3_0b, s3_0c, s3b, s3c, s3d, s3e, s3f(←3d), s3g(←3-0a,3-0c), s3h(←bundle)`, then `build_constraint_map()` and `build_story_brief()`), then `run_premise_expansion()`, `run_craft_spine()`, `run_cast()`, `run_world()`, `run_step4()`.

**The content kernel.** Step 2 splits the kernel into `s2_kernel.txt` (content, verbatim minus shape clauses) and `s2_shape.json` (ending-count tier, linearity, choice density, length). Every later step reads the content kernel; the shape reaches only step 4, as advisory targets computed by `brief.shape_targets`.

**The brief.** `generator/brief.py` computes `s3_brief.json` (each phase-3 field's value and binding class) from the bundle, the map and 3h. Every prompt after 3h receives the brief, never the raw bundle; `brief_lite()` is the further cut the per-node prompts get. Keep it that way: trace length scales with input size.

**Blind execution** is the default for phase 3; three steps are chained only because their field is undefined without the other's output. Never chain for agreement — that is 3h's job.

**Build / verify / repair** (`run_verified_step`): 3.5 and 3.75 each run build → verify → (repair → re-verify) up to `--max-repairs` while the verdict needs repair (3.5v `hard_issues`; 3.75v `flagged`). Files: original build `s3_5_premise_expansion.json`, verdict `s3_5v_fidelity_check.json`, repairs `s3_5r<n>_premise_repair.json` (`{"repair_log", "revised"}`), re-verdicts `s3_5v_r<n>_fidelity_check.json`, the accepted version `s3_5_premise_expansion_accepted.json`, and `s3_5_loop.json`. A hard finding that survives the rounds raises `PipelineHalt` (exit 2).

**3.5 is the dramatic engine**: protagonist (with `cannot_do`), pressure, opposition, mediation (what each pole of the question takes and costs, and the levers), turns (3–5, each a different form), cast seeds (every crowd has a representative). All mandatory at every budget; the budget governs texture only. 3.5v's `engine_findings` audit fails hard on a missing engine.

**3.6 cast / 3.7 world** run once, before any story line: named characters (`s3_6_cast.json`, validator rejects a crowd without a representative) and the room map (`s3_7_world.json`, validator normalizes connections). Nodes choose subsets of these.

**Step 4** (`generator/step4.py`, `Step4Builder`): iteration 1 runs `s4a_main_line`; iteration n runs `s4c_divergence` (a different motivation/strategy, where it takes hold: `existing_exit` | `new_opportunity` | `state_variant`, the new nodes, its ending or `rejoins_at`); every iteration rebuilds changed nodes, builds new nodes with `s4b_node_build`, runs `mechanical_checks()` (computed: exit reachability, reads before writes, outline/build mismatches, menu interactions), then `s4d_review`, node repair for every finding's `node_ids`, and one re-review. Prefixes: `s4a_i1`, `s4c_i<n>`, `s4b_i<n>_<node>[_r<k>]`, `s4d_i<n>[_r1]`. State is rebuilt by replaying the driver over saved files, so a rerun makes no model calls. `s4_story.json` / `s4_story.md` are rewritten each iteration.

**Re-running a step**: delete its saved output file(s). For a verify/repair loop, delete every file of its build/verify/repair prefixes. Downstream outputs are not invalidated automatically — delete them too when an input changed. Story directories from before 2026-09-29 do not load (schemas changed); delete them.

## Prompts

`prompts/s*.prompt` are the real product. Each demands JSON-only output with a fixed key shape. Extraction prompts carry `evidence_basis` from the five-tier set `explicit → strong_inference → genre_association → mixed → no_signal`; construction prompts (3.5, 3.75) carry `provenance` + `serves` instead. Every prompt that takes an optional upstream JSON tolerates the literal string `none`. Every prompt ends with a short REASONING DISCIPLINE block; the judgment rules above it are the thing not to weaken.

**Read `docs/step3_consolidated_design_lessons.md` before drafting or editing any prompt** (§6a/§6b/§6c carry the pipeline-level patterns), and `docs/step4_design.md` §6.4 for the JSON shapes `step4.py` depends on — changing a step-4 prompt's schema means changing the driver and the stub.

Rules that apply pipeline-wide: **generation and verification never share a prompt**; **repair is a third call that receives the violation list**; **a prompt receives the brief or a packet, never the bundle**; **the question is not the verb** (a story decision is reached through play, never offered as a menu).

Iteration workflow: draft prompt → run against real kernels → read the full thinking trace, not just the JSON → make the narrowest fix → re-test only the affected kernels. `docs/step4_design.md` §9 lists what has never been run against a live model.

## Other files

- `tests/kernels/kernel1..30.txt` — the test kernel batch (input fixtures, not automated tests); 28–30 are adversarial kernels for 3.5 and the 3d retrofit; 17 is the linear-shape case.
- `stories/current_output.tar` — the archived kernel1 run (through two step-4 iterations, with full thinking traces) from before the 2026-09-29 redesign. Use it as the baseline when measuring trace length; its per-call timings are tabulated in `docs/fable_response_3.md`.
- `config/current_axes.json` — the taxonomy of story axes; vocabulary for later phases.
- `src/common/features.py` — an abandoned, syntactically incomplete sketch. Don't import it.
- `docs/fable_strategy_review.md`, `docs/fable_request_2.txt`, `docs/fable_request_3.txt` — the external review and the two requests the last two passes implemented.
