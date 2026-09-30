# Response to `fable_request_3.txt`

Date: 2026-09-29. Inputs read: the request, the previous request and its
design doc, all 24 prompts, `main.py` / `step4.py` / the clients, and the
kernel1 archive in `stories/current_output.tar`: every JSON output, the
thinking traces for 3.5, 3.5v, 4a (both iterations), 4d (all four), and five
4b beats, and the per-call timings from the log timestamps.

The six issues you raised turn out to have three roots, and the pipeline
that comes out of fixing them is different enough that I rebuilt everything
from 3.5 on. `docs/step4_design.md` is the live description of what runs
now; this document is the reasoning and the answers to your questions.

## 1. What the kernel1 run actually cost

From the log timestamps (seconds per call):

| call | time | thinking |
|---|---|---|
| phase 3 (10 calls) | 12,600 | 6–52 KB each |
| 3.5 | 5,780 | 88 KB |
| 3.5v | 4,420 | 76 KB |
| 3.75 + 3.75v | 4,740 | 28 + 52 KB |
| 4a iteration 1 | 5,560 | 79 KB |
| 12 entity calls | 4,660 | 2–16 KB |
| 10 beats | 19,700 | 20–52 KB |
| 4d, first attempt | 18,470 | crashed |
| 4d, third attempt | 9,360 | 109 KB |
| 3 beat repairs + 4d re-review | 7,000 + 19,200 (crashed) + 6,650 | |
| iteration 2 (4a, 3 beats, 2 revisions, 4d) | 16,600 | |

About 43 hours for two iterations, and the 4d review is a quarter of it on
its own: it received the whole digest plus the state registry, roster,
branch table, premise, 3g and 3c, produced 100 KB of reasoning, and failed
twice (the first attempt's log stops mid-sentence at 94 KB, which is what
running out of context looks like).

## 2. The three roots

**Root A: every downstream call was handed the whole upstream corpus.** 4a
received the kernel, all nine extractions with their notes and tiers, 3h,
3.5 and 3.75. Its trace begins with 35 lines restating them. The
reasoning-discipline blocks could not touch that, because restating inputs
is how this model orients itself; the length is a function of what it was
given, not of what it was told. Same for the "need maybe X ... good" tail:
one line per rule and per output field, so it scales with the prompt's rule
count and schema size. This is issue 1, and the fix is smaller calls, not
better instructions.

**Root B: the pipeline had no concept of an obstacle.** 3-0a extracts a
decision axis; 3.5 turned it into N *instances* of that same decision; 4a
made a beat per instance whose "decision" was the axis as a two-way pick; 4d
counted the combinations as endings. Vent/spare/vent/spare is not a failure
of the model's imagination, it is the only story that architecture can
produce. The old 3.5 also forbade "new mechanics" in a way the model read as
"do not give the protagonist anything to push against", and the enrichment
budget came out `minimal` because kernel1 is specific about tone and setting,
which then suppressed the one place invention was allowed. This is issues 2
and 6 (crowds as characters follow directly from instances being sectors),
and most of issue 3.

**Root C: the pipeline was building a choose-your-own-adventure.** Beats
with `available_actions` and a `decision` with `outcomes` is a menu. Once
the engine is rooms, fixtures and people, a "decision" is the state the
player reached by what they did, and the unit of outline has to be a section
of play with a room subset, not a beat with a choice. This is issue 5, and
the rest of issue 3 (4a was planning ending mechanisms and selector
variables because a menu graph needs them; a room-based node graph does
not).

Issue 4, the ending count, is downstream of all three: it was an explicit
constraint, so 4a designed six selector variables to hit six or seven
combinations, 4d spent pages counting variants against the target, and the
whole story shape was arithmetic.

## 3. What changed

Prompts removed: `s4a_first_outline`, `s4a_next_outline`,
`s4c5_craft_refresh`, `s4_entity_define`, `s4_beat_generate`, `s4d_verify`.
New: `s2_shape_split`, `s3_6_cast`, `s3_7_world`, `s4a_main_line`,
`s4b_node_build`, `s4c_divergence`, `s4d_review`. Rewritten: `s3_5` and its
verifier and repair. Adapted to smaller inputs: `s3_75` and its pair. Phase
3 prompts are untouched. Code: `brief.py` is new, `step4.py` is rewritten,
`main.py` routes the new steps, `stub_client.py` answers the new prompts.

### 3.1 Trace length (issue 1)

Every prompt after 3h now receives a computed **brief** (each field's value
and binding class, ~3 KB) instead of the bundle and the constraint map. 3.75
gets three inputs instead of nine. The node build gets only its own rooms
and characters. The review's mechanical half (exit reachability, reads
before writes, outline/build mismatches, menu interactions) is computed in
Python and handed to the review as "already found; do not repeat". The
outline has no framework, mechanism or selector fields. Schemas are smaller
across the board. The reasoning-discipline blocks are three lines each.

