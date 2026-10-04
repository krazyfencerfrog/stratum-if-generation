# Backlog: work for the hours the local model is busy

Batches take hours (85-140 minutes per kernel), so most of the time the GPU
is busy and everything else is free. This is the standing list of work that
does not need the model, or needs it only to verify afterwards. Keep it
current: move items to Done with the date and the commit or doc that closed
them, add new ones as runs turn them up.

Tags: **[solo]** Claude can do it alone without the GPU. **[you]** needs the
user's input or decision. **[GPU]** needs model time to verify, usually an
overnight batch.

## Active

### Thinking budget investigation [solo, then GPU]
First look (2026-10-04): kernel35's forced 4a trace was still choosing its
crisis beat at the 25 KB cut, not re-checking settled decisions; the traces
are telegraphic deliberation ("Need ...", "Could ...", "But maybe ..."), so
the old "drafting starts at X%" heuristic finds nothing. Worth measuring.
The question: would a larger thinking budget for construction calls give
clearly better outlines, and is it affordable? The user is open to longer
runs if the outlines get significantly better.

What we know (runs of 2026-10-03/04, Fable 5 branch):
- Every construction call runs to its limit and is forced: 3.5a 4/6,
  3.5b 4/4, 3.5v 9/9, 4a 4/4, 4b 18/20, 4c 10/10, 4p 5/5. Phase-3
  extractions (no breaker) finish on their own at 5-31 KB.
- The one earlier test (4a only, one sample each, the smaller pre-Fable
  prompts): 25 KB was as good as 40 KB or unlimited (89 KB, 14.6 min).
  That result may not hold now: the prompts carry more rules (3.5a/b about
  29 KB, 4c about 40 KB), and premise repair rounds rose (kernel31 needed
  two), which could be forced answers missing rules.
- Context: num_ctx is 32768 tokens. At about 4 chars per token, 4c is
  about 10k tokens of prompt + 6k of thinking at 25 KB + 3-4k of answer,
  so about 20k. A 60 KB budget (about 15k tokens) would put 4c near the
  ceiling; anything larger needs num_ctx 48k. VRAM looks able to take it
  (13.4 GiB model; the q8 KV cache was about 1.1 GiB at 32k and only the
  16 full-attention layers grow it), but that has to be checked with
  `ollama ps` after a load.

Plan:
1. [solo] Trace analysis on the saved traces: where in each forced trace
   the decisions are settled (when the model starts drafting the final
   answer), what the rest is spent on (re-checks, rule lists, restating
   the input), and whether forced answers miss rules that a validator,
   the audit or a repair then catches. If decisions settle well before
   25 KB, a larger budget buys checking, not thinking.
2. [solo] Build a replay harness: send a saved `*_raw_input_prompt.txt`
   with a given budget and seed, save the answer, run the call's validator
   and the computed checks on it (example guard, brief echoes, events, set
   piece, menu verbs).
3. [GPU] Matrix: 3.5a, 3.5b, 4a and 4c (and 4p) at 25 / 40 / 60 KB, two
   seeds, on kernels 31, 32 and 35 from their saved inputs. About 50 calls
   at 5-12 minutes, one night. Compare validator and audit outcomes and
   computed metrics, and read the answers blind (labels hidden).
4. [GPU, if 3 says yes] Full-pipeline A/B at the winning budget on the
   evaluation set, with num_ctx raised if needed. Decide per call class:
   the answer may be "40 KB for 3.5a/b and 4c, 25 KB for 4b".

### Review of the Fable 5 outlines [solo]
- Read 31, 32, 8, 35, 34 (done in conversation 2026-10-04); 33 when it
  lands. Write the quality ledger into `docs/run_samples/<date>/README.md`
  with the outputs, as for the 2026-10-03 samples.
- Retry and repair forensics: which soft retries and audit findings fire,
  how often, whether the fix took. A rule that fires on every kernel is a
  rule the model cannot follow as written.
- Calibrate `evaluate.py` and the outline judge against the reading.

### Known weak spots from the runs [solo, then GPU]
- node summaries run long: 76-99 words against the 45-75 target;
- a cast member's voice description leaks into summaries ("commuter" in
  kernel32): the brief-echo treatment could cover voices;
