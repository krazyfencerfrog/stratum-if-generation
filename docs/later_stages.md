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
plain words. Minor nodes do not create lines; they hang off the major
node's position on each line that passes through it, and a shared major
node is expanded once, with every line through it in the packet.

**Arc state and line shifts.** Opportunities move named states. A line's
ending may come in variants keyed to state (a companion stays or goes). An
edge may also be `accumulated`: a line shift triggered by a state pattern
("you sided with the ghost at every chance"), which is where the outline's
accumulated triggers finally come from. Big choices stay `act` triggers, as
the outline wrote them.

Computed checks after A2: every arc moment is played by some major or minor
node; every state an arc resolution needs is moved by at least two
opportunities on the paths that reach it (aggregate, never single); every
accumulated trigger's pattern is reachable; every resolution variant has a
state condition; minor-node summaries stay within size.

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
5-10 minutes, A2 about 5-10 minutes per major node, so about 2-3 hours for
a 15-node story, plus any audit and repair.

## 3. Stage B: character and setting buildout

**Job.** Depth for the people and places the outline actually uses. This is
where voice, stance, topics, fixtures and connections belong. Each entity
gets a long form (for people and for later reference) and a packet form of
150 words or fewer (what per-node calls receive), as the lessons doc's §6a
requires.

**B1, characters (`s6c_<id>`, one call each, or two or three sketches per
call).** Basis: `prompts/later/sB_cast.prompt`. Packet: the sketch (label,
kind, wants, holds, speaks_for, opposition), the nodes the character is in
(summary and the expansion events that name them), and how each line they
are on ends for them.

```json
"profile": {
  "name": "...", "voice": "...", "stance_at_open": "...", "moved_by": "...",
  "arcs": {"T1": "where they end on this line", "T2": "..."},
  "topics": [{"topic": "...", "knows": "...", "says_it_when": "plain words"}],
  "ties": [{"to": "label", "what": "..."}]
},
"packet": "150 words or fewer: who they are, what they want, how they talk, what moves them"
```

A naming pass may run first as one small no-think call for the whole cast,
so names are chosen together. Crowds get a `who` line and no profile; the
rule that a crowd has a representative is already enforced.

**B2, locations (`s6l_<id>`, one call each).** Basis:
`prompts/later/sB_world.prompt`. Packet: the sketch, the nodes that use it
with their expansion events located there, the protagonist's can/cannot, and
the premise's levers.

```json
"rooms": [{"id": "L04.a", "name": "...", "purpose": "...", "fixtures": ["..."], "connects": ["L04.b"]}],
"protagonist_can": "...",
"levers_here": ["..."],
"packet": "150 words or fewer"
```

One to three rooms per location. A final computed pass makes connections
mutual and links locations to each other (`validate_world` in
`generator/later/cast_world_craft.py` already does the first half); which
locations adjoin is one small classification call over the list of names.

**Cost estimate.** About 12 minutes per character and per location: a cast
of six and seven locations is about 2.5 hours.

## 4. Stage C: reconciliation

**Job.** Make sure the depth from B is reflected in the right paths and
nothing is orphaned or contradicted. Mostly computed.

Computed (extending `generator/checks.py`):

- every `events.who` and `events.where` resolves; every character with a
  profile appears in a node, every room is used by an event or is flagged
- every lever the premise names is placed in exactly one room or held by one
  character
- every character's `arcs` has an entry for each line they appear on
- every topic's `says_it_when` names something an event provides
- a character's `stance_at_open` is not contradicted by their first node
  (keyword overlap warning only)

One model pass per line (class: classify), over packets only: for each node
on the line, "does this node's expansion contradict the packet of anyone in
it, or of the place it is in? yes/no, one sentence, quote". Findings name a
node or an entity; repair re-runs exactly that A1 or B call with the finding
attached, as a third call, and returns only what changed.

Output: `story.reconciliation = {findings, repairs}` and `stage:
"reconciled"`. After C the graph is locked: D may not add nodes, lines,
characters or locations.

## 5. Stage D: per-node room build

**Job.** What the old 4b did: per-room interactions with `requires` and
`sets`, per-character agendas, structured exit conditions. It runs last
because by then every input it needs is a packet.

Carry over, from `generator/later/node_build.py` and
`prompts/later/sD_node_build.prompt`: `normalize_writes`, the node validator,
the state registry (recomputed from every built node), `mechanical_checks`
(exit reachability, reads before writes, menu interactions, missing rooms and
characters), node repair from a finding list, and the review prompt
`sD_review.prompt` for the judgment checks on node interiors.

What changes:

- the packet comes from the story document: the node's summary and
  expansion, the rooms of its locations, the packets of its characters, and
  the state registry
- exits are not invented: each outgoing edge already exists with a
  plain-language trigger. D writes the condition that sentence becomes
  (`edge.trigger.formal = [{variable, value}]`) and the default edge's
  condition from `otherwise`. An `accumulated` trigger reads variables set
  in earlier nodes; the registry says which exist.
- `mechanical_checks` gains: every `expansion.enables` entry is reachable
  through interactions that set the trigger's variables
- the open-exit problem is gone by construction: there are no exits with
  `leads_to: null`, so the review cannot flag one and repair cannot "fix"
  one by rewording it

```json
"annotations": {"build": {
  "arrival": "...",
  "rooms": [{"room": "L04.a", "now": "...", "interactions": [{"target": "...", "action": "...", "requires": [], "result": "...", "sets": []}]}],
  "characters": [{"label": "...", "in_room": "L04.a", "agenda": "...", "moved_by": "..."}],
  "clock": null
}}
```

**Cost estimate, honestly.** The archived run spent 65 to 150 minutes per
node on this with a 60 to 124 KB trace. With packets instead of full
definitions and exits given instead of invented it should be less, but this
is the stage to split before running: one call per room of a node, with the
node-level pieces (arrival, exits) in a small call of their own. Budget it as
the most expensive stage and measure it on two nodes before running a story.

## 6. What to build first

A1 on the kernel1 outline's first three nodes, by hand-checking the packet
size and the trace, before A0 or anything in B. The packet design is the
risk in every later stage, and three nodes are enough to see whether it
holds.
