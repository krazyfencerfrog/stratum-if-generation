# The stratum engine: design

Status: agreed in conversation with the user, 2026-10-04; the core is built
(`engine/`: expressions.py, state.py, story.py with the validator,
runtime.py, cli.py; `engine/examples/kernel35_demo.json` is a hand-written
two-scene package; `tests/test_engine.py`). The old `stratum-if` repository
is mothballed. Its useful parts were ported (see §9). §11 lists what the
build added or settled beyond this design.

## 1. What the engine is

A room-based interactive fiction engine in the tradition of Inform 7, TADS
and ADRIFT: a persistent map of rooms, objects and people; a story that
emerges from where you go and what you do; state that changes what is
possible. The difference is the interface. There is no parser: the player
acts through a **radial menu that drills down verb -> object -> detail**
("Talk -> Lazlo -> about the money"; "Use -> the kettle -> on the crack";
"Wait"), so there is no guessing the word. Every option the menu shows is
something that works.

The engine is a data interpreter. A story is one JSON package produced by
the generator (stages B and D, then prose); the engine loads it, keeps the
game state, builds the menu, applies what the player chose, and assembles
the text. It never needs the model at play time.

Design rules that follow from the menu:
- **The action set is finite and explicit.** A parser has a default answer
  for everything; a menu lists exactly the interactions the story defines.
  Stage D writes them.
- **Disclosure is the craft.** In a parser an action nobody thinks to type
  is hidden; here every listed option is visible. So each interaction has
  conditions for when it APPEARS (you know about it, you hold the thing, the
  scene allows it), and solutions are kept out of the menu until the player
  has earned the knowledge that makes them sensible.
- **No dead options.** A verb with nothing available does not appear; a
  level with one option collapses into its parent.

## 2. Layers of story position

| layer | what it is | made by |
|---|---|---|
| line | one through-line of the story (the protagonist's arc) | outline (step 4) |
| beat (major node) | a story function: "the relationship deepens", "the crisis hits" | outline (step 4) |
| **scene** | continuous time and place: the dinner, the walk home, the argument on the stairs | stage A2 groups a line's minor nodes into scenes |
| moment | an opportunity, revelation, demonstration or resolution inside a scene | stage A2 |

A beat holds one or more scenes; "building a closer relationship" is one
beat played as several scenes, its result the aggregate change to the
relationship's state. A new scene starts when time jumps or the set of
places changes. **The scene is the engine's unit of story position:** at any
moment the player is in exactly one scene, which decides which rooms are
open, who is where, and what can be done.

## 3. The story package

One JSON document:

```json
{
  "format": "stratum-story/1",
  "story_id": "kernel35",
  "title": "...",
  "protagonist": {"name": "Teodor Fairweather", "pronoun": "you"},
  "states": { ... },          // §5
  "world": {
    "rooms": { ... },         // §4.1
    "objects": { ... },       // §4.2
    "characters": { ... }     // §4.3
  },
  "scenes": { ... },          // §4.4
  "start": {"scene": "S01", "room": "stern_deck"},
  "endings": { ... }          // §4.5
}
```

## 4. The world and the scenes

### 4.1 Rooms

```json
"wheelhouse": {
  "name": "the wheelhouse",
  "description": [ {"text": "..."}, {"text": "...", "when": "stats.captain_regard_up >= 2"} ],
  "fragments": [ {"text": "The lamp is lit.", "when": "flags.lamp_lit", "position": "post"} ],
  "exits": [ {"to": "stern_deck", "label": "aft, to the stern deck"}, {"to": "cabin", "label": "down the steps"} ],
  "image": "wheelhouse_night"
}
```

A room has a description (text variants: the first whose `when` holds;
random among a list where marked), fragments (conditional snippets before
or after), exits, and an image id.

Room text is **layered**, so where the story is changes what a place is
like now: the permanent base (written by B2: what the place is, its
fixtures), the current scene's layer (written by D: what is different now,
"water is coming through the floor"), state fragments (small changes: the
lamp lit or dark), then who and what is here. The engine composes them in
that order. **Base text names only what never changes**: a line that
snaps, a drawer that opens, a lamp that can go out belong in fragments or a
scene's layer, or the base text contradicts the story once they change (the
demo package hit this twice). Exits are interactions under the verb
**Go**; an exit to a room the current scene does not open is not shown.

### 4.2 Objects

