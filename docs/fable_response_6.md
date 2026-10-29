# Response to `fable_request_6.txt`

Date: 2026-10-28. What was done: one end-to-end run of the current architecture on
`tests/kernels/kernel38.txt` (the snowbound country-house murder) with Claude Fable 5.1 as the
model, through stage D (a playable package, no prose pass), then a read of every stage's goal,
input and output against the criteria in the request, and a play of the package. Before any
constructive output was read I wrote down what a skilled IF author would build from that kernel,
to have a yardstick that the pipeline's own vocabulary had not shaped
(`docs/runs/kernel38_fable_2026-10-28/analysis/blind_target_written_before_premise.md`).

Everything the run produced is mirrored under `docs/runs/kernel38_fable_2026-10-28/`: every
prompt as sent, every answer, every parsed artifact, every per-call log, the run statistics, the
pipeline log, and the analysis notes written as the run went. The live directory is
`stories/kernel38_fable/` (gitignored). The package plays now:

    python -m engine stories/kernel38_fable/kernel38_fable_package_draft.json

Run cost: 109 model calls, 2h02m wall, 1h23m of model time, 39 minutes of Python (the stage D
playtest), 34% of the subscription's five-hour window. Thirteen first attempts were rejected by
validators and re-asked; by my reading nine of those rejections were wrong (section 7).

## 0. Short version

You were right on both counts. The infrastructure is good: every call is resumable, logged,
schema-checked and timed; parallel calls work; the engine is a real room-based IF runtime with
state, disclosure, menus and an exhaustive playtest. And the architecture, run on the best model
available, does not make interactive fiction. It makes a very good branching short story and
compiles it into rooms.

The premise Fable built is better than the one I wrote blind. The self-appointed detective is the
killer; he broke the door down himself and let the key fall from his hand so the gallery would hear
it land; the clue is a tallow stub in a room that burns only wax, one short from the housekeeper's
own box, which only the valet draws from after ten; six other guests lie about six other things.
The outline judge would play it. The computed metrics are all green. The world has fifteen rooms
whose furniture tells the house's history, ten people with distinct voices and forty things each
to say, a protagonist with a past and a mind. Read as a story, it answers criteria a, b, d, e, f
and g.

Played, it does not answer c, i, j or k, and the reason is structural, not a prompt:

- The unit of the architecture is a LINE: a through-line whose ending is fixed when the line is
  seeded, laid over the beats of a drama framework, and made causally inevitable by a model that is
  very good at inevitability. The player's agency inside that is (1) which line, decided by one
  act or one accumulated pattern, and (2) how five people feel about them in the last paragraph.
- Nothing the player learns, finds, holds or shows is state anywhere in the generator. The engine
  supports it (`has()`, `seen()`, `show`, knowledge flags); no stage writes it. So the
  investigation that the kernel, the genre and most of parser IF are made of cannot be a mechanic.
  It is narrated.
- The climax is a node on a line, not a decision point. In the drawing room of the main line the
  menu offers exactly one accusation: the Major. "I want to be able to accuse the wrong person"
  became a separate line the player is put on by a trade at midnight, two scenes before the name
  is said, and the only wrong name available is the fiancée's. Five of seven suspects can never be
  accused.

The better the model, the more polished the inevitability. Section 5 says how to change the middle
of the architecture so that the player's state, not the planner's lines, decides the ending; most
of the parts already exist.

## 1. The run at a glance

