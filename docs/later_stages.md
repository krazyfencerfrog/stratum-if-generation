# Stages after the outline loop: design sketch

Nothing in this document is built. It says what each stage after the outline
loop reads, what it writes, where in the story document it writes it, and what
is already in the repository to build it from. The outline loop's schema was
shaped to leave these hooks; they are listed in section 1 so a change to the
loop does not quietly remove one.

Order: **A** arcs and node expansion, **B** character and setting buildout, **C**
reconciliation, **D** per-node room build. Prose comes after D.

All four annotate one evolving document, `<id>_story.json`. Per-call files
remain the resume mechanism (one prefix per call, replayed by the driver);
the document is the assembled view every stage reads and rewrites.
`story.stage` says how far it has got.

## 1. Hooks the outline stage leaves

| in the story document | written by the loop as | filled by |
|---|---|---|
| `nodes[id].annotations` | `{}` | A2 writes `expansion` (the minor nodes it added); D writes `build` |
| `nodes[id].additions` | what a later line needs this node to contain for its trigger to be possible | A must honor each one |
| `edges[].trigger` | `{text, kind: act or accumulated, formal: null}` | D writes `formal`: the condition over state variables |
| `edges[].otherwise` | the other side of each fork, in plain words | D, when it writes the default exit |
| `characters[id].name, profile, packet` | name from Python, the rest `null` | B (A0 adds `arc_tier`, A1 adds `arc`) |
| `locations[id].rooms, packet` | `null` | B |
| `lines[id].ending` | title and summary; for a rejoining line, how the shared ending reads on that line | A (ending variants), D (variant conditions) |
| `hooks` | ways through a turn no line took | A may mention them as roads not taken; D may make them visible dead ends |
| `checks` | computed findings and notes | C extends the same function |
| `stage` | `"outline"` | each stage advances it |

Prefixes continue the numbering: `s5*` stage A, `s6*` stage B, `s7*` stage C,
`s8*` stage D. Each call gets a class from `generator/stats.py` before its
prompt is written; the class is its budget.

## 2. Stage A: arcs and node expansion

Revised 2026-10-04 in conversation with the user. This replaces the earlier
"beat expansion" sketch; its craft devices (setup/payoff pairs, irony) are
kept as part of A1.

**Built 2026-10-04** (`generator/arcs.py`, prompts `s5a0`-`s5a2`; `main.py
--stage-a`, or `python arcs.py <story_id>` on an outline made by older code;
output `<id>_arcs.json` and `<id>_arcs.md`). Not yet run on the live model.
Settled while building:
- **A0 tiers:** arc = the opposition, anyone whose standing differs between
  endings, or a companion with a breaking point who is in at least half the
  nodes. A breaking point alone is not enough: the cast step gives one to
  every companion, which would have made kernel35's lock keeper and towpath
  keeper arc characters. The call sorts the rest into supporting and
  functional.
- **Tells** must land by the next beat: within two nodes, or at the first
  major node after the opportunity (minor nodes other lines hang after a
  shared node can push the next beat further away). A minor node after a
  shared major node is on every line through it, so its tell must land on
  all of them; the packet lists each major node's lines, and the validator
  checks every line (the stub found a T3-only tell on a node T1 and T4 also
  pass through).
- **Minor nodes hang after a major node only**; "before N05" is "after N04".
  A branch leaves from the last minor node of its major node's group.
