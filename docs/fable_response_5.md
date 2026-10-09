# Response to `fable_request_5.txt`

Date: 2026-10-04. Inputs read: the request; CLAUDE.md, `outline_design.md`
(§10 included), `fable_response_4.md`, the lessons doc, every prompt and
every file in `generator/`; the git log since the last pass; and all of
`docs/run_samples/2026-10-03/`: the nine outlines read start to finish, the
briefs, the accepted premises, the audit loops, the run stats, and the four
thinking traces.

Short version. I agree with your eight findings and with your reading of the
before/after pairs. I think the cause of what is left ("it reads like a
summary of an outline") is mostly upstream of the outline, in what the
premise is made of: the turns are errands between people at tables, nothing
in the world happens that the player did not set off, and the cast has edges
and ties but nothing in the premise ever asks them to break. The outline loop
then faithfully varies errands. So this pass puts most of its weight on the
premise and on how divergences are planned, and only a little on the node
format. The pipeline now reads the Kernel for what its audience expects
(3.4), gives the engine events that happen whatever the player does, gives
every companion a voice and a breaking point, names a set piece, plans every
divergence together against a computed test of "different worlds" and "an
early fork" (4p), writes one image per node, and measures all of it
(`evaluate.py`, `ab.py`). Everything new is behind a flag or has an old-mode
flag, and `python tests/test_plumbing.py` passes (30 tests).

**Nothing here has run against a live model.** Section 8 is the order to
find out what holds, and for each item what result would mean it failed.

## 1. What I saw in the samples

Your eight findings stand. Reading the nine outlines as a player, these are
the things underneath them that I think explain the residue you listed.

1. **The turns are logistics.** Every turn in every premise is "get across",
   "get it opened", "get the key", "bring it out", and every way through is
   a ledger line: "X happens, because you gave Y, and Z sees you spend it".
   That is the design doing its job against menus, and it has a cost: the
   middle of every story is the player running errands. Nothing arrives.
   kernel31's dragon "acts" only inside cost clauses; kernel32's tower has no
   trap, no treasure and nothing alive in it; kernel1's manifold fails on
   schedule and nobody but the player moves. The pressure field describes
   stages, but no step is asked to place a stage as a scene. This is the
   first reason the outlines read like summaries: a summary of errands is an
   itinerary.
2. **Companion loyalty has no mechanism.** kernel31 asks for "who is still
   with you at the end" to vary, and in all four endings Rowan and Teague
   stand beside you and Corra is the only variable. The cast seeds carry an
   edge and a tie, but no turn's ways differ in which companion is lost, and
   no seed says what would make one leave. The ending cannot vary what the
   premise never put at stake. The 4d prompt's preference for accumulated
   triggers had nothing to accumulate.
3. **Every line replays the same scenes.** A divergent line plays the same
   turns in the same beats, so T2N01, T3N02 and T4N01 are all "at the ruined
   shrine Corra will not let you touch the ash and Rowan has found a mark",
   with a different way each time. `repeated_node` catches identical ways
   only. For a player this is the same room three times.
4. **The budget is backwards.** A richly specified Kernel (31, 1, 5) comes
   out `minimal` because most fields bind, and `minimal` meant one
   complication and a one-sentence arena. Complications are craft, not
   invention against the Kernel; a detailed Kernel is where there is most to
   complicate.
5. **The brief's language leaks by a specific route.** 3-0a's description
   for kernel32 contains "the sword's stated desire to be returned"; 3.5a put
   that clause into `levers`; 3.5b used the lever's name in four costs; 4b
   repeated it in every node. It is a copied five-word phrase, which is a
   lookup, not a judgment.
6. **The opposition rule pulled kernel32 toward a gatekeeper.** 3.5a's rule
   says the opposition is a person with a want, so the model invented a
   warden who negotiates at every gate. A dungeon's opposition is the dungeon.
   The rule is right in general and wrong for this genre; what was missing
   was anyone saying what the genre's audience came for.
7. **4d's judgment was good at the one thing it could see.** Its stop
   reasons on 32 and 28 are sound. What it could not see is the set: that
   every seed so far leaves at the climax, and that two planned endings are
   one world. That is a property of the set of lines, and a one-seed-at-a-time
   call cannot judge it.
8. **kernel17's endings are one ending four times** because the linear
   shape makes every line a single node after the climax, and the only thing
   left to vary there was who holds the ledger. The kernel's "a dozen wildly
   different endings" needs the endings to be designed as a set, and more
   than four of them.
9. **Smaller things.** Names were assigned with the wrong gender where the
   premise text was long (every pronoun in a JSON dump counted for every
   role); a `hidden_truth` that is good (31) still gets paid off three times
   the same way because nothing distinguishes "comes out" from "comes out and
   changes what the party does"; `turn_cast_absent` notes fire on nearly
   every climax because the turn involves everyone.

On your question of whether the summary feel is the node format, the
premise, or the model: mostly the premise (points 1, 2, 4, 6), then the loop
(3, 7, 8), and last the model. The node format at 45-75 words with where and
who is the right grain; what it lacked was one concrete image and any event
to report that the player did not cause. The model's ceiling shows in prose
flatness and in how literally it generalizes an example, and neither is what
makes these outlines dull.

## 2. What changed, step by step

Each new call names its class and its projected cost. The classes and
breakers are unchanged.

### 3.4 Genre promises (new; `classify`, thinking off, about a minute)

`prompts/s3_4_promises.prompt` reads the content Kernel and the brief's
tone, affect, failure, setting and decision lines and writes: `reading`,
`genre`, `player_fantasy`, three to six `promises` (each `in_kernel` true or
false, each a picturable thing), two to four `set_pieces` (scene and kind
of place), `tone_engine` (how the stated tone is produced: who is
ridiculous, what the running joke is; what the player is made to wait for),
at most three `obligatory_cast` roles, and `must_not` (what the Kernel's
words rule out that the genre would supply). Examples: a western from three
words, and a jury-room drama that excludes the courtroom and the defendant.

It reaches 3.5a, 3.5b, 4a and 4c through `brief.promises_lines()` under a
rule stated in each prompt: a promise is a default one rank below a brief
default; the Kernel's words beat it, every brief constraint beats it. Nothing
audits the premise against promises, so a promise can never be enforced
against the Kernel. `--no-promises` skips the call and the prompts get
`none`.

Why a separate call and not a paragraph in 3.5a: 3.5a already runs to its
25 KB limit; adding a reading task to it costs the same minutes and loses
the record. A thinking-off call with a rationale first produces a short,
inspectable list, and the list is what the later prompts need.

### 3.5a Engine: `events`, and the story's own words

The engine gains `events`: two or three things that happen whatever "you"
do, each with `when` (early, middle, late), each a picturable happening (the
dragon burns the river bridge; the chain's manager takes a room at the
hotel; the water reaches the second landing). Events are not turns: a turn
is a situation the player must act in, an event is what arrives and makes
the next situation worse. A missing or empty list is a computed finding; the
repair prompt knows how to fill it. The prompt also says what the promises
are for (the arena holds the set pieces; the opposition, the pressure or the
events deliver them; an obligatory role becomes the opposition or a lever
someone holds) and carries a new rule: never carry a phrase of the brief
into the engine as a thing in the world.

That rule is also computed. `example_guard.brief_echoes` finds five-word
phrases of the brief's free-text fields (decision label and description,
thematic poles, protagonist role, moral valence) inside the engine's
mediation, pressure, opposition and events, and inside the turns' ways and
costs. A hit is a `SoftReject`: the call is re-asked once with the phrases
quoted and the instruction to name the thing in the story's words; if it
comes back the same it is accepted and the phrase will show in the metrics.

