# Response to `fable_request_4.txt`

Date: 2026-10-01. Inputs read: the request; CLAUDE.md, `step4_design.md`,
`fable_response_3.md`, `fable_request_3.txt`, the lessons doc, `strategy.txt`;
every prompt and every file in `generator/`; and the archive in
`stories/current_output.tar`: every JSON output, the timings from the log
timestamps, and the thinking traces of s2, 3.5, 3.5v, 4a, 4b (n02), 4d and 4c.

Short version. You were right that step 4 was working at the wrong level, and
right that telling this model how to reason does nothing. Step 4 is now an
outline loop over a chosen story framework; 3.6, 3.7, 3.75 and the node build
are parked as later-stage material; the premise is built in three small
calls and audited by a call that costs minutes; every call has a class with a
budget and a circuit breaker; and there is a test script, a report script and
a probe for your Ollama server. I disagree with your direction in a few
places, listed in section 4.

**Nothing here has run against a live model.** This sandbox has no model. The
plumbing is tested on a stub (18 tests, about 8 seconds); every estimate of
time or trace size below is a projection from the archive, and section 9 is
the order in which to find out whether I was right.

`docs/outline_design.md` is the live description of what runs.
`docs/later_stages.md` is the sketch for stages A to D.
`docs/kernel1_target_outline.md` is the hand-written target.

## 1. What the archive says

Rebuilt from the log timestamps (`python report.py --from-logs`, saved as
`docs/baseline_kernel1_run_stats.json`), and it matches your numbers:

| stage | calls | minutes | thinking KB |
|---|---|---|---|
| step 2 shape split | 1 | 25 | 30 |
| phase 3 | 10 | 189 | 227 |
| 3.5 + 3.5v | 2 | 176 | 164 |
| 3.6 + 3.7 | 2 | 59 | 58 |
| 3.75 + 3.75v | 2 | 53 | 57 |
| 4a + 4c (the story lines) | 2 | 104 | 87 |
| 4b node builds | 14 | 1097 | 971 |
| 4d reviews | 2 | 200 | 165 |
| total | 35 | 1903 (31.7 h) | 1759 |

Two things I took from the traces that drive everything else.

**Output speed is constant, so trace size is the time.** Every call lands
between 14 and 23 bytes per second of thinking plus response; the long ones
sit at 16 to 17. Thirty kilobytes of thinking is thirty minutes. There is no
other cost to manage.

