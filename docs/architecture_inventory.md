# Pipeline Architecture Inventory: Division of Logic Between Prompts and Python

**Document Version:** 1.0 (Stratum IF Pipeline v0.2)  
**Date:** 2026-10-12  
**Tracking Issue:** Fixes #14  

---

## 1. Executive Summary & Architectural Invariant

A founding design principle of the Stratum Interactive Fiction pipeline is:

> **Deterministic Computation Over LLM Intuition**: Counts, lookups, structural graph invariants, and quote verification are enforced in Python, not trusted to model reasoning.

As the pipeline expanded from a premise-to-outline generator into a full multi-stage compiler (adding Stages A–D, visual keyframing, dynamic companion movement, drop actions, content ratings, and the Stage 8 prose pass), the division of responsibilities between LLM prompts (`prompts/*.prompt`) and deterministic Python (`generator/*.py`, `engine/*.py`) has grown organically.

This inventory provides:
1. A systematic audit matrix of all pipeline stages from Step 2 through Stage 8.
2. An assessment of boundary violations (where prompts perform pseudo-computation or bloat input context, and where Python attempts brittle semantic interpretation).
3. A prioritized migration plan to guide v0.2+ architectural refactoring.

---

## 2. Stage-by-Stage Architecture Inventory Matrix

| Stage & Step | Primary Model Responsibility (Generative / Semantic) | Python Pre-Processing & Context Injection | Python Post-Processing & Deterministic Validation | Boundary Assessment |
| :--- | :--- | :--- | :--- | :--- |
| **Step 2: Filter & Shape** (`s2_filter`, `s2_shape`) | Extracts story content; suggests structural preferences (branching ambition, linear vs branchy). | Injects raw kernel and target content rating string. | Parses JSON shape; deterministically extracts numbers (`ending_tier_from_stated`); overrides model tier with exact integer counts (`shape_targets`). | **Sound**: Model proposes narrative desires; Python enforces exact through-line and node bounds. |
| **Phase 3: Extraction** (`s3_0a`–`s3_0c`, `s3b`–`s3g`) | Blind analytical extractions across 9 narrative dimensions (question, identity, failure, affect, theme, viewpoint, timeline, setting, complexity). | Injects content kernel; formats step prompts. | Normalizes JSON schemas; verifies evidence tiers; computes texture budget and constraint shares (`build_brief`). | **Exemplary**: Clean separation. Model extracts quotes and inferences; Python deterministically calculates constraints and budgets. |
| **Step 3.4: Genre Promises** (`s3_4_promises`) | Identifies unstated audience expectations, default genre conventions, and open questions. | Injects kernel and brief summary. | Validates schema (`schemas.PROMISES`); validates fields. Injects results into all subsequent premise prompts. | **Sound**: Semantic extraction of genre conventions; minimal deterministic logic required. |
| **Step 3.5: Dramatic Engine** (`s3_5a`, `s3_5b`, `s3_5c`) | Generates protagonist, arena, pressure, opposition, dramatic turns, ways through, and cast sketches. | Injects brief constraints, promises, shared terms (`terms.py`), and name pools (`names.py`). | Validates schema (`schemas.PREMISE_*`); checks substantive stakes (no bureaucratic paper stakes via `paper.py`); enforces balanced dilemma representation across factions/sectors; rejects non-agent entities in cast seeds. | **Sound with Minor Bloat**: Heavy prompt preambles; Python checks enforce substantive stakes and representation invariants. |
| **Step 3.5k: Kernel Check** (`s3_5k_kernel_check`) | Evaluates candidate premise against independent clauses of the Kernel to spot direct contradictions. | Extracts individual kernel clauses (`brief.py`). Prompts model clause by clause. | Verifies quoted excerpts against source text in Python; strictly halts if a true contradiction is confirmed. | **Exemplary**: Only model evaluates semantic contradiction; Python verifies verbatim quotes to prevent hallucinated violations. |
| **Step 3.5v/r: Audit & Repair** (`s3_5v_premise_check`, `s3_5r_premise_repair`) | Identifies structural gaps in turns, cast ties, or opposition; generates targeted JSON section replacements. | Synthesizes verified findings into prompt. | Verifies quoted complaints; replaces *only* returned sections in the premise document; re-runs Python checks. | **Sound**: Targeted section replacement prevents full document re-generation and drift. |
| **Step 3.8: Story Form** (`s3_8_framework`) | Selects best structural dramatic framework from a shortlist. | Scores and filters framework shortlist in Python (`frameworks.py`) based on brief constraints. | Validates framework id against `frameworks.json`. | **Exemplary**: Shortlist and metric evaluation in Python; model only makes the final aesthetic fit selection. |
| **Step 4: Outline Loop** (`s4a`, `s4p`, `s4c`, `s4b`) | Fills beats of framework with story nodes, dramatic choices, branch paths, and ending worlds. | Injects premise, framework beat definitions, and existing graph state. | Reconstructs graph topology (`outline.py`); derives edges, beat grid, hooks, and character usage (`checks.py`); detects verbal tics; enforces graph connectivity invariants. | **Exemplary**: Python owns graph topology, edge resolution, and invariants; model supplies beat narrative. |
| **Step 4e: Outline Judge** (`s4e_outline_judge`) | Scores outline coherence and checks ending emotional weight. | Computes outline graph metrics (branching factor, hook coverage, character distribution) in Python. | Verifies quotes and ratings; produces audit report. | **Sound**: Model acts as qualitative reviewer; Python computes all graph statistics. |
| **Stage A: Arcs & States** (`s5a_arcs`, `s5b_minor_nodes`, `s5c_endings`) | Defines character/thematic arc states, minor choice opportunities, revelation moments, and composed endings. | Injects outline nodes, characters, and theme poles. | Assigns state variable keys; verifies arc directionality; builds state transition graphs; attaches ending variant metadata. | **Sound**: Python manages engine state variables and flags; model writes narrative content. |
| **Stage B: World Building** (`s6a_cast`, `s6b_rooms`, `s6c_topology`, `s6d_props`) | Creates rooms, descriptions, exits, characters, conversation topics, and initial item placements. | Injects minor nodes, scene locations, and character roles. | Enforces room topology reciprocity (A->B implies B->A exit); validates strongly connected components (no dead-end room traps); formats unnamed handles; validates topic slugification. | **High Complexity**: High number of serialized LLM calls; prompt carries substantial formatting instructions. |
| **Stage C/D: Scene Compilation** (`s7d_scene`) | Generates scene openings, interactions, dialogue lines, event reactions, and nudges. | Assembles room subsets, cast placements, minor node opportunities, and outgoing edges per scene. | Injects engine mechanics: sets `done_*` flags; assigns state effects by index; validates required moments and neutral options; validates scene reachability; runs Monte Carlo playtest simulator. | **Solid Python Scaffolding**: Model outputs pure scene interaction choices; Python injects all state mutations and mechanics. |
| **Stage 8: Prose Revision** (`s8a_style`, `s8v_style_check`, `s8b_edit`) | Creates story stylesheet; revises room descriptions, interactions, dialogue, and endings into unified voice. | Masks proper names with engine codes (`{C01}`); splits story into modular textual units (`units()`). | Verifies structural skeleton invariance (`skeleton(before) == skeleton(after)`); measures character dialogue distinctiveness (TTR and pairwise Jaccard); checks somatic drift and formulaic syntax. | **High Verification Rigor**: Strict structural invariance check guarantees no engine IDs or options are lost or mutated during rewriting. |