The brief's own rendering changed in one way: a field whose constraint rests
on `strong_inference` is shown as `[constraint, inferred]`, and 3.5a is told
that such a field still may not be contradicted but is a floor the Kernel's
details forced, never a ceiling on what the genre may add. Section 3
explains why I did not go further on binding.

The complications budget is now minimal 2, moderate 3, generous 4 (was 1, 3,
4), and at least one is a reversal at every budget.

### 3.5b Turns: a set piece, companion stakes, events as openings

Three rules and a field. `set_piece`: at least one turn is a scene the
audience came for, with the world acting on people and things in a way a
reader can see, and the turn says which in `set_piece` (null elsewhere).
When the promises offered set pieces and no turn names any, it is a
computed finding. Companion stakes: when "you" travel or work with
companions, at least one turn's ways differ in which companion is won, lost,
hurt or turned. Events: a turn's situation may be what an event leaves
behind, and at least one turn should open on one. A tone rule: under a comic
tone, two turns each have one way that is funny in a way a reader can see;
under a frightening one, the set piece is where the fear lives.

Example B is rewritten. The quartet put every turn on the decision axis
(its Kernel asked for that, and you were right that the model may
generalize it). The new Example B is a dig above a village in the last days
before the rains: a foreman whose family farms the hill, a student who
wants her name on the find, a sponsor's agent who wants it on the train. It
shows a turn that opens on an event (the early rain) and is a set piece (the
trench wall coming down with a man under it), a turn whose ways differ in
which companion walks off the hill, a hidden truth with a clue in turn 1,
and two reversals among three complications. Example A (the newspaper)
keeps its shape and gains events and a set piece (the press turned by hand
in the dark). Neither resembles a test kernel in judgment shape; kernel23
("finding something you weren't supposed to find") is one sentence and has
neither the companions nor the institution-against-locals axis.