| stage | calls | model min | rejected | what came out | verdict |
|---|---|---|---|---|---|
| step 2: shape, genre, clauses, catalysts | 6 | 1.7 | 0 | shape all "unstated" (so 3 lines); genre whodunit; catalysts: a fake police sergeant on skis, a buddy-pair draw | shape under-read; catalysts noise |
| phase 3: nine extractions + cross-check | 10 | 1.5 | 0 | endings 1-2; wrong accusation = terminal fail; theme truth vs discretion; budget minimal | two damaging readings for IF |
| 3.4 genre promises | 1 | 0.5 | 0 | the locked room walked; seven lies; the housekeeper's timeline; clues you can hold; the storm as jailer; the drawing room | the best read of the kernel in the run |
| 3.5 premise (engine, turns, cast, audits, one repair) | 13 | 14 | 1 | hidden truth with mechanism; five turns, each a set piece, 3-4 ways each; nine cast with voices; one real E6 repeat fixed | strong |
| 3.8 story form | 1 | 0.3 | 0 | Fichtean curve, no modifier | fine for a drama; no beat for an investigation |
| step 4 outline (main line, plan, two divergences, fills) | 16 | 25 | 7 | 3 lines, 16 nodes, 3 endings: the Major named (twice), the fiancée named (once) | a good story; no play in it |
| 4e judge + metrics | 1 | 0.8 | 0 | all metrics green; would_play true; worst thing: T2's trigger never shown | measures outline health, not agency |
| stage A arcs + minor nodes | 8 | 18 | 3 | 5 arcs with states; 36 minor scenes; 1 pattern shift; 32 composed endings per line | the best interactive material in the run |
| stage B world | 33 | 16 | 2 | 15 rooms, 105 objects, 10 people x ~38 topics, "you" | rich; keyed to nodes, not knowledge |
| stages C-D compile + playtest | 20 | 5 | 3 | 16 scenes, validator clean, 289k states explored, 0 stuck | plays; coherence slips in composition |

## 2. Stage by stage

### Step 2: shape split, genre, kernel clauses, catalysts
Goal: separate shape preferences from content, classify the genre, cut the kernel into auditable
clauses, inject two creative catalysts. Output: every shape field "unstated", which sets the line
count to three. The kernel's strongest shape signal for IF, "seven guests" and "accuse the wrong
person", is content to this step, so the ending count it implies (at least one per accusable
suspect, plus the right one, plus silence) is never computed. The genre classification is right
and changes nothing (only the general pack exists). The catalysts, picked at random from a list of
twenty works and sanitized, were an eighth person arriving in a seven-guest kernel (and a policeman,
which the promises step then forbade) and a bowl-of-slips pairing mechanic. Nothing downstream used
them, which is the best outcome for a fully specified kernel; nothing audited them against the
kernel either. The catalyst prompts carry the NO PAPERWORK rule in capitals three times.

### Phase 3: nine blind extractions and the cross-check
Goal: an analytic brief with evidence tiers. Mostly right: the decision axis (which guest to
accuse), its layered landscape (which lie to press is the secondary axis), the single viewpoint,
the single building, the escalating affect. Two readings did real damage downstream and the
cross-check endorsed both:
- 3-0c: failure hard, terminal, isolated; "the snowstorm isolation is setting, not a deadline
  mechanic". The wrong accusation is read as a game-over, when the kernel asked for it as a
  playable outcome; the thaw clock is lost as a mechanic (the premise put it back as fiction).
- 3g: target endings 1-2, "wrong accusations are terminal failure off-ramps against that one
  answer, not counted as distinct endings". For a whodunit this is the opposite of what the player
  wants, and it propagates: three lines, one of them the wrong name.
The budget came out "minimal" for the most specified kernel in the set. 3g names the state
channels the engine would need (clues found, lies exposed) and nothing consumes them. The
cross-check caught that the theme does not map onto the accusation (true) and left the interactive
flashback unresolved (nothing picked it up).

### 3.4 Genre promises
One classify call, 31 seconds, and it reads like a designer's brief: the study walked and
measured; seven lies true to character but not to the murder; the housekeeper's own timeline as her
evidence; physical clues that can be held; the storm as jailer; the drawing-room naming. Set pieces:
the door broken down, dinner with the empty chair, the candle-walk of the gallery, the moment the
name is spoken. `must_not`: no police before the accusation, no unfair solution, the wrong guest
must be condemnable. Everything the premise did well traces to this call. It cost less than any
one of the sixteen calls before it.

