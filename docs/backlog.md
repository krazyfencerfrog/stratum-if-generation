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

**Step 1 done (2026-10-04, `generator/trace_analysis.py`, 233 traced calls in
12 runs: the Fable 5 branch runs plus batch3's kernel35/38).** Sentence by
sentence, each trace is sorted into restating the prompt, deliberating
(questions, could/maybe/either/whether), checking, planning notes and
drafting (phrases that reach the answer), per tenth of the trace:
- Phase-3 extractions, which finish on their own, SETTLE: deliberation falls
  from about 0.34 to 0.27 in the last fifth, checking rises to 0.06 and
  drafting to 0.20.
- Construction calls cut at 25 KB (3.5a/b, 4a, 4b, 4c, 4p: 131 of them)
  never settle: deliberation stays at 0.30-0.34 to the last tenth, checking
  at 0.02-0.03; drafting climbs to 0.20. They are cut in the drafting-while-
  still-deciding phase, before the settle-and-check phase.
- Only 22-31% of the 4a, 4c and 4p answers' distinctive content (content-word
  trigrams not in the prompt) appears anywhere in their traces (3.5a 49%,
  4b 64%), against 72-98% for phase 3: most of a forced construction answer
  is composed after the cut.
- First attempts rejected by their validator: forced 7/135 (5%), finished
  build calls 0/14 (too few to mean much).
So a larger budget would buy finished decisions, not re-checking; the
earlier "25 KB is as good as unlimited" (4a only, smaller prompts) does not
describe today's prompts. Whether finished decisions make better stories is
step 3's question. `STRATUM_THINKING_LIMIT=build=40000` (any class) and
`STRATUM_NUM_CTX` now set the budget per run for that experiment, in any
copy of the code. Proposed first matrix (cheapest, fits num_ctx 32k even at
60 KB: 3.5a's prompt is about 7k tokens): the premise (ab.py ...
--stop-after=3.5) on kernels 31, 32, 35 at 25 / 40 / 60 KB, one seed each,
about 4 hours; then 4a/4c if the premises improve.

Plan:
1. [solo, DONE] Trace analysis on the saved traces: where in each forced trace
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
- Quality ledger: DONE 2026-10-04, `docs/run_samples/2026-10-04/` (the six
  Fable 5 runs and batch3's three). Still to read in depth: kernel33_f5.
- Retry and repair forensics (DONE 2026-10-04, over 32 saved runs):
  validator rejections are rare (about 20 clauses in 32 runs, all fixed by
  the retry); no step rule is one the model cannot follow. The cost is the
  premise audit: 13 of 29 premise loops needed one or two repair rounds.
  Findings: engine boundary 7 (a ledger or gate condition read as a system
  the engine lacks), the brief's epistemic gap contradicted 5 (AI kernels),
  turn form "choose" 5 (now a soft retry at 3.5b instead of a repair round),
  failure presence 2 (reported as three findings each: presence, triggers,
  cost, for one dawn deadline). Open: fold the three failure findings into
  one; read the engine-boundary findings, which may be the audit being too
  strict about ledgers and fees that are just objects.
- Calibrate `evaluate.py` and the outline judge against the reading.

### Known weak spots from the runs [solo, then GPU]
- node summaries run long: 76-99 words against the 45-75 target;
- a cast member's voice description leaks into summaries ("commuter" in
  kernel32): DONE 2026-10-04 for phrases (4 of 265 saved summaries, e.g.
  "in quick practical fragments"), folded into 4b's soft check; single words
  like "commuter" are not caught;
