# Proposal draft (to be merged into docs/fable_response_6.md after stage D is read)

## The diagnosis in one paragraph

The pipeline is an excellent generator of a branching short story and a poor generator of interactive
fiction, and the two are not the same artefact. Its unit of structure is the LINE: a through-line whose
ending is fixed when the line is seeded, laid over the beats of a drama framework, made causally
inevitable by a model that is very good at making things inevitable. The player's agency inside that
structure is (1) which line, decided by one act or one accumulated pattern, and (2) how five people feel
about them in the epilogue. Nothing the player learns, finds, holds or shows is state, so nothing the
player learns can change what happens, whom they can accuse, or how it ends. The better the model, the
more polished the inevitability. That is why "even with the horizon models this architecture will not make
enjoyable IF" is right, and why the fix is not prompts.

## What to keep (it works, and better than expected on Fable)

- The dramatic engine (3.5a): hidden truth with mechanism, opposition shown early, events on a clock,
  setups and payoffs. Keep the audit/repair loop.
- Genre promises (3.4): one 30-second call that reads the kernel better than the sixteen before it.
- Stage A's opportunity grammar: situation, two or three acts, one active attempt that can fail, a tell
  within two nodes, observed visibility. Keep, and widen what an option may change.
- Stage B's texture: rooms with examinable history, per-subject conversation in voice, "you" with think
  topics. Keep; key the breadth to path and knowledge.
- The engine: has(), seen(), visited(), pattern(), show, moments, nudges, playtest. It already supports
  everything below; the generator does not use it.
- The per-call artifact discipline, the stub, the plumbing tests.

## What to change (the architecture)

### 1. Replace fixed-ending lines with a state-resolved ending
The outline stage should produce three things instead of lines:
 (a) the EVENT SPINE: what the world does on its clock whatever the player does (the door, the dinner,
     the breakfast reversal, the thaw, the gathering). This is the Fichtean curve's real content and it
     is already in the premise's events.
 (b) THREADS: the things the player can pursue in any order inside that spine: each suspect's lie
     (clue -> where -> what it opens), each companion's loyalty, the player's own secret. Each thread has
     states the player's acts move, exactly as stage A's arcs do now, but including KNOWLEDGE and
     POSSESSION states, not only regard.
 (c) a RESOLVER at each convergence point (the drawing room): an outcome table over state. For kernel38:
     name x (proof held: key/keyhole, stub+box, valet's word, doctor's word) x (who stands). The model
     writes the outcome texts; Python composes which fires, as it already composes resolution variants.
Divergent LINES remain for genuinely different middles (T3's "the room as witness" is a real strategy),
seeded as now, but a line no longer owns its ending; it feeds the resolver.

### 2. Make knowledge and evidence first-class state
A computed CLUE TABLE from the premise: for each lie and for the hidden truth, the clue(s), where each
can be found, what it proves, which topic it opens, which accusation it supports or breaks. Stage B
places clues as objects, observations and per-subject lines (it already writes them; now they are
indexed). Stage D gates topics and interactions on has()/knows flags, and writes SHOW X TO Y
interactions (the engine has the verb). The accusation becomes a moment with one option per suspect,
each outcome resolved from the clue flags. This is not mystery-specific: every parser IF is "what you
have learned and hold unlocks what you can do".

### 3. Widen what a small choice may change
Stage A options get three effect kinds: regard (as now), knowledge (sets a knows/has flag, gives an
object), world (changes what is possible later: the stub in your apron or in the ash). Rule: at least a
third of a scene's opportunities change knowledge or world. Consequences feed later SCENES, not only the
epilogue (the room search happens because you held the glass over Millicent; the engine's scene
room_text and events can already read the flags).

### 4. Collapse phase 3
Nine extractions + cross-check + brief cost 16 calls and produced the two worst readings of the run
(1-2 endings; the wrong accusation as a terminal fail) while the one promises call got the genre right.
Replace with: kernel clauses (keep, for the fidelity check) + promises (keep) + one SHAPE READ that
reads IF cues the current fields cannot: named decisions and their cardinality (seven suspects means at
least seven outcomes), whether a "failure" is a requested playable ending, what state the kernel
implies the engine must track. Catalysts only when the brief is mostly free fields.

### 5. Make the validators model-aware
13 of 89 attempts were rejected; by my reading 9 wrongly (sworn "account" counted as paperwork;
illustration connective phrases counted as copying; the same event on three lines counted as a tic;
a topic cap of five). Each cost a full re-ask (2-4 min on Fable; 15-25 min on the local model). Put
the craft SoftRejects behind a strictness level; keep structural rejects. Fix the paper regex to
exclude testimony words; drop the topic cap for suspects in a mystery; let anti-mirroring exempt
shared events.

### 6. Frameworks and the premise vocabulary
Add shapes that are not drama arcs, or let the event spine BE the scaffold when the brief is an
investigation or an exploration. The premise's turns/ways vocabulary should carry a per-way
"what the player must have found or hold" so that ways are gated by state rather than assigned to lines.

### 7. Measure agency, not outline health
New computed metrics on the compiled package, via the playtest: (a) decisions per scene that change
knowledge or world vs regard only; (b) endings reachable and the share of ending variance explained by
choices AFTER the first fork; (c) for a mystery, suspects accusable and clues required for each proof;
(d) optional discoveries findable (revelations the seeker players miss); (e) convergence: how many
distinct states reach the resolver. And one judge that PLAYS the CLI as a player with a goal ("I think
the doctor did it; can I act on that?") and reports where the game refused.

### 8. For the local model
Everything above makes the calls smaller and more tabular (a clue row, an outcome row, an option with
three typed effects), which is what a 27B model handles; the current 25-45 KB prose prompts with
twenty rules are what it does not.
