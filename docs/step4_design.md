# Pipeline design: step 2's shape split, the dramatic engine, and the story-line loop

This is the current description of everything after phase 3, plus the step-2
change that feeds it. `strategy.txt` is the historical plan; this document is
what `generator/main.py`, `generator/brief.py` and `generator/step4.py`
actually do, why, and what is still unvalidated. Read
`step3_consolidated_design_lessons.md` first for the rules every prompt
follows, and `fable_response_3.md` for the analysis of the kernel1 run that
produced this shape.

## 1. Shape of the pipeline

```
s1 kernel (as written)
s2 rating filter (if --rating)  ─►  s2 shape split: content kernel + shape prefs
phase 3 (blind extraction ×9 over the CONTENT kernel; chained only where a
         field is undefined otherwise)
s3h cross-check  ──►  constraint map + STORY BRIEF (both computed)
s3.5  premise: the dramatic engine  ─► 3.5v audit ─► 3.5r repair ─► re-audit
s3.75 craft spine                   ─► 3.75v ─► 3.75r ─► re-audit
s3.6  cast   (named individuals; every crowd has a representative)
s3.7  world  (the room map, drawn once; the premise's levers placed)
step 4, one story line per iteration:
    4a main line (iteration 1)  |  4c divergence (iteration n)
    4b node build × new nodes (+ revision of nodes the line changed or rejoined)
    computed checks → 4d review → node repair → 4d re-review
    stop when 4d says stop, 4c finds nothing worth building, or --max-iterations
export: <id>_s4_story.json, <id>_s4_story.md
```

Standing rules, all enforced in code:

1. **Generation and verification never share a prompt.** Every builder has a
   separate auditor with its own JSON.
2. **Repair is a third call that receives the violation list.** 3.5r, 3.75r,
   and node rebuilds in revision mode.
3. **Counts, lookups and mechanical checks are computed, not asked.** The
   constraint map, the brief, the shape targets, the state registry, the story
   digest, and step 4's reachability checks are all Python. The model is spent
   on judgment.
4. **Downstream prompts receive the brief, never the raw bundle.** See §3.

## 2. Step 2: the shape split

`s2_shape_split.prompt` separates the kernel into a CONTENT kernel (every word
kept except the shape clauses) and SHAPE preferences: ending count as a tier
(one / few / several / many / unstated, with the stated wording kept for the
record), linearity, choice density, length. Files: `s2_shape.json`,
`s2_kernel.txt` (the content kernel), `s2_rated_kernel.txt` when a rating
filter ran, `s2_rating.txt`.

Every later step reads the content kernel. The shape preferences reach only
step 4, as computed targets (`brief.shape_targets`): a suggested number of
through-lines (one→1, few→2, several→3, many→5, unstated→3), a node-count
range for the main line, and a `linear` flag. They are advisory: the review
decides whether each next line is worth building, and `--max-iterations` caps
it. Why this split exists is argued in `fable_response_3.md` §4; the short
form is that a stated ending count was being treated as an explicit
constraint by every downstream step and the outline was designing selector
variables to hit it arithmetically.

## 3. The story brief (computed)