```json
"logbook": {
  "name": "the captain's logbook",
  "location": "wheelhouse",           // a room id, a character id, or "player"
  "description": [ {"text": "..."} ],
  "portable": false
}
```

Objects are things the menu can name: fixtures, items, documents. Where an
object is can change (taken, given), so location is state the engine keeps.
What can be done with an object is not stored on the object: it is the set
of interactions that name it (§4.4), so the same logbook can be read in one
scene and burned in another.

### 4.3 Characters

```json
"lazlo": {
  "name": "Lazlo Brandt", "role": "your brother-in-law", "gender": "m",
  "arc_tier": "arc",
  "description": [ {"text": "..."}, {"text": "...", "when": "pattern('lazlo_nerve','down',3,0.75)"} ],
  "topics": {
    "the_loan": {"label": "the funeral loan", "known_when": "true",
                 "says": [ {"text": "...", "when": "stats.lazlo_nerve_up >= 2"}, {"text": "..."} ],
                 "effects": []},
    "the_ghost": {"label": "the ghost", "known_when": "flags.saw_captain", "says": [ {"text": "..."} ]}
  }
}
```

A character has a description (state-keyed), and **topics**: what you can
talk to them about. A topic appears under Talk -> character once its
`known_when` holds (disclosure: you cannot ask about the ghost before you
have seen him), and what they say is chosen by state (their stance: what
Lazlo says about the loan depends on his nerve). A topic may have effects
(asking moves a state, sets a flag). Where a character is depends on the
scene (§4.4), not on the character.

### 4.4 Scenes

```json
"S04": {
  "beat": "N04", "lines": ["T1", "T3"], "title": "The crack in the dark",
  "opening": [ {"text": "Midnight. The captain stands at the helm in full rigging ..."} ],
  "rooms": ["wheelhouse", "cabin", "stern_deck", "towpath"],
  "cast": {"lake_kaur": "wheelhouse", "lazlo": "cabin", "stellan": "towpath"},
  "room_text": { "cabin": [ {"text": "Water is coming through the floor.", "when": "not flags.crack_plugged"} ] },
  "interactions": [ ... ],
  "events": [ ... ],
  "exits": [ ... ]
}
```

A scene names the beat it plays and the lines it is on; an opening (text
shown on entry); the rooms it opens (the rest of the map is closed for now);
where each present character is; scene-specific room text; its
interactions, events and exits.

**Interactions** are the menu's content:

```json
{ "id": "S04.bail", "verb": "use", "object": "kettle", "detail": "crack",
  "room": "cabin", "when": "not flags.crack_plugged",
  "text": "You jam a cushion into the crack and bail with the kettle. The water keeps coming until a cold hand shows you where to press: 'Not like that. Here.'",
  "effects": [ {"move": "captain_regard", "dir": "up"}, {"move": "lazlo_nerve", "dir": "down"}, {"set": "crack_plugged"} ],
  "once": true }
```

`verb` is one of a small fixed set (§6); `object` names an object,
character, exit or topic; `detail` refines it (a topic, a second object).
`room` limits it to one room of the scene (or `null`: anywhere in the
scene). `when` is its disclosure condition. `text` is what happens.
`effects` change state (§5). `once` hides it after use. Opportunities
from stage A2 are interactions whose effects move arc states; revelations
are interactions that set a knowledge flag (and so disclose topics and
later interactions); demonstrations are conditional text in room_text or a
character's description.

**Events** are the world acting on its own:

```json
{ "id": "S04.lamps", "when": "flags.provisional_signed", "once": true,
  "text": "Every lamp aboard dims at once, and the timbers groan along the length of the boat.",
  "effects": [] }
```

Checked after every action; an event whose `when` holds fires (its text
shown, its effects applied). Turn-based timing uses `turns`
(`"turns_in_scene >= 3"`), so the outline's events ("the regent's plan
advances whether or not you act") land on schedule.

**Scene exits** are the outline's edges:

```json
"exits": [
  { "to": "S05", "when": "flags.let_captain_name_defect", "kind": "act" },
  { "to": "T3S01", "when": "flags.took_ledger_price", "kind": "act" },
  { "to": "T3S02", "when": "pattern('captain_regard','down',3,0.75)", "kind": "accumulated" }
]
```

