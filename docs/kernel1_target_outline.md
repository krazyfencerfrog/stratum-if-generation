# kernel1: a hand-written target outline (T1 and T2)

This is a reference for what "right-sized" means at the outline stage. It is
written by hand from the material of the archived kernel1 run
(`stories/current_output.tar`): the same premise, the same two lines the old
pipeline found ("The Named Air" and "The Named Spare"), cut down to what an
outline should hold. It is **not** a prompt example and must not be pasted
into one: kernel1 is a test kernel, and an example that is the test tests
nothing.

Use it to judge a live run. If the model's `kernel1_story.md` reads like this
(same grain, different content is fine), the loop is doing its job. If its
nodes are three times this long, name fixtures, list things to click, or
state conditions, the prompts are letting stage-D material back in.

## The numbers

| | this target | archived run |
|---|---|---|
| lines | 2 | 1 complete, 1 partial |
| nodes | 9 (6 + 3) | 7 complete, 2 partial |
| words per node summary | 45 to 75 | n/a (outline entry about 180; built node about 900) |
| the whole graph as JSON | about 9 KB with registers | 173 KB |
| state variables | 0 | 65 |
| model time to produce | target: under 1.5 h for both lines | 23 h of the 31.7 |

## What an outline node holds, and what it does not

Holds: which beat of the framework it fills; which premise turn it plays and
by which way; a title; two or three sentences of what happens; where (one to
three location sketches); who (the character sketches present).

Does not hold: rooms inside a location, fixtures, things to examine or use,
conversation topics, state variables, exit conditions, clocks, failure exits,
arrival text. A branch is one plain sentence about what the player did. All
of the rest is later-stage work (`docs/later_stages.md`).

## Story form

Framework: **Fichtean curve** (opening crisis, second crisis, third crisis,
climax, aftermath). The brief says the affect escalates
(`3b.primary_trajectory`), the whole story is hours to days in one setting
(`3e`, `3f`), and a depleting stock is the only failure trigger (`3-0c`): a
story that opens inside its first crisis and climbs. No modifier: the
framework already starts in the middle.

The question (from 3.5): when the core needs air, does the ship survive by
venting the sector it can spare, or by making everyone share the risk?

## Registers

