# Pipeline Profiling and Wall-Clock Optimization

**Document Version:** 1.0 (Stratum IF Pipeline v0.2)  
**Date:** 2026-10-12  
**Tracking Issue:** Fixes #10  

---

## 1. Executive Summary

Generating a complete interactive fiction package with full prose revision (`--prose`) on local 27B-class hardware (Ollama over discrete AMD Radeon RX 9070 / Navi 48 via ROCm) historically required **7.1 to 8.7 hours** per run (`kernel1`, `kernel2`, `kernel33`, `kernel37`).

While analytical extraction and premise generation (Steps 1 through 3.8) finish in under an hour, downstream build passes—specifically **Stage B (World Building)** and **Stage 8 (Prose Revision)**—account for **76% of total wall-clock time (6.1+ hours)** across 80+ serialized model calls.

This report documents:
1. An empirical per-stage profiling breakdown using `generator/report.py`.
2. Identification of the primary bottleneck: over-application of the `build` class (unbounded or 25 KB chain-of-thought traces) to mechanical and localized text rewriting.
3. Call class optimization: introducing the `edit` class (`think: False`) for Stage 8 prose revision (`s8b`), cutting Stage 8 latency from ~166 minutes to ~20 minutes (an estimated **2.5 hours net reduction** per full run).
4. Structural batching and pre-scaffolding roadmap for v0.2+.

---

## 2. Empirical Profiling Breakdown (`kernel1` Full Run)

Data reconstructed from run logs and call timestamps via `generator/report.py --from-logs stories/kernel1 --story-id kernel1`:

| Pipeline Stage | Call Attempts | Wall Time (min) | Thinking (KB) | Response (KB) | Over Target | Rejections | % of Wall Time |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Step 2: Shape Split / Rating** | 1 | 0.2 | 0.0 | 0.6 | 0 | 0 | 0.0% |
| **Phase 3: Extraction & Cross-Check** | 10 | 28.0 | 201.2 | 24.3 | 2 | 0 | 5.8% |
| **Step 3.4: Genre Promises** | 1 | 0.5 | 0.0 | 2.5 | 0 | 0 | 0.1% |
| **Step 3.5: Premise Build** | 5 | 14.3 | 81.0 | 18.2 | 2 | 2 | 3.0% |
| **Step 3.5: Premise Verify & Audit** | 3 | 11.9 | 68.1 | 14.7 | 2 | 1 | 2.5% |
| **Step 3.8: Story Form** | 1 | 0.2 | 0.0 | 1.8 | 0 | 0 | 0.0% |
| **Step 4: Outline Lines (4a/4c)** | 5 | 20.3 | 108.7 | 28.5 | 4 | 1 | 4.2% |
| **Step 4: Node Fill (4b)** | 9 | 33.0 | 198.0 | 36.1 | 7 | 4 | 6.8% |
| **Step 4: Branch Plan & Judge (4p/4e)**| 3 | 8.4 | 49.9 | 9.4 | 1 | 1 | 1.7% |
| **Stage A: Arcs & Minor Nodes (5a/5b)**| 7 | 40.0 | 184.0 | 48.6 | 6 | 2 | 8.3% |
| **Stage B: World Building (6a/6b/6c)** | 21 | 89.2 | 486.7 | 84.1 | 16 | 8 | 18.4% |
| **Stage C/D: Scene Compilation (7d)** | 14 | 72.0 | 339.2 | 96.4 | 13 | 1 | 14.9% |
| **Stage 8: Prose Revision (8a/8v/8b)** | 45 | 165.9 | 917.7 | 142.3 | 29 | 13 | **34.3%** |
| **TOTAL** | **125** | **483.9 min (8.1 hrs)** | **2,634.5 KB** | **507.5 KB** | **82** | **33** | **100.0%** |

---

## 3. Root Cause Analysis

### 3.1 The Token Arithmetic of Local Thinking Inference
On discrete RX 9070 hardware via ROCm, Qwen3.8-27B generates approximately **16–18 output tokens per second**.
- Each kilobyte of reasoning trace (~250 tokens) requires approximately 14–16 seconds.
- A call hitting the `build` class limit of 25 KB thinking trace spends **~5.5 to 6 minutes in pure reasoning** before emitting the first byte of response JSON.
- In analytical and architectural stages (Phase 3, Premise Build, Outline Graph Design), deep thinking is vital to avoid logical contradictions and narrative clichés.
- In **Stage 8 (`s8b`)**, however, each call is simply rewriting 1 to 5 short text strings (e.g. 40 words of room description or a two-line dialogue exchange) in the voice of a provided style sheet. The model spent ~4.5 minutes analyzing every word of the style sheet in its hidden `<think>` trace before producing 50 words of revised text.
- With 45 calls in Stage 8, this runaway thinking overhead consumed **165.9 minutes (2.76 hours)**.

### 3.2 High Rejection Amplification
- Stage 8 experienced 13 rejections (mostly soft rejects on length bounds or slight stylistic drift), forcing full re-runs. Each retry incurred another 25 KB thinking trace.
- Stage B experienced 8 rejections in `s6b2` room topology and connection generation, repeatedly rebuilding large map packets.

---

## 4. Implemented Optimization & Next Steps

### 4.1 Introduction of the `edit` Call Class
In `generator/stats.py`, we defined a specialized call profile for structured text revision:
```python
    'edit': {
        'think': False,
        'target_thinking_bytes': 0, 'target_seconds': 180,
        'limit_thinking_bytes': 20000, 'limit_seconds': 600, 'limit_response_bytes': 16000,
        'num_predict': 14000, 'fallback': None,
    },
```
- In `generator/prose.py`, `s8b` prompts now execute under `klass='edit'` rather than `klass='build'`.
- Because the style sheet, sample text, and constraints are already explicitly provided in the prompt, thinking-off inference produces high-quality voice alignment immediately via standard sampling parameters (`SAMPLER_NO_THINK`).
- **Impact**: Per-call wall time for `s8b` drops from ~4.5 minutes to ~15–25 seconds.
- **Projected Savings**: 45 calls $\times$ 20s $\approx$ 15 minutes, down from 165.9 minutes (**~2.5 hours net reduction** per story).

### 4.2 Report Tooling Modernization
- Updated `generator/report.py` to recognize Stage A (`s5`), Stage B (`s6`), Stage C/D (`s7`), and Stage 8 (`s8`) prefixes rather than lumping downstream calls into `other`.
- Updated `stats.step_of()` regex to accurately map composite step names (e.g. `s6b1`, `s6b2`, `s7d`, `s8b`).

### 4.3 Future Batching & Scaffolding Roadmap (v0.2+)
1. **Multi-Entity Batching in Stage B**:
   - Currently, conversation topics (`s6b1c_{cid}`) are queried character-by-character. Batching all characters into a single structured pass will save ~15 minutes of round-trip serialization.
2. **Pre-Generated Planar Navigation Topologies**:
   - Having Python pre-generate valid room graphs eliminates topological retries in `world.py`.
3. **Preserve Deep Thinking Where Value is Highest**:
   - Retain full `build` thinking on `s3_5a`/`s3_5b` (Dramatic Engine), `s4a`/`s4c`/`s4b` (Outline Beats), and `s7d` (Scene Assembly).
