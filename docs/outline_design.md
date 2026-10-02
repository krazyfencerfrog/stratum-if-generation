# Pipeline design: the premise, the story form, and the outline loop

This is the live description of what `generator/main.py`,
`generator/outline.py` and their helpers do after phase 3, plus the changes to
step 2 and to how every model call is run. It supersedes
`docs/step4_design.md` (kept as a historical record of the node build that is
now stage-D material). `docs/fable_response_4.md` gives the reasons;
`docs/later_stages.md` sketches what comes after;
`docs/step3_consolidated_design_lessons.md` holds the rules every prompt
follows.

## 1. Shape of the pipeline

```
s1  kernel (as written)
s2  rating filter (if --rating)  ->  shape split: content kernel + shape prefs     [no think]
phase 3   nine blind extractions over the content kernel, 3h cross-check           [unchanged]
          constraint map + STORY BRIEF (computed)
s3.5  premise: the dramatic engine
        3.5a engine   protagonist, arena, pressure, opposition, mediation          [think]
        3.5b turns    3-5 situations, each with ways through and a form            [think]
        3.5c cast     a rough sketch per role the turns name                       [no think]
        computed checks + 3.5v audit                                               [no think]
        3.5r repair (only if findings; returns only the changed sections)          [think]
s3.8  story form: a framework chosen from a computed shortlist                     [no think]
step 4, the outline loop, one line per iteration:
        4a main line plan (iteration 1)  |  4c divergence plan (iteration n)       [think]
        4b line nodes: summary, where, who; registers grow as needed; <=4 per call [think]
        computed checks (graph, beats, turns, branches, registers)
        4d next line: is another line worth building, and its seed                 [think, small]
story document: <id>_story.json, <id>_story.md (rewritten every iteration)
run statistics: <id>_run_stats.json (appended every call attempt)
```

Standing rules, enforced in code:

1. **Generation and verification never share a prompt.** The premise is
   audited by a separate call; the outline is checked by Python.
2. **Repair is a separate call that receives the violation list.** 3.5r gets
   the findings; a rejected answer anywhere is re-asked with the validator's
   complaint and its own previous answer.
3. **Counts, lookups and structural checks are computed, not asked.**
4. **A prompt receives the brief or a packet, never the bundle.**
5. **The question is not the verb.** A story decision is something the
   player did; a branch carries a sentence about it, never a menu.
6. **Every call has a class, and the class is its budget** (section 7).

## 2. Step 2: the shape split

Unchanged in what it decides (content kernel; ending tier, linearity, choice
density, length). Changed in how it runs: thinking off, structured output, a
`reading` field first. The archived call spent 29 KB of reasoning on two
boundary questions (is "6 or 7" several or many; what goes in `stated`). Both
are gone: the prompt defines `stated` exactly, and when it holds a number the
tier is a lookup in `brief.ending_tier_from_stated` (the smallest number
stated, so a range never rounds the story up).

## 3. The brief, and its compact form

`brief.py` still computes `s3_brief.json`. Prompts after 3h now receive it as
`brief_lines()`: one line per field, `field id [binding]: value`, about 2.4 KB
for kernel1 against 4.3 KB of JSON. Every archived trace began by rewriting
the brief into that form; it is now given in it. The two shape-level fields
(`3g.target_ending_count`, `3g.branching_density`) are left out of it and out
of the audit's constraint list: step 2 strips the Kernel's shape clauses
before phase 3 sees them, and shape reaches only the outline loop.
`brief_lite()` remains the cut the outline prompts get.

Two tables the premise audit used to work out for itself are computed:
`kernel_clauses()` (the Kernel cut at sentence ends, semicolons and dashes,
numbered) and `constraint_fields()` (the constraint-class fields, numbered).

## 4. The premise (3.5)

The engine is the same one the previous pass designed; it is built in three
calls in the order the old prompt asked the model to think in.

| call | builds | output |
|---|---|---|
| `s3_5a_engine` | protagonist (with `cannot_do`), arena, pressure, opposition, mediation | about 2.5 KB |
| `s3_5b_turns` | 3 to 5 turns (situation, task, `ways_through` with costs, `involves`, `form`), complications by budget | about 3 KB |
| `s3_5c_cast` | one sketch per role the turns name: kind, speaks_for, wants, holds, opposition | about 1.5 KB |

`assemble_premise` puts them side by side as `s3_5_premise.json` and looks up
each seed's `matters_to_turns` from the turns. Dropped from the old single
output: `provenance` on every item (the archived trace mentions it 54 times),
`withheld`, the self-reported `fidelity_check`, and the echo of the budget.
`serves` stays on every constructed item.