**The trace has four parts, and none of them is "reasoning style".** In every
trace I read: (a) a compressed restatement of every input ("Need answer...
Brief fields: 3-0a ... constraint ..."); (b) a long back-and-forth wherever a
rule has an unclear edge; (c) the whole output drafted in prose, field by
field, usually twice; (d) a tail of "Potential issue: ... Good." lines, one
per rule per field. The 4b trace I counted has 34 of those tail lines; the 3.5
trace mentions `provenance` 54 times. The step-2 trace is the cleanest case of
(b): 29 KB spent on whether "6 or 7" is `several` or `many`, and on what the
`stated` field should contain, including the model asking itself "which would
an evaluator expect?".

So, roughly: trace = inputs + ambiguous rules + 2 x output + rules x fields.
Each term is something code or schema design can cut. The discipline blocks
address none of them, which is why they did nothing.

## 2. Traces as an engineering problem: what I built

**Call classes with budgets** (`generator/stats.py`). Every call belongs to
one of four classes. The class decides whether the call thinks, what it
should cost, and where it is cut off.

| class | which calls | thinking | target | hard limit | when the limit trips |
|---|---|---|---|---|---|
| extract | phase 3, rating filter | on | 30 KB / 30 min | none | reported only |
| classify | s2 shape, 3.5c, 3.5v, 3.8 | off | 6 min | 45 min | the run stops, naming the partial trace |
| judge | 4d | on | 12 KB / 12 min | 24 KB / 25 min | re-run once with thinking off |
| build | 3.5a, 3.5b, 3.5r, 4a, 4b, 4c | on | 25 KB / 25 min | 40 KB / 45 min | re-run once with thinking off |

Why these numbers. You suggested nothing over about 30 KB or 25 minutes. At
17 bytes per second those are nearly the same line (25 minutes is 25 KB of
total output), so I set the build *target* at 25 KB / 25 minutes and the
*breaker* at 40 KB / 45 minutes. The gap is deliberate: a call at 32 KB is
over target and gets flagged in the report, but killing it would throw away
thirty minutes to save ten. The breaker is for the 90 to 124 KB runaways,
which it now ends at 40. The judge class is tighter because its input is a
digest and its output is under 1 KB; if it needs more than 12 KB of thought,
something is wrong with what it was given. Phase 3 has a target and no
breaker: three of its calls are over 30 KB on kernel1 (3b 42, 3c 37, 3h 36),
but a breaker's fallback is a no-think re-run, and that would weaken phase 3
silently. Those three are reported; I did not touch them.

**What you asked me to evaluate, and what I did with each.**

- *think=false for classification and transcription, with a rationale field
  first.* Adopted for four calls. The shape split, the cast sketch, the
  premise audit and the framework choice run with thinking off and a short
  free-text field first in the schema (`reading`, `notes`, a per-item `note`
  before each verdict). The audit is the one I am least sure of; section 9
  says how to compare it both ways (`--think-steps=s3_5v`). I did **not**
  turn thinking off for the construction calls. I have no evidence either
  way on whether this model plans a story line better with a hidden trace or
  with a visible plan field, and the breaker's fallback already exercises the
  no-think path, so the report will show you what a no-think 4a looks like
  the first time one trips. `--no-think-steps=s4a,s4b` tries it deliberately.
- *Structured outputs.* Every new prompt has a JSON schema
  (`generator/schemas.py`): enums for tiers and forms, nullable fields, and a
  fixed key order, which is what makes rationale-first work. The client sends
  the schema on thinking-off calls by default. Whether your server (0.32.13)
  handles a schema *together with* thinking I could not check: there is no
  server here, and I will not guess at a version I cannot run.
  `python probe_ollama.py` answers it in a couple of minutes (check 5) and
  tells you whether to set `structured="always"`. If a server rejects a
  schema outright, the client drops it for the rest of the run instead of
  failing.
- *num_predict and wall-clock breakers.* Both, plus a thinking-byte limit and
  a response-byte limit, enforced by the client as chunks arrive; it closes
  the connection, which stops generation. `done_reason: "length"` is treated
  as a cut. A cut call keeps its partial trace on disk
  (`..._raw_output_thinking_cut_<time>.txt`), and so does a call that dies in
  transport. About the two 4d crashes: I cannot tell from here whether they
  were context exhaustion or the client's own `max_duration` raise, because
  the old client discarded the partial trace and the server's stop reason.
  It now records both, so next time the stats say which.
- *Sampler.* We were sending nothing, so the model ran on whatever its
  Modelfile sets, or Ollama's defaults if it sets nothing (temperature 0.8,
  top_k 40, top_p 0.9, repeat_penalty 1.1). The pipeline now sends Qwen's
  published thinking-mode values on thinking calls (temperature 0.6, top_p
  0.95, top_k 20) and its non-thinking values on the others (0.7, 0.8, 20),
  with `repeat_penalty` 1.0 because 1.1 penalizes the quotes and braces JSON
  is made of. No presence penalty by default; `STRATUM_PRESENCE_PENALTY=1.0`
  if a trace loops. Caveats: those values are the ones Qwen published for
  the Qwen3 family, and I cannot see a model card for the build you are
  running, so check them against it. This also changes what phase 3 is
  sampled with. Anything you set in `dynamic_config.py` wins, and
  `STRATUM_SAMPLER=model` sends nothing.
- *Run statistics.* `<id>_run_stats.json`, one record per call attempt:
  prefix, class, mode, prompt characters, thinking bytes, response bytes,
  seconds, accepted or rejected, breaker, token counts. `report.py` totals by
  stage, flags what is over target, and compares against the baseline.

**Structural cuts, by term of the trace.**

- *Inputs.* The brief goes in as one line per field (2.4 KB against 4.3 KB of
  JSON, and already in the form the model rewrote it into). The outline
  prompts get the premise without its bookkeeping tags, and a digest of one
  line per node instead of the story. Rendered prompt sizes on the stub run:
  4a 12 KB, 4b 11 KB, 4c 16 KB, 4d 7 to 8 KB.
- *Ambiguous rules.* The ending tier is a lookup when a number is stated.
  The audit no longer decides what a clause is, which fields bind, or how
  severe a finding is. A `serves` tag is checked by prefix match in Python.