- **Pattern-shift conditions** are computed exactly (dynamic programming over
  each opportunity's option split): the least strict pattern with at least
  three moves and a share of 0.75-1.0 that random play meets under 15% of
  the time; with four two-option opportunities that is all four (6%).
  Resolution and ending shifts become the first variant of the composed
  ending; line shifts become accumulated edges.
- **Resolution variants** use a weaker pattern (a majority of at least two
  moves, share 0.6), with the line's fixed resolution, or the last one, as
  the fallback.

**The idea.** The outline's lines carry the PROTAGONIST's arc: each line is
a different answer to what "you" want and how it resolves, and the player
picks among them through big, informed choices. The other characters' arcs
live inside and across those lines, and stage A makes them playable: it maps
every arc onto the node graph, then expands the graph with small nodes that
give the player chances to influence, understand and complete those arcs.
Character arcs drive the expansion; rooms come much later (stage D).

### Principles (from the user)

- **Arcs may vary by line but are not forced to.** A character's arc is
  shared wherever nothing pushes it apart, and forks only where a line, or
  the player's accumulated choices, actually change it.
- **No blind switches.** A single minor choice never throws the whole line.
  A line shift comes either from a big choice whose consequences the player
  can broadly foresee, or from the AGGREGATE of many minor choices: a
  pattern that shows a preference or a play style. A "do you answer the
  phone" choice, with no information about what it will cause, never
  decides an outcome on its own.
- **The player perceives arcs through whatever the story affords:** what
  characters say, what they do, where they are, what the player discovers.
  The means vary by story; the stage does not fix one.
- **The protagonist has an arc** in most stories: the general direction of
  their path. Lines change it significantly; they are how the player shows
  how they WANT it to resolve.
- **"You" is defined, but steerable** (decided 2026-10-04): between a blank
  player insert and a fixed character. The premise (3.5a) gives the
  protagonist a `history` (how you came to be here), a `need` under the want,
  `ties` (what each key person is to you, from your side; 3.5c's cast ties
  must agree), and `open` (what is left to the player: how you feel, which
  way you grow). Without this, the protagonist's arc describes what you do,
  not who changes (found writing the kernel35 example). The pipeline also
  fixes `gender` (3.5a) and a name (Python, from the story's pool, before
  the cast; human protagonists only): "you" stays "you" in the text, the
  name is what others call you. A different "you" is a different story; the
  story is not weakened to leave the protagonist undefined.
- **Small nodes, separate in the graph.** Expansion adds minor beats as
  their own nodes, not as content inside the major ones: the graph grows,
  every node stays small (which later stages need), and the structure stays
  checkable.
- **Cost is not the constraint.** This is the stage that makes the story;
  every call should earn its place, but none is cut to save time.

### A0. Arc cast (computed, plus one small classify call)

Every character gets an `arc` tier:
- `arc`: companions and the opposition, whose standing can differ between
  endings (computed from `opposition`, `breaking_point`, and whether their
  standing varies across the ending worlds);
- `supporting`: recurring, with a stance that shifts but no ending of their
  own (a thinking-off call decides between supporting and functional for
  the rest, with a reason first);
- `functional`: a role in one or two nodes.

Typically two to four `arc` characters; it depends on the story. **The arc
cast is closed here.** Later stages may add only functional characters (a
role, one line of purpose, where they are); a new character who needs an
arc means the outline is missing something and goes back through it.

### A1. Arc plan (one call per story, judge or build class)

Input: the line digests (motivation, strategy, turning point, path, ending
world), the arc and supporting cast (wants, edge, tie, voice, breaking
point), the premise's turns, events and hidden truth, the node list with
summaries.

Output, per arc character (and, lighter, per supporting character: see
Decisions), plus the story's `state_visibility` with its reason, and for the
protagonist whose arc is written from
each line's motivation and turning point in the same form so the whole set
can be checked together):

```json
"arcs": {"C02": {
  "starts": "what they want, believe and feel about you at the opening",
  "moments": [{"node": "N04", "lines": ["T1", "T2"], "change": "what shifts and why",
               "kind": "turn | reveal | test | demonstration"}],
  "forks": [{"after": "N04", "by": "line | state", "how": "what makes the arc split here"}],
  "resolutions": [{"lines": ["T1"], "state": "what they have become, and whether they stand with you",
                   "needs": "the pattern of play that leads here (for state forks), or null"}],
  "state": {"name": "lazlo_trust", "meaning": "how far he believes you will sell", "moves": "up when you ..., down when you ..."}
}}
```

Also carried from the old craft pass: setup/payoff pairs citing node ids
(computed: the setup precedes the payoff on at least one line), and the
irony device (its type is a lookup against the epistemic gap).

Computed checks: every arc character has at least one moment on every line
they appear in; their resolutions match the ending worlds (who stands, who is
lost); a state fork names a state that some minor choice moves; no arc
resolves on a single minor choice. Audit and repair as 3.5 does, if the
checks are not enough.

### A2. Node expansion (one call per line, build class)

For each line, and for each major node on it, add minor nodes before, inside or after it, each of one
kind:

- **opportunity**: a small choice that moves an arc's state ("help him hide
  the stain" / "show the lock keeper"). Its effect is on state, never on
  the line by itself; what each option means is something the player can
  read from the situation.
- **revelation**: something learned that explains a character or the
  hidden truth (a logbook, an overheard call, an object).