`ways_through` stays, at the level of *what is brought about and what it
costs*, one clause each. They are the story's forks: a line records which way
it takes through each turn, and the ways no line has taken are the computed
hook table the next-line judge reads.

**Verification** has two halves.

*Computed* (`premise_computed_findings`): `cannot_do` empty or equal to
`can_do`; fewer than 3 or more than 5 turns; an unknown or repeated form; a
turn with fewer than two ways or a way without a cost; a `serves` tag that
names no brief field (prefix match); complications over budget; a role a turn
involves with no seed; a crowd with nobody who speaks for it.

*Asked* (`s3_5v_premise_check`, thinking off, structured output): three fixed
lists and one search. One entry per numbered Kernel clause (`contradiction`),
per numbered constraint (`violated`), per engine check (`holds`: E1 the limit
is real, E2 the opposition has its own want, E3/E4 each pole takes an action
with a cost, T<n> turn n is not the axis handed over as a pick), plus any
mechanic the engine lacks. In each entry `note` precedes the verdict, so the
deliberation is one visible sentence per item. The verdict is computed from
the entries; there is no severity field to agonize over. Any failure is a
finding.

**Repair** (`s3_5r<n>_premise_repair`) receives the normalized finding list
and returns `{"repair_log", "revised"}` where `revised` holds only the
top-level sections it changed. `merge_premise` carries everything else over
untouched, so "do not touch what the findings do not name" is enforced by
construction. Up to `--max-repairs` rounds; a finding that survives raises
`PipelineHalt` (exit 2).

Files: `s3_5a_engine.json`, `s3_5b_turns.json`, `s3_5c_cast.json`,
`s3_5_premise.json`, `s3_5v[_r<n>]_premise_check.json`,
`s3_5r<n>_premise_repair.json`, `s3_5_premise_accepted.json`,
`s3_5_loop.json`.

## 5. The story form (3.8)

`config/frameworks.json` is the library: eight frameworks, each condensed to
four to eight beats. A beat has an id, a name, a job, and `required`.

| id | beats |
|---|---|
| `three_act` (fallback) | setup, inciting_incident, commitment, midpoint, crisis, climax, resolution |
| `freytag` | exposition, rising_action, reversal, falling_action, denouement |
| `heros_journey` | ordinary_world, call, threshold, trials, ordeal, reward, road_back*, return |
| `save_the_cat` | opening_image, catalyst, debate*, promise_of_premise, midpoint, closing_in, all_is_lost, finale |
| `fichtean_curve` | opening_crisis, second_crisis, third_crisis, climax, aftermath |
| `seven_point` | hook, plot_turn_1, pinch_1, midpoint, pinch_2, plot_turn_2*, resolution |
| `story_circle` | comfort, need, go, search, find, take, return*, change |
| `kishotenketsu` | ki, sho, ten, ketsu |

(* not required.) Modifiers: `in_medias_res`, `countdown`, `frame`,
`braided_timelines`, `loop`, `episodic`, `relay`, each one line of effect on
how beats are filled.

`frameworks.py` computes the choice down to a shortlist:

- `score_all`: rules over the brief (trajectory, failure model, timeline,
  setting footprint, epistemic gap, decision mechanism, transgression, tone)
  add or subtract points per framework, each with the reason. `three_act`
  has a fixed score of 2, so it is offered only when few others fit.
- `named_form`: a form the Kernel names ("5-act tragedy") is content and
  binds; it becomes the only candidate.
- `shortlist`: the best three, presented in an order shuffled by a hash of
  the story id so position carries no signal.
- `available_modifiers`: only those the brief licenses (a countdown needs a
  time or stock trigger; a loop needs a looping timeline). The step cannot
  invent a clock or a second viewpoint by choosing a modifier.

`s3_8_story_form` (thinking off, structured output, `reading` first) picks
one candidate and one modifier and says why. `--framework=<id>` makes the
choice instead: no call is made and no modifier is applied. The result, with the library's beats attached, is
`s3_8_framework.json`.

The framework scaffolds beats and nothing else. It does not set how many
lines or endings are built, and no prompt after 3.8 is asked about either.

## 6. Step 4: the outline loop

### 6.1 Units