- *Output.* 3.5's 13 KB output is now three outputs of about 2.5, 3 and 1.5
  KB. `provenance`, `withheld`, the self-reported `fidelity_check` and the
  budget echo are gone. A line plan is about 2 KB; a node is about 450 bytes.
- *Rules x fields.* 4a had eleven fields per node and rules about exits,
  failure exits, craft notes and open hooks. It now has four fields per
  entry. The rules about structure moved into validators.

**One more thing that may matter more than all of it.** Your model tag ends
in `-128k`. If that is `num_ctx 131072`, the server reserves a 128k context
cache next to a 27B model on a 16 GB card, and the layers that no longer fit
run on the CPU. The largest prompt in this pipeline is about 13k tokens and
the largest allowed output about 14k. `python probe_ollama.py --ctx-test
32768` times the same call at both sizes. I do not know your Modelfile, so
this is a thing to measure, not a finding; but 4 to 5 tokens per second is
slow enough that it is the first thing I would check.

## 3. What changed

Pipeline, before and after:

```
before: s2 > phase 3 > 3.5 + 3.5v/r > 3.75 + 3.75v/r > 3.6 cast > 3.7 world
        > [4a/4c line > 4b build every node > checks > 4d review > 4b repairs > 4d re-review] x lines

after:  s2 > phase 3 > 3.5a engine, 3.5b turns, 3.5c cast sketch + 3.5v/r > 3.8 story form
        > [4a/4c line plan > 4b fill nodes at summary level > computed checks > 4d next-line judge] x lines
        ...then, not built: A beat expansion > B character/setting depth > C reconciliation > D node build
```

Prompts. New: `s3_5a_engine`, `s3_5b_turns`, `s3_5c_cast`,
`s3_5v_premise_check`, `s3_8_story_form`, `s4b_line_nodes`, `s4d_next_line`.
Rewritten: `s2_shape_split`, `s3_5r_premise_repair`, `s4a_main_line`,
`s4c_divergence`. Removed (their content lives on in the split prompts):
`s3_5_premise_expansion`, `s3_5v_fidelity_check`. Parked in `prompts/later/`
with a README: the craft spine and its pair (stage A), cast and world (stage
B), node build and review (stage D). Phase 3 is untouched.

Code. New: `outline.py` (the loop), `checks.py` (computed views and checks,
pure functions of the story document), `frameworks.py` +
`config/frameworks.json`, `stats.py`, `schemas.py`, `report.py`,
`probe_ollama.py`, `tests/test_plumbing.py`. Rewritten: `main.py`,
`ollama_client.py`, `stub_client.py`. Parked in `generator/later/`:
`node_build.py` (the old `step4.py`, whole, with a header listing what stage
D lifts from it: the node validator, the state registry, the mechanical
checks), `cast_world_craft.py`, and the old stub handlers.

Output. `<id>_story.json` and `<id>_story.md`: lines, nodes, edges with
plain-language triggers, the two registers, the lines x beats grid, ways no
line has taken, and the computed checks. `<id>_pipeline.json` stamps the
schema version (4); an older directory stops the run and prints the `rm`
command, and tells you its phase-3 outputs can stay.

## 4. Your direction: what I took, and where I differ

Taken as asked: the loop works at outline level; a framework is chosen
first; a node is a beat with a short summary, a where and a who; lines are
still found one per iteration by motivation or strategy; branch points carry
a plain sentence about what the player did; characters and locations are
rough registers; the product is a graph; checking is computed; one small
model call per iteration decides whether to go on.

Where I went a different way, and why.

1. **The framework is chosen from a computed shortlist, not from the full
   list.** Asked to pick a story structure, this model will pick three-act
   and write a paragraph defending it. Most of the fit is a lookup over the
   brief anyway (an escalating affect over hours with a depleting stock is a
   Fichtean curve; a looping timeline is a story circle; a Kernel that says
   "5-act tragedy" has named its form). So Python scores all eight, offers
   the best three with the reasons, and offers only the modifiers the brief
   licenses, so that choosing "countdown" cannot invent a clock the
   extraction did not find. Three-act carries a fixed fallback score and
   shows up only when little else fits. The model still makes the call, with
   the premise in view, and `--framework` lets you make it instead. The
   scoring rules are my heuristics, written as data; expect to tune them.