### 3.5 The premise
Goal: the dramatic engine, the turns, the cast, audited and repaired. Output, all accepted after one
repair round: a protagonist with a history (a widow, hired by the master himself, not yet given the
study key), a need (whether a servant's word with the thing in her hand can count against her
betters), four ties and an open question (say everything, or keep back the lies that have nothing
to do with the murder), which is the theme the cross-check said was unmapped, mapped. Pressure: the
thaw, told through the drip, the lodge-keeper, the maids with pails. Opposition: the Major, shown
pocketing the key and dispatching the one witness. Three events that are three set pieces. A
hidden truth with a mechanism, a motive and two who know. Five turns in five distinct forms, each
with three or four ways that are different kinds of act with concrete relational costs (the valet
sees you on the back stairs and goes to the Major; the housemaid cries and will not go up again).
Nine cast seeds with voice specifications and two breaking points. The audit found one genuine
repeat (turn 4 re-ran turn 1's defiance in the doorway) and the repair replaced it with "whom do
you make your accomplice before noon". The kernel check kept all eleven clauses twice.

What the premise cannot represent: an investigation. Its vocabulary is turns, ways and costs, a
drama vocabulary. There is no clue table, no mapping from lie to clue to what it opens, no
statement of what the player must hold for the name to stick. Turn 5 has three ways to name the
Major and one way that covers naming any of the other six, with the cost "the one way to lose".

### 3.8 Story form
Fichtean curve, well argued. Five beats for five turns means one node per beat on the main line
and no beat in which a whodunit's middle (the house searched, the seven questioned, in any order)
could live. The framework library holds drama shapes only.

### Step 4: the outline loop
Main line: seven nodes, and as a short story it is complete and good. Read as IF it is a
walkthrough: N01 alone has the player kneel at the keyhole, go down, double back, look again, hide
behind the linen basket and note four clues, all narrated, the way through each turn fixed per
line. Branch plan: two seeds. T2 "The Wrong Passenger" diverges at N03 by trading silence with the
widow and then inevitably accuses the fiancée; the divergence call fixes the player's BELIEF in
the fiction ("a housekeeper who believes the Major was behind his own door at eleven is left with
one name") and adds to N03 what the widow says so that the player "walks away from that midnight
having handed the killer an alibi", and plays turn 4 by the ice-house way "because a line that
finishes by naming Millicent needs the tallow stub raked out". T3 "The Keyhole Filled" diverges at
the first decision of the game (refuse the Major in the doorway), names him by the room alone, and
costs the housekeeper her post; its middle is the freshest writing in the outline (the Major's
signature sheet passed round the table; the roof-snow coming down past the gallery windows at one
in the morning; the flooded coal cellar). The model did exactly what the architecture asks: it made
each line inevitable.

Seven of sixteen first attempts were rejected by validators and re-asked (section 7).

### 4e: the outline judge and the computed metrics
Three lines, sixteen nodes, three distinct worlds, forks at nodes 1 and 3, five companions whose
standing varies, events 3 of 3, promise coverage 1.0, no brief echoes, no retold nodes. The judge
found eight real losses, seven plants with payoffs, a true reversal, and would play it. Its worst
thing was sharp: T2's trigger, catching the widow at the keyhole, is never shown in N03, so "the
whole wrong-passenger line hangs on an event the player never plays" (stage A later supplied it as
a revelation). The finding is that every number the pipeline computes is green and none of them
can see that the player decides nothing inside a node and that five suspects cannot be accused.

### Stage A: arcs and minor nodes
Five arc characters with named states whose up/down conditions are things the housekeeper does
("count his box one short where the maids can hear"), moments on every node they appear in, two
resolutions per line each, visibility "observed" with a reason that is itself good writing
("nobody tells a servant what they think of her; she reads it off the linen and the stairs"). One
pattern shift: an obedient player is moved onto the wrong-accusation line at N03 without the widow
trade. Thirty-six minor scenes: each opportunity is a situation with two or three acts, one of them
often a physical attempt that can fail ("take the stub into your apron while his back is to you";
"slide the drawer shut as the Major opens the pantry door"; "set the long-case clock against his
watch before the table"), each with a tell one or two nodes on. Revelations are optional
discoveries: the widow's account of what she heard at eleven, the nephew's pencilled scrap, the
hairpin below the keyhole, the stub in the housemaid's own candlestick. Demonstrations are small
and true (the valet setting out two pairs of boots, one for a dead man). This is the best
interactive material in the run, and this is where the ceiling is:

- what a choice DOES is move one relationship state;
- what the states DO is choose a resolution line per character in the epilogue (32 combinations
  per ending), and once, a pattern shift;
- they never change what the player knows, holds, can ask, can accuse, or whether the name sticks.

The computed check reported sixteen ending combinations unreachable on T3 (all five arcs "up" at
once is impossible when options trade one person against another).

### Stage B: the world
Fifteen rooms, 105 objects, ten people, "you". The room text is the kind of thing a parser-IF
player wants to examine: the sconces (wax above stairs, tallow below), the bare boards below the
keyhole where a knee would rest, the loose stair-rod that rings, the case of waxwings shot in the
great snow of 1838. The Major's eight curated topics vary by his regard and by node (after the
drawing room: "It was on his chain. He never took it off."), and asking about the key costs
regard. The valet's thirty-odd per-subject lines are the richest vein of fair-play clue material in
the whole run, all in voice: the Major's greatcoat dry on the stand after a night it snowed
sideways; the blue-room door that must be lifted to shut quietly and did not bang on Thursday; a
cloth back in the scullery with tallow on it; a pillowslip gone from the second shelf; the library
sharing a chimney with the study. "You" has five self-descriptions by node and six think topics,
one of which states the theme exactly.

Two structural limits. Topics are gated by node (`known_when: flags.done_N02`) or by having seen a
thing, never by what the player has found or holds, so conversation cannot react to evidence (no
"the tallow stub" topic that opens when you carry it; no "show the Major the hairpin"). And the
per-subject lines are written per character with no line in view, so some contradict a line's
events (the valet "stood in the study doorway until Netherby had finished, so that nothing went
into her pail" on a line where the stub comes down in her apron). Breadth not keyed to path costs
coherence.

### Stages C and D: compilation and the playtest
Sixteen scenes, each with an opening that narrates what is found rather than what the player did,
placement, state-keyed room text, the moments with a neutral option where required, one or two
timed events, two nudges in a character's voice, and the way on. Stage C joined four rooms a scene
could not otherwise reach. The validator passed; the exhaustive playtest explored 289,105 states
over all sixteen scenes, every ending reachable, no stuck state. Simulated players: the seekers
finish (main line 46 of 50, T2 4), the obedient style takes the pattern shift 100% of the time,
and 200 of 200 random players never finished within the step limit.

The drawing room on the main line has three required moments (what you say of the fiancée's
sherry, of the widow's hairpin, of the valet's silence), one action (count the candles aloud), and
exactly one accusation, `talk Lucius Carrington › 'Major Carrington.'`, which is the scene's only
exit. There is no menu entry for any other name.

### Playing it
The first screen is a hook: the door in two pieces, the Major's order already given, the valet's
line "the hall remembers who forgot it", sixty-eight things to do. Examining pays (the escutcheon
"rubbed bright at the bottom edge where a cheek has pressed against it more than once"). Asking the
Major where the key went makes the doctor's hands stop on the master's collar; the branch to T3
then appears, marked as a major commitment. Dinner opens with 151 menu leaves. The three curated
moments of three different minor scenes (the clock at table, the glass in the pantry, the apron in
the library past midnight) are all live at once in one room, and "turn out the apron, stub and all"
is offered at the soup. The midnight gallery is atmospheric and the choices there are exactly what
stage A wrote (ask the valet only whether the master rang; hand the widow her pin; knock on the
Major's door yourself). Then the way on is a single marked action and the next scene opens on a
time jump that narrates what happened in between.

Coherence slips seen in play, all composition rather than invention: the housekeeper is "Mrs
Hollis" at dinner and Arabella Vane everywhere else; "Nathaniel Netherby" once; the tallow stub
and the sherry glass each exist twice (a place object and a scene prop; the glass is also in your
pocket from the start); the jet hairpin and the nephew's pencilled scrap are visible in scene one
though they belong to later revelations on other lines; the Major stands "at parade rest" on the
midnight gallery while the fiction has him behind his door. None of these is a model failure; each
is a place where stage B and stage D build from different packets with no index between them.

## 3. The criteria, answered for this run

- a. Interesting story: yes. The premise is a genuinely good golden-age solution and the outline
  has a reversal, eight real losses and a price.
- b. Coherent: at outline level yes; in the package, mostly, with the slips above, which are
  fixable in Python (one object registry; names from one source; revelation objects placed when
  their node is live; breadth lines given the line digest).
- c. Agency: no. Meaningful impact: one act or one pattern chooses among three lines; thirty-six
  small choices change epilogue sentences. Telegraphed: yes, well (tells within two nodes; branch
  labels marked and in character). Differentiation between playthroughs: three endings times
  which of five people are warm to you at the end; the investigation is identical on every play.
  Choices make sense for the situation: yes, almost every option is a thing this woman would do in
  that room.
- d. NPCs: yes. Backgrounds (histories), arcs (five, with up and down resolutions per line, and
  moments on every node), motivations (each has a want, a lie, a thing they protect), distinct
  (the Major's parade-ground sentences, the valet's third-person deference, the widow circling,
  the ward reciting). Weakness: arcs resolve only as epilogue variants and never alter a scene.
- e. Player character: yes. History, need, ties, an open question, a self that changes by node,
  think topics that hold the theme. The one thing my blind target had that this lacks is a secret
  of her own on the clock, which gives a servant-detective a reason to act beyond duty.
- f. Structure: as drama yes, with rhythm (door, dinner, midnight walk, dawn thaw, drawing room,
  cart); the events arrive on a clock and the breakfast reversal is a true turn of the screw. As
  IF no: there is no middle in which to investigate; every scene is a corridor with one to four
  moments and one marked exit.
- g. Ending earned: in the text, yes, and it wraps every thread (the composed resolutions are
  good writing). By the player, no: the proof is narrated by the housekeeper in a single menu
  entry; nothing the player found is checked.
- h. Optional discovery: yes, abundant and varied (room histories, forty things each person will
  say, revelations, think). Interesting: yes. Consequential: never.
- i. Feels like IF: in the room, yes (walk, examine, talk, take); at the level of the story,
  no (a scene corridor with say-line choices and a marked way on is a visual novel's spine).
- j. Would anyone play it: start it, yes; the first screen and the premise would carry most
  players to the dinner. Finish it: the random-player statistic says the way forward is hard to
  find among 100-150 flavour options per scene, and a human who has decided the doctor did it will
  stop when they find they cannot act on it.
- k. Would they enjoy it: the reading, yes. The playing, up to the point where they notice their
  deductions do not count, and then no.

## 4. Why: the diagnosis

Four causes, in order of weight.

1. **The unit is the line and the climax is a node.** Lines are seeded with their endings; every
   later stage's job is to make the ending inevitable from the seed, and the model is superb at
   it. A decision point with N outcomes computed from state (the accusation; most IF endings) has
   nowhere to exist. "Accuse the wrong person" therefore became a line, entered by an unrelated
   choice, with one predetermined wrong name.
2. **The generator has no knowledge or evidence state.** The engine does (`has`, `seen`,
   `known`, flags, `show`); no stage writes it. Investigation, the heart of this kernel and of
   parser IF generally (what you have learned and hold unlocks what you can do), is narrated.
   Revelations set flags that only conversation reads.
3. **Small choices may change only regard.** Stage A's option grammar is good, but its one effect
   type is an arc state, and arc states only recolour the epilogue. Nothing a player does feeds a
   later scene's content except through the one pattern shift.
4. **The front of the pipeline reads for drama and measures drama.** Phase 3 read the kernel's
   IF signals as fail states and a one-to-two-ending story; the metrics and the judge score outline
   health and cannot see agency; the frameworks are drama arcs. The promises call, which reads the
   audience's wants, got everything right in thirty seconds.

Two more, smaller: the validators and the anti-paper rules are tuned to the local model's habits
and tax a strong model while fighting this genre's material (section 7); and stages B and D compose
from separate packets with no shared index, which is where the coherence slips come from.

## 5. How to make i, j and k yes

Keep: the dramatic engine and its audit loop; the promises call; stage A's opportunity grammar;
stage B's texture; the engine; the artifact discipline. Change the middle.

### 5.1 Replace fixed-ending lines with a state-resolved ending
The outline stage produces three things instead of lines:
- the EVENT SPINE: what the world does on its clock whatever the player does. The door, the
  dinner, the breakfast reversal, the thaw, the gathering. This is what the Fichtean curve was
  really carrying, and it is already the premise's `events`.
- THREADS: what the player can pursue in any order inside the spine. For kernel38: each suspect's
  lie (clue, where, what it opens), each companion's loyalty, the player's own secret. Each thread
  has states, as stage A's arcs do now, but including knowledge and possession states.
- a RESOLVER at each convergence point. For the drawing room: name × proof held (the key and the
  keyhole; the stub and the box; the valet's word; the doctor's word) × who stands. The model
  writes the outcome texts; Python composes which fires, exactly as it already composes
  resolution variants. The wrong name is then the player's own error, with its cost.
Divergent lines remain for genuinely different middles (T3's "the room as witness" is a real
strategy), seeded as now, but a line no longer owns its ending; it feeds the resolver.

### 5.2 Make knowledge and evidence first-class state
A computed CLUE TABLE from the premise: for the hidden truth and each lie, the clue(s), where each
can be found, what it proves, which topics it opens, which accusations it supports or breaks.
Stage B places clues as objects, observations and per-subject lines (it already writes them; now
they are indexed, which also fixes the duplicates). Stage D gates topics and interactions on
`has()`/knows flags and writes SHOW X TO Y interactions. The accusation is a moment with one
option per suspect, each outcome resolved from the clue flags. The generalisation beyond mystery is
direct: every IF has "the thing you learned or obtained unlocks the option".

### 5.3 Widen what a small choice may change
Three effect kinds on a stage A option: regard (as now), knowledge (a knows/has flag, an object),
world (what is possible later: the stub in your apron or in the ash pail). Rule: at least a third
of a scene's opportunities change knowledge or world. Consequences feed later scenes' content (the
room search happens because you held the glass over Millicent); scene room_text and events can
already read the flags.

### 5.4 Collapse phase 3
Keep the kernel clauses (for the fidelity check) and the promises call. Replace the nine
extractions and the cross-check with one SHAPE READ that reads the IF cues the current fields
cannot: named decisions and their cardinality (seven suspects means at least seven outcomes),
whether a "failure" is a requested playable ending, and what state the kernel implies the engine
must track. Run the catalysts only when most of the brief is free fields. This removes sixteen
calls and the two readings that hurt most.

### 5.5 Make the validators model-aware
Put the craft SoftRejects (paperwork share, illustration-phrase copying, mirroring, verbal tics,
topic caps, summary length) behind a strictness level; keep the structural rejects. Fix the
paperwork regex so testimony words ("account", "sworn") do not count; exempt shared events from
anti-mirroring; replace the topic cap with a per-tier floor.

### 5.6 Frameworks and the premise vocabulary
Let the event spine be the scaffold when the brief is an investigation or an exploration, or add
such shapes to the library. Give each premise way a "what the player must know or hold" so ways
are gated by state rather than assigned to lines.

### 5.7 Measure agency, not outline health
On the compiled package, via the playtest: decisions per scene that change knowledge or world
versus regard only; endings reachable and the share of ending variance explained by choices after
the first fork; for a mystery, suspects accusable and the clues each proof needs; optional
discoveries the seeker players miss; how many distinct states reach each resolver. And one judge
that plays the CLI as a player with a goal ("I think the doctor did it; can I act on that?") and
reports where the game refused.

### 5.8 The local model
Everything above makes the calls smaller and more tabular: a clue row, an outcome row, an option
with three typed effects. That is what a 27B model handles. The present 25-45 KB prose prompts
with twenty rules each, and the validators that re-ask them whole, are what it does not.

## 6. What to do first

1. **Prove the resolver on the saved run** (no new generation before stage D). From
   `stories/kernel38_fable/`, write the clue table by hand for this premise (about twelve rows),
   add knows/has flags to the existing revelations and takes, replace S_N06's single exit with an
   accusation moment of seven options whose outcomes are resolved from those flags, and re-run
   stage D's playtest. Success: seven suspects accusable; the right name sticks only with the
   proof; the metrics in 5.7 can be computed. This is a few days of Python and one prompt, and it
   tells us whether the engine and the compiler can carry the design before anything upstream
   moves.
2. **Knowledge and world effects in stage A, gated topics and show interactions in B and D**,
   behind a flag; A/B on kernel38 and kernel35 against the current pipeline with the 5.7 metrics.
3. **The outline stage as spine + threads + resolver** (5.1), replacing lines as the primary
   unit; lines kept for divergent middles.
4. **Phase 3 collapsed behind a flag** (5.4) and the strictness level for validators (5.5); A/B on
   the evaluation set.
5. Then the local model, on the new call shapes.

## 7. Smaller findings

- Validator rejections, 13 of 109 attempts, each a full re-ask: summaries over 80 words (three,
  fair); "2 of 4 summaries turn on paper: 'account'" (three; the household's sworn account is
  testimony); "copies the prompt's illustration" (connective phrases such as "seed holds as
  given"); "mirrors existing line beats" (the same dinner and the same dawn on another line;
  the retry did invent fresh friction, so this one paid); a verbal tic ("Carrington orders the
  carriage", the same event on three lines); a topic cap of five; two placement mismatches and one
  condition written in English instead of the condition language (fair, and cheap retries).
- The anti-paper rules did not stop a will, a forged letter of credit and a sworn account from
  being the story's material, and should not have; in this genre paper is evidence.
- The enrichment budget was "minimal" for the most specified kernel in the set.
- The glass is in the player's pocket from the start; the kernel's "only person who saw where
  everyone was" became "the person holding the evidence" by fiat.
- Menu sizes of 68-151 leaves per scene; the "way on" is one of them and random players never
  find it. The engine's "more…" and grouping work; the volume is the breadth layer.
- Stage A's tell-placement validator rejected three answers for tells landing on a shared node's
  far side; the rule is right, the prompt could compute the legal targets and list them.
- The 4c `opportunity` field (what the shared node must contain for a branch to be possible) was
  not used for T2's widow scene; stage A's must_contain supplied it as a revelation. The judge
  caught the gap at 4e.

## 8. What this pass did not do, and caveats

- One kernel, one run, one model. The architectural findings do not depend on the seed; the
  quality findings about Fable's output might vary by run.
- No prose pass, by agreement. Nothing here is about sentences.
- The Claude backend returns no thinking text, so there are no traces to read; the run statistics
  record token counts only.
- No pipeline code was changed. The run directory, the mirror, the notes and the scripted player
  (`analysis/play.py`, which acts on the engine API by substring match) are the artifacts.