### 3.5c Cast: `voice` and `breaking_point`

Every individual gets `voice`: how they talk, in one clause, plus one thing
they might say in quotation marks that nobody else in the cast would say.
Under a comic tone each individual gets a different way of being funny, not
a joke. A talking object or creature gets a voice like anyone else: this is
where kernel32's sword stops being a function. Companions (people on your
side who could leave) get `breaking_point`: what "you" could do or fail to
do that would make them leave, turn, or act alone. Both ride into the
register 4b reads (voice) and into 4p and 4d (breaking points, as the table
of worlds a line can end in). 3.5c also now receives the hidden truth and
the tone line. The newspaper example carries both fields for every seed.

### 3.5v and 3.5r

The audit's lists are unchanged; the engine checks it answers are the same
six plus one per turn. Events and set pieces are counts, so they are
computed, not asked. The repair prompt names the two new sections and says
what a repair for a missing event or set piece supplies.

### 4a Main line: events placed, an ending world, loyalty tested

Each beat entry gains `event` (the engine's event that lands there, or
null); the main line places at least one, shows what it does, and leaves
the rest for other lines. That rule is a `SoftReject`. The ending gains its
world in comparable form: `answer` (pole_a, pole_b, mixed, neither),
`standing` (who is still with you, by role), `lost` (who left, turned, died
or was taken), `changed` (what stands or is destroyed). Two further rules:
the main line tests at least one companion's loyalty in an entry, so that
who stands at the end was paid for; a set piece is played as the scene it
is, in the open; under a comic tone two entries say what is funny. The
theatre illustration gains events, two companions with breaking points, and
the ending world.

### 4p Branch plan (new; `judge`, thinking on, about five minutes once)