2. **Your steps 2 and 3 are two calls, and step 3 runs over a few beats at
   a time, not one.** "List the beats adapted to this story" is the line
   *plan* (4a/4c: one or two sentences per beat, plus which premise turn
   lands in it). "Fill each beat" is 4b: summary, where, who, registers, at
   most four nodes per call, so a seven-node main line is two calls. I
   considered one call per beat and rejected it: seven calls each re-reading
   the setting and the registers cost more in total, and a per-beat call
   cannot see the beat after it. Splitting plan from fill is what keeps each
   call under target, and the plan's one-liners double as the digest every
   later call reads.

3. **The framework's beats do not replace 3.5's turns.** Beats are slots
   with jobs; turns are this story's situations. The plan's work is placing
   each turn in the beat whose job it does and saying what the remaining
   beats are here. That is also the guard against generic output you asked
   for: a beat with a turn in it is specific by construction, and the rule
   for the others is that a sentence which could be pasted into another
   story is the beat's job repeated, not an adapted beat.

4. **`ways_through` stays.** You asked whether the ways and costs are the
   beginning of the "how". I think they are the story's forks, which is
   outline material: turn 2's second way ("take the overseer's trade") *is*
   the branch T2 grew from. What was how-level was their wording, so the
   turn prompt now asks for what is brought about and what it costs, one
   clause each. Keeping them buys something concrete: each line records
   which way it takes through each turn, so "ways no line has taken" is a
   computed table, and that table is what the next-line judge reads.

5. **No open exits in the graph.** 4a planted `leads_to: null` exits as
   hooks and 4d flagged them every time. Instead of teaching a reviewer to
   leave them alone, the graph is always complete and the hooks are the
   computed table from point 4. A deliberate gap in an artifact that a
   checker reads will keep being "fixed".

6. **There is no review call at all, and validators do the repair.** You
   asked for mostly computed checks. I went further: every structural rule
   (beat order, coverage, each turn once and in order, a valid place to
   leave from, a rejoin that lies ahead, a crowd with a voice) is the
   validator of the call that could break it. A bad answer is rejected and
   re-asked once with the list of problems and its own previous answer.
   That is "repair receives the violation list" at the smallest grain, and
   it costs a call only when something is wrong. `check_story` then runs
   over the whole document; its findings should be impossible and its notes
   are for you and for stage C. What I gave up: nothing now judges whether a
   line is *good*. The judge decides whether the next one is worth building,
   not whether the last one was.

7. **3.75 moves behind the loop instead of being made cheaper in place.**
   You asked for 3.75v to be cheaper and said not to delete the repair
   loops. The craft spine's `escalation_shape` duplicated what a framework
   is; its want/need tension is now carried per line by the through-line's
   motivation (each line has its own, which is the point of branching by
   motivation); and its irony device, setup/payoff pair and motif are about
   how beats play, which is your stage A. So it is parked as the first call
   of stage A, with its loop, and `later_stages.md` says how its check gets
   cheap (two of its four checks are lookups). The loop machinery is not
   deleted, and 3.5 uses a better version of it. But be clear on the effect:
   the default pipeline no longer runs a craft pass. If T1's motivation
   comes out flat on the first live run, this is the decision to revisit.

8. **Thinking stays on for construction** (section 2).

9. **One evolving document, yes; but files per call stay.** `story.json` is
   the document every later stage annotates, and it has the slots for them.
   The per-call files remain the resume mechanism, because replaying saved
   calls is what makes a 6-hour run restartable.

10. **Phase 3 is now half the run, and I left it alone as instructed.** At
    189 minutes it is the largest block of a projected 6.6 hours. The three
    over-target calls (3b, 3c, 3h) are where to look next, and the lessons
    doc already knows why two of them run long (rules with no stated
    precedence). That is a pass of its own, with its own kernels.

## 5. Your specific questions

**3.6 and 3.7.** Both move to stage B. The character register starts from a
new small call, `s3_5c_cast` (thinking off): one sketch per role the turns
name, with kind, speaks_for, wants, holds, and whether the opposition acts
through them. That is all a line plan needs, and it keeps the rule that a
crowd has a representative, validated in code. The location register starts
empty; the fill call adds a place when a node needs one (name, kind, one line
of why). Names, voice, stance, topics, fixtures, connections and
`protagonist_can` are stage B, written once the outline says where each
person and place is used. Characters are role labels until then; the
outline reads fine with "the life-support overseer".

**Whether registering is its own step.** It is part of the fill call. The
model writes names; ids are assigned in code. Two names are the same entry
only when they match after case, punctuation and a leading article are
dropped; a reference from a node may also be a shortened form of exactly one
registered name, which is resolved and reported. A place used but never
declared is registered bare and reported instead of costing a retry.

