# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A story/content generator for the `stratum-if` interactive-fiction engine. A user supplies a short free-text story premise (a **kernel**), and a multi-step LLM pipeline progressively analyzes and expands it into a branching second-person story outline. The pipeline is: step 2 (rating filter), phase 3 (nine blind extractions + 3h cross-check + a computed constraint map), 3.5 premise expansion, 3.75 craft spine, and step 4, an iterative outline build-out (framework, beats, entities, whole-story review) that produces `stories/<id>/<id>_s4_story.json`. Everything after the outline (rooms, transitions, prose) is unbuilt.

`docs/step4_design.md` is the live design document for 3.5 onward. `docs/strategy.txt` is the original numbered plan; its header says which parts are historical. The project has no test framework or linter; the prompts are the main thing being iterated on.

## Setup and running

```
python -m venv .env
pip install -e .
```

The LLM backend is a local Ollama server (default `http://localhost:11434`, override with `OLLAMA_HOST`). `generator/ollama_client.py` streams from `/api/generate`; it collects the model's reasoning from the server's separate `thinking` field (Ollama ≥ 0.9) or from `<think>` tags in the response (older servers) and returns `(thinking, response)`. It accepts `options={"num_ctx": N}`; the later prompts need 16k+ tokens of context or the server truncates silently.

**`dynamic_config` is required but not in the repo.** `main.py` does `import dynamic_config` and calls `dynamic_config.get_client()`, which must return an `LlmClient` subclass. Create `generator/dynamic_config.py` locally (see README for a template); don't commit it. `generator/stub_client.py` is a model-free client that answers every prompt with schema-valid canned JSON; select it with `STRATUM_CLIENT=stub` (if your `dynamic_config` honors it) to test plumbing in seconds.

All scripts use sibling-module imports, so **run from inside `generator/`**:

```
cd generator
python main.py --story-id=kernel1 < ../tests/kernels/kernel1.txt      # one kernel, whole pipeline
python main.py --story-id=foo --rating=PG-13 --stop-after=3.5 < k.txt  # rating filter; stop after 3.5 (3 | 3.5 | 3.75)
python main.py --story-id=kernel1 --max-iterations=3 < ...            # cap step-4 paths (default 6)
./todo.sh                                                             # all 30 test kernels
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt
```

Other flags: `--max-repairs` (repair rounds per verify loop, default 2), `--repair-on-soft` (also repair 3.5v soft_issues), `--max-repair-beats` (beats regenerated per review, default 6). Output goes to `stories/<story_id>/`. `stories/` is not gitignored; `*.log` is.

## Pipeline architecture

`generator/main.py` — `StoryGenerator`. `run_prompt(prefix, name, replacements, prompt_file=None, validator=None)` is the one model call: it loads `prompts/<prompt_file or prefix_name>.prompt`, substitutes `$$PLACEHOLDER$$`s by plain string replace (a leftover placeholder raises), calls the client, saves `<prefix>_raw_output_thinking.txt`, `<prefix>_raw_output_response.txt` and the parsed `<prefix>_<name>.json`, and returns the parsed value. A `validator` can reject a wrong shape; the call is retried once. JSON goes through `lenient_json_loads` (fences, surrounding prose, smart quotes, trailing commas).

Order: `s1 → s2 → run_phase3()` (`s3_0a, s3_0b, s3_0c, s3b, s3c, s3d, s3e, s3f(←3d), s3g(←3-0a,3-0c), s3h(←bundle)`, then `build_constraint_map()`), then `run_premise_expansion()`, `run_craft_spine()`, `run_step4()`.

**Blind execution** is the default for phase 3; three steps are chained only because their field is undefined without the other's output. Never chain for agreement — that is 3h's job. Three things are computed in Python rather than asked: `step3_bundle_json()`, `build_constraint_map()` (saved as `<id>_s3h_constraint_map.json`, recomputed every run), and everything step 4 derives (branch-point table, story digest, state registry).