- **demonstration**: a character acting from where their arc currently is,
  so the change is seen, not told.
- **resolution**: where an arc lands, usually near an ending; may come in
  variants keyed to state.

Each minor node: id, kind, the arc(s) it serves, a 30-50 word summary, one
image, who, and for opportunities the options with their state effects in
plain words.

Rules for opportunities (decided 2026-10-04):
- **Two or three options**, each something done or said, never a moral
  label ("be kind").
- **Sometimes an active attempt**: about one opportunity in three on a line
  offers a physical try at changing the situation (fix it, take it, go
  there) that can succeed, fail or be stopped; a failed attempt has its own
  effect, it is never a dead end. Not every situation needs one.
- **A tell, soon**: each opportunity names `tell`, how and where its effect
  becomes perceptible, within the next one or two nodes on that line, in
  the story's visibility mode (a ledger entry, a lamp, a change in how
  someone stands or what they call you). The engine has a visual-novel style
  rollback, so a player who gets an unexpected outcome must be able to see
  it early, not rewind across half the story. `hidden` visibility hides what
  an effect means, never that something happened. Minor nodes do not create lines; they hang off the major
node's position on each line that passes through it, and a shared major
node is expanded once, with every line through it in the packet.

**Pattern shifts** (decided 2026-10-04). An obvious pattern of choices may
change any level of the story: an arc's resolution, a line's ending, or the
line itself (a jump to another line where the graph has a node to land on).
"Obvious" means it cannot be random:
- at least three opportunities on the path so far moved the state, and at
  least three quarters of them moved it the same way;
- before the shift lands, the player has seen at least two of those
  opportunities' tells and one warning: a demonstration node where the
  character visibly nears the edge (with rollback, the player sees it coming
  and can turn back without a long rewind);
- every path through the shift point also has a way to avoid it.
A1 declares each one: `{"state", "direction", "threshold", "at": node,
"does": "resolution | ending | line", "to": target}`; the computed checks
confirm all three conditions.
The fixed rule is not enough by itself: with exactly four opportunities,
"three of four" is met by random play about 31% of the time (found by
`generator/playtest.py`). So the threshold is computed, not declared: Python
sets it from the number of opportunities on the paths to the shift so that
random play triggers it rarely (target under 15%), and the playtest
simulator verifies it by sampling.

**Arc state and line shifts.** Opportunities move named states. A line's
ending may come in variants keyed to state (a companion stays or goes). An
edge may also be `accumulated`: a line shift triggered by a state pattern
("you sided with the ghost at every chance"), which is where the outline's
accumulated triggers finally come from. Big choices stay `act` triggers, as
the outline wrote them.

Computed checks after A2: every opportunity has a tell placed within two
nodes; about one in three opportunities on a line offers an active attempt;
every arc moment is played by some major or minor node; every state an arc resolution needs is moved by at least two
opportunities on the paths that reach it (aggregate, never single); every
accumulated trigger's pattern is reachable; every resolution variant has a
state condition; minor-node summaries stay within size.

### What Python does and what the model does (decided 2026-10-04)

The pipeline's rule holds here too: counts, lookups and structure are
Python; judgment and invention are the model's. Stage A has a lot of
structure, so roughly half of it is code.

**Python owns:**
- **Graph surgery.** The model describes minor nodes; Python assigns ids,
  inserts them, wires edges, attaches them to every line through a shared
  major node, and assembles each call's packet.
- **The state registry.** A1 declares named states. Every option effect
  carries a structured tag beside its plain-language text
  (`{"state": "lazlo_nerve", "direction": "up"}`); a tag naming an
  undeclared state is rejected.
- **All threshold math.** The model never counts "three quarters of at
  least three". It declares a pattern shift's state and direction; Python
  counts the opportunities on each path, decides whether the threshold is
  reachable and avoidable, and computes the condition.
- **Every rule check:** a tell within two nodes; about one active attempt
  in three opportunities; each state an outcome depends on moved by two or
  more opportunities; arc moments spread, not piled into one node;
  resolutions agree with the ending worlds; a warning placed before each
  shift; the arc cast closed.
