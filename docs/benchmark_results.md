# Stratum IF Benchmark & Evaluation Results

This document records pipeline benchmark runs, structural metrics, playability evaluations, and model behavior across test suites.

---

## 1. Test Suite: `week1` (October 8–10, 2026)

### Run Environment
* **Platform**: AMD Ryzen 7 7700X, discrete AMD Radeon RX 9070 (Navi 48) with ROCm.
* **Inference Backend**: Local Ollama 0.35.1 (single-job serialization via `.stratum_gpu.lock`).
* **Model Configuration**: 27B-class reasoning model with Flash Attention, `q8_0` KV cache, context shift enabled.
* **Target Flags**: `--prose` enabled on `kernel35_f5`, `kernel2`, `kernel33`, `kernel37`. Staged stopping on reference kernel variants (`ref_man_who_would_be_king_k4`–`k9`).

---

### Batch Execution Summary

| Story ID | Kernel / Focus | Flags | Status | Time (min) | Nodes | Forks | Worlds | Paperwork Share | Notes / Halts |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `kernel35_f5` | The Mooring Line | `--prose` | **done** | 132.7 | 9 | [2, 4] | 3/3 | 0% | Loss none; opposition clean |
| `kernel2` | The Chain That Names the Dead | `--prose` | **done** | 430.1 | 12 | [1, 2] | 3/3 | 14.3% | Moral stakes, 3 full endings |
| `ref_man_k4` | Man Who Would Be King | `--stop-after=3.5` | **done** | 24.5 | - | - | - | - | Reference premise check |
| `ref_man_k5` | Man Who Would Be King | `--stop-after=3.5` | **done** | 51.3 | - | - | - | - | Reference premise check |
| `ref_man_k6` | Man Who Would Be King | `--stop-after=3.5` | **done** | 30.0 | - | - | - | - | Reference premise check |
| `ref_man_k7` | Man Who Would Be King | `--stop-after=3.5` | **done** | 29.5 | - | - | - | - | Reference premise check |
| `ref_man_k8` | Man Who Would Be King | `--stop-after=3.5` | **done** | 27.9 | - | - | - | - | Reference premise check |
| `ref_man_k9` | Man Who Would Be King | `--stop-after=3.5` | **done** | 44.3 | - | - | - | - | Reference premise check |
| `kernel1` | Mountain Observatory | baseline | **done** | 127.8 | 15 | [1, 2, 2] | 4/4 | 16.7% | Stage D compile |
| `kernel31` | The Clock Tower Archive | baseline | **done** | 153.0 | 19 | [3, 6] | 4/4 | 11.8% | Large node graph |
| `kernel34` | The Salt Mine | baseline | **halted** | 105.7 | - | - | - | - | Halted at s3_5k audit (Issue #26) |
| `kernel33` | The Seaside Hotel | `--prose` | **done** | 521.4 | 14 | [6, 2, 6] | 4/4 | 29.4% | Complete prose package |
| `kernel37` | The Wire and the Gun | `--prose` | **done** | 519.1 | 13 | [2, 6] | 3/3 | 11.1% | Complete prose package |

---

### Playability & Engine Verification

The four complete `--prose` runs produced standalone playable packages that pass all deterministic engine checks (`python engine/cli.py <pkg> --check`):

1. **`examples/kernel35_the_mooring_line.json`** (215 KB)
   - 7 playable nodes, 3 distinct endings.
   - Zero bureaucratic errands or abstract paperwork stakes.
2. **`examples/kernel2_the_chain_that_names_the_dead.json`** (242 KB)
   - 9 playable nodes, 3 distinct endings.
   - Comprehensive playability: 157,489 unique state combinations explored across simulated playthroughs with 100% completion across all three endings without deadlock.
3. **`examples/kernel33_the_seaside_hotel.json`** (256 KB)
   - 11 playable nodes, 3 endings.
   - Higher paperwork/lease ratio flagged for future prompt tuning.
4. **`examples/kernel37_the_wire_and_the_gun.json`** (230 KB)
   - 12 playable nodes, 3 endings.
   - Low abstraction score, strong physical interaction model.

---

### Pipeline Audit Observations

* **Kernel 34 Premise Auditor Halt**: 
  - `kernel34` triggered a halting violation at step 3.5k when the model generated a premise variation directly conflicting with an explicit kernel clause. The halt prevented wasteful downstream scene generation and accurately flagged the defect for pipeline repair (tracked in Issue #26).
* **Bureaucratic Stakes Metric**:
  - The deterministic paperwork detection audit (`s4e_outline_judge.json`) successfully caught varying levels of bureaucratic stakes across runs (0% in `kernel35` vs 29.4% in `kernel33`), proving the utility of programmatic metrics over LLM self-evaluation.
