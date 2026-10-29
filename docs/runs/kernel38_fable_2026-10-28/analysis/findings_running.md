# Running findings, kernel38 on Fable 5.1 (run id kernel38_fable, started 2026-10-28 19:45)

## Step 2 (shape, genre, clauses, catalysts) — 1m39s, 6 calls
- Shape: everything "unstated" → ending tier unstated → through_lines 3, max_iterations 3. The kernel's
  "accuse the wrong person" + "seven guests" is not read as a shape signal, though for IF it is the strongest
  one in the kernel: at least 2 wrong accusations + 1 right + a no-accusation is the floor of a whodunit's
  ending set.
- Genre classified classic_whodunit (good), but only the general pack exists, so the classification changes
  nothing downstream.
- Catalysts (s2a/b/c): random pick of one in-genre and one fusion element, sanitized. Got: a fake police
  sergeant arriving on skis (an EIGHTH guest in a seven-guest kernel; also contradicts the promises'
  must_not "no police before the accusation") and a "draw pairs from a bowl each night" buddy rule.
  Both are mechanics bolted on from outside the kernel. On a fully specified kernel the catalyst step is noise
  with a non-zero chance of contradicting the kernel; it is unaudited (3.5k audits the premise against the
  kernel, not the catalysts). Verdict: useful only for thin kernels ("surprise me"); gate it on the free-field
  share of the brief.
- The catalyst prompts carry the NO PAPERWORK rule in capitals three times. For a Victorian whodunit the
  will, the letter, the ledger and the forged reference ARE the genre's clue material. A global prohibition
  tuned for the local model's habit (errands at tables) actively fights this genre. Same rule in 3.5a
  ("NO PAPER DRIVERS"), 3.5b2, s6b1, s6b2, s7d. The right rule is "paper only where the story is about it",
  which the prompts also say, and the shouting version wins with a small model.

## Phase 3 (nine extractions + cross-check) — 1m29s, 10 calls
- 3-0a decision axis: which guest to accuse; single_fork; layered landscape; secondary axis "which lie to
  press". Correct and well argued.
- 3-0c: failure hard/terminal/isolated, trigger incorrect_resolution. "The snowstorm isolation is setting,
  not a deadline mechanic." This loses the thaw clock (the genre's pressure) and makes the wrong accusation a
  game-over rather than an ending with a world. The kernel says "I want to be ABLE to accuse the wrong
  person", which is a request for a playable consequence, not a fail state.