- `ending.lost` lists things as well as people: DONE 2026-10-04, soft-rejected
  at 4a, 4c and 4p (8 of 78 saved endings; kernel39's "the different
  senator", a phrase from a way, was the judge's worst thing);
- no accumulated triggers in any run yet;
- invented magic stays vague (kernel31: "the old bond", "the smoke of your
  village");
- premise repair rounds: kernel31 needed two;
- endings phrased as permutations of one sentence ("the child is safe, X is
  lost, Y stands"; kernel34) and repeated motifs ("folded" list, oath, copy);
- procedure standing in for drama (kernel34's stakes run through seating
  charts and oath wording).
- DONE 2026-10-04: verbal tics along one line soft-rejected at 4b (d79e9aa;
  repetition across alternative lines is left alone, since no player reads
  them together, though the outline judge does and complains: kernel38's
  "spreads the signed debt on the table" sits two to a line); roles written
  as plot functions ("the guest whose secret is easiest to hear", invented
  by 3.5c from 3.5a's pole text) soft-rejected at 3.5b and 3.5c.

## Next

### Later stages: after the first generated package [GPU, then solo]
Stages A, B, C and D are built and ran live on kernel35_f5 (2026-10-04; the
package is stratum-compare/staged/stories/kernel35_f5/kernel35_f5_package.json,
playable, every ending reachable). That run used stage A before the seesaw
fix and stage B before the duplicate-room and topic fixes, so its world has
twin rooms and 50-64 topics a person. Next:
- a clean re-run, stage A then B then D, on kernel35_f5 (about 3.5 hours of
  GPU) to see every fix of 2026-10-04 in one story [GPU];
- a stage D repair call fed by the playtest's findings (MENU, STUCK, ways on
  hard to find), like the outline loop's repair [solo, then GPU];
- the prose stage design (later_stages.md §6) [you];
- per-scene exploration samples entry states (8 a scene, by arc state and
  flags); a STUCK found from a sampled entry could, rarely, come from what the
  sampled player happened to carry; watch for it.

### Premise A/B: DONE 2026-10-04 (stratum-compare/ab_premise)
Three 3.4-3.5 replays of kernel35 each on Fable's 4651810 and on b67f48a
(this branch with the protagonist fields). No sign the branch weakened the
premises: the same turn count, three set pieces each, the same shapes, and
some of the best images on the branch; paperwork in every turn on both
sides (the kernel's sale and debt invite it). One branch run halted after
two repair rounds on the audit's "a deadline is a system the engine lacks"
false alarm, fixed since in 97c7f3e. The one difference to watch: smaller
casts on the branch (3, 2, 2 people against 4, 3, 3); 3.5c sketches only
the roles the turns name, so the branch's turns lean on fewer people.
Three samples; check it again in the next runs. kernel35_f5's strong
premise was mostly a good draw.

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
Measured 2026-10-04: 3.5a's template is 24 KB, 11 KB of it the two
calibration examples (each with a reasoning paragraph and a full output);
3.5b 20 KB, 4c 16 KB. Deliberately not cut blind: wait for the premise A/B
(which tests whether the protagonist fields added to 3.5a hurt), then try a
trimmed 3.5a (one example, or examples without their reasoning) as an A/B
variant at the same budget.

### Relationship states at the premise level: DECIDED 2026-10-04
"Whatever makes the better story": companions whose loyalty is earned or
lost, and whose loyalty opens or closes doors, are the heart of interactive
drama, and the new engine and stage A can carry them. 3.5a now names such a
relationship as a primitive, and the audit permits it; it still reports a
number the player is shown or must watch, and rule systems the engine lacks.

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
- 2026-10-04 (evening): the first live stages B, C and D (kernel35_f5), and what
  they turned up, fixed: duplicate rooms when locations are parts of one place
  (7c22c7d); topics labelled with whole sentences, roles missing, namesakes
  (ab97299); 50-64 topics a person, now the objects tied to them (c318999);
  undirected variants and abstract targets costing retries (f0eb785); takes
  that took nothing, ways on and moments behind fetching things, rooms out of
  reach (f160cec, 4f42c0a, 93cdefb); one thing per name (a0d928a); a batch in
  a code copy locking its own GPU lock file (e9665e8). Engine: one key press
  per choice (33bacf3), new markers, topic groups, brief revisits (702cd28),
  the menu checked by the playtest (26a406c), exploration scene by scene and
  seeking players (cf02e3d).
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
- 2026-10-04: engine core, terminal player with history and rewind, playtest
  simulator (engine/); modern names by culture with a home culture per story
  (b67f48a); stage A built (6d0ae3e).