- **Composing ending variants:** the table of combinations (Lazlo stays or
  goes x the captain's regard) is generated, not written by the model.
- **A playtest simulator.** Once the graph has states and effects, Python
  walks it with different play styles (always conciliatory, always
  dismissive, random, mixed) and reports which endings, variants and
  pattern shifts each reaches. It tests the design rules directly: an
  obvious pattern does shift the story; random play never does; every
  ending and resolution is reachable. No prompt can check that.

**The model owns:** what each arc is (what changes, why, at what cost); the
minor nodes' scenes, the options' wording, what each tell and warning
looks like; the judgment calls (visibility mode, supporting vs. functional,
which pattern shifts make narrative sense).

**Working pattern: the model proposes, Python checks, the model repairs
from precise complaints.** This also keeps prompts small: instead of a
prompt carrying every rule (on this model a long rule list mostly buys
re-checking), Python finds exactly what is missing and asks for exactly
that ("add one opportunity before N05 that moves lazlo_nerve"), as a small
targeted call.

**Option to try: Python as planner, the model as writer.** After A1, Python
computes each line's task list (arc moments that need a node, states that
need another opportunity, where each tell must land) and the model writes
one item per small call. More calls, each with a tiny input; given that
trace size follows input size, possibly better than one large per-line
call. Build the per-line version first and compare.

### Decisions (2026-10-04)

- **A2 works a line at a time**, not a node at a time: an arc's moments are
  paced across the whole line, and a per-node packet cannot see that. A
  major node shared by several lines is expanded on the first line that
  reaches it; later lines see its minor nodes and add only what their own
  arcs need there.
- **How visible arc state is, is decided per story**, in A1, with a reason:
  `state_visibility` is `signposted` (characters say where they stand, "he
  won't forget that"), `observed` (shown through what they do and where
  they are, for the player to read) or `hidden` (discovered at the
  resolution). It follows how observant the protagonist is and the story's
  viewpoint (a detective notices; a frightened newcomer may not). A2 writes
  opportunities to match.
- **Supporting characters get light arcs**, or they read as cardboard: in
  A1 each has `starts`, one or two `moments` where their stance shifts, and
  an end stance per line; no forks of their own and no named state. A2 may
  give them demonstration nodes. Functional characters get none.
- **The outline's `additions`** (what a later line needs a node to contain
  for its trigger to be possible) are honored in A2, as part of expanding
  that major node. Can move later if it fits better elsewhere.

**Cost.** Not the constraint (see principles). Rough: A0 a minute, A1 about
10 minutes, A2 one larger call per line (10-15 minutes, more if the packet
has to be split), so 1-2 hours for a four-line story, plus any audit and
repair.

## 3. Stage B: the world (characters, rooms, objects)

Revised 2026-10-04 to target the engine in `docs/engine_design.md`, then
designed in conversation with the user the same evening (decisions below).

**Job.** Build the world the scenes will use: characters with topics and
stances, rooms with exits, the objects in them, and "you". Depth follows the
arc tiers from A0: full profiles for `arc` characters, medium for
`supporting`, a line or two for `functional`. Much of what this stage once
had to invent now exists (voice, edge, tie, breaking point from 3.5c; arcs
and states from A1; minor nodes from A2); B's new work is what the engine
needs, and a world worth wandering in.

### Decisions (2026-10-04)

- **Scale is story-dependent, never small.** The floor is the middle ground
  (kernel35: the boat's five rooms, the towpath, the lock, the boatyard;
  about ten rooms, most scenes opening three to six). Exploration and
  adventure stories span more (twenty to forty). B0 computes a target from
  the brief (setting scale and structure, the genre promises) and B2 builds
  to it.
- **Talk to anyone about anything you know, within reason.** Curated topics
  carry the story; on top of them every character has something to say
  about every person, notable object, place and event the player has
  encountered, in their own voice (short lines; for arc characters the
  subjects that matter vary by their state). It costs more writing and
  gives better play: it is where characters live, and it masks which
  conversations matter.
- **Examine everything, within reason:** four to eight examinable things
  per room, two or three of them story-relevant, most of the rest saying
  something about a person or the place's history rather than pure scenery.
- **"You" is part of the world:** a self-description that changes with the
  story (examine yourself), what you start out carrying (Mira's ring), and
  a THINK verb: topics about your history, your ties and your need, what you
  think shifting as the story moves. This is where the defined-but-steerable
  protagonist (later_stages §2 principles) shows up in play.
- **Connective places are added fairly freely, never as skeletons:** the
  stairs, the yard, the corridor exist where the geography wants them, and
  each must contribute to the story's feel: specific details and at least
  one thing worth examining.

### Engine additions these need

- `seen` state: characters present in a room the player enters and objects
  the player sees or examines are recorded automatically; `seen('x')` in
  conditions. Conversations about encountered subjects use it, so B writes
  no flag per subject.
- `think` as a core verb, with the protagonist's topics; `examine` of the
  player; the player's starting inventory (objects with location
  `player`, already supported).