- `ending.lost` lists things as well as people (now ignored when comparing
  worlds, but the field drifts);
- no accumulated triggers in any run yet;
- invented magic stays vague (kernel31: "the old bond", "the smoke of your
  village");
- premise repair rounds: kernel31 needed two;
- endings phrased as permutations of one sentence ("the child is safe, X is
  lost, Y stands"; kernel34) and repeated motifs ("folded" list, oath, copy);
- procedure standing in for drama (kernel34's stakes run through seating
  charts and oath wording).

## Next

### Later stages design [you, interactively]
Stage A designed (2026-10-04): arcs and node expansion, the Python/model
split, pattern shifts, tells, active attempts (`docs/later_stages.md` §2;
worked example `docs/stage_a_example_kernel35.md`). Next: stages B, C and D
at the same level. Small open items for A: composing resolution variants;
whether some outline forks should become pattern triggers.

### Protagonist fields on the model [GPU]
The defined-but-steerable protagonist (history, need, ties, open, gender,
a Python name; commits 8b46995, 3769dd9) has not run on the model yet. Starting
point: `docs/later_stages.md` (A beat expansion, B cast and world buildout,
C reconciliation, D the per-node room build). Questions: what each stage
consumes and produces, what the outline must carry for them (the node
`image` and cast `voice` are early hooks), how it maps onto the stratum-if
engine (rooms, objects, characters with topics).

### Prompt size [solo, then GPU]
3.5a, 3.5b, 4a and 4c carry 26-40 KB. Find text that changes nothing
(redundant rules, oversized examples) and cut it: a smaller input leaves
more of a fixed budget for the story. Pairs with the budget investigation.

### Code health [solo]
- Review `main.py` (about 1,500 lines) and `outline.py`: three authors in
  quick succession; look for dead code, duplicated logic, confusing flow.
- Tests for the quality logic (evaluate metrics, guards, checks) beyond
  spot tests.
- Merge the Fable 5 branch into main once it is proven; update docs.

### Tooling [solo]
- `report.py` across many stories; a side-by-side view of two outlines of
  the same kernel for before/after reading.

### Infrastructure [mixed]
- [GPU] Would a larger quant that still fits on the GPU (a Q4 at 32-48k
  context) beat IQ3_XS on quality? Speculative decoding with a small
  draft model?
- Running unattended: a small queue service that resumes after a reboot or
  a kill.

## Done
- 2026-10-04: code review of main.py/outline.py and fixes: a finished premise loop
  replays as saved (no model calls from new checks); rejected attempts' outputs kept;
  the run summary prints on a crash; line ids count lines (no gap after a dropped
  seed); the plan validator trims seeds first; "you" ignored in a node's who; one
  TURN_FORMS; dead helpers removed. Left as is: long run_prompt/story_markdown, the
  per-attempt .log files.
- 2026-10-04: batch runner (`generator/batch.py`): a queue file, a machine-wide GPU
  lock so two runs never share the GPU (two runs had collided that day),
  resume after kills, one retry for transient failures, a metrics report.
- 2026-10-04: playtest simulator (`generator/playtest.py`). On the five Fable 5
  outlines: all valid, but every ending is reached with at most ONE decision
  per playthrough, the case for stage A in one number. Its random-play check
  showed the fixed pattern-shift threshold is too loose (31% of random play
  meets 3-of-4), so thresholds are now computed in the design.
- 2026-10-04: kernel audit: retired 9, 18, 23 (duplicates); added 36 horror with a
  group, 37 crew heist, 38 Victorian murder, 39 ancient Rome, 40 frontier West;
  evaluation split into EVAL_SET (9, two nights) and EVAL_QUICK (4, one night).
  Still open from the audit: hand-written target outlines for a few kernels.
- 2026-10-04: stage A design (later_stages.md §2), worked example for
  kernel35, protagonist fields and naming.
- 2026-10-04: name generator, 20 pools, per-culture styles, races, stated
  gender (commit 574e041 on fable-response-5).
- 2026-10-04: ending worlds compare people only (d453412); free brief
  fields read as placeholders, fixing "surprise me" (557edce).