Checked after every action, in order; the first that holds moves the story
to the next scene (its opening is shown, its rooms open). A branch edge's
plain-language trigger becomes the flag or pattern condition here (stage D
writes `when`; the trigger text stays as documentation).

### 4.5 Endings

```json
"endings": {
  "N07": { "title": "Under the Dead Captain's Name", "text": [ ... ],
           "variants": [ {"when": "pattern('lazlo_nerve','up',2,0.6)", "text": "Lazlo sits on the cabin roof ..."},
                         {"when": "true", "text": "At the last lock Lazlo steps off ..."} ] }
}
```

A scene exit may lead to an ending instead of a scene. The ending's text is
assembled from its base text plus, for each arc character, the first
resolution variant whose condition holds (stage A's resolutions; the
combinations are composed, not enumerated).

## 5. State

- **flags** (true/false): facts and knowledge (`saw_captain`, `crack_plugged`).
- **stats** (numbers): counters and quantities.
- **arc states** are declared in `states` and kept as two stats each:
  `<name>_up` and `<name>_down`, incremented by `{"move": name, "dir": ...}`.
  Keeping both directions (not a net value) is what lets a condition ask for
  a pattern rather than a sum:
  `pattern(name, dir, at_least, share)` is true when the state moved at
  least `at_least` times and at least `share` of those moves went `dir`
  (§2 of later_stages.md: pattern shifts). Thresholds are computed by the
  generator from the opportunities on the paths (random play must trigger a
  shift rarely); the engine only evaluates.
- **object locations**, **visited rooms and scenes**, **turns** (total and
  in the current scene), and a deterministic seed for random text choices.

Conditions use the existing safe expression language (`flags.x`,
`stats.y >= 3`, `and`/`or`/`not`, `visited('room')`, `d(20)`,
`chance(0.3)`), extended with `pattern(...)`, `has('object')`,
`at('room')`, `in_scene('S04')` and `turns_in_scene`. Effects: `set`,
`clear`, `add` (stat delta), `move` (arc state), `give`/`take`/`place`
(object location).

**Rewind:** every action snapshots the full state onto a timeline (the
visual-novel rollback). Save and load serialize the state; the story
package is not part of a save.

## 6. The radial menu

The engine builds the menu from the interactions available now: those of
the current scene whose `room` is the player's room or null and whose
`when` holds, plus the always-present ones (Look, Go through open exits,
Talk to present characters about known topics, Examine visible objects,
Inventory).

- **Level 1, verbs** with at least one available interaction: the core set
  (Look, Examine, Go, Talk, Take, Give, Show, Use, Wait) plus whatever story
  verbs the package declares. There is no limit on story verbs: an action
  story may be built mostly from its own (Climb, Shoot, Dodge, Break). A
  verb with nothing available is not shown.
- **Level 2, objects** for the chosen verb: rooms for Go, characters for
  Talk, objects for Examine/Take/Use.
- **Level 3, details** where the interaction has one: the topic for Talk,
  the second object for Use and Give.
