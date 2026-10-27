# Stratum IF

[![CI](https://github.com/krazyfencerfrog/stratum-if-generation/actions/workflows/ci.yml/badge.svg)](https://github.com/krazyfencerfrog/stratum-if-generation/actions/workflows/ci.yml)

An end-to-end system for room-based, second-person interactive fiction.

Stratum brings together two distinct systems:
1. **The Engine** (`engine/`): A lightweight, deterministic runtime for room-based interactive fiction. It delivers the world depth of parser classics (Inform 7, TADS) without "guess-the-verb" friction, using a collapsible drill-down menu (`Verb → Object → Detail`). The engine is a pure data interpreter: it requires **no language model at playtime**.
2. **The Generator** (`generator/`): An automated narrative compiler that takes an unformatted 2–3 sentence story premise (a **kernel**) and expands it—with no human in the loop—into a fully realized, multi-branching, playable story package. Generation runs entirely on **local 27B-class thinking models** via Ollama.

---

## Quickstart: Play Immediately

You can play a story package right now in your terminal without configuring a language model or touching a GPU.

```bash
# Clone and set up virtual environment
python -m venv .env
source .env/bin/activate
pip install -e .

# Play via the paned curses TUI (default, requires 80x24 terminal):
python -m engine examples/kernel35_the_mooring_line.json

# Or play via the plain terminal player:
python -m engine --cli examples/kernel35_the_mooring_line.json
```

### Controls & Navigation
- **Drill-down menu**: Select numbers to navigate actions (`Verb → Object → Detail`, e.g., `1. Talk → 2. Lazlo → 1. About the missing ledger`).
- **Journal (`j`)**: View known facts, character states, and discovered threads.
- **Unwind (`u`)**: Rewind state turn-by-turn if you want to explore an alternate path.
- **History (`h`)**: Review prior narration.

---

## 1. The Stratum Engine

The engine interprets compiled story packages (`stratum-story/1` JSON). It models a persistent world of locations, fixtures, carried items, and characters with evolving topics.

### Parser Depth Without Parser Frustration
Traditional parser IF hides actions behind natural language input, forcing players to hunt for verbs. Choice-based IF (CYOA) often collapses spatial grounding into arbitrary menus. 

Stratum uses a **radial drill-down menu**:
- Every displayed action is syntactically and semantically valid.
- Verbs with nothing to act on do not appear.
- Menus collapse dynamically: single-target verbs skip straight to their action.

### Earned Disclosure
Because menu options are visible, puzzles cannot rely on the player failing to think of an action. Instead, **disclosure is governed by world and character state**:
- Clues, topics, and interactions only enter the menu once the player has observed prerequisite details or earned character trust.
- Solutions are kept off the screen until the player possesses the context that makes them sensible.

### Engine Architecture
- **State & Expressions** (`engine/state.py`, `engine/expressions.py`): Safe boolean logic and pattern matching against world flags and character arc states.
- **Scenes & Moments** (`engine/story.py`): Stories transition across scenes (continuous time and place) with automated nudges, background world events, and distinct exits.
- **Exhaustive Playtesting** (`engine/playtest.py`): An automated solver walks every reachable state in a package, detecting dead ends, unreachable moments, and stuck states before a player ever sees them.

---

## 2. The Stratum Generation Pipeline

The generator compiles a short premise into an engine-ready story package through an automated, multi-phase pipeline:

```
Story Kernel (2-3 sentences)
   │
   ▼
[ Step 2 ] Rating Filter & Shape Analysis
   │
   ▼
[ Phase 3 ] 9 Blind Analytical Extractions & Cross-Check (s3h)
   │        ↳ Computed Constraint Map & Story Brief
   ▼
[ Step 3.4 ] Genre Promises (Unstated Audience Expectations)
   │
   ▼
[ Step 3.5 ] Dramatic Engine (Protagonist, Pressure, Opposition, Independent Events)
   │        ↳ Audited by 3.5k (Kernel Check) & 3.5v (Premise Verifier)
   │        ↳ Repaired by 3.5r (Section-Targeted Repairs)
   ▼
[ Step 3.8 ] Framework Selection (Beat Archetypes scored from library)
   │
   ▼
[ Step 4 ] Outline Loop (Main Line → Divergence Plan → Divergent Line Builds)
   │        ↳ Evaluated by 4e (Computed Metrics + Quoted Fact Auditor)
   ▼
[ Stage A ] Character Arc States & Opportunity Mapping (generator/arcs.py)
   │
   ▼
[ Stage B ] World Synthesis: Rooms, Fixtures, Topics, Map Topology (generator/world.py)
   │
   ▼
[ Stages C & D ] Scene Compilation, Engine Package Assembly & Playtesting
   │        ↳ Emits <id>_package_draft.json (resume checkpoint)
   ▼
[ Stage 8 ] Prose Revision: Voice Harmonization & Engine Tokenization (generator/prose.py)
   │
   ▼
Playable Story Package (<id>_package.json)
```

### Key Stages
- **Analytical Briefing (Phase 3)**: Nine isolated, parallel extractions analyze tone, protagonist constraints, opposition mechanics, and world rules before any plot is drafted.
- **The Dramatic Engine (Step 3.5)**: Constructs substantive stakes. An adversarial audit (`3.5k` / `3.5v`) verifies that the engine does not contradict the kernel and enforces real loss conditions.
- **Branch Planning & Divergence (Step 4)**: The generator plans its branch tree holistically (`s4p`), guaranteeing that each divergent through-line terminates in a distinctly different world state.
- **World & Scene Realization (Stages A–D)**: Outlined beats are translated into physical rooms, item placement, character conversational graphs, and scene trigger conditions.
- **Prose Styling (Stage 8)**: Generates a bespoke voice stylesheet per story and rewrites every room, interaction, and description to match.

---

## 3. Engineering Principles

1. **Local Inference by Design**: All generation targets local 27B-class models (`qwen3.8-27b` / `orcarouter-27b`) running on consumer GPUs via Ollama. No component requires frontier cloud APIs.
2. **Separation of Generation and Verification**: Generators never evaluate their own work. Audits and validators execute in independent prompt contexts with isolated system instructions.
3. **Deterministic Rules Over LLM Intuition**: State checks, token limits, quote verifications, graph connectivity, and structural invariants are checked in deterministic Python code, not delegated to model self-reflection.
4. **Substantive Physical Stakes**: Prompts and validators explicitly suppress bureaucratic stakes (permits, debt contracts, licensing fees) in favor of bodily, relational, and material consequence.
5. **Targeted Repair Discipline**: When audits find violations, repair prompts receive only the verified findings and return strictly the modified sections.

---

## 4. Setup & Generator Configuration

### Prerequisites
- Python 3.11+ (Standard Library only — **no third-party Python dependencies** required to run or play)
- [Ollama](https://ollama.com/) running locally (typically with ROCm or CUDA acceleration).

### Local Model Configuration
Create `generator/dynamic_config.py` (gitignored):

```python
from ollama_client import OllamaClient

def get_client():
    return OllamaClient(
        host="http://localhost:11434",
        model="qwen3.8_27b_unc_q5-128k",
        keep_alive="30m",
        idle_timeout=180,
        max_duration=14400,
        echo=True,
        options={"num_ctx": 32768},
        structured="no_think"
    )
```

- `num_ctx: 32768`: Accommodates the pipeline's largest analytical prompts (~13k input, ~14k max output).
- `structured: "no_think"`: Enforces JSON schema on non-reasoning calls while leaving reasoning traces unconstrained during deep drafting passes.

---

## 5. Development & Testing

### Running Tests (No GPU Required)
You can verify the entire codebase without invoking an LLM:

```bash
# Verify the engine runtime, menu collapse, expressions, and playtest solver (~25s)
python tests/test_engine.py

# Verify the generation pipeline using canned schema-valid stub fixtures (~20s)
python tests/test_plumbing.py
```

Both run one test at a time by default. `-j N` spreads the tests over N worker processes and `-j 0` over one
per CPU.

### Running the Pipeline
Run the pipeline directly from the repository root:

```bash
# Run a full story generation run from a kernel (front-to-back through prose)
python -m generator --story-id=my_story tests/kernels/kernel1.txt

# Run through Stage D compilation without prose revision (emits <id>_package_draft.json)
python -m generator --story-id=my_story --no-prose tests/kernels/kernel1.txt

# Run through Stage A (Arc synthesis)
python -m generator --story-id=my_story --stage-a tests/kernels/kernel1.txt

# Stop after the outline loop (Step 3.8 / 4)
python -m generator --story-id=my_story --stop-after 3.8 tests/kernels/kernel1.txt

# Run against a model-free stub client for rapid pipeline testing
STRATUM_CLIENT=stub python -m generator --story-id=stubtest tests/kernels/kernel1.txt

# Run on a Claude subscription via the Claude Code CLI (`claude -p`, logged in)
STRATUM_CLIENT=claude STRATUM_CLAUDE_MODEL=opus python -m generator --story-id=my_story tests/kernels/kernel1.txt
```

The Claude backend (`generator/claude_client.py`) runs each call as a stateless, tool-less `claude -p`
completion with schema-constrained output. Non-thinking steps run at `--effort low`, thinking steps at
`STRATUM_CLAUDE_EFFORT` (default `high`). When the subscription usage limit is hit it sleeps and retries
(`STRATUM_CLAUDE_LIMIT_WAIT`, default 900s, up to `STRATUM_CLAUDE_LIMIT_MAX`, default 6h). Each call logs how much
of the subscription's 5-hour and weekly usage is used and when each resets (`| claude usage: 5h 34% (resets 15:00),
week 12% (resets Mon 10:00)` on its `[timing]` line), saves it as the call's `usage_limits` in `<id>_run_stats.json`,
and the run ends with the last reading.

With a remote client (such as `STRATUM_CLIENT=claude` or `agy`), `--parallel N` runs independent calls N
at a time: phase 3's blind extractions (seven at once, then 3f and 3g), each 3.5 round's audits (3.5v, the
Kernel check and the rule-terms check), stage B's characters (with the functional people's call) and
conversations, and stage D's scenes. The outline loop, stage A's line expansions, places and the prose pass stay
sequential, because each of those calls is shown what the earlier ones already wrote. The output is the same
as a serial run. The default is 1; leave it there on a local Ollama GPU.

Every run logs where its time went. Each model call prints a `[timing]` line (time waiting on the model, then
the Python that checked the answer), each stage prints one as it ends (its wall time split into model time and
Python time, overlapping calls counted once), and the run ends with a table of every stage. The same numbers are
saved in `<id>_run_stats.json`: each call's `started`, `seconds` and `check_seconds` (plus the client's own
breakdown where it has one: Ollama's `load_seconds`, `prompt_eval_seconds` and `eval_seconds`, Claude's
`api_seconds` and `limit_wait_seconds`), and each run under `sessions` with its stages. `report.py` prints them.

To follow a run as it goes, start the dashboard in another terminal and open http://127.0.0.1:8765:

```bash
python generator/dashboard.py              # --port N, --stories DIR
```

It lists the stories, newest first, and for one story shows its latest run: how far it has got through the stages
it planned, the calls in flight, each stage's model and Python time, and every call so far. Next to each wall time it
shows how long the same work would have taken one thing at a time (every call's wait and checking added up, plus the
time the engine playtest's worker processes spent beyond their wall time), so you can see what `--parallel` and
`STRATUM_PLAYTEST_JOBS` saved. Each call in flight shows
its stage and place in a parallel batch, the model and effort, how long it has run against its class's target and
cut-off, why it is a retry, and links to the tail of its log and the prompt it was sent. On Claude the call also
streams: its phase (requesting, thinking, writing), the thinking tokens so far (`-p` withholds the thinking itself),
the time to its first answer token and the answer's size, with the answer itself written to the log as it arrives;
a call sleeping out a usage limit shows when it will try again. Above that, for Claude runs, it shows the 5-hour and weekly usage as the newest call left them. It reads
`<id>_run_stats.json`, which the run saves as each stage and call starts, so it can be opened
before, during or after a run. A run that was killed shows as stopped.

You can also run internal developer tools from `generator/`:

```bash
cd generator

# Probe local Ollama server capabilities (context speed, structured output, breakers)
python probe_ollama.py

# Inspect call timings, token counts, circuit breaker interventions, and each run's model/Python time by stage
python report.py my_story --baseline ../docs/baseline_kernel1_run_stats.json
```

### Batch Runs & GPU Safety
The queue manager (`generator/batch.py`) coordinates multi-story runs under a machine-wide lock file (`.stratum_gpu.lock`) to prevent concurrent VRAM saturation:

```bash
cd generator
python batch.py add kernel38,kernel39
python batch.py run
python batch.py status
```

---

## 6. Repository Layout & Further Reading

- [`examples/`](examples/): Curated, standalone playable story packages ready to run in the engine.
- [`engine/`](engine/): The interactive fiction runtime, CLI player, curses TUI, and automated playtest verifier.
- [`generator/`](generator/): The multi-stage narrative generation pipeline, Ollama client, and validators.
- [`prompts/`](prompts/): System prompts and few-shot calibration fixtures for all generation stages.
- [`tests/kernels/`](tests/kernels/): Curated test kernels across multiple genres and structural challenges.
- [`docs/engine_design.md`](docs/engine_design.md): Deep-dive into engine mechanics, disclosure design, and UI layout.
- [`docs/outline_design.md`](docs/outline_design.md): Design document for the outline generation loop and story graph invariants.