- 3g: target_ending_count 1-2 ("wrong accusations are terminal failure off-ramps against that one answer,
  not counted as distinct endings"). This is the single most damaging phase-3 reading for IF: it frames the
  whodunit as a puzzle with one answer plus fail states. 3h then endorses it (C5 coherent).
- 3c theme: truth vs protective discretion (genre_association). 3h flags C3: the theme does not map onto the
  accusation. Good catch, left unresolved for 3.5.
- 3d: an interactive flashback to the night is "invited" — a good idea (Deadline-style) that nothing
  downstream picks up (C9 unresolved).
- enrichment_budget: minimal (a richly specified kernel). The "budget is backwards" finding from response 5
  still stands for texture: the brief says minimal, the premise prompt says "a second sentence allowed above
  minimal".
- The cross-check works as designed; the problem is that the extraction fields themselves cannot represent
  the thing this genre is made of: an information state (clues found, lies exposed) that decides endings.
  3g.state_richness names the channels and nothing downstream consumes them.

## 3.4 promises — 31s
- Excellent. Reads like a designer's brief: the locked study walked and measured; seven lies true to character
  but not to the murder; the housekeeper's own timeline; physical clues that can be held; the storm as jailer;
  the drawing-room accusation. Set pieces: the door broken down; dinner with the empty chair; the
  candle-walk of the gallery; the moment the name is spoken. must_not: no police before the accusation; no
  unfair solution; the wrong guest must be condemnable.
- This is the stage that most resembles what a human author would start from. Note it took one classify
  call of 31 seconds. Everything before it (16 calls) adds a constraint map the promises step mostly
  restates in better words.

## Baseline from an existing package (kernel40, Opus run, stage D)
- 15 scenes, 3 endings, 6 characters x ~30 topics, 13 rooms, 81 objects.
- Choice texture: nearly every scene has 1-5 "moments", each a pair of lines to say ("'Sign it.'" vs
  "'Name the horse.'") moving one named state up or down. Same binary at every scene (the seesaw). Only two
  branch actions in the whole story (read the ledger at S_N02; let the vote pass at S_N04); everything else
  is linear scene-to-scene with the default exit.
- Conversations are one-liners; characters answer topics with a sentence of aphorism-adjacent dialogue.
- Despite every anti-paper rule, the whole story is a contract, a pen, a ledger and a deed (the kernel's
  water rights made it so, which is fine; the rules did not stop it, which says the rules are not the lever).

## 3.5a engine — ~5 min, one call, accepted first time
- Strong. Better than my blind target in two places: the key-drop trick (the Major breaks the door down
  himself, goes in first, lets the key fall from his hand so the gallery hears it and takes it for the inside
  lock) and the tallow stub from the housekeeper's own candle box, which only the valet draws after ten.
  The hidden truth has a mechanism, a motive (a thirty-year-old cowardice the dying master meant to confess),
  two who know (the valet who lit him up; the doctor who knew the master was dying), and six enumerated
  red-herring lies. The obligatory "self-appointed detective who is confidently wrong" from 3.4 became the
  killer: the genre's best trick.
- The protagonist has history (widow, hired by the master, not yet given the study key), a need (whether a
  servant's word can count against her betters), four ties, and an open question (say everything or keep
  back the lies that have nothing to do with the murder). This IS the theme 3h flagged as unmapped (C3), and
  the engine mapped it: discretion vs truth becomes what she does with the six innocent secrets.
- Pressure: the thaw, told through events (the drip, the lodge-keeper, the maids with pails). Good.
- Events: three picturable ones (door down; dinner with the Major's accusation and the nephew bolting; dawn
  thaw and the drawing room). All three are set pieces from 3.4.
- Weak spots to watch downstream: (1) mediation is still two poles (the Major / one of the other six),
  "the one way you can lose" for pole_b: a wrong accusation is written as a terminal loss, which is the
  3-0c reading; (2) the price is the valet's forty years, paid only on the RIGHT path: the right answer costs
  the most, which is fine drama but means the "wrong" endings cost nothing to the player's people;
  (3) ten levers, two of them documents (the forged letter of credit, the unsigned will): the anti-paper
  rules did not stop Fable and should not have.

## 3.5b turns, 3.5c cast, audits, repair — about 12 min, 13 calls (one spine retry, one repair round)
- Five turns, each a genre set piece or close to it: the door coming down (discover), dinner with the
  empty chair (conceal_or_reveal), the candle-walk of the gallery (persuade), the study being cleared at
  dawn (sabotage), the drawing room (confront). Each has three or four ways with modality-distinct acts and
  concrete relational costs (the valet sees you on the back stairs and goes to the Major; the housemaid
  cries and will not go up again). This is a real story spine. Complications: a true reversal (the hour
  you forced out of the valet comes back as the Major's plank against the nephew) and the search of your
  room that takes the stub and your written timeline.
- Audit caught a real E6 repeat (turn 4 re-ran turn 1's "defy the Major in the doorway"); the repair
  replaced it with "whom do you make your accomplice before noon" (the housemaid / the solicitor / the
  doctor). The audit-repair loop earned its keep here, once.
- Cast: nine individuals, each with a lie, a want, a voice spec and a tie; two breaking points (the valet,
  the housemaid). Only the Major is opposition. All voices are described, not sampled (the rules forbid
  samples), so whether they will SOUND distinct is deferred to stage B.
- Structural worry for the stages after: the kernel's "which lie to press" is now inside the ways-through
  of five fixed situations in fixed order. The investigation has been linearized into a spine; what makes a
  whodunit play like IF (question anyone about anything, in any order, show a found thing to the person
  it indicts) is not in the premise's shape at all. The premise vocabulary (turns, ways, costs) is a drama
  vocabulary, not an investigation vocabulary; there is no clue table, no evidence inventory, no
  lie-to-clue mapping, no "what the player must hold to make the name stick".
- The accusation: turn 5 has three ways to name the Major and ONE way that covers naming any of the other
  six, with the cost "the one way to lose". So "accuse the wrong person" is one way through one turn, and
  the kernel's seven-way choice will survive only if the outline gives it lines (it has three to give).

## 3.8 story form — 17s
- Fichtean curve (opening crisis, second, third, climax, aftermath), no modifier; shortlist was
  three_act / fichtean / seven_point. Reasoning is sound for a drama. But: five beats for five turns means
  one turn per beat, one node per beat on the main line, and a whodunit's middle (the free investigation,
  the seven interviews, the house searched) has no beat to live in. The framework library is a library of
  DRAMA shapes; there is no investigation shape (gather / cross-check / confront / second crime / denouement)
  in it, and the scoring rules read only the brief's affect/failure/timeline fields.

## 4a main line + 4p branch plan — about 8 min
- 4a: seven entries over five beats (turn 1 at opening crisis, turns 2 and 3 at second crisis, event 3 +
  turn 4 at third crisis, turn 5 climax, aftermath). Read as a short story it is complete and good: the
  keyhole plant, the candle box plant, the valet's reversal at breakfast, the room search, the reckoning
  in the drawing room, the price paid (the valet's forty years, the fiancée's ring, the doctor's practice).
- Read as IF it is a narrated walkthrough. Every entry is a chain of deeds "you" do with their outcomes:
  N01 alone has the player kneel at the keyhole, go down, double back, look through the keyhole again,
  hide behind the linen basket, note four clues. The way through each turn is FIXED per line (way 2, 1, 1,
  1, 1); the other ways exist only where another line starts. So on the main line the player makes no
  investigative choice at all: the investigation is the summary.
- 4p: two seeds (through_lines = 3 from the unstated tier). T2 "The Wrong Passenger": diverges at N03 by
  trading silence with the widow, and then INEVITABLY accuses the fiancée in the drawing room. T3 "The
  Keyhole Filled": diverges at N01 by defying the Major, names him by the room alone, costs the housekeeper
  her post. So the ending set is: Major named (two flavours) and fiancée named (one). The kernel's seven-way
  accusation has become a mid-story fork at N03 whose consequence is "you will accuse Millicent two scenes
  from now". The player who wants to accuse the nephew, the widow, the doctor, the solicitor or the ward
  cannot. The wrong accusation is not a deduction the player gets wrong at the end; it is a line they
  were put on by a trade at midnight. That is the inverse of what the kernel asked for, and it follows
  directly from the architecture: a LINE is a through-line with its ending fixed at seed time, and the
  climax is a beat on that line, not a decision point with N outcomes computed from state.
- Numbers: 7 + about 3 + about 4 nodes, 3 endings. Compare the floor for this kernel: 7 possible
  accusations x (evidence held or not) x (who you protected).

## 4c divergent lines (T2, T3) — both accepted first time
- T2 "The Wrong Passenger" fixes the player's BELIEF in the fiction: "a housekeeper who ... believes the
  Major was behind his own door at eleven is left with one name the glass in her drawer can carry". The
  line even adds to N03 what the widow says (she heard the ward's voice through the Major's door) so that
  the player "walks away from that midnight having handed the killer an alibi", and plays turn 4 by the
  ice-house way "because a line that finishes by naming Millicent needs the tallow stub raked out". The
  model is doing exactly what the architecture asks: build a through-line whose ending was fixed at seed
  time and make it causally inevitable. The result is a wrong accusation the player cannot avoid once they
  traded silence with the widow two scenes earlier, and cannot reach by any other route. In a whodunit the
  wrong accusation must be the player's own error of deduction at the moment of naming.
- T3 "The Keyhole Filled" has the freshest middle (the Major's signature sheet passed round the dinner
  table; the roof-snow coming down past the gallery windows at one in the morning; the flooded coal cellar
  slowing the maids' hod). The anti-mirroring rules worked, and a horizon model fills them with real craft.
- Across the three lines: the Major is named twice, the fiancée once; nobody can accuse the nephew, the
  widow, the doctor, the solicitor or the ward. Six of seven "lies" (promised in 3.4 as the red herrings
  that make the wrong name tempting) are never playable accusations. The pipeline measured this as
  ending_distinctness 1.0 and will be satisfied.

## Step 4 validators — 25 min, 16 calls, 7 first attempts rejected
Every rejection re-asks the whole call (2-4 min each on Fable), so the validator layer roughly doubled the
outline's cost. What rejected, and whether it was right:
- summaries over 80 words (three calls): a real rule, and the model did write long. Fair.
- "2 of 4 node summaries turn on paper: 'account'" (three calls): the word is the household's SWORN
  ACCOUNT, i.e. testimony, the genre's central object; the paperwork regex counts it as a ledger. Wrong,
  and it fired three times.
- "copies the prompt's illustration (10 phrases: 'come to want the', 'gives the other answer', 'seed holds
  as given')": stock connective phrases from the example's prose shape, not its content. Wrong.
- "mirrors existing line beats (23 shared phrases: 'a cart by noon', 'a fresh scuttle')": T3 passes
  through the same dinner and the same dawn as T1 because the events are the same events; the anti-
  mirroring check cannot tell a shared world from a cloned obstacle. Partly wrong; the model's retry
  invented new friction (the roof-fall, the flooded cellar), which was good, so this one paid off.
- "narrates a person with their cast sketch's description ('laid at her door')": marginal.
- "verbal tic: 'carrington orders the carriage' in three nodes": the same event on three lines. Wrong.
Reading: the validators are tuned to the local model's failure modes (paperwork, example copying, tics)
and treat the horizon model's correct output as those failures. The computed checks that matter for IF
(does the player ever decide anything inside a node? can every suspect be accused?) do not exist.

## 4e outline judge + computed metrics — 49s
- Metrics: 3 lines, 16 nodes, 3 endings, 3 distinct worlds, forks at nodes 3 and 1, both in the first
  half, 5 companions whose standing varies, events placed 3/3, promise_coverage 1.0, paperwork 0.06,
  no brief echoes, no retold nodes. By every number the pipeline computes this is an excellent outline.
  That is the finding: the metrics measure drama-outline health, and none of them can see that the
  player's investigation has no decisions in it and five of seven suspects cannot be accused.
- Judge: lost (8 real losses, all verified), 7 plants with payoffs, opposition at work in N01, a true
  reversal at N06 (recasts N04), one errand, would_play true. best_thing: the key set in the lock from the
  gallery so the kneeling guests see the keyhole go dark. worst_thing: T2's branch trigger (catching the
  widow at the keyhole) is never shown in N03; "the whole wrong-passenger line hangs on an event the
  player never plays." A real catch; the 4c `opportunity` field exists for exactly this and stage A's
  must_contain should add it, so watch whether it does.

## Stage A: arcs and minor nodes — 18 min, 8 calls, 3 first attempts rejected (tell placement rules)
- A1 arc plan: five arc characters (the Major, the valet, the fiancée, the widow, the housemaid), each
  with a named state, up/down conditions written as things the housekeeper DOES ("count his box one short
  where the maids can hear"), moments on every node they appear in, and two resolutions per line (up/down).
  Visibility "observed", with a reason that is itself good writing ("nobody tells a servant what they
  think of her; she reads it off the linen and the stairs"). Four light arcs. One pattern shift: if the
  player has been obedient to the Major at every chance, the story jumps at N03 onto T2 (the wrong
  accusation) without the widow trade. So there are now two routes onto the wrong-accusation line, one an
  act and one accumulated; neither is "the player deduced wrongly".
- A2 minor nodes: 13 on T1, 10 on T2, 13 on T3. These are the best IF material in the run. Each
  opportunity is a real situation with two or three acts, one of them often an active physical attempt
  that can fail ("take the stub into your apron while his back is to you"; "slide the drawer shut as the
  Major opens the pantry door"; "set the long-case clock against his watch before the table"), each with
  a tell one or two nodes later written in the observed mode. Revelations are optional discoveries (the
  widow's account of what she heard at eleven; the nephew's pencilled scrap; the hairpin below the
  keyhole; the tallow stub in Lavinia's own candlestick). Demonstrations are small and good (the valet
  setting out two pairs of boots, one for a dead man).
- What the choices DO: move one relationship state each. What the states DO: pick a resolution variant
  per character in the ending epilogue, and (once) a pattern shift. They never change what the player
  knows, what evidence they hold, whom they can accuse, or whether the name sticks. So the player's agency
  in this architecture is: one line-choosing act (or pattern), plus how each of five people feels about
  you in the last paragraph. The investigation (what you examine, whom you ask, what you show to whom) is
  not a choice anywhere, because no stage models knowledge or evidence as state.
- Computed checks: 16 ending combinations unreachable on T3 (all-up across five arcs is impossible when
  options trade one person against another); reported, not fixed. The playtest at this stage: one path
  per line.

## Stage B (in progress): characters
- C01 the Major: history in three sentences that is the hidden truth from his side; description and
  here-lines keyed to carrington_regard; eight curated topics with variants by state and by node (after
  N06 the key topic becomes "It was on his chain. He never took it off."). The voice spec from 3.5c
  came through: clipped, regimental, dispatching. Asking about the study key moves his regard down (a
  topic with a cost). This is good NPC writing and it is state-aware.
- Where it still falls short of an IF mystery: topics are gated by NODE (known_after N02), not by what
  the player has found. There is no topic "the tallow stub" that opens when you hold the stub, no "show
  the Major the hairpin". The engine supports has()/seen() conditions; stage B only writes known_after
  node ids and state variants, so conversation cannot react to evidence.

## Stage B: world — 16 min, 33 calls (parallel 8), 2 rejections (a topic-count cap: 6 topics, max 5)
- 15 rooms (stair head, gallery, study end, stair foot, back stair, dining room, serving pantry,
  housekeeper's room, servants' hall, drawing room, front hall, study, ice house, library, drifted yard),
  ten people, "you" with state-keyed self-descriptions and think topics. The room text is the best
  "examine everything" material I have seen from the pipeline: the sconces (wax above stairs, tallow
  below), the bare boards below the keyhole where a knee would rest, the loose stair-rod that rings,
  the case of waxwings shot in the great snow of 1838, the glass cloth with the previous housekeeper's
  initial. Objects flagged story:true where a scene needs them.
- The topic-count validator (2-5 for a supporting character) rejected two characters for having six.
  A whodunit's supporting suspects each need: their alibi, the quarrel, the master, the other suspect
  they are covering for, their secret. Five is tight; the cap is a local-model economy, not a craft rule.
- Topics per person: 36-41 (5-8 curated, the rest "about X" lines gated by seen(X)/visited/done flags).
  The valet's per-subject lines are the single best vein of fair-play clue material in the whole run,
  all in voice: the Major's greatcoat dry on the stand after a night it snowed sideways; the blue-room
  door that must be lifted to shut quietly and did not bang on Thursday; a cloth back in the scullery
  with tallow on it; a pillowslip gone from the second shelf; the library sharing a chimney with the
  study. These are exactly the optional discoveries criterion (h) asks for, varied and interesting.
- And they are structurally invisible: nothing reads them. A player who learns from the valet that the
  Major's coat was dry has learned a clue the accusation cannot use, because the accusation is a line.
  They are also written per character without the lines in view, so some contradict a line's events
  (the valet "stood in the study doorway until Netherby had finished, so that nothing went into her
  pail" on a line where the stub comes down in her apron). Coherence risk grows with breadth when
  breadth is not keyed to path.
- "You": five self-descriptions by node, six think topics with up to three variants each; the "what you
  say" thought states the theme exactly (which of their lies deserve to live). Starting inventory: the
  ring of keys, the glass, your wedding ring. Note the glass is in your pocket from the start, so the
  kernel's "only person who saw where everyone was" has become "only person holding the evidence" by
  fiat, before any play.

## Stage D (in progress): compiled scenes
- S_N01 (the door down): opening narrates the found scene, not a deed of the player's; one moment with
  three acts + a neutral (ask about the key / palm the stub / the fire excuse); two ways on: go down the
  back stairs (T1/T2) or "refuse the Major: walk the four walls" (T3). Two timed events, two nudges in
  the Major's voice. Well made. The branch to T3 is the FIRST decision of the game, labelled as a
  strategic commitment, which is at least honest.
- S_N06 (the drawing room, T1's climax): three moments (the glass: debts or begging; the hairpin: the
  gallery empty or the widow knelt there; the valet: let the silence stand or say it for him), one
  action "count the candles aloud", and exactly ONE accusation: talk Lucius Carrington › 'Major
  Carrington.' → S_N07. There is no menu entry for any other name. On the main line the player cannot
  accuse the wrong person; the kernel's defining request is absent from the scene that was built to
  deliver it. The three moments are good drama (what you say about the innocents' secrets in public is
  the theme), but they decide epilogue lines, not the case.
