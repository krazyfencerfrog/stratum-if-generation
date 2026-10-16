# Repository Guidelines & Architecture: Stratum IF Generation

This document establishes development guidelines, pipeline architecture, operational constraints, and engineering principles for working within this repository.

---

## 1. System Overview & Entry Points

Stratum IF is an end-to-end interactive fiction system consisting of two decoupled components:
1. **The Engine (`engine/`)**: A deterministic, zero-LLM runtime for room-based interactive fiction. Uses a collapsible radial drill-down menu (`Verb → Object → Detail`) and persistent world state.
2. **The Generator (`generator/`)**: An automated narrative compiler that expands a 2–3 sentence premise kernel into a multi-branching, second-person playable story package. Generation is optimized for local 27B-class thinking models via Ollama.

### Primary Entry Points
All execution can be run directly from the repository root:

```bash
# Play a story package via TUI (default) or line-oriented CLI
python -m engine examples/kernel35_the_mooring_line.json
python -m engine --cli examples/kernel35_the_mooring_line.json
python -m engine --check examples/kernel35_the_mooring_line.json   # Static validation
python -m engine --playtest examples/kernel35_the_mooring_line.json # Reachability solver

# Run full story generation (front-to-back through Stage 8 prose revision)
python -m generator --story-id=my_story tests/kernels/kernel1.txt

# Run generation without prose pass (stops after Stage D compilation)
python -m generator --story-id=my_story --no-prose tests/kernels/kernel1.txt

# Model-free test generation using canned stub fixtures
STRATUM_CLIENT=stub python -m generator --story-id=stubtest tests/kernels/kernel1.txt
```

---

## 2. Operational Constraints & Inference Discipline

### GPU & Inference Discipline
* **Target Environment**: Production inference targets local 27B-class models running on Ollama over ROCm or CUDA.
* **Strict Single-Job Concurrency**: Never launch concurrent generation jobs or saturate VRAM while an existing model call or batch run is active.
* **Pre-Flight Hardware Check**: Prior to dispatching live inference, always verify:
  1. GPU utilization and VRAM are idle (`rocm-smi` or `nvidia-smi`).
  2. Currently loaded model and context memory via `ollama ps`.
  3. No background `batch.py run` is active and the GPU lockfile is free.
* **No Speculative Execution**: Do not run live model inference or start batch runs unless explicitly directed. Report memory aborts or process crashes plainly; never restart a killed job automatically.
* **Model-Free Testing**: Use `STRATUM_CLIENT=stub` or stub test fixtures (`python tests/test_plumbing.py`, `python tests/test_engine.py`) for all plumbing, schema, and logic verification.

### Git & Sandbox Protocols
* **Explicit Commits**: Use explicit `git add <file>`; never stage blanket sweeps.
* **Author Identity**: Commit as Krazy via environment variables (`GIT_AUTHOR_NAME="Krazy"`, `GIT_AUTHOR_EMAIL="krazyfencerfrog@gmail.com"`).
* **Forbidden Commits**: Never commit `dynamic_config.py`, `.claude/` files, or local credential artifacts.
* **No Automatic Remote Push**: Do not run `git push` to origin automatically. Remote pushes are explicitly executed or instructed by the user.
* **Sandbox Network Constraints**: In sandboxed agent environments, network access is blocked by default. Commands requiring external network access (`git push`, `gh issue ...`) require approval to run unsandboxed.

---

## 3. Pipeline Architecture & Artifacts

The story generation pipeline processes a premise kernel into a second-person IF package:

1. **Step 2 (Filter & Shape)**: Content/shape split (`s2_kernel.txt`, `s2_shape.json`).
2. **Phase 3 (Analysis & Brief)**: Blind analytical extractions (`s3_0a`–`s3_0c`, `s3b`–`s3g`), cross-check (`s3h`), followed by deterministic constraint mapping and brief generation (`s3_brief.json`).
3. **Step 3.4 (Genre Promises)**: Unstated audience expectations and defaults (`s3_4_promises.json`).
4. **Step 3.5 (Dramatic Engine)**:
   * `s3_5a_engine`: Protagonist, arena, pressure, opposition, events, hidden truth, rules, price.
   * `s3_5b_turns`: 3–5 dramatic turns and ways through.
   * `s3_5c_cast`: Cast sketches, breaking points, and ties.
   * `s3_5k_kernel_check`: Independent clause-by-clause Kernel contradiction audit (the sole halting audit condition).
   * `s3_5v_premise_check`: Constraint verification and structural audit.
   * `s3_5r_premise_repair`: Targeted repairs (returns only modified sections).