### Steps

**B0 (Python): scenes and subjects.** Group each line's expanded path
(major and minor nodes, from A2) into scenes: consecutive nodes in the same
places with no time jump (the engine's unit; engine_design §2). The model
reviews only the borderline joins, if any. Collect the subject list: every
person, notable object (levers, revelation objects, what the moments name),
place and event, with where each first appears. Compute the target room
count.

**B1, characters (one call per arc or supporting character; functional
characters in one batch).** Input: the cast seed, the arc or light arc, the
scenes they are in, the states that concern them, the hidden truth if they
know it. Output (engine §4.3): curated `topics` (when each becomes known,
what they say by state, effects); `description` and `here` variants by
state (the tells live here); for arc characters a short history. Python
checks: every `known_when` names a flag some moment sets or a `seen()`;
every state a stance reads is declared; the hidden truth appears only in
the topics of those who know it.

**B1c, conversation (one call per character; functional characters in
batches).** Input: the character's packet and voice, the subject list with
where each first appears, the character's tie to each subject. Output: one
line per subject they would plausibly have something to say about, in
voice, gated by `seen(subject)`; for arc characters, variants by state on
the subjects their arc touches. A subject a character would not know about
gets a line that says so in character, or nothing.

**B2, places (one call per location) and the map.** Input: the location
sketch, the scenes that use it and their moments, the objects the moments
need, the room target. Output (engine §4.1-4.2): rooms with permanent base
descriptions (base text names only what never changes; engine §4.1),
exits, story objects where the moments need them and four to eight
examinable things per room. One map call over all locations decides which
adjoin and adds connective places; Python makes exits mutual and checks
every scene's rooms are connected among themselves.

**B3, you (one call).** Input: the protagonist (who, history, need, ties,
open, gender, name), the lines and the protagonist's arc per line from A1.
Output: self-description variants, starting inventory, THINK topics (your
history, each tie, your need, the open question) with what you think by
state or line.

**Cost.** Not the constraint (see the principles in §2). Roughly 5-10
minutes per character, per conversation, per location and for you; kernel35
would be fifteen to twenty calls, two to three hours.

## 4. Stage C: reconciliation

**Job.** Make sure the world from B fits the scenes from A and nothing is
orphaned or contradicted, before D compiles. Mostly computed:
- every scene's rooms exist and are connected among themselves;
- every object a moment names exists and can be where the moment needs it;
- every topic is reachable (its `known_when` flag is set by some moment
  before a scene where the character is present);
- every character's stances cover the states their arc moves;
- the playtest simulator walks the A2 graph with the B world attached and
  reports unreachable scenes, endings and resolution variants.

One model pass per line (thinking off, over packets): for each scene, does
anything in it contradict the packet of anyone in it, or of a room it uses?
yes/no with a quote. A finding re-runs the one B or A2 call it names, with
the finding attached, and returns only what changed. After C the world is
locked: D may not add characters, rooms or scenes.

## 5. Stage D: compile scenes

**Job.** Turn each scene into engine data (engine §4.4): which rooms it
opens, where the cast is, its interactions (from its moments: opportunities
with their arc-state effects, revelations setting knowledge flags, active
attempts with their outcomes), its events (the outline's events that land
here, tells that must appear soon after an opportunity), scene-specific
room text (demonstrations, tells), and its exits (the outline's branch
triggers as flag or pattern conditions; accumulated triggers as pattern
conditions with the thresholds Python computed).

One call per scene (the unit is small: one place-set, one stretch of time,
a handful of moments). Python assembles the package, validates every
condition and id, composes ending variants, and runs the playtest
simulator on the result.

**The playtest is the check, in the loop** (as the computed checks are for
the outline). `engine/story.validate` and `engine/playtest.py` run on every
scene D returns, assembled with what is built so far; their findings are
the repair list a separate repair call receives, returning only what it
changed. What they catch that a reader of the JSON would not:
- **stuck states**: some sequence of actions leaves no way to any ending;
- **missed opportunities**: an arc-moving choice offered to under half of
  curious simulated players. The rule this enforces: **a scene's way
  forward must not bypass its opportunities.** The demo's first draft had
  "Untie the line" open from turn one, and 65% of players left the scene
  without ever being offered Lazlo's ledger choice. The fix is narrative
  gating (your first try at the line brings Lazlo up the steps with the
  ledger, and the line comes free once you have answered him), with a
  neutral answer so the choice is offered, never forced one way.
  Discoveries a player may miss by design are marked `optional`;
- **pattern shifts random play triggers** (over 15% of random plays) or
  that no consistent style can reach;
- content nothing ever offers (interactions, topics, events, nudges, scene
  exits, ending resolutions), and people named before anyone introduced
  them.
The walkthroughs (the shortest route to each ending and resolution
combination) go into the run's report for a human to read.

### Decisions (2026-10-04, with the user)

- **Ignored opportunities: a mix.** An opportunity whose state feeds an
  ending variant or a pattern shift on a line through the scene is
  REQUIRED (Python decides, from A1's resolutions and shifts): it gates the
  scene's exits, and always offers a neutral option, so the choice is
  offered, never forced one way. Every other opportunity LAPSES: after a
  while, or when you leave, the moment passes, and walking away is itself
  the answer, with its own small effect ("Lazlo writes 'ignored' in the
  ledger").
- **Big, line-changing choices are signposted in the fiction** (people say
  what is at stake; the text weighs it), always. The interaction also
  carries `weight: "major"`, which the front end may show on the radial (a
  distinct ring or icon) as a player option.
- **Time is computed.** An action takes time if it changes something (a
  flag, an arc state, where an object is), moves you to another room, or
  is Wait; an action that changes nothing is free (examining, incidental
  talk, thinking). D may override per interaction where the fiction says
  otherwise ("search the whole hold"). Turn-timed events count time; nudges
  count every action, so endless examining still gets a prod.
- **Two to four incidental activities per scene** beyond examining and
  conversation: a chore to help with, a drink to share, the dog; flavour,
  sometimes with a small effect. They make a place lived in, and they mask
  which actions matter.
- **Text that fires anywhere must not assume a place.** Events, nudges and
  lapses fire wherever the player is; the demo's nudge said "Lazlo's voice
  comes up from the cabin" to a player standing in the cabin. Give such text
  room variants (`at('cabin')`) or write it placeless. A check for D: an
  event or nudge naming a room the player can be in, without a variant for
  that room.
- **Story verbs:** prefer the core verbs; add a story verb where a genre
  action deserves its own word, especially one the story repeats (Bail,
  Climb, Salute). Action stories lean on them more. A one-use story verb is
  a validator note.

### Engine additions these need

- **Moments** in a scene: `{id, options: [interaction ids], required,
  neutral: interaction id, lapse: {after, text, effects}}`. Taking an option
  closes the rest; a required moment holds the scene's exits until
  answered; an optional one lapses after `after` actions, or on leaving its
  room, firing its lapse. The playtest's missed-opportunity check reads
  `required` instead of the hand-marked `optional`.
- **Computed time:** each action reports whether time passed (the rule
  above, with an interaction's `takes_time` overriding); `turns` and
  `turns_in_scene` advance only then.
- **`weight`** on interactions, passed through to the menu tree.

Carry over from `generator/later/node_build.py` where it fits: the state
registry, `mechanical_checks` (reachability, reads before writes, menu
options that are moral labels rather than acts), node repair from a finding
list. The open-exit problem the old node build had is gone by construction:
scene exits come from the outline's edges.

## 6. Prose

After D: the text the player reads, written into the package's text
fields (room and character descriptions, what characters say, interaction
text, scene openings, endings). D and B write short functional placeholders;
the prose stage rewrites them in the story's voice, scene by scene, with
the tone line and the cast's voices. Not designed further yet.

## 7. What to build first

1. ~~Port the engine core (expression language, text variants, rewind) into
   `engine/` and fix its three bugs; add the world, scene and interaction
   model and the menu builder; hand-write a tiny package (two scenes of
   kernel35) and play it in a terminal.~~ Done 2026-10-04 (engine_design.md
   §11; `python engine/cli.py engine/examples/kernel35_demo.json`).
2. ~~The playtest simulator on the engine format.~~ Done 2026-10-04
   (`python engine/playtest.py <package> --walkthroughs`; see §5 for how
   stage D uses it).
3. Stage A (A0-A2) on one kernel (built; first live run on kernel35_f5
   queued), then B, C, D, checked against the hand-written package.