I could not measure the effect here (no model in this sandbox). The
comparison to make on your next run is thinking bytes per call against the
numbers in §1. I also added `--no-think-steps` (sends `think: false` to
Ollama for named prefixes) so you can experiment with switching the trace
off for mechanical calls such as the step-2 split; it is off by default
because I do not want to degrade judgment calls without evidence.

### 3.2 The dramatic engine (issues 2, 6)

3.5 now builds: a protagonist with a **cannot_do**; a **pressure**; an
**opposition** with its own want and means; **mediation**, which restates
the decision axis as the question at stake and says what the player must DO
in the world to bring each pole about and at what cost, plus the levers
(people, objects, facts, authorities) that stand in the way; **turns**, 3–5
escalating situations each with a different form (discover, persuade,
trade, confront, conceal_or_reveal, ...) and 2–3 ways through with costs;
and **cast seeds** where every crowd has an individual who speaks for it.
The prompt's one hard rule is "the question is not the verb": even when the
kernel says the protagonist can do the decisive thing directly, 3.5 decides
what has to be true first and who can help or stop it. All of that is
mandatory at every budget; the budget now governs texture only.

Your council-of-representatives idea is exactly the kind of thing this
produces, and I used a version of it as the stub's canned premise. But the
prompt does not prescribe it; it prescribes that an obstacle exist, that
each pole cost something to reach, and that the turns differ in form. The
3.5 verifier has a new audit that fails hard on a missing engine (bare
turns, a mediation pole that just restates the pole, an opposition that
only wants to stop you, a crowd without a face), and the repair step is told
that this is the one finding it fixes by adding material.

Cast and world are now their own small steps (3.6, 3.7), run once before any
story line, so the outline chooses room and character subsets from things
that exist. The cast validator rejects a crowd with no named representative.

### 3.3 The story-line loop (issues 3, 5)

Step 4's unit is a **node**: a goal the player works toward, 1–3 rooms, 1–3
characters, a pressure, and exits that are states of play ("you hold the
override and the foreman has stopped answering"), each leading to another
node or left open. Iteration 1 lays down the **main line**: one through-line
(motivation, strategy, turning point), every turn in one node in order, one
ending. It plans nothing else.

Iteration n runs the **divergence** step, which is your Star Wars model
made literal: find a different motivation or strategy for the protagonist,
find where in the existing story it can take hold (an open exit, or a new
opportunity added to an existing node: an offer, a discovery, an arrival),
explain the shift, outline the new nodes, and either end or rejoin. The
driver rebuilds the node the line changed so the opportunity exists in it,
builds the new nodes, and rebuilds a rejoined node with ending variants. For
a linear kernel (kernel17) the divergence is a `state_variant`: the same
nodes played differently, and a variant of the final node's ending.

The node build writes per-room interactions (target, action, requires,
sets), per-character agendas and what moves them, a clock if the premise
licenses one, and exits with structured `when` conditions. "Choose" and
"decide" interactions are forbidden by the prompt and caught by a computed
check. The review's judgment checks are: earned choices, continuity, cast
and rooms, through-line novelty, pacing, and termination, which proposes
the next seed (a motivation and where it could diverge) or recommends stop.

## 4. Should the kernel drive the shape?

No, and I have implemented that: step 2 now splits the kernel into a content
kernel and shape preferences, every later step sees only the content kernel,
and the preferences reach step 4 as coarse advisory targets (a suggested
number of through-lines and a node-count range), which the review may
overrule per line and `--max-iterations` caps.

The argument. A kernel is a statement about the experience the user wants;
"6 or 7 endings" is the user's guess at a means to that experience. The user
cannot know whether the premise supports seven endings that differ in kind,
and holding the pipeline to the number produced the worst behavior in the
archive: selector variables designed for combinatorics, endings that were
"two spared / two vented" variants of one ledger, and a review counting
against a ceiling instead of judging the next line. What the user can
legitimately say is coarse: linear or branching, one ending or many, short
or long. Those survive the split as tiers, and the linear tier changes the
build (state variants instead of new nodes), because "no real forks" is a
constraint on play, not a count.

The one thing I kept deliberately: the stated wording is recorded in
`s2_shape.json` so a human can see what was asked, and a named form ("a
5-act tragedy", "a chamber piece") stays in the content kernel because it
says what kind of story this is, not how many endings to build.

Side effect to know about: 3g's `target_ending_count` will now come back as
a fallback for kernels that stated one, since the clause is gone before
phase 3. Nothing downstream reads it any more.

## 5. What I could not do here

There is no Ollama server in this sandbox, so nothing has been run against
a live model. The stub client exercises every path (both repair loops, the
halt, a bad node caught by the computed checks and repaired, a review
finding, divergence by open exit, by new opportunity, by rejoin, and by
linear state variant, a "nothing worth building" stop, resume with zero
model calls, and stale-file detection). Section 9 of `step4_design.md`
lists what to read first on the first live run; the short version is: run
one kernel with `--stop-after=3.5`, read the 3.5 trace and the 3.5v verdict,
and only then let it go to `--max-iterations=2`.

Old story directories (including `stories/kernel1/`) will not load: the
schemas changed and `run_prompt` now names a stale file and stops. Delete
the directory for a fresh run.