5. **Step 3.8 (Story Form)**: Framework scoring and selection from `config/frameworks.json`.
6. **Step 4 (Outline Loop)**: Main line generation (`s4a`), branch planning (`s4p`), divergent paths (`s4c`), and node definitions (`s4b`).
7. **Step 4e (Evaluation)**: Computed graph metrics and checked quote analysis (`s4e_outline_judge.json`).
8. **Stage A (Arcs)**: Arc state mapping, demonstration/revelation opportunities (`generator/arcs.py`).
9. **Stage B (World Building)**: Characters, topics, rooms, fixtures, map topology with threshold transitions, and player definition (`generator/world.py`).
10. **Stages C & D (Compilation & Playtesting)**: Scene assembly (`generator/compile_scenes.py`), static validation, and automated walk/stuck state testing. Emits `<id>_package_draft.json` as a resume checkpoint.
11. **Stage 8 (Prose Revision)**: Voice and stylesheet generation (`s8a`/`s8v`) followed by targeted component rewriting (`s8b`) via `generator/prose.py`. Emits `<id>_package.json` as the final playable story deliverable.

---

## 4. Engineering Principles

* **Global Fixes Only**: Solve systemic issues in pipeline prompts, schemas, or validators. Reject kernel-specific workarounds.
* **Separation of Generation and Verification**: Generators and validators must never share a single prompt or call context.
* **Deterministic Computation Over LLM Intuition**: Counts, lookups, structural graph invariants, and quote verification are enforced in Python, not trusted to model self-reflection.
* **Substantive Stakes Over Paperwork**: Prevent LLMs from defaulting to bureaucratic stakes (permits, contracts, debts); enforce physical, relational, and material consequences.
* **Calibration Example Leakage Protection**: Local models aggressively mirror nouns, props, and structural devices from prompt calibration examples. Keep calibration examples strictly domain-separated from test kernels in judgment shape, not just nouns. Never introduce bureaucratic devices into examples unless the prompt specifically demands them.
* **Transitional Movement vs. Boilerplate Filler**: For movement between rooms, avoid generic engine filler (`"You make your way to..."`). Unobstructed internal connections remain `null` (the engine reports room arrival via header and description). Physical thresholds (stairs, hatches, gangplanks, ladders, weather borders) use concise (10–25 words), self-contained crossing prose (`text` / `back_text`) with no destination spoilers.
* **Control Fixtures vs. Portable Inventory**: Vehicle controls and fixed machinery (tillers, wheels, levers, capstans, valves) must use manipulation verbs (`grip`, `turn`, `steer`, `heave`), never `take` (which is reserved exclusively for pocketable inventory).
* **Validation & SoftReject Discipline**: Enforce quality and style rules with deterministic Python validators (regex, word lists, length bounds). Use `SoftReject` for non-fatal craft issues to trigger a single retry with the specific complaint; reserve hard rejections (`PipelineHalt` / `ValueError`) strictly for unrecoverable structural or schema faults.
* **Repair Discipline**: Repair prompts receive specific verified violations and return only the sections requiring modification.

---

## 5. Verification & Testing Playbook

### Automated Test Suites (Model-Free)
Run both test suites from the repository root:
```bash
# Verify prompt coverage, schemas, stub fixtures, and outline invariants (~40s)
python tests/test_plumbing.py

# Verify engine runtime, menus, expressions, exit transitions, and playtest solver (~145s)
python tests/test_engine.py
```

### Sibling Import Discipline
* Test suites run directly from the repo root.
* All generator modules rely on sibling module imports; when executing individual scripts directly (`compile_scenes.py`, `world.py`, `steptest.py`), execute them with working directory in `generator/` (or with `PYTHONPATH=generator`). The root `python -m generator` entry point handles this setup automatically.

### Empirical Single-Step Model Testing (Avoiding Full Runs)
When verifying prompt, schema, or validator changes against the live local model:
1. **Never rerun the full pipeline from scratch** for an isolated prompt adjustment.
2. **Use saved story runs**: Copy a completed story run to a temporary scratch directory:
   ```bash
   cp -r stories/kernel35 stories/k35_check
   ```
3. **Execute only the targeted step**:
   * For Stage B world/room generation: `cd generator && python world.py k35_check`
   * For premise audit regression: `cd generator && python steptest.py` (evaluates against stored fixtures in `tests/steps/premise_audit/`).
4. **Inspect and clean up**: Verify the raw response and parsed JSON, then delete the scratch directory (`rm -rf stories/k35_check`).