Under `--branching=plan` (the default), one call after the main line
designs every further line's seed at once: motivation, strategy,
`diverges_at`, trigger and `trigger_kind`, `way`, the ending with its world,
and `why_different`. It reads the question, the companions' breaking points,
the events, the digest (which now carries the main line's ending world),
the unused ways, and the counts (`seeds_wanted` from the shape,
`seeds_at_most` from the iteration cap, the main line's first half).

The validator rejects an invalid node, two seeds leaving one node by the
same way, or a seed without an ending world, and soft-rejects two things
one-at-a-time judging could never see: a set with no seed leaving in the
main line's first half (when the main line has four or more nodes and the
shape is not linear), and two seeds whose ending worlds are equal, or equal
to the main line's. World equality is a computed tuple: the same answer,
the same people standing, the same people lost. A plan that comes back the
same after the complaint is accepted and the story document notes the
duplicate (`same_world`). The seeds are consumed in order; a seed that 4c
returns `nothing_worth_building` on is dropped and the next is tried; the
loop stops when the plan is spent or at `--max-iterations`.

Why this and not 4d: the two things that most hurt agency, late forks and
same-world endings, are properties of the set of lines. 4d saw one seed and
a digest; told to prefer early forks, it still chose N03 and N04 on kernel1,
because from where it stood each was the best next seed. A plan makes the
set a thing that can be checked. It also costs less: one judge call instead
of three or four. The old behaviour is `--branching=judge`, unchanged, with
the companions' breaking points added to 4d's input.

Under a linear shape the plan is an ending plan: every seed leaves the last
node before the main ending on an accumulated trigger, as before, but all
of them are designed together against each other's worlds.

### 4c Divergence: the seed's world, no retold nodes, a new illustration

4c receives the planned seed with its ending world and is told to land in
it, or to say in `why` where the line had to move. Each new entry may place
an event; a new entry that plays a turn an existing line plays at the same
beat by the same way is a `SoftReject` (take a different way, or resolve the
turn in a way of this line's own). The ending states its world. The
illustration is no longer the theatre: it is the dig, leaving early (at the
second crisis, by the crane) into the other answer, so that the one
divergence the model sees is an early fork into a different world with a
companion kept for a reason. 4a keeps the theatre, so main lines and
divergences no longer come from one story.

### 4b Nodes: `image`, tone, events

Each node gains `image`: one concrete sight, sound or object the player
keeps from it, a dozen words at most, not a feeling and not a summary. It
is the picturability test (if you cannot write one, the summary is too
abstract) and stage D's first fixture. The summary opens on the event the
packet names; under a comic tone, a person's voice shows in one thing said
or done in their manner. The register 4b reads now carries voices.

### Computed checks and notes (`checks.py`)

New notes: `repeated_situation` (two nodes on different lines, same beat and
turn, whose summaries share most of their distinctive phrases, whatever the
way), `same_world` (two lines' endings with the same answer, standing and
lost), `companions_static` (three or more lines, a cast with breaking
points, and no companion whose standing differs between endings).

### 4e Evaluation (new; computed, plus one `classify` call of about a minute)

`generator/evaluate.py` computes, over the finished document: fork
positions on the main line and how many fall in its first half;
accumulated triggers; distinct ending worlds and the answers given;
companions whose standing varies across endings; events placed; set-piece
turns and the nodes that play them; promise coverage (a promise or set
piece counts as covered when a node summary or image shares two content
words with it: crude, and computed); phrases of four words that recur in
three or more nodes (the "stated desire to be returned" detector); brief
echoes surviving into summaries; retold nodes and situations; summary size
against the 45-75 word target; opposition presence per line; registers.

Then `prompts/s4e_outline_judge.prompt` (thinking off, `reading` first)
scores plot, people, reveals, agency, specificity and genre from 1 to 5
with a note each, names the best and the worst thing, and says whether it
would play. I want to be plain about this number: it is the same 27B model
grading its own output, and a 3-bit one. Treat its total as a tiebreaker
between two runs that the computed metrics cannot separate, and read its
`worst_thing` as a pointer, not a verdict. Both land in `<id>_eval.json`
and print at the end of the run; `--no-outline-judge` skips the call.

### `ab.py`, the A/B harness

```
cd generator
python ab.py run --variant plan  --kernels eval -- --branching=plan
python ab.py run --variant judge --kernels eval -- --branching=judge --no-promises
python ab.py compare --variants plan,judge --kernels eval
```

`run` copies a kernel's step-2 and phase-3 files from `stories/<kernel>/`
into `stories/<kernel>_<variant>/`, stamps it, and runs `main.py` from 3.4
on with the flags after `--`. `compare` prints, per kernel and as means,
the metrics above, the judge total and the minutes each variant took.
`--kernels eval` is `tests/kernels/EVAL_SET.txt`. A kernel whose source
directory has not run through phase 3 is skipped with a message. `ab.py
eval <story_id>` recomputes the metrics of any finished story without a
model.

### Smaller changes

- `--max-iterations` defaults to the Kernel's ending tier: one 1, few 2,
  several 4, many 6, unstated 3; a linear shape gets two more, because its
  extra lines are one node each. kernel17 now builds up to eight endings
  instead of four.
- Name gender hints read the seed's own fields and only the sentences that
  name the role; the premise's JSON dump no longer counts as one sentence.
- `SoftReject` and `PipelineHalt` live in `generator/errors.py`.
- Schema version 5. A directory stamped 4 stops the run and prints the
  files to delete; its phase-3 files can stay, and `ab.py` will copy them.
- Three kernels added (33 romance, 34 court intrigue, 35 ghost comedy),
  `todo.sh` extended, and the test script's kernel loop reads the directory.

## 3. Your questions, one by one

**Kernel augmentation.** Yes, between phase 3 and 3.5, as a separate call
whose output is ranked below the brief's defaults. Not before phase 3: the
extraction must keep reading only the user's words, or "the genre expects a
corpse" becomes a constraint on kernel28. The thing I would watch first is
whether 3.5a treats promises as license to override a constraint; the audit's
clause and constraint lists are the backstop, and `must_not` repeats the
Kernel's exclusions in the promises block itself so the engine step sees
them twice.

**Phase-3 binding.** I read the two failures you cite as misreadings of what
a field means, not as the binding being wrong: "relational_collapse only"
never said the dragon could not act, and "single" never said one room. Both
readings were fixed in the prompts on 2026-10-03 and the after-runs show it.
Making inferred fields non-binding would re-open the thing phase 3 exists
to prevent (a genre default overriding an inference the Kernel's details
force, which is exactly how kernel28 gets a corpse). What I changed instead:
the brief marks an inferred constraint as such, and the construction prompts
are told what that means (a floor, not a ceiling on what the genre may add);
the texture budget no longer collapses to one complication because a Kernel
is well specified. If a live run shows an inferred field blocking something
the genre plainly owes, the place to fix it is the brief's rendering of that
one field, not the binding class.

**Invention steps (several candidates, then a selection).** Not built, on
cost grounds I would want measured before paying. A divergent step with
thinking off produces three or four candidates in two minutes, but the
selection is a judgment call, and the kernel1 runs showed this model's
thinking-off judgment passing a copied premise. I think the specific
inventions that were missing are better named than sampled: the set piece,
the events, the twist (a reversal complication is required; the hidden truth
is stated; 4p's seeds are each a different world). If after a live run the
engines still come out generic, the cheapest divergent step is three 3.5a
candidates with thinking off and a 4p-style plan call choosing among them;
the plumbing for a classify call with a rationale first already exists.

**Structure and branching.** Yes to planning divergences up front, as 4p,
with the old loop behind a flag. Merges: the schema already allows a line
to rejoin, and nothing in the samples suggested the model wanted to and
could not; I left it. `--max-iterations` now scales with the shape. For
kernel17 the honest answer is that the dozen endings the Kernel asks for
need a premise whose last turn has a dozen different things at stake, and
the plan can only ask for worlds the premise makes reachable; eight is what
I would try first.

**The premise's primitives.** Added: events (an antagonist plan and a world
that moves on its own), voice, breaking point, set piece, and the ending
world as a target. I did not add a midpoint reversal as a field: the
framework's midpoint beat and the required reversal complication already
carry it, and a field the model fills by rote becomes another ledger line.
A cost the protagonist pays personally is in the pole costs already; what
was missing was that nothing in the lines made it visible, which the image
and the event rules address more directly than a field would.

**Node content.** One field, `image`. "What the player sees or does here" I
left out: the summary already says what happens, and a line about what the
player does slides into stage-D material (actions, objects handled one at a
time), which the 4b prompt forbids for good reason.

**Evaluation.** Built: the metrics, the judge, the harness, the set. What
I believe about the measure: the computed columns (`fork@`, `early`,
`worlds`, `events`, `tics`, `retold`, `promise`) are the ones to trust; the
judge total is a weak signal; and the thing none of them measure is whether
a line is interesting, which still takes a reader. The harness makes the
reading comparable: two variants on one brief, the same kernel set, the
same table.

**Test kernels.** The fixed set is eight: 1 (hard sci-fi, systemic
protagonist, a stock, tense), 4 (loop horror, hard failure, high complexity:
the failure model and the loop modifier), 5 (relay viewpoint, funny with
sadness, no failure: tone under a sustained trajectory), 8 ("surprise me":
the no-signal case, where 3.4 has to supply everything), 17 (linear with
many endings: the ending plan), 28 (the adversarial negative: promises must
not add a crime), 31 (party quest: companions, events, set pieces, early
forks), 32 (terse comic dungeon: genre promises and voice). Three kernels
added for what the batch did not cover: 33, a romance (the genre with the
most obligatory beats, and a stated wish for one ending that works out); 34,
a court intrigue whose antagonist's plan advances on a nine-day clock
whether or not the player acts, with three courtiers who can be won and lost
(events and breaking points by name); 35, a ghost story that must be funny
and frightening at once, with one living companion who may turn and a boat
that must leave its mooring (the double tone, one companion's breaking
point, a set piece the Kernel asks for). Kernels 9, 21, 22, 23, 24 are weak
as outline tests (9 and 23 are near no-signal and duplicate 8; 21, 22, 24
were built for 3e), but they still exercise phase 3 and I left them.

**Calibration examples.** Rewritten or replaced: 3.5b Example B (the
quartet, which put every turn on the axis) is the dig; 4c's illustration is
the dig instead of the theatre, so a main line and a divergence no longer
come from one story; 4p's illustration is the dig's branch plan; 3.4's
examples are a western and a jury room; 3.5a, 3.5c and 4a keep the
newspaper and the theatre with the new fields filled in. Every example was
checked against the kernel list for judgment shape. The example guard
covers the new prompts (the same four-word test, per prompt file).

## 4. Where I differ from your assessment

- "Everything still reads like a summary of an outline": I think this is
  mostly fixable upstream, as section 1 says, and I would not change the
  node format further until the premise changes have met the model.
- The comedy: a tone is produced by people with voices wanting things too
  much, not by a step that adds jokes. The voice field and the tone engine
  are the mechanism; if "funny" still survives as one laugh after this,
  the next thing to try is a tone-specific example in 3.5b, not a tone pass.
- The 4d prompt's judgment was not the problem; its vantage point was.
- Phase-3 binding: keep it, mark it, fix the budget (section 3).

## 5. What I decided against, and why

- A divergent-candidates step (section 3): cost before evidence.
- A separate twist step: the hidden truth, the reversal complication and the
  events give the twist three homes already; a fourth call would be asked
  to invent one by rote.
- Lines that merge state rather than path: no evidence it is needed yet.
- Thinking off for the construction calls: still no evidence either way;
  the flags exist (`--no-think-steps=s4a,s4c`).
- Changing phase 3: untouched, as instructed and as I believe.

## 6. Flags and how to A/B

| flag | default | the other arm |
|---|---|---|
| `--branching=plan` | the branch plan (4p) | `--branching=judge`: 4d after every line, as before |
| (3.4 on) | promises run and are given to 3.5a/b, 4a, 4c | `--no-promises`: the prompts get `none` |
| (4e on) | metrics plus the judge call | `--no-outline-judge`: metrics only |
| `--max-iterations` | from the ending tier (1-6, +2 linear) | a number |

The baseline arm of the quality changes that have no flag (events, set
piece, voice, breaking point, image, ending worlds, the dig examples, the
echo check) is the previous commit; the harness can run it from a checkout
of `c3316ba` into a differently named variant if you want that comparison,
since it only needs the phase-3 files and a `main.py`.

The matrix I would run first, on the evaluation set, from the phase-3
files you already have:

```
python ab.py run --variant plan  --kernels eval -- --branching=plan
python ab.py run --variant judge --kernels eval -- --branching=judge
python ab.py run --variant bare  --kernels eval -- --branching=judge --no-promises
python ab.py compare --variants plan,judge,bare --kernels eval
```

`plan` against `judge` isolates 4p; `judge` against `bare` isolates 3.4.
Both arms carry the premise changes.

## 7. Projected cost

Per kernel, from 3.4 on, on your numbers (each thinking call about five
minutes at the 25 KB limit, thinking-off calls one to two minutes).

| call | class | before | now | note |
|---|---|---|---|---|
| 3.4 promises | classify | - | about 1 min | new |
| 3.5a, 3.5b | build | 5 + 5 | 5 + 5 | prompts grew to about 25 KB each (examples, promises); the limit decides the time |
| 3.5c | classify | 0.5 | about 1 | voice and breaking point |
| 3.5v, 3.5r | audit, build | as before | as before | events and set piece are computed findings; a missing one costs a repair round (about 10 min) |
| 4a | build | 5 | 5 | one soft retry possible (no event placed) |
| 4p | judge | - | about 5 once | replaces 4d |
| 4d | judge | 4 per iteration | 0 (plan) | `--branching=judge` as before |
| 4c | build | 5 per line | 5 per line | one soft retry possible (retold node) |
| 4b | build | 4 per call | 4 per call | `image` adds a line per node |
| 4e | classify | - | about 1 | new |

A four-line story: about the same as before, within a few minutes either
way (two new cheap calls, one judge call instead of three). The things that
can add time are the soft retries, each one more thinking call, and the two
new computed findings in 3.5, each a repair round. If the model places
events and names a set piece on its own, none of those fire.

## 8. First live run: what to check, in order

Each step names the file to read and what would make me change course.
Run the stub first: `python tests/test_plumbing.py`.

1. **3.4 on three kernels** (`--stop-after=3.4` on 32, 8 and 28; a minute
   each). Read `s3_4_promises.json`. kernel32 should promise traps, a
   treasure or a reason the sword was there, something alive in the lower
   levels, and a tone engine that says who is ridiculous; kernel8 should
   pick a genre and commit; kernel28's `must_not` must say no death and no
   crime, and its promises must contain neither. **Failure:** a promise that
   contradicts the Kernel on 28, or promises so generic ("danger",
   "mystery") that they add nothing. Then 3.5 is not worth running with it;
   fix the prompt's examples first.
2. **The premise on 32 and 31** (`--stop-after=3.5`; about 15 minutes each
   plus any repair). Read `s3_5_premise_accepted.json` and `s3_5_loop.json`.
   Look for: `events` that are things happening (a wall coming down, a
   party arriving), not restatements of the pressure; a turn with
   `set_piece` filled and a situation that opens on an event; on 31, a turn
   whose ways differ in which companion is lost; on 32, a sword with a voice
   you can hear and an opposition that is the tower, not only a warden;
   `breaking_point` on the companions; levers and costs in the story's own
   words (grep the premise for the longest phrase of the brief's decision
   description). Then `report.py`: did the echo check or the event finding
   cost a retry or a repair round, and did the retry fix it? **Failure:**
   events that are the pressure sentence split in three; a set piece that
   is a conversation; ways that still read "X, because you gave Y (cost: Z
   sees it)" with the new fields bolted on. The first is a prompt fix; the
   third would mean the ledger form is the model's habit and the next lever
   is the examples' ways.
3. **The main line and the plan on 31** (`--max-iterations=1` then let it
   run; about 10 minutes for 4a and 4b, 5 for 4p). Read `s4a_i1_main_line.json`
   for `event` placements and the ending world, then `s4p_i1_branch_plan.json`.
   The plan should have three seeds with three worlds, one leaving at N01
   or N02, standing and lost differing between them, triggers that are acts
   or patterns. Read its thinking trace: did it spend its bytes on the
   worlds, or on restating the digest? **Failure:** every seed at the climax
   after the soft retry (the complaint names the first-half nodes; if the
   model still cannot, the problem is upstream: the early turns' ways do not
   differ enough to carry a line), or worlds that differ only in `changed`
   while standing and lost are identical (then the companion-stakes turn did
   not land in 3.5b).
4. **The whole outline on 31 and 32** (default flags; 75-90 minutes each).
   Read `story.md` as a player. Then `eval.json`. The numbers I would expect
   if the changes work: `forks_in_first_half` at least 1; `ending_distinctness`
   1.0; `companions_whose_standing_varies` non-empty on 31; `events_placed`
   at least 2; `repeated_phrase_count` below 5 and no analyst's phrase in
   the list; `repeated_situations` 0; images that name objects. **Failure:**
   `same_world` or `companions_static` notes in the checks; `Image:` lines
   that are feelings; the judge's `worst_thing` naming the same thing the
   request named.
5. **The A/B matrix** (section 6) on the evaluation set, overnight. Compare
   with `ab.py compare`. The decision rule I would use: keep 4p if `early`
   and `worlds` improve on most kernels without `retold` rising; keep 3.4 if
   `promise` coverage rises and the 28 run stays clean; if the judge total
   moves against the computed columns, trust the columns.
6. **kernel17** (linear, eight endings). Read the eight ending worlds in the
   plan. **Failure:** eight payers of one price; then the premise's last
   turn needs more at stake, and `--max-iterations` for linear shapes should
   come back down.
7. **kernel8** end to end. This is where 3.4 does the most and where the
   audit has the least to check. Read the premise for whether the chosen
   genre's promises arrived as scenes.
8. **Then 33, 34, 35.** 34 is the events test (the regent's plan should land
   as placed events whether or not the player acts); 35 is the voice test
   (the ghost); 33 is the promise-coverage test (the near-miss, the night
   everything almost happens, the one who says it first).

At every step `python report.py <id>` first, and the trace of any call that
retried second. A soft retry that fires on every kernel is a rule the model
cannot follow as written; look at the complaint text in the retry prompt
and at what the retry changed.

## 9. What I could not do

- Run anything against a model. Every prompt change above is untested on
  one; the stub proves the plumbing and nothing about quality.
- Verify the cost projections; they are the archive's per-call numbers with
  the new calls counted in.
- Judge the new examples by anything but reading them against the kernel
  list. If a live run's premise quotes the dig or the western, the example
  guard will say so.

Nothing is committed; the changes are in the working tree.