A **beat** is a slot of the framework. A **node** is one beat filled on one
line: `beat`, `turn` (the premise turn it plays, or null), `way` (which of
that turn's ways this line takes, or null), `adapted` (the plan line),
`title`, `summary` (two or three sentences), `where` (location ids), `who`
(character ids). A **line** is a through-line: motivation, strategy, turning
point, ending, and a path of node ids. A node holds no fixtures,
interactions, state variables or exit conditions.

Characters and locations are **sketches** in two registers. The character
register starts from the premise's cast seeds; a line adds one only when no
registered character can do what a node needs. The location register starts
empty; lines add places as they need them (name, kind, why). The model
refers to both by name; ids (`C01`, `L01`) are assigned in code. Two names
are the same entry when they match after case, punctuation and a leading
article are dropped, and nothing looser is ever applied to a declaration
("Sector B" is never folded into "Sector A"). A reference from a node may
also be a shortened form of exactly one registered name ("the overseer" for
"the life-support overseer"); that is resolved and reported.

### 6.2 One iteration

1. **Plan.** Iteration 1 runs `s4a_main_line`: the through-line, the
   ending, and one entry per beat (`beat`, `turn`, `way`, `adapted`).
   Iteration n runs `s4c_divergence` on the previous judge's seed: the new
   through-line and how it differs in kind, where it leaves
   (`diverges_at`), the trigger in plain past-tense words, `instead_of` (the
   other side of the fork), `opportunity` (what the shared node must now
   contain, if anything), `shift` (why the motivation changes there), the
   new beat entries, and either its own ending or `rejoins_at`.
2. **Fill.** `s4b_line_nodes` fills the line's new nodes: title, summary,
   where, who, and any new register entries. At most four nodes per call
   (a seven-node line is filled in two calls, four then three); a later
   call sees the summaries and places the earlier one produced.
3. **Check.** `checks.check_story` over the whole document.
4. **Judge.** `s4d_next_line` reads a digest (one line per node), the
   computed hook table, and the counts, and answers: continue with this seed,
   or stop. It is skipped when the Kernel asked for one ending or the
   iteration cap is reached.

The loop stops when the judge says stop, when 4c finds the seed does not
hold (`nothing_worth_building`), or at `--max-iterations`.

Under a **linear** shape (kernel17) a new line may leave only at the last
node before the main ending, its trigger is `accumulated` (the pattern of
play across earlier nodes), and it adds exactly one node: an ending. One
road, many endings, and the graph says so.

### 6.3 What the validators enforce

Every structural rule is enforced at the call that could break it. A
violation rejects the answer and the call is re-asked once with the list.

*Plans (4a, 4c):* beats exist in the framework and follow its order; at
most two entries per beat; a turn exists, is played once per path, in order;
a `way` is one the turn has; the main line covers every required beat and
plays every turn; a divergent line covers each required beat or skips it
with a reason; a divergence leaves from a valid node, by a way no line
already takes there, adds one to five nodes, and continues from the
divergence node's beat; a rejoin target lies further on, and the whole path
through it passes no node twice and plays its turns once each, in order.

*Fill (4b):* one entry per node; title, summary and at least one place; who
resolves to the register or to a declared new character; a new crowd has a
representative. A place used but not declared is registered bare and
reported; a crowd present without its voice gets its representative added
and the fact is reported.

*Judge (4d):* a seed's `diverges_at` is a valid node.

### 6.4 Computed views and checks (`generator/checks.py`)

Pure functions of the story document.

- `derive_edges`: `continue`, `branch` (with `trigger {text, kind, formal:
  null}`) and `rejoin` edges, and on the edge a branch competes with, the
  branch's `instead_of` under `otherwise`.
- `derive_grid`: lines x beats, the node ids in each cell.
- `derive_hooks`: ways through a turn that no line has taken, per node.
- `derive_usage`: which nodes use each character and location.
- `check_story`: **findings** (broken invariants: a path that does not run
  from the start to an ending, beats out of order, a required beat uncovered
  without a reason, a turn twice or out of order, a branch without a trigger
  or off its parent line, an unresolved place or person, a crowd without a
  voice, a cycle, an orphan or unreachable node) and **notes** (unused
  characters and locations, a line outside the advisory node range, the
  opposition present in fewer than two nodes of a line, a turn played
  without the people it involves, a trigger phrased as a pick, a divergent
  line that ends before playing every turn).

Findings should be impossible given the validators; one appearing means a
bug or a hand-edited file, and it is printed. Notes are for a person and for
stage C.

### 6.5 Files

| call | file |
|---|---|
| main line plan | `s4a_i1_main_line.json` |
| divergence plan | `s4c_i<n>_divergence.json` |
| node fill | `s4b_i<n>_line_nodes.json`, then `s4b_i<n>_p2_line_nodes.json` ... for a line with more than four new nodes |
| next-line judge | `s4d_i<n>_next_line.json` |
| story document | `story.json`, `story.md` |

Every call also saves `<prefix>_raw_input_prompt.txt` (exactly what was
sent), `<prefix>_raw_output_thinking.txt` and `<prefix>_raw_output_response.txt`.
A call cut off by a breaker keeps its partial trace as
`<prefix>_raw_output_thinking_cut_<time>.txt`.

State is rebuilt by replaying the driver over the saved files; a rerun makes
no model call. Each directory carries `<id>_pipeline.json` with the schema
version (4). A directory stamped otherwise, or an unstamped one holding
outputs of the replaced steps, stops the run and prints what to delete; an
unstamped directory holding only phase-3 outputs is adopted.

### 6.6 The story document

```
schema_version, story_id, stage ("outline"), kernel, shape, premise, framework
lines{id: title, motivation, strategy, turning_point, differs_from, ending{title, summary, node},
          path[], new_nodes[], parent, divergence{diverges_at, trigger, trigger_kind, way,
          instead_of, opportunity, shift}, rejoins_at, skipped_beats[]}
nodes{id: line, iteration, beat, turn, way, adapted, title, summary, where[], who[],
          is_ending, lines[], additions[], annotations{}}
edges[{from, to, lines[], kind, trigger{text, kind, formal}, otherwise[]}]
characters{id: label, kind, speaks_for, wants, holds, opposition, why, source, nodes[],
          name, profile, packet}            (last three null until stage B)
locations{id: name, kind, why, source, nodes[], rooms, packet}   (last two null until stage B)
grid, hooks, checks{findings, notes}, iterations[], stop_reason, warnings[]
```

## 7. How every call is run

`generator/stats.py` defines four classes. A call's class decides whether it
thinks, what it should cost, and where it is cut off.

| class | calls | thinking | target | breaker | on a breach |
|---|---|---|---|---|---|
| `extract` | phase 3, rating filter | model default | 30 KB, 30 min | none | reported only |
| `classify` | s2 shape, 3.5c, 3.5v, 3.8 | off | 6 min | 45 min | stops the run, naming the partial trace |
| `judge` | 4d | on | 12 KB, 12 min | 24 KB, 25 min | retried with thinking off |
| `build` | 3.5a, 3.5b, 3.5r, 4a, 4b, 4c | on | 25 KB, 25 min | 40 KB, 45 min | retried with thinking off |

- **Breakers** are enforced by the client as the stream arrives
  (`max_thinking_bytes`, `max_response_bytes`, `max_seconds`); it closes the
  connection, which stops generation. `num_predict` is set as a backstop,
  and a `done_reason` of `length` is treated as a cut. `--no-breakers`
  disables them.
- **Sampler.** Thinking calls send temperature 0.6, top_p 0.95, top_k 20;
  thinking-off calls 0.7, 0.8, 20; both `repeat_penalty` 1.0. Options set on
  the client in `dynamic_config.py` win. `STRATUM_SAMPLER=model` sends
  nothing; `STRATUM_PRESENCE_PENALTY` adds a presence penalty.
- **Structured outputs.** Every new prompt has a JSON schema in
  `schemas.py`. The client sends it on thinking-off calls by default
  (`structured='no_think'`), on all calls with `structured='always'`. A
  schema the server rejects is dropped for the rest of the run.
- **Overrides.** `--no-think-steps` and `--think-steps` take a prefix
  (`s4a_i1`), a step (`s4a`) or step_name (`s2_shape`).
- **Retries.** A rejected answer is re-asked once with the complaint and the
  previous answer appended. A cut that has no fallback left (a call already
  running without thinking, or the client's own `max_duration`) stops the
  run instead of repeating the same call. A transport failure, including a
  stream that ends without the server's closing object, saves the partial
  trace and stops the run.

`<id>_run_stats.json` gets one record per attempt: prefix, class, mode,
prompt characters, thinking bytes, response bytes, seconds, accepted or not,
breaker, token counts when the client knows them. `report.py` totals by
stage, flags calls over target, and compares against a baseline;
`docs/baseline_kernel1_run_stats.json` is the archived run.

`probe_ollama.py` asks the real server what it supports (thinking field,
think:false, schemas with and without thinking, num_predict, whether closing
the connection stops generation, speed, optionally a smaller `num_ctx`).

## 8. Testing without a model

```
python tests/test_plumbing.py
```

Eighteen tests, about six seconds: every stub scenario (repair loop, halt,
informed retries, sloppy answers, breaker fallback and a cut with no
fallback, rejoin, new cast, nothing-worth-building, linear shape, overrides,
stale directories), the loop's validators driven directly with answers that
must be rejected, the computed checks against deliberately broken graphs,
the Ollama client against a fake server, the helpers, the probe and the
report. It also fails
if a prompt in `prompts/` is exercised by no scenario or mentions kernel1.

`STRATUM_CLIENT=stub` works without a `dynamic_config.py`. The stub's knobs
are listed at the top of `generator/stub_client.py`.

## 9. Not yet run against a live model

Everything after phase 3. `docs/fable_response_4.md` section 9 is the
checklist, in priority order.