**The lines x beats grid.** Yes. It is the coverage check (every required
beat on every line, or skipped with a reason; a line that ends early says
which beats it drops) and it is the most readable summary of the branching,
so it is a table in `story.md`.

**Can 3.5v be cheaper without losing what it catches.** The old call took 61
minutes to find nothing. Half of what it checked is a count or a lookup and
is now Python (turn count, repeated forms, ways without costs, bad `serves`
tags, complications over budget, crowds without a voice). The rest is a
fixed list answered item by item with thinking off: the Kernel is pre-split
into numbered clauses, the constraint fields are pre-listed, the engine
checks are enumerated per turn. Projected cost: about five minutes. What it
should still catch: a hard negative broken by genre (kernel28), an invented
score or losing condition, a pole restated as its own action, a turn that is
the axis as a two-way pick. What I removed: the soft/hard distinction (any
failed item is a finding), the "flagged but permitted" reports, and the
audit of the builder's self-report, since the builder no longer writes one.
Repair returns only the sections it changed and code does the merge.

**Calibration examples.** This took two passes, and the second one changed
my mind about an example I had inherited.

The four step-4 prompts share one invented story: the stage manager of a
touring theatre company whose leading actress walks out two nights before
opening, laid over a three-act framework. The story-form prompt has three
small cases chosen so that none has the shape of a common test kernel (no
one-night escalating crisis, no quiet no-stakes story, no loop, no named
form).

My first draft of the step-4 prompts reused 3.5's Example A, the water agent
in a dry valley. An independent review of every new prompt (section 8a) caught
what I had not: that example is a gatekeeper deciding who is cut off from a
scarce, life-critical stock, which is kernel1's judgment shape with different
nouns, and my illustration branched at the same turn, by the same way, into
the same number of nodes as the kernel1 target outline. A kernel1 run would
have "matched the target" by copying the example. Hence the theatre company,
which rations nothing and branches somewhere else.

The same review, and my own reading, found inherited examples that were test
kernels:

- step 2: one example was kernel2 almost word for word (a 5-act tragedy that
  ends badly whatever the player does), another was kernel17's shape (linear,
  with endings that vary), and the rule text quoted kernel1's and kernel17's
  own phrases as worked answers. All replaced.
- 3.5v: its first example was kernel28 verbatim; its engine example, and
  3.5r's, was kernel1's vent/spare. Replaced.
- 3.5 Example B (the string quartet) had kernel2's shape: a fixed outcome,
  with the player deciding only who is left. The outcome is no longer fixed.
- 3.75's Example A is kernel1. Flagged in `prompts/later/README.md`, since
  that prompt is parked.

**One thing I left alone and want you to decide.** 3.5 still uses the water
agent as its Example A (repaired: its question now restates the decision
axis instead of the theme, its turns are tasks instead of either/ors, the
opposition acts with its stated means). I kept it because it is the only
construction example that has met the model, and you said the kernel1 engine
it produced was a real improvement. But there are signs that engine leaned on
it: the archived kernel1 premise uses the example's signature word "draw"
seven times, and its third turn (put every deck's draw on a public display
before the council) parallels the example's third turn (put the mill's draw
on the record at a hearing). That is suggestive, not proof. If the 3.5 turns
for other kernels keep coming out as "discover a hidden allocation, then
publish the figures", replace Example A with a premise that is not about a
shared resource, and re-run kernel1 to see what the engine looks like without
the crib.

The test script fails if a live prompt mentions kernel1. Nothing automated
checks judgment shape; that still takes a reader with the kernel list open.

**The kernel1 target.** `docs/kernel1_target_outline.md`: T1 in six nodes, T2
in three, at 45 to 75 words a node, with the registers, the grid, one node
and one edge as JSON, and a note on what a good third seed and a reskin look
like. It uses the Fichtean curve, which is what the shortlist puts first for
kernel1's brief.

**Stale docs and the schema stamp.** CLAUDE.md, README and the design docs
are rewritten; `step4_design.md` and `strategy.txt` carry superseded headers
saying what in them is still the specification of stage D. CLAUDE.md also
listed `config/current_axes.json` and `src/common/features.py`, which do not
exist in the repository; those lines are gone.