---

## 3. Boundary Violation Audit & Key Findings

### 3.1 Prompt Logic That Should Migrate to Deterministic Python

1. **Format Enforcement & Text Sanitization in Stage B & 7D**:
   - *Current State*: Prompts spend hundreds of preamble tokens explaining how to format interaction labels (e.g. `Take › the lamp`, maximum length limits, no redundant words).
   - *Problem*: Small 27B models occasionally produce `Take the lamp` or `Examine › lamp`.
   - *Recommendation*: Move label formatting and symbol insertion (`›`) completely into Python post-processing. Let the prompt return raw `verb` and `target`, and let Python assemble and clamp display labels.

2. **Room Connectivity & Reciprocal Exit Scaffolding in Stage B**:
   - *Current State*: `s6c_topology` prompts the model to output full two-way exit arrays for rooms. Python then validates reciprocity and SCC connectivity, rejecting or repairing violations.
   - *Problem*: LLMs struggle with spatial graphs, leading to asymmetric paths or isolated rooms.
   - *Recommendation*: Python should pre-generate the baseline navigation topology (spanning trees / planar room graph) and pass the fixed exit slots to the model, asking only for crossing descriptions (`text` / `back_text`) and physical threshold types.

3. **Character Unnamed Handle Shortening (`unnamed_short`)**:
   - *Current State*: Prompt instructions ask the model to generate both `unnamed` ("the weathered captain in the oilskin coat") and `unnamed_short` ("the captain").
   - *Problem*: Models frequently forget `unnamed_short` or generate inconsistent handles.
   - *Recommendation*: Python's regex cutoff (`SHORT_CUT` in `engine/story.py`) already computes the short noun phrase deterministically. Eliminate `unnamed_short` from prompt requests entirely; generate it deterministically in Python unless explicitly provided.

### 3.2 Python Logic That is Overly Brittle or Performing Semantic Guessing

1. **Regex-Based Topic Match Suppressions in Runtime**:
   - *Current State*: Engine suppresses topics if the menu label matches display text or previous options via string equality.
   - *Status*: Recently refactored to use semantic normalized keys. Working cleanly.

2. **Somatic Drift and Epilogue Formulaic Pattern Checkers**:
   - *Current State*: `checks.py` uses regex lists (`SOMATIC_DRIFT_PATTERNS`, `EPILOGUE_FORMULA_PATTERN`) to catch AI stylistic clichés (e.g. `", that trust broken"`, disembodied AI stepping/breathing).
   - *Status*: High craft payoff; non-fatal craft notes (not hard halts), allowing models to self-correct during the prose pass without breaking pipeline execution.

---

## 4. Prioritized Architectural Refactoring Plan (v0.2+)

### Priority 1: Navigation Topology Pre-Scaffolding (Stage B)
- **Goal**: Eliminate topological failures and disconnected rooms by having Python generate valid planar room graphs and exit pairs before prompting for room descriptions.
- **Impact**: Removes retry loops in `world.py`; eliminates spatial hallucinations.

### Priority 2: Label & Handle Generation Simplification (Stage B & C)
- **Goal**: Strip formatting rules for menu labels and `unnamed_short` from `s6a`, `s6b`, and `s7d` prompts.
- **Implementation**: Python post-processes interaction labels, splits noun phrases for `unnamed_short`, and trims lengths deterministically.
- **Impact**: Saves ~15–20% prompt token budget on downstream calls; cuts reasoning trace length.

### Priority 3: Minor Prop and Topic Batching (Stages B & 7D)
- **Goal**: Consolidate small, isolated single-entity LLM calls into coherent structured batches.
- **Impact**: Directly reduces serialized network latency and Ollama KV cache rebuild overhead (key prerequisite for Issue #10).
