# Stages after the outline loop: design sketch

Nothing in this document is built. It says what each stage after the outline
loop reads, what it writes, where in the story document it writes it, and what
is already in the repository to build it from. The outline loop's schema was
shaped to leave these hooks; they are listed in section 1 so a change to the
loop does not quietly remove one.

Order: **A** beat expansion, **B** character and setting buildout, **C**
reconciliation, **D** per-node room build. Prose comes after D.

All four annotate one evolving document, `<id>_story.json`. Per-call files
remain the resume mechanism (one prefix per call, replayed by the driver);
the document is the assembled view every stage reads and rewrites.
`story.stage` says how far it has got.

## 1. Hooks the outline stage leaves

| in the story document | written by the loop as | filled by |
|---|---|---|
| `nodes[id].annotations` | `{}` | A writes `expansion`; D writes `build` |
| `nodes[id].additions` | what a later line needs this node to contain for its trigger to be possible | A must honor each one |
| `edges[].trigger` | `{text, kind: act or accumulated, formal: null}` | D writes `formal`: the condition over state variables |
| `edges[].otherwise` | the other side of each fork, in plain words | D, when it writes the default exit |
| `characters[id].name, profile, packet` | `null` | B |
| `locations[id].rooms, packet` | `null` | B |
| `lines[id].ending` | title and summary; for a rejoining line, how the shared ending reads on that line | A (ending variants), D (variant conditions) |
| `hooks` | ways through a turn no line took | A may mention them as roads not taken; D may make them visible dead ends |
| `checks` | computed findings and notes | C extends the same function |
| `stage` | `"outline"` | each stage advances it |

Prefixes continue the numbering: `s5*` stage A, `s6*` stage B, `s7*` stage C,
`s8*` stage D. Each call gets a class from `generator/stats.py` before its
prompt is written; the class is its budget.

## 2. Stage A: beat expansion

**Job.** For each node, work out what needs to happen in it: what serves each
present character's arc, what makes each outgoing trigger possible, and one
or two things that make it interesting. Still an outline: ordered events, not
rooms.

**A0, the craft pass (one call per story, plus one small call per extra
line).** This is the old 3.75, moved here because its devices are about how
beats play. Changes from `prompts/later/sA_craft_spine.prompt`:

- `want_need_tension` becomes one entry per line. Each line has its own
  motivation; a single story-wide need fought that.
- `escalation_shape` is dropped. The framework is the escalation shape, and
  matching a pattern to `3b.primary_trajectory` is now part of the computed
  shortlist.
- `setup_payoff_pairs` cite node ids, and a pair is valid only if the setup
  node precedes the payoff node on at least one line (computed).
- `irony_mode` stays; its type against `3-0b.epistemic_gap.present` is a
  lookup and is computed.

```json
"craft": {
  "arcs": {"T1": {"want": "...", "need": "...", "tension": "..."}},
  "irony": {"type": "situational | dramatic", "device": "..."},
  "setup_payoff": [{"setup_node": "N02", "payoff_node": "N04", "what": "...", "lines": ["T1"]}],
  "motif": null
}
```

Verify and repair as 3.5 does now: computed checks first (node ids exist,
order on a shared path, irony type), then a no-think audit with one entry per
Kernel clause and per device ("does this create a second decision axis?"),
then a repair that returns only the changed sections. Class: build for A0,
classify for the audit.

**A1, per node (`s5b_<node>`).** Packet, and nothing else:

- the node: beat job, `adapted`, `summary`, `where` and `who` as sketches
- for each line through it: motivation and strategy, and the summaries of
  the node before and the node after on that line
- `must_enable`: each outgoing edge's trigger text and `otherwise` text
- `additions`
- the craft devices that name this node
- the node's premise turn, with the way each line through it takes

```json
"annotations": {"expansion": {
  "arrives_with": ["what is true when play reaches this node, in plain words"],
  "events": [{"what": "...", "who": ["label"], "where": "location name"}],
  "arc_beats": [{"character": "label", "change": "what shifts for them here"}],
  "enables": [{"edge": "N03->T2N01", "by": "what the player can do here that the trigger sentence describes"}],
  "interest": [{"kind": "reversal | reveal | plant | payoff | cost_shown", "what": "..."}],
  "leaves_with": ["what is true when play leaves, per outgoing edge where it differs"]
}}
```

Three to six events. Class: build, but the packet is small; if traces run
long, split `events` from the rest. A shared node is expanded once, with
every line through it in the packet.

**Computed checks after A.** Every outgoing branch has an `enables` entry;
every `additions` text is covered by an event; everyone in `events.who` is
in the node's `who` (or is reported for the register); every setup/payoff
pair lands in an event of each named node; `leaves_with` of a node is
consistent with `arrives_with` of its successors (a string-overlap warning,
not a judgment).

**Cost estimate.** A0 about 20 minutes; A1 about 10 minutes a node. A
four-line story of 18 nodes: about 3.5 hours.

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