**The test script.** `python tests/test_plumbing.py`. No framework. It runs
the pipeline on the stub under every scenario (repair loop, halt, rejected
answers, sloppy answers, a tripped breaker, a rejoining line, new cast, a
seed that does not hold, the linear shape, overrides, stale directories),
asserts the graph invariants on each result, drives the loop's validators
directly with answers that must be rejected, mutates a good story eighteen
ways to prove the checks catch each break, runs the Ollama client against a
fake server (streaming, both thinking formats, every breaker, schema and
think-parameter rejection), and fails if any prompt is exercised by no
scenario. The stub needs no `dynamic_config.py` now.

## 6. Stages A to D

`docs/later_stages.md`. In brief: A is the old craft spine plus a per-node
expansion (ordered events, what changes for each character present, and for
each outgoing trigger what the player can do here that the trigger sentence
describes). B is the old 3.6 and 3.7 run per entity on a packet, each
producing a long form and a 150-word packet. C is mostly computed, extending
`checks.py`, with one no-think pass per line over packets. D is the old 4b,
with one large difference: it no longer invents exits. Every edge already
exists with a sentence on it, and D's job is to turn that sentence into a
condition. The hooks are in the schema now (`annotations`, `additions`,
`trigger.formal`, the null `profile`/`packet`/`rooms` fields, `stage`).

I did not write prompts for A to D. The loop's prompts have not met the model
yet, and the outline's schema is the input contract for all four stages;
writing four more layers of unvalidated prompts on top of an unvalidated one
would be the 3.6/3.7 mistake again, one level up.

## 7. Projected cost

Estimates from the trace model in section 1 at 17 bytes per second. They are
what the targets assume, not measurements.

| call | thinks | output | projected trace | projected minutes | was |
|---|---|---|---|---|---|
| s2 shape split | no | 0.9 KB | 0 | 1 to 2 | 25 |
| phase 3 (10 calls) | yes | unchanged | unchanged | 189 | 189 |
| 3.5a engine | yes | 2.5 KB | 15 to 25 KB | 15 to 25 | 3.5: 114 |
| 3.5b turns | yes | 3 KB | 18 to 28 KB | 20 to 30 | |
| 3.5c cast sketch | no | 1.5 KB | 0 | 2 | 3.6: 23 |
| 3.5v audit | no | 4.5 KB | 0 | 4 to 6 | 61 |
| 3.8 story form | no | 0.6 KB | 0 | 1 | - |
| 4a main line plan | yes | 2 KB | 10 to 18 KB | 10 to 18 | 55 |
| 4b fill, main line (2 calls) | yes | 2 KB each | 9 to 14 KB each | 20 to 30 together | 4b builds: 600 |
| 4d judge | yes | 0.7 KB | 5 to 10 KB | 5 to 10 | 4d review: 84 to 117 |
| 4c divergence plan | yes | 2.5 KB | 12 to 20 KB | 14 to 22 | 49 |
| 4b fill, later line | yes | 1.5 KB | 8 to 12 KB | 9 to 13 | |

Before any outline: about 4.1 hours, of which phase 3 is 3.2 (was 8.4). The
main line: about 40 minutes. Each further line: about 40 minutes. A
four-line outline: about 2.5 hours of loop, about 6.6 hours end to end,
against 31.7 hours for one line and part of a second.

The calls most likely to miss: 3.5b (the largest construction output left)
and 4c (the most fields). Both have the breaker behind them, and both can be
split further if they miss: 3.5b into turns then complications, 4c into the
divergence itself and then its beats. 4b is already capped at four nodes a
call (`FILL_CHUNK` in `outline.py`).

## 8. Other changes I made without being asked

- A rejected answer is re-asked with the reason and its previous answer. The
  old retry was a blind re-roll at full price.
- The exact prompt sent is saved beside every trace
  (`<prefix>_raw_input_prompt.txt`).
- Partial traces survive a cut or a crash.
- If the server refuses `think: false` for this model (a model it does not
  recognize as a thinking model), the client falls back to Qwen's `/no_think`
  prompt suffix for the rest of the run instead of failing.
- `STRATUM_CLIENT=stub` is handled in `main.py`, so the stub works with your
  `dynamic_config.py` as it is, or with none.
- The client instance is reused across calls; the run ends with a summary of
  what this session cost and which calls went over.
- Under a linear shape (kernel17) a new line may leave only at the last node
  before the ending, on a trigger that is the pattern of earlier play, and
  adds one node. "One road, a dozen endings" is now visible in the graph
  rather than hidden in state variants.