- A level with exactly one option collapses into its parent ("Wait"; "Talk
  -> Lazlo" when he is the only one there and only one topic is known).

The menu is always visible (it is the only way to act), showing the root
level, the verbs; choosing one opens its objects, and so on. The engine
returns the menu as a tree; the front end draws it (a radial UI later, a
terminal list now). Each leaf carries the interaction id the front end
sends back.

**Examine everything.** Every object, person and room the text names can be
examined, and most have something to say even when it leads nowhere. Heavy
interaction is the point, and it also masks which objects and conversations
matter: if only the important things were interactive, the menu would point
at the solution.

## 7. One action, in order

1. The player picks a leaf; the engine checks the interaction is still
   available.
2. Its text is queued; its effects are applied; turns advance; `once`
   interactions are marked used.
3. Events whose `when` now holds fire (text queued, effects applied).
4. Scene exits are checked in order; the first that holds moves to the next
   scene (its opening queued, its rooms opened, characters placed) or to an
   ending.
5. A snapshot is taken (rewind).
6. The view is assembled: queued text, then the current room's description
   (variant, scene room_text, fragments, who and what is here), then the
   menu tree.

## 8. How the pipeline produces it

| package part | produced by |
|---|---|
| states, pattern thresholds | stage A1 (states), Python (thresholds, from the opportunities on each path) |
| scenes: grouping, beat, lines | stage A2 (groups a line's minor nodes into scenes) |
| rooms, exits between rooms, objects | stage B2 (locations to rooms) |
| characters, topics, stances by state | stage B1 |
| scene rooms, cast placement, interactions, events, scene exits | stage D (one scene at a time, from its moments and the world) |
| endings and resolution variants | stage A2 resolutions, composed by Python |
| all text (descriptions, says, interaction text, openings) | the prose stage, after D (D writes short placeholders) |
| validation | Python: every condition parses and names declared flags/stats/states; every id resolves; every scene is reachable and every ending reachable from the start (the playtest simulator, extended to this format); no scene without a way out except endings |

## 9. Ported from stratum-if

From `engine/` of the old repository, with its three bugs fixed
(`Action.from_dict` referenced `self`; `StateManager._enter_node` looked up
the current node instead of the target; the integration test asserted
`False is True`):
- the expression language and `validate_expression` (predicates.py);
- text variants with deterministic random choice, and fragments (sub_node.py);
- the snapshot timeline for rewind, save and load (state_manager.py);
- GameState's flags, stats, visits, turns and seed.

In the event the code was rewritten rather than copied, so the three bugs
did not come across; what survived is the design of each piece.

The FrameNode/SubNode priority fall-through survives as the rule for
choosing text variants and, inside a scene, room text; scenes and the world
model replace frames as the unit of navigation. The old `generation/`
directory (genre pools, cast discovery) stays in the mothballed repository
for reference.

## 10. Decisions (2026-10-04)

- **Verbs:** the core set plus any number of story verbs. A story verb used
  by only one interaction in the whole story is flagged by the validator
  (it likely points at a solution: "Salute" appearing on the wheel says
  what to do), as a note, never an error.
- **Room text is layered:** permanent base (B2), scene layer (D), state
  fragments, then who and what is here. Story position changes the room.
- **Scenes do not stall:** the player wanders the scene's rooms freely;
  every scene has a forward path findable from every state (the outline's
  default edge as an explicit or signposted interaction; the playtest
  simulator checks every state, not just that an exit exists), and one or
  two nudges per scene fire after a number of actions without progress (a
  character prompts, or the world pushes: time pressure arriving).
- **Saves** record the package's hash; loading a save into a regenerated
  story says so plainly instead of breaking. No compatibility across
  versions.
- **Examine everything:** every named object, person and room is
  examinable, most with something to say; heavy interaction masks what
  matters.
- **The menu is always visible,** at its root (the verbs), drilling down on
  choice.

## 11. Settled while building (2026-10-04)

- **Arc states are two counts** (`state.arcs[name] = {up, down}`);
  `stats.<name>_up` / `_down` read them, so both spellings in §5 work.
  `moved(name)` gives the number of moves.
- **Further helpers:** `here('character')` (in the player's room). Objects
  may carry `when` (visible only while it holds: the logbook appears when the
  drawer is opened), `listed` (named in "You can see ..."; defaults to
  portable), and `take_text`. Characters carry `here` variants (how they
  appear in the room text, by state: this is where tells live).
- **Built-in actions** are generated (Look, Examine what is visible, Go
  through open exits, Talk about known topics, Take portable things, Wait,
  Inventory); an authored interaction with the same verb, object and detail
  replaces one. Look and Inventory take no time and are not snapshotted.
  An interaction is offered only when its object and detail are present
  (in the room or carried); `"reach": "any"` lifts that.
- **Free-text details:** a detail that is not an id (a line to say, an
  answer to give) carries `detail_label`; a label in quotes reads "say '...'"
  in the menu.
- **Topics** may be `once` and carry effects; `known_when` discloses them.
- **Nudges** are a scene's `nudges: [{id, after, text, effects, when?}]`,
  fired once each, in order, when `after` actions have passed without
  progress (a change to flags, stats, arcs, object locations or used
  interactions; walking about is not progress).
- **Events** default to `once: true`; one action runs events, then nudges,
  then scene exits, repeated (up to 10 times) while a scene change lands.
- **Effects** also include `room` (move the player) and `place` on a
  character (move them within the scene).
- **Endings** take `resolutions: [{about, variants}]` (one composed line per
  group, the first variant whose `when` holds); a bare `variants` list is one
  group.
- **Validator** errors: unknown ids, expressions that do not parse or name
  undeclared states, a flag a condition reads that nothing sets, scenes or
  endings unreachable over scene exits, scenes without exits, duplicate
  interaction ids, bad effects. Notes: story verbs used once or never,
  things with nothing to say when examined, flags set but never read.
- **Saves** hold the state, the whole rewind timeline and the history, with
  the package hash (`stratum-save/1`).
- **History:** beside each snapshot the engine keeps what was chosen (the
  menu path, "Talk › Lazlo Brandt › about the ledger") and what it said;
  `rewind_to(n)` returns to any entry (the visual-novel backlog; the
  terminal player's `h`). Walkthroughs from the playtest simulator can use
  the same record.
- **Collapse is a front-end choice:** the engine builds the full tree and
  merges levels by mode. `trivial` (default) merges only where there is
  nothing to choose (Wait, Look, an object with one way to act on it), so
  the menu keeps one shape (verb, then object) and a lone option never
  jumps to the root and points at the solution; `all` merges every single
  option ("Untie › the stern line").
- **Things a character holds** are visible (examinable, readable) while
  they are in the room; only things in the room can be taken.
- **Playtest** (`engine/playtest.py`): an exhaustive search over normalized
  states (turn counters capped at the largest threshold any condition
  compares them with; fixed seed) for reachability, stuck states and content
  that never happens, plus simulated players (random; `up`/`down`/
  `<state>:dir` styles that are also curious, preferring options they have
  not tried) for endings, resolution combinations, missed opportunities and
  pattern-shift rates. An interaction or topic may be marked `optional`
  (a discovery the player may miss by design). The demo: 14,639 states,
  about 2 s.
- **Introductions:** the validator notes event or nudge text naming a
  character whom neither the intro nor a scene opening (this scene or an
  earlier one) has introduced; events fire wherever the player is, so an
  unintroduced name is a stranger shouting (playtest feedback, 2026-10-04).
- **Built for stages B and D (2026-10-04):** `seen` (people present in the
  player's room and objects visible there are recorded after every action;
  `seen('x')`), the THINK verb and examine yourself from the package's
  `protagonist` block (`description`, `think` topics), moments (a scene's
  `moments: [{id, options, required, neutral, lapse}]`; `answered('id')`),
  computed time (`turns` advance only for actions that change something,
  move you, or wait; `takes_time` overrides; `actions` counts everything),
  and `weight: "major"` passed to menu leaves (the terminal player marks it
  ◆). The playtest explorer drops what cannot matter from a state (other
  scenes' interactions and events, flags read only by text, seen-subjects no
  condition asks about), which keeps the demo at 27k states.
- **Built after the first generated world (2026-10-04):** `heard` (what the
  player has examined, asked or thought, and which rooms have been
  described): menu leaves for examine, talk and think carry `new` until
  taken, and a node is new when anything under it is (the terminal player
  marks it •). A room's base description is given on the first visit and
  on Look; a revisit gives only the scene layer, fragments and who and what
  is here. Topics (and interactions) may carry `group` (person, place,
  object, event): an object with more than 8 options sorts its grouped ones
  into submenus (people, places, things, what happened) after its ungrouped
  ones. The playtest checks every explored state's menu: every option in it
  exactly once, no level showing two entries alike or one unlabelled, no
  level wider than 29 (the terminal player's keys). The terminal player
  takes one key press per choice.
- **Exploration scene by scene (2026-10-04):** a story of more than three
  scenes is explored one scene at a time, each from the states the scenes
  before it are left in (up to 8, spread by arc state and flags), so the
  cost grows with a scene's size, not the story's. A state's identity
  leaves out what cannot change what happens: objects no interaction of the
  scene needs at hand, one-time interactions without effects, seen() and
  visited() that only gate what a topic says. `seek` and `seek:branch`
  players play the story (answer choices, head for the way on).
- **Planned with stage B (2026-10-04, superseded by the entry above):** a `seen` state
  (people present in rooms the player enters, objects seen or examined;
  `seen('x')` in conditions) so conversations about anything encountered
  need no per-subject flags; `think` as a core verb with the protagonist's
  topics; examine yourself. See later_stages.md §3.
- **Planned with stage D (2026-10-04, not built yet):** moments (grouped,
  mutually exclusive options; required ones gate the scene's exits with a
  neutral option, optional ones lapse with an effect), computed time
  (actions that change nothing are free; `takes_time` overrides), and
  `weight: "major"` on line-changing interactions for the front end to show
  or not. See later_stages.md §5.