`generator/brief.py` builds `<id>_s3_brief.json` from the bundle, the
constraint map and 3h: every phase-3 judgment keyed by its field id
(`3-0a.primary_decision_axis`, `3b.transgression`, ...) with its VALUE and a
binding class (`constraint` / `default` / `free`, the strongest class among
the map's leaf paths under that id), the cross-check's resolved conflicts and
`primary_branch_source`, and the suggested budget. No notes, no tiers. About
3k characters against 10k+ tokens for the bundle.

`brief_lite()` is the further cut the per-node and review prompts get:
decision, theme, protagonist, affect (primary, trajectory, tone, somatic
channels, transgression ceiling), failure model, epistemic gap present.

The `serves` vocabulary is unchanged: tags still name phase-3 field ids, and
3.5v checks a tag against the brief's keys by prefix.

## 4. The dramatic engine (3.5)

The old 3.5 built an `instance_generator`: N instances of the extracted
decision, each "what the decision looks like here". On kernel1 that was four
sectors, each "vent it or spare it", and the outline turned that directly into
four vent/spare beats with consequence beats between them. Nothing in the
pipeline asked what stood between the AI and venting, who wanted what, or
what the player would do in a room. The one hard rule of the old prompt ("on
interactive axes you may not invent") also read as "do not give the
protagonist an obstacle".

The new 3.5 builds an engine. Fields, all mandatory at every budget:

| field | what it is |
|---|---|
| `protagonist` | who, wants, can_do, **cannot_do** (the limit the obstacle lives in) |
| `arena` | the setting instance, inside the extracted footprint |
| `pressure` | what forces the situation to a head; `clock_or_stock` says whether the engine tracks anything for it (only where 3-0c or the kernel licenses one) |
| `opposition` | a force with its own want (not "to stop you") and means |
| `mediation` | the decision axis restated as the question at stake; for each pole what the player must DO and what it costs; the levers (people, objects, facts, authorities) that stand between the protagonist and either answer |
| `turns` | 3–5 escalating situations, each with what you must do, 2–3 ways through with costs, who is involved, and a **form** (discover, persuade, trade, confront, conceal_or_reveal, sabotage, endure, choose_whom, rescue, escape); no two turns share a form; no turn is the bare decision axis |
| `cast_seeds` | 3–7 role-level people; every `crowd` seed has an individual who `speaks_for` it; the opposition is embodied |
| `complications`, `withheld`, `fidelity_check` | as before |

The rule that replaced "no new mechanics": the engine's primitives (rooms,
exits, objects to examine/take/use/give, characters with topics whose stance
moves, a clock, flags and counters) are always available; what may not be
invented is a different kind of game (combat, skill checks, minigames, an
economy or reputation score) or a way to lose that 3-0c does not name. The
enrichment budget governs texture (complications, arena elaboration), never
the engine.

3.5v gained a fourth audit, `engine_findings`, which is hard on: a
cannot_do that is empty, an opposition without a want and means, a mediation
pole that is just the pole restated, turns that share a form or are the bare
axis, a crowd seed without a representative. 3.5r repairs those by supplying
what is missing, the one kind of finding where repair adds material.

3.75 is unchanged in judgment; its inputs are now the kernel, the brief and
3.5, and its setup/payoff pair cites turns.

## 5. Cast and world (3.6, 3.7)

Both run once, after the spine and before any story line, because a node is
a subset of rooms with a subset of the cast and the outline has to choose
from something that exists.

`s3_6_cast.prompt` → `s3_6_cast.json`: named individuals with `wants`,
`holds`, `stance`, `moved_by`, `voice`, `topics`, `matters_to_turns`; crowds
with `representatives`. The validator rejects a crowd with no representative
among the characters. This is the fix for "Hydroponics Crew" as a character:
a crowd may exist, but the player never talks to one.

`s3_7_world.prompt` → `s3_7_world.json`: 6–12 rooms (`id`, `name`, `purpose`,
`fixtures`, `connections`, `usually_here`, `protagonist_can`),
`protagonist_presence` (how "you" are embodied and what you can act on
without a person), and `levers_placed` (every mediation lever in a room, a
character's holding, or a record). The validator drops unknown connections
and names and makes connections mutual.

## 6. Step 4

### 6.1 Units

A **node** is a section of play: `goal` (what the player is trying to do),
`turn_ref`, `rooms` (1–3 ids), `characters` (1–3 names), `pressure`,
`what_happens` (on the line that outlined it), and `exits`, each a state of
play the player brings about, with `leads_to` (a node id, or null for an
**open exit** no line follows yet). An ending node has no exits.

A **through-line** is one complete story: `motivation`, `strategy`,
`turning_point`, an `ending`, and a `path` of node ids. Iteration 1 builds
T1; each later iteration adds one.

### 6.2 One iteration

1. **Outline.** Iteration 1 runs `s4a_main_line.prompt`: the canonical
   telling, 5–8 nodes (from the shape's length), every turn in exactly one
   node in order, the opposition acting in at least two nodes, at most one
   open exit per node. No framework choice, no ending mechanism, no selector
   variables: the craft spine's escalation shape and the turns' order carry
   the structure. Iteration n runs `s4c_divergence.prompt`: a different
   motivation or strategy for the protagonist, where it takes hold, how the
   shift is explained, and the new nodes. Three kinds: `existing_exit`
   (claims an open exit), `new_opportunity` (adds something to an existing
   node and an exit from it), `state_variant` (linear shape: no new nodes; the
   same nodes played differently, and an ending variant of the final node
   selected by state). A line ends in its own ending node or `rejoins_at` an
   existing node. The driver rejects a selection that is not an open exit, a
   non-fresh id, or an unknown node, and retries once.
2. **Rebuild changed nodes.** A node the divergence modified (or whose open
   exit was claimed) is rebuilt in revision mode with the change as the
   finding. A rejoined node is rebuilt to add `ending_variants` (or, for a
   state variant, the variant the new line's `ending.when` selects).
3. **Build new nodes** in path order with `s4b_node_build.prompt`. The packet:
   the through-line, the outline entry with `previous` (the exit that led
   here, its `when` and `transition`), `next`, `shared_with`, the turn, the
   mediation, the full definitions of exactly this node's rooms and
   characters, the protagonist's presence, tone (brief_lite + compact spine),
   the state registry (name, kind, values), the budget, and the revision. The
   output is per-room `interactions` (`target`, `action`, `requires`, `sets`),
   per-character `agenda`/`moved_by`, an optional `clock`, and `exits` whose
   `when` is a structured condition over variables. "Choose"/"decide"
   interactions are forbidden.
4. **Computed checks** (`Step4Builder.mechanical_checks`): an exit whose
   `when` no interaction in the node or earlier on any of its lines sets; an
   interaction whose `requires` nothing sets; outline rooms or characters
   missing from the build; a room with no interactions; a menu interaction.
   Each names its node. Also notes rooms never used and cast never present.
5. **Review** with `s4d_review.prompt`: earned choices, continuity, cast and
   rooms, through-line novelty, pacing, termination. It receives the computed
   findings and is told not to repeat them. Every finding names node ids.
   Termination proposes `next_seed` (motivation, strategy, where it could
   diverge) or recommends stop.
6. **Repair**: computed and review findings grouped by node, up to
   `--max-repair-nodes` nodes rebuilt in revision mode, then one re-review.

### 6.3 Files

| call | prefix |
|---|---|
| main line | `s4a_i1_main_line.json` |
| divergence | `s4c_i<n>_divergence.json` |
| node | `s4b_i<n>_<node-slug>_node.json`, revisions `…_r<k>_node.json` |
| review | `s4d_i<n>_review.json`, re-review `s4d_i<n>_r1_review.json` |
| assembled story | `s4_story.json`, `s4_story.md` (rewritten every iteration) |

State is replayed from files; a rerun makes no model calls (the stub proves
zero new logs). `run_prompt` now validates a loaded file too and names it if
it no longer matches the schema, so an old story directory fails loudly
instead of feeding stale shapes downstream.

### 6.4 Schemas the code depends on

Outline node entry (4a `nodes`, 4c `new_nodes`):
```json
{"id": "N03", "title": "...", "goal": "...", "turn_ref": 2, "rooms": ["R02"], "characters": ["..."],
 "pressure": "...", "what_happens": "...",
 "exits": [{"id": "N03.a", "summary": "...", "leads_to": "N04"}, {"id": "N03.b", "summary": "...", "leads_to": null}],
 "failure_exit": null, "craft_note": ""}
```
4c: `status`, `through_line{id,...}`, `divergence{kind,node,exit_id,opportunity,how_the_shift_is_explained}`,
`modify_nodes[{id,add,add_exit}]`, `new_nodes`, `rejoins_at`, `ending{...,node,when}`.

Node build: `arrival`, `rooms[{room, now, interactions[{target, action, requires, result, sets}]}]`,
`characters[{name,in_room,agenda,moved_by}]`, `clock`, `exits[{id, when, transition}]`
(ids must match the outline's), `failure_exit`, `ending_variants`, `design_note`.
`when`, `requires`, `sets` are `[{"variable","value"}]`; `normalize_writes`
tolerates `"var = value"` strings.

Review: six sections; each of the first five has `findings[{issue,node_ids,fix}]`;
`termination{through_lines_built,target,next_seed,recommendation,reasoning}`.

## 7. Trace length: what changed and why

The reasoning-discipline blocks added in the previous pass did not shorten
the kernel1 traces. Reading them shows why: the block stopped literal JSON
drafting in some calls (4a's trace has no braces) but every trace still
opened with 30–40 lines restating all its inputs, and closed with a
"need maybe X ... good" pass over every rule and every output field. Both
scale with the prompt, not with the block. The 4d review, with the full
digest, took 2.6–5.3 hours per call and crashed twice.

So this pass cuts inputs and outputs instead of adding instructions:

- the brief replaces the bundle everywhere downstream (3.5's prompt is now
  kernel + brief; the old one was kernel + bundle + constraint map + 3h);
- 3.75's nine raw inputs are now three;
- the node packet carries only this node's rooms and characters;
- the review's mechanical half is computed, and the review no longer has to
  count endings against a target or scan for unexplored outcomes;
- the outline has no framework, mechanism or selector-variable fields, and
  its node entries have ten fields instead of eleven with three sub-objects;
- the reasoning-discipline blocks are three lines.

Measure on the next run: thinking bytes per call against
`stories/current_output.tar` (s3_5 88k, s4a 79k, s4d 99–109k, s4b 20–52k).
`--no-think-steps` can switch a thinking model's trace off for named
prefixes (the Ollama client sends `think: false`); it is off by default
everywhere.

## 8. Testing without a model

`STRATUM_CLIENT=stub` selects `generator/stub_client.py`, which answers every
prompt with schema-valid JSON built from the JSON sections of the prompt it
was given. Knobs:

```
cd generator
STRATUM_CLIENT=stub STUB_PREMISE_HARD_ROUNDS=1 STUB_SPINE_FLAGGED_ROUNDS=1 \
  STUB_BAD_NODE=N02 STUB_REVIEW_FLAG_FIRST=1 STUB_REJOIN_ON=3 STUB_NOTHING_ON=4 STUB_STOP_AFTER=9 \
  python3 main.py --story-id=stubtest --max-iterations=5 < ../tests/kernels/kernel1.txt
STRATUM_CLIENT=stub python3 main.py --story-id=stublin < ../tests/kernels/kernel17.txt   # linear: state variants
STRATUM_CLIENT=stub STUB_PREMISE_ALWAYS_HARD=1 python3 main.py --story-id=stubhalt < ...  # exit 2
```

## 9. Unvalidated against a live model (in order of risk)

1. **3.5's dramatic engine and the 3.5v engine audit.** Every other change
   depends on 3.5 producing a real obstacle, mediation with costs, and turns
   of distinct form. First live run: one kernel with `--stop-after=3.5`, read
   the 3.5 trace and the 3.5v verdict in full. If 3.5v flags the engine, the
   3.5r repair (which adds material) has never run either.
2. **Every step-4 prompt.** 4a, 4b, 4c, 4d are new; their illustrations are
   marked hypothetical. Run one kernel with `--max-iterations=2`, read the 4a
   trace, one 4b trace, and the first 4d trace, then fix the narrowest thing.
   Watch 4b for menu interactions the regex does not catch ("elect", "opt").
3. **The shape split** on kernels that are mostly shape (kernel17) and on
   kernels with none (kernel8, kernel9): check `s2_shape.json` and that the
   content kernel is verbatim minus the clauses.
4. **3.6 and 3.7** have no verifier; the review's cast_and_rooms check and
   the computed notes (rooms never used, characters never present) are the
   only feedback. If a live run shows the world step inventing rooms the
   outline never uses, cap it at 8.
5. **Phase 3 on the content kernel.** 3g will now fall back on ending count
   for kernels that stated one; nothing downstream reads it any more except
   as a brief field. 3-0a's `decision_mechanism` was inferred from plural
   sectors on kernel1, not from the branching clause, so it should hold.
6. **Context window.** The largest prompt is now 4c (premise + cast + world +
   spine + digest). With the digest carrying only outline-level nodes it
   should stay under 8k tokens through four lines; check `num_ctx` anyway.

## 10. What comes after step 4

`s4_story.json` is close to the engine's needs: rooms with fixtures and
connections, a cast with topics and agendas, nodes with per-room interactions,
structured exit conditions, and state variables. The unbuilt phase is prose:
room descriptions, interaction text, and transitions per node, on the node
packet plus the room's definition, the shape the old plan's steps 14–17
describe.