- A branch records both sides: the trigger, and what the existing line does
  instead. Stage D gets a sentence for the default exit too.
- A divergence can say what the shared node must now contain for its trigger
  to be possible (an offer, a discovery). It is stored on that node for stage
  A instead of forcing a rebuild.
- `generator/dynamic_config.py` and the test story directories are
  gitignored.

Not done, and worth doing: resampling for genericness (run the same kernel's
3.5b three times and compare the turns; cheap now that it is a 25-minute
call); a judgment-shape check of examples against the kernel list, which
nothing automates; the three over-target phase-3 calls.

## 8a. Two independent reviews, and what they changed

Before writing this response I had two fresh readers go through the work
without my conclusions in front of them: one checked every new prompt's
examples against that prompt's own rules, against the code, and against the
30 kernels; the other hunted for bugs in the loop, the checks and the client,
and ran experiments against a copy. Both found real problems. All of the
following are fixed, and each code fix has a regression test.

Prompts:

- the kernel-shaped examples described in section 5;
- 3.5b's examples modelled the two-button turn the redesign exists to
  prevent: six of seven tasks were phrased "X or Y", and one turn would have
  failed 3.5v's own check. Rewritten as tasks with ways that each require an
  act;
- 3.5r's example repair introduced a character with no cast seed (which the
  next round's computed check would have flagged) and its output was not
  valid JSON. Replaced with a complete one-section repair;
- three rules with no stated precedence (a default failure model against "no
  new way to lose"; a turn's best beat against the turns' order; who is
  present in a node against "nobody as furniture"). Each now says which wins;
- `skipped_beats` meant three different things in three places. The main line
  no longer has the field, and a divergent line lists required beats only;
- freytag's beat id `turning_point` collided with the through-line's field of
  the same name. It is `reversal` now.

Code:

- name matching was too generous: it would have merged a declared "Sector B"
  into "Sector A", and "the widow's son" into "the widow", silently. For
  kernel1 that means the ship's sectors collapsing into one location. Names
  now match only after case, punctuation and a leading article are dropped;
- a mediation pole written as a string passed the 3.5a validator and crashed
  step 4 an hour later, on every rerun. Rejected at 3.5a now;
- the validators and the computed checks normalized "who speaks for a crowd"
  differently, so a valid answer could produce a broken-invariant finding;
- a line rejoining another divergent line could pass a node twice or play its
  turns out of order. The validator now checks the whole path;
- "more than one ending" was read as one ending, which would have stopped the
  loop after the main line;
- a stream that ended without the server's closing message was accepted as a
  complete answer. It is a transport failure now, with the fragment kept;
- the client's default overall timeout (30 minutes) would have cut phase-3
  calls and made the 45-minute class limits unreachable for anyone not
  setting it. The default is 4 hours, and a cut with nothing to fall back to
  stops the run once instead of repeating the same call;
- several smaller ones (a framework id with trailing whitespace, a turn id
  written as 2.0, verdicts written as the string "false", an empty rating
  filter answer, inline `<think>` edge cases on old servers).

Not fixed: the reviewer noted that 3.5's Example A is itself resource
rationing (section 5 explains why it stays for now).

## 9. First live run: what to check, in order

Each step names the file to read and what would make me change course.

0. **`python tests/test_plumbing.py`**, then **`cd generator && python
   probe_ollama.py --ctx-test 32768`**. The probe tells you: whether
   `think: false` is honored (if not, the four classify calls will think,
   and the report will say so); whether schemas work with thinking on (set
   `structured="always"` if so); whether closing the connection stops
   generation (the breakers depend on it); and whether a 32k window is
   faster than what the model tag sets. Fix the client config before
   anything else.

1. **`python main.py --story-id=kernel1 --stop-after=2 < ../tests/kernels/kernel1.txt`.**
   One call, a minute or two. Read `kernel1_s2_shape.json`: the content
   kernel must be the Kernel minus the branching sentence, verbatim, and the
   tier `several`. This is the cheapest test of the whole no-think,
   rationale-first, schema path. If the content kernel is paraphrased,
   thinking-off transcription is not safe on this model and the shape split
   goes back to `--think-steps=s2_shape`.