**Build / verify / repair** (`run_verified_step`): 3.5 and 3.75 each run build → verify → (repair → re-verify) up to `--max-repairs` while the verdict needs repair (3.5v `hard_issues`; 3.75v `flagged`). Files: original build `s3_5_premise_expansion.json`, verdict `s3_5v_fidelity_check.json`, repairs `s3_5r<n>_premise_repair.json` (`{"repair_log", "revised"}`), re-verdicts `s3_5v_r<n>_fidelity_check.json`, the accepted version `s3_5_premise_expansion_accepted.json`, and `s3_5_loop.json`. Downstream reads the accepted version under the build's own key in `self.analysis`. A hard finding that survives the rounds raises `PipelineHalt` (exit 2). 3h's output goes to 3.5, 3.5v, 3.75, 3.75v and 4a; a constraint 3h ruled against is not a constraint downstream.

**Step 4** (`generator/step4.py`, `Step4Builder`): iteration 1 runs `s4a_first_outline` (framework, ending mechanism, main path); iteration n runs `s4a_next_outline` against a computed branch-point table and the last review, optionally `s4c5_craft_refresh` on a transform; each iteration then runs `s4_entity_define` per unmapped role, `s4_beat_generate` per new beat in path order, `s4d_verify` over the digest, beat regeneration for every finding's `beat_ids`, and one re-review. Prefixes: `s4a_i<n>`, `s4c5_i<n>`, `s4e_i<n>_<k>_<role>`, `s4b_i<n>_<beat>[_r<k>]`, `s4d_i<n>[_r1]`. State is rebuilt by replaying the driver over saved files, so a rerun makes no model calls. `s4_story.json` / `s4_story.md` are rewritten each iteration.

**Re-running a step**: delete its saved output file(s). For step 2, delete `_s2_rating.txt`. For a verify/repair loop, delete every file of its build/verify/repair prefixes. Downstream outputs are not invalidated automatically — delete them too when an input changed.

## Prompts

`prompts/s*.prompt` are the real product. Each demands JSON-only output with a fixed key shape. Extraction prompts carry `evidence_basis` from the five-tier set `explicit → strong_inference → genre_association → mixed → no_signal`; construction prompts (3.5, 3.75, step 4) carry `provenance` + `serves` instead. Every prompt that takes an optional upstream JSON tolerates the literal string `none`. Every prompt ends with a short REASONING DISCIPLINE block (reason once, write the JSON once, don't re-narrate inputs); the judgment rules above it are the thing not to weaken.

**Read `docs/step3_consolidated_design_lessons.md` before drafting or editing any prompt** (§6a/§6b carry the pipeline-level patterns; §6 lists what is settled), and `docs/step4_design.md` §3.4 for the JSON shapes `step4.py` depends on — changing a step-4 prompt's schema means changing the driver.

Two rules apply pipeline-wide: **generation and verification never share a prompt**, and **repair is a third call that receives the violation list** (3.5r, 3.75r, and beat regeneration in revision mode).

Iteration workflow: draft prompt → run against real kernels → read the full thinking trace, not just the JSON → make the narrowest fix → re-test only the affected kernels. `docs/step4_design.md` §6 lists what has never been run against a live model.

## Other files

- `tests/kernels/kernel1..30.txt` — the test kernel batch (input fixtures, not automated tests); 28–30 are adversarial kernels for 3.5 and the 3d retrofit.
- `stories/current_output.tar` — the archived batch (kernels 1–8 through 3.75v, with full thinking traces) from before this pass's changes. Use it as the baseline when measuring trace length or diffing outputs.
- `config/current_axes.json` — the taxonomy of story axes; vocabulary for later phases.
- `src/common/features.py` — an abandoned, syntactically incomplete sketch. Don't import it.
- `docs/fable_strategy_review.md`, `docs/fable_request_2.txt` — the external review and the request this pass implemented.
