# Stratum IF

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

# Play via the plain terminal player:
python engine/cli.py engine/examples/kernel35_demo.json

# Or play via the paned curses TUI (requires 80x24 terminal):
python engine/tui.py engine/examples/kernel35_demo.json
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
   │
   ▼
[ Stage 8 ] Prose Revision: Voice Harmonization & Engine Tokenization (generator/prose.py)
   │
   ▼
Playable Story Package (<id>_package_prose.json)
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
- Python 3.11+
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

### Running the Pipeline
Run scripts from inside the `generator/` directory:

```bash
cd generator

# Probe local Ollama server capabilities (context speed, structured output, breakers)
python probe_ollama.py

# Run a full story generation run from a kernel
python main.py --story-id=my_story < ../tests/kernels/kernel1.txt

# Run through Stage A (Arc synthesis)
python main.py --story-id=my_story --stage-a < ../tests/kernels/kernel1.txt

# Inspect call timings, token counts, and circuit breaker interventions
python report.py my_story --baseline ../docs/baseline_kernel1_run_stats.json

# Run against a model-free stub client for rapid pipeline testing
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt
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

- [`engine/`](file:///home/krazy/claude/stratum-if-generation/engine/): The interactive fiction runtime, CLI player, curses TUI, and automated playtest verifier.
- [`generator/`](file:///home/krazy/claude/stratum-if-generation/generator/): The multi-stage narrative generation pipeline, Ollama client, and validators.
- [`prompts/`](file:///home/krazy/claude/stratum-if-generation/prompts/): System prompts and few-shot calibration fixtures for all generation stages.
- [`tests/kernels/`](file:///home/krazy/claude/stratum-if-generation/tests/kernels/): Curated test kernels across multiple genres and structural challenges.
- [`CLAUDE.md`](file:///home/krazy/claude/stratum-if-generation/CLAUDE.md): Detailed architectural and operational manual for code development.
- [`docs/engine_design.md`](file:///home/krazy/claude/stratum-if-generation/docs/engine_design.md): Deep-dive into engine mechanics, disclosure design, and UI layout.
- [`docs/outline_design.md`](file:///home/krazy/claude/stratum-if-generation/docs/outline_design.md): Design document for the outline generation loop and story graph invariants.