2. **Phase 3** (`--stop-after=3`). You can reuse the old run's phase-3 files:
   copy the `s1`, `s2`, `s3_0a` to `s3h` files and `s3_brief.json` from the
   archive into `stories/kernel1/` and the run adopts them. Do that the
   first time, so everything downstream is compared on the same brief. Later,
   run it fresh once to see what the new sampler settings do to 3b, 3c and
   3h; if they get longer, set `STRATUM_SAMPLER=model` for phase 3.

3. **The premise** (`--stop-after=3.5`). About an hour. Read, in this order:
   - `python report.py kernel1`: 3.5a and 3.5b against 25 KB. If either
     tripped the breaker, read its `_cut1` trace before anything else.
   - `kernel1_s3_5_premise.json` beside the archive's
     `s3_5_premise_expansion.json`. The engine should be as good as the old
     one: an opposition with its own want, turns of different forms, crowds
     with a voice. If splitting the call cost quality (turns that do not use
     the levers, an opposition that never acts), that shows here.
   - `kernel1_s3_5v_premise_check.json`: every clause, constraint and engine
     check has an entry with a sensible one-line note. Then run
     `--think-steps=s3_5v` into a second story id and compare verdicts. If
     the thinking version finds something the no-think version missed, the
     audit goes back to thinking and to the `judge` class.
   - Run kernel28 and kernel29 to 3.5 as well. They are the kernels the
     audit exists for. A clean verdict on a premise with a corpse in it means
     the cheap audit lost what the expensive one caught.

4. **The story form** (`--stop-after=3.8`). A minute. `s3_8_framework.json`
   shows the shortlist, the scores and the pick. For kernel1 I expect
   `fichtean_curve`. If it picks `three_act` from a list where another
   candidate has five reasons, the prompt's tie-break is not biting; if the
   shortlist itself looks wrong, the scoring rules in `frameworks.py` are
   mine and easy to change. Run 3.8 on kernel2 (named form), kernel4 (loop),
   kernel6 (quiet) and kernel17 to see four different shortlists.

5. **The main line** (`--max-iterations=1`). About 40 minutes. Read:
   - `kernel1_story.md` beside `docs/kernel1_target_outline.md`. Same grain?
     Nodes that name fixtures, list actions, or state conditions mean 4b is
     writing scenes.
   - the 4a trace. Where did it spend its bytes? If on placing turns in
     beats, the rule needs a tie-break. If on node count, fix the range.
   - the 4a through-line. This is the test of moving 3.75: the old T1 had a
     motivation that changed (from keeping the core alive to making the cost
     visible), and that came from the craft spine's want/need. If the new
     one has no turn in it, add a want/need line to the story-form call
     before anything else.
   - `checks.notes` in the story document: is the opposition in at least two
     nodes; did 4b register four to eight places or fifteen.

6. **A second and third line** (default `--max-iterations=4`, or 3). Read:
   - `s4d_i1_next_line.json`: is the seed a different story or a reskin? It
     should name a different answer to the question, not a different sector.
     Compare with the last section of the target outline.
   - `s4c_i2_divergence.json`: does `shift` explain why the motivation
     changes, and is `trigger` something done, in past tense? Was the first
     answer rejected (two attempts in the report)? The validator's message
     is in the retry prompt; if the same rule fails on several kernels, the
     prompt is not stating it clearly.
   - when the judge says stop, and why. If it never stops before the cap,
     the not-worth-building list needs to be harder.

7. **kernel17 through the loop.** The linear shape has never run: one road,
   each further line a single ending on an accumulated trigger. Check that
   the endings differ in kind, not in the last sentence.

8. **Then, and only then, more kernels.** kernel2 (tragedy, fixed ending),
   kernel6 (no failure, kishotenketsu or episodic), kernel9 (generous
   budget), kernel15 (alone: an empty cast must not break the cast step).

At every step, `python report.py <id> --baseline
../docs/baseline_kernel1_run_stats.json` is the first thing to look at, and
the trace of the call that went over is the second.

## 10. What I could not do

- Run anything against a model. Every prompt after phase 3 is untested on
  one, and so are the client's parameters against a real server (they are
  tested against a fake one).
- Verify claims about your specific model build and server version. Where I
  recommend a setting I say what it rests on, and the probe checks the
  server's behavior directly.
- Build stages A to D (section 6).

The old `stories/kernel1/` in the working tree (three failed 3-0a attempts
and no outputs) is untouched and will be adopted as a fresh directory.
Nothing is committed; the changes are in the working tree.