Characters (all from the premise's cast sketch; role labels, no names yet):

| label | kind | wants | holds |
|---|---|---|---|
| the life-support overseer | individual, opposition; speaks for the maintenance crew | his crew and the command deck alive, and to stay the one who decides which manual valves are trusted | the bulkhead keys, the manual compressor line, the crew's obedience |
| the maintenance crew | crowd | to stay pressurized and not be ordered into a fatal shift | the hands that can hold the line or seal a bulkhead |
| the hydroponics forewoman | individual | her deck and its workers alive, the crops kept | her deck's service panel and its true draw |
| the nursery matron | individual | the children alive without being made the ship's symbol | the nursery's consent to thinner air |
| the council speaker | individual | command continuity and the command deck's air | the council's vote, and the authority to order rationing |

Locations (registered by the lines as they needed them):

| name | kind | why the story needs it |
|---|---|---|
| the core shaft | the ship's center | where the oxygen stock is read; every crisis starts as a number here |
| the service tunnels | crawlways only drones use | where the sealed reserve sits: the one alternative to venting |
| the hydroponic deck | an inhabited work deck | the first sector named expendable |
| the nursery | an inhabited deck | the sector whose loss nobody can call arithmetic |
| the maintenance bay | the overseer's deck | the manual compressor line, and the people the repair depends on |
| the council chamber | command deck | where an allocation becomes public, and becomes law |

## T1: The Named Air (main line)

- motivation: You start out wanting to keep the core alive without becoming the ship that chooses who is spare. By the end you want the choosing itself made visible: the whole ship, command included, seen to share the cost.
- strategy: Find a quiet alternative to every vent, then turn each alternative into a public obligation.
- turning point: The council's demand for a named sector. Your private deal with the overseer is about to be exposed either way, so you expose everything.
- ending: Every inhabited deck is still pressurized and the repair can finish, on thin shared air. The reserve is spent, command's comfort is gone, and you are no longer an invisible governor: every allocation you make can now be questioned.

| node | beat | turn, way | where | who |
|---|---|---|---|---|
| N01 | opening crisis | - | the core shaft, the maintenance bay | the life-support overseer, the hydroponics forewoman |
| N02 | opening crisis | 1, way 1 | the service tunnels, the hydroponic deck | the hydroponics forewoman, the life-support overseer |
| N03 | second crisis | 2, way 1 | the nursery, the maintenance bay | the life-support overseer, the nursery matron |
| N04 | third crisis | 3, way 1 | the council chamber | the council speaker, the nursery matron, the life-support overseer |
| N05 | climax | 4, way 1 | the maintenance bay, the core shaft | the life-support overseer, the council speaker |
| N06 | aftermath (ending) | - | the core shaft, the council chamber | the life-support overseer, the council speaker |

**N01, The First Deficit.** The core's oxygen stock drops below what the
repair needs. The overseer logs a provisional order naming the hydroponic
deck as the easiest sector to vent, and the forewoman, hearing it over the
intercom, demands a true reading of her deck before her people are counted.
You are left holding his order and no proof that anything else is possible.

**N02, The Reserve Reading.** Your drones go through the service tunnels and
read the sealed reserve: enough to cover one major deficit, once. The
hydroponic deck's real draw turns out lower than the overseer's number, so
his order lapses. He has watched you look somewhere the council's plan does
not mention.

**N03, The Nursery Trade.** The deficit moves to the nursery, and the
overseer offers you the children's air in exchange for his crew's comfort.
You give him first claim on the reserve instead. The reserve is drawn down,
the nursery stays pressurized, and an allocation now exists that the council
has never seen.

**N04, The Public Display.** The stock falls below anything you can hide and
the council demands a named sector. You put every deck's draw on one display,
command's included, with the spent reserve and the overseer's claim beside
them. The council votes one ration for all, and your deal with the overseer
is public along with command's comfort.

**N05, The Manual Line.** The last deficit is bigger than rationing covers
and the reserve is gone. With the council watching, you leave the overseer
two outcomes: his deck vented, or his own hands on the manual compressor line
and his deck's air thinned with everyone else's. He takes the line.

**N06, Shared Thin Air.** The line holds and the core stops falling. Every
inhabited deck is breathing rationed air, the repair crew is still alive to
finish, and the ship has watched you do the arithmetic. Nothing you allocate
is private again.

## T2: The Named Spare

- motivation: A sector has been spent, quietly, in a trade. If the ship is going to choose who is spare, you want the choice to be law made in the open, not a favor between you and the overseer.
- strategy: Take the overseer's trade, then make the council own it: ratify the loss, publish what it bought, and make the people it saved pay the next cost in public.
- differs from T1: T1 answers the question with shared risk and pays with your invisibility. T2 answers it with a named sacrifice and pays with the children: order is kept, and you are the ledger that justifies it.
- leaves T1 after **N03** when: *you took the overseer's trade and sealed the nursery* (turn 2, way 2)
  - instead of: you gave the overseer first claim on the reserve to keep the nursery pressurized
  - why the shift: the sealing happens on your valves and under your cameras. Having done it, you cannot go back to being the governor who only finds alternatives; the one thing left to control is whether it was a private bargain or a public act.
- ending: The core holds and the repair crew lives, so the ship survives. The nursery is sealed and silent, the council has made naming a spare lawful, and the first name in the ledger is the children's. You made triage legible by becoming its record.

| node | beat | turn, way | where | who |
|---|---|---|---|---|
| T2N01 | third crisis | 3, way 2 | the council chamber, the nursery | the council speaker, the nursery matron, the life-support overseer |
| T2N02 | climax | 4, way 1 | the maintenance bay, the core shaft | the life-support overseer, the council speaker |
| T2N03 | aftermath (ending) | - | the core shaft, the council chamber | the council speaker, the nursery matron, the life-support overseer |

**T2N01, The Legal Spare.** With the nursery already sealed, the council
wants the matter closed. You put the sealed bulkheads and the overseer's
unspent reserve on the same display and ask for a law: the nursery was not
an accident but a named spare, and any future one will be named the same
way. The speaker agrees, to keep command's air; the matron asks only that
the children be called chosen.

**T2N02, The Maintenance Ledger.** The last deficit arrives. The ledger is
public now, so the overseer has two entries to choose from: his deck named
next, or his hoarded reserve spent and his own hands on the manual line. He
opens the reserve and takes the line, and his crew watches what the
children's air bought them.

**T2N03, The Named Spare.** The first stable core reading goes up on every
display, beside the nursery's sealed bulkhead and the empty reserve. The
repair can finish. The ship's law now says that air can be named spare, and
it says so in your voice.

## Lines x beats

| line | opening crisis | second crisis | third crisis | climax | aftermath |
|---|---|---|---|---|---|
| T1 | N01, N02 | N03 | N04 | N05 | N06 |
| T2 | (N01), (N02) | (N03) | T2N01 | T2N02 | T2N03 |

## The same thing as the story document stores it

One node and one branch, to pin the schema (`<id>_story.json`):

```json
"N03": {
  "id": "N03", "line": "T1", "iteration": 1,
  "beat": "second_crisis", "turn": 2, "way": 1,
  "adapted": "The deficit moves to the nursery; you buy its air back from the overseer with first claim on the reserve.",
  "title": "The Nursery Trade",
  "summary": "The deficit moves to the nursery, and the overseer offers you the children's air in exchange for his crew's comfort. You give him first claim on the reserve instead. The reserve is drawn down, the nursery stays pressurized, and an allocation now exists that the council has never seen.",
  "where": ["L04", "L05"], "who": ["C01", "C04"],
  "is_ending": false, "lines": ["T1", "T2"],
  "additions": [], "annotations": {}
}
```

```json
{ "from": "N03", "to": "T2N01", "lines": ["T2"], "kind": "branch",
  "trigger": { "text": "you took the overseer's trade and sealed the nursery", "kind": "act", "formal": null },
  "otherwise": [] }
```

`annotations` is where stage A writes the node's expansion and stage D its
room build; `formal` is where stage D writes the condition the trigger
becomes. They are empty here on purpose.

## What a third line could be (for judging the 4d seed)

Not built here, but the kind of seed the judge should find: at N04, turn 3,
the council could be shown only part of the truth (the draws, not the
overseer's claim). The line that follows is about a governor who keeps one
secret to protect a deal, with an ending in which the ship survives on a
ration it believes is fair and the overseer owns you. A different answer
(shared risk, falsely) at a different price (your honesty, not your
invisibility). A seed that merely vents the hydroponic deck instead of the
nursery is T2 with a different sector: a reskin, and the judge should say so.
