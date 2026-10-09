# Reference stories: the pipeline against human craft

Started 2026-10-04. The question: where do our premises and outlines fall
short of what a skilled author does with the same request? Five
public-domain short stories, one per genre we test, each turned into a
kernel that asks for what the story delivers without giving away how
(`tests/kernels/reference/`). The pipeline runs each kernel; we compare its
premise and main line with the author's structure, written below in the
pipeline's own terms, and the 4e judge scores both (`generator/reference.py`).

What it can and cannot show:
- The human stories are linear, so they compare with our MAIN LINE only.
  Branching has no human counterpart here (the judge's agency axis is not
  comparable).
- The comparison is at the level of structure: escalation, what is planted
  and paid off, the cast's edges and how they collide, set pieces, how the
  ending changes the world. Prose is not compared; our outline is not prose.
- The kernel is the user's request, not the story: the pipeline is free to
  build something different and better. The question is whether ours has
  the same QUALITIES (a turn that recontextualises, a running gag that pays
  off, a death that costs), not the same events.
- Judge calibration: if the judge scores the human outline no higher than
  ours, the judge cannot see what matters and its numbers should be
  discounted.

How to run: `python batch.py add reference/<id>` for each, `python batch.py
run`, then `python reference.py judge` and `python reference.py report`.
The human outlines (`*_reference.json`) are built by
`tests/kernels/reference/build_references.py`; texts checked against Project
Gutenberg (ebooks 14522, 1661 / sherlock-holm.es, 12122, 8147, 13415).

## The sheets

Each sheet is the story as a premise: who you are, the engine (pressure,
opposition, events, hidden truth), the turns, the cast, the ending world,
and then the craft points to look for in our output.

### ref_canterville: Wilde, The Canterville Ghost (1887)

- **You:** Virginia Otis, fifteen, the quiet one in a loud, practical
  American family. Want: nothing at first (the family's adventure is not
  hers). Need: to be the one who takes someone else's suffering seriously.
- **Pressure:** none in the usual sense; the comic engine is an INVERSION.
  The haunted are not frightened, and the ghost is the victim of the
  haunting. Every scare he attempts is met by a consumer product or a prank.
- **Opposition:** officially the ghost; in practice the twins, who drive him
  to despair.
- **Events (the world acts):** the stain returns every morning in a new
  colour; the ghost's set-piece nights (each a named role he has played for
  centuries); the counterfeit ghost; his withdrawal.
- **Hidden truth:** he starved to death walled up by his wife's brothers and
  has not slept in three hundred years; the prophecy on the library window
  says how he can rest.
- **Turns:** discover (the stain and the ghost are real); endure/confront
  (the comic battle, escalated by the twins); persuade/choose (Virginia and
  the ghost alone: the tone turns); rescue (the Garden of Death, offstage).
- **Cast edges:** the ghost is a vain actor wounded by bad reviews (comic
  and pitiable at once); the father answers terror with lubricant; the twins
  are relentless; the Duke is a quiet romantic thread for Virginia.
- **Ending world:** the ghost at rest (standing, in a sense), the house
  still, Virginia changed and silent about what she saw; the almond tree in
  blossom.
- **Craft to look for in ours:**
  1. A comic engine stated as a premise mechanism (inversion), not jokes
     laid on top.
  2. A running gag that becomes a plot device (the stain: the ghost stole
     Virginia's paints to make it, which is how their first conversation
     starts).
  3. A planted prophecy paid off (the window verse; the barren almond).
  4. A tonal turn carried by ONE character who refuses the group's attitude;
     she was set apart early (she alone is upset by the stain).
  5. The ending withholds (what happened in the Garden is never told).

### ref_speckled_band: Conan Doyle, The Adventure of the Speckled Band (1892)

- **You:** the detective. Want: a strange case. Need: (not an arc story)
  to read what the coroner missed.
- **Pressure:** a clock made of a wedding: Helen is engaged, as Julia was,
  and has just been moved into Julia's room.
- **Opposition:** Dr Grimesby Roylott: violent, brilliant, ruined, with a
  money motive that a document proves (the will) and a menace that a scene
  proves (the bent poker).
- **Events:** Roylott's visit to Baker Street; the whistle; the vigil.
- **Hidden truth:** a trained swamp adder sent through a ventilator, down a
  dummy bell-rope, onto a bed clamped to the floor; recalled by a whistle;
  fed from a saucer of milk.
- **Turns:** discover (Helen's account), confront (Roylott's visit),
  discover (the will), discover (the room: the physical clues), endure (the
  vigil in the dark), confront (the strike).
- **Clue design:** every fact needed is on the page before the answer
  (ventilator to another room, bell-rope to nothing, clamped bed, milk,
  looped lash, Indian animals, the whistle, the clang of the safe); a red
  herring with real weight (the gypsies; "band" read as a band of people,
  spotted handkerchiefs); the dying words mean both.
- **Ending world:** Roylott dead by his own weapon; Helen free.
- **Craft to look for in ours:**
  1. Clues that are physical objects in rooms the player can examine (this
     story is almost a room-based IF puzzle), each odd in a describable way.
  2. A red herring the victim herself believes.
  3. The antagonist met in person early, with a demonstration of menace.
  4. A motive proved by a document, not stated.
  5. A climax the protagonist causes, where the plan recoils on its author.

### ref_monkeys_paw: W. W. Jacobs, The Monkey's Paw (1902)

- **You:** Mr White, an ordinary man who wants a little more (the last of
  the mortgage). Need: to accept what cannot be undone.
- **Pressure:** the paw itself: every wish is granted, and fate punishes
  the wisher. The dread is built entirely from things the reader is told
  early (the first man's third wish was for death).
- **Opposition:** fate; then, in the third part, your wife's grief.
- **Events:** Morris's warning; the wish answered by the firm's
  compensation; the knocking.
- **Hidden truth:** what is outside the door (never shown).
- **Turns:** trade (the first wish), endure (the news), choose_whom /
  confront (the second wish, forced by your wife against your fear),
  rescue/escape (the third wish, in the dark, against the bolt).
- **Structure:** three parts, three wishes; each wish answers the previous
  one; the comic first part (Herbert's jokes) is the setup for every
  horror (the money "in a bag on the bed", the face in the fire).
- **Ending world:** Herbert dead and kept dead; the money paid; a marriage
  broken by what each wanted.
- **Craft to look for in ours:**
  1. Horror from a rule stated early and obeyed exactly (the exact sum).
  2. Jokes early that come back as horror.
  3. The worst thing kept offstage; the knocking and the bolt do the work.
  4. The companion (the wife) turns into the pressure: her love is the
     danger.
  5. A small, closed cast and one room; dread without spectacle.

### ref_man_who_would_be_king: Kipling, The Man Who Would Be King (1888)

- **You:** Peachey Carnehan, loafer, loyal to your partner. Want: to be
  king. Need: (in the end) to keep faith with Dravot whatever it costs.
- **Pressure:** the contract (no liquor, no women, stand by each other):
  a rule set in scene two whose breaking is the catastrophe.
- **Opposition:** the country itself, then the priests, then Dravot's own
  vanity.
- **Events:** the valley battle; the Masonic mark; the wedding.
- **Hidden truth:** the priests' belief rests on Dravot being a god; a
  single drop of blood ends it.
- **Turns:** trade/sabotage (the con to get in, rifles under toys),
  confront (the first battle), conceal (the Masonic god), choose (the
  marriage, against the contract), escape (the bridge).
- **Ending world:** Dravot dead, Billy Fish dead, you crucified and broken,
  the kingdom gone, a crowned head as the only proof.
- **Craft to look for in ours:**
  1. A written contract stated early whose terms are the plot.
  2. The rise made specific and plausible by craft (rifles, drill,
     Freemasonry), so the fall is earned.
  3. The partner's breaking point named early (women) and reached.
  4. A frame (the newspaperman) that makes the ending a story told.
  5. Forgiveness at the bridge: the partnership is the heart, as asked.

### ref_lady_with_the_dog: Chekhov, The Lady with the Dog (1899)

- **You:** Gurov, near forty, a practised and contemptuous seducer. Want: a
  light affair. Need: to love, for the first time, and to bear it.
- **Pressure:** none external; time and absence. The engine is the gap
  between what he thinks he feels and what he does.
- **Opposition:** respectability, and the two marriages; her husband is
  barely a person ("a flunkey").
- **Events:** her husband's letter summoning her home; winter in Moscow; the
  theatre.
- **Hidden truth:** (in him) she was never an episode.
- **Turns:** persuade (the meeting through the dog), endure (her shame and
  his indifference), endure (Moscow: she will not fade), confront (going to
  S., the fence), conceal (the double life).
- **Ending world:** nothing resolved: two people who now love, two lives,
  and the hardest part beginning.
- **Craft to look for in ours:**
  1. Small, exact images doing the emotional work (the watermelon, the
     sturgeon, the grey fence, grey hairs).
  2. The protagonist's view of women and love stated early and reversed.
  3. The turning point as something NOT done (he cannot forget; he cannot
     stay away), not a big choice.
  4. An ending that refuses resolution and is still an ending.
  5. Almost no plot events; the change is entirely inside, shown through
     what he does.

## Results

First pass 2026-10-05, all five stories (code cba46c3; Lady with the Dog ran
again after a one-off GPU library error). Scores
are the 4e judge's six axes; agency is not comparable (the human stories are
linear), so the second total leaves it out.

| story | pipeline | human | pipeline w/o agency | human w/o agency |
|---|---|---|---|---|
| Canterville Ghost | 21 | 24 | 17 | 20 |
| Monkey's Paw | 23 | 28 | 19 | 24 |
| Speckled Band | 22 | 20 | 19 | 18 |
| Man Who Would Be King | 28 | 24 | 23 | 21 |
| Lady with the Dog | 27 | 22 | 22 | 20 |

The judge prefers the human outline twice and ours three times. Read against the
sheets, ours misses the core of all four, including the two it scored
higher, so **the judge cannot see the qualities below and its totals should
be discounted** for this kind of question. Ours also runs long: 76-87 words
a node against 45-51 for the human outlines, with 2-16 repeated phrases
against none.

### Point by point

**Canterville** (the closest). The comic inversion is there as a premise
mechanism (1, yes): the family critiques the ghost's full show from the
sofa and leaves him "looking hurt". A child is set apart early and the
protagonist turns the tone ("the senior resident", 4, partly). Missing: no
running gag becomes a device (the dish rota recurs but does nothing, 2);
no prophecy or plant pays off (3); the ending explains instead of
withholding (5); the ghost has no name, no history and no suffering, so
there is nothing to pity, and Wilde's turn needs pity.

**Monkey's Paw** (the furthest). The rule is vague: the paw "wants a want"
and "makes small things true in crooked ways", where the story's power is an
exact sum paid exactly (1, no). No jokes to come back as horror (2, no).
Nothing terrible happens offstage or on: the paw is burned and "the want you
had kept is gone" (3, no). The family is gone: the cast is one soldier who
falls asleep, so the companion cannot become the danger (4, no). Small cast
and one room (5), but dread without any event.

**Speckled Band.** Physical clues in rooms exist and are odd in describable
ways: a thread mark on a key bow, a whistle in a ring box, a silk fibre (1,
yes). No red herring (2, no). The antagonist is present from the first node
but polite, never shown to be dangerous (3, no). No motive at all, let alone
one proved by a document (4, no). The climax is a demonstration followed
by the villain leaving the room; nothing recoils on him (5, no). The
mechanism (smothering through a keyhole by thread) would not survive a
reader's second look.

**Man Who Would Be King.** A contract is everywhere, but its terms are
whose name is on it, burned or sealed: paperwork, not rules of conduct
whose breaking is the plot (1, no). The rise is ceremony (ford a river,
burn a name), not craft (2, no). The partner's breaking point is never
named; the conflict is billing (3, no). No frame (4, no). And no fall: the
ending is a shared kingdom on its first morning, so there is no bridge and
nothing to forgive (5, no). This is the judge's favourite (28/30).

**Lady with the Dog.** Small exact images do some of the work (rain on
the bench, a coat laid over the dog, the flat grey beach at low tide; 1,
partly), and the protagonist's view is stated early (2, stated but barely
reversed). But the whole arc happens inside one seaside week: there is no
absence, no Moscow winter, no affair that will not fade, no going to S.,
which is the story. The turning point is something said (a name, in every
node), where Chekhov's is something he cannot stop doing (3, no). The
husband is a present opposition where Chekhov's is barely a person. The
dog was given a human name by the name generator (fixed). The judge
preferred ours, 27 to 22.

### What the pipeline systematically misses

1. **The cost lands nowhere.** Every human story here kills or breaks
   someone (Herbert, Dravot, Roylott, the ghost's rest bought with
   Virginia's silence). Our endings are hollow or ambiguous states ("almost
   relief but not quite", a shared crown). No line pays an irreversible
   price.
2. **Nothing planted early pays off late.** The human stories run on
   setups: the first man's third wish, the window verse, the contract's
   terms, the jokes. Ours introduce and use things in the same node.
3. **Rules are vague where they should be exact**: magic, contracts and
   mechanisms are described by mood ("crooked", "hungry") instead of terms
   that can be obeyed to the letter.
4. **Antagonists are present but not dangerous**: no early scene shows
   what they will do (the bent poker).
5. **The cast shrinks or loses the person the story turns on** (the
   Whites' family; the ghost's history). The premise keeps the frame and
   drops the relationship.
6. **Paperwork** still turns up where the kernel names a document (the
   contract became a story about signatures).

These are design-level gaps for the premise (3.5a/3.5v) and the line plans
(4a/4c/4p), not prompt polish.

### What was changed (2026-10-05)

The cause of 1 was in the design: 3-0c models how the player can lose, and
with nothing asking what a story costs, "failure: none" became "no cost"
(Kipling's kernel: failure presence none, so no fall). The premise now
names a price, separate from the failure model and scaled to genre, and
some line's ending must pay it; setups are planted in an early beat entry
and paid in a later one (checked in Python); rules carry terms; the
opposition is shown at work early; ties are people and a Kernel's family
stays in the cast (the Monkey's Paw lost the family at 3.5a: ties named
"the cottage", turns involved only the soldier, the cast is seeded from
the turns); the judge must name what is lost, the plant and its payoff;
summaries are capped at 70 words. Re-run queued (stratum-compare/refs2).

## Second pass (2026-10-05, code c1faf1b)

Each story's saved phase 3 replayed, so the runs differ from the first pass
only from 3.4 on: the price, setups, rules, ties and judge changes above.
The human outlines were judged again by the changed judge.

| story | pipeline before | pipeline now | human now |
|---|---|---|---|
| Canterville Ghost | 21 | 24 | 19 |
| Monkey's Paw | 23 | 21 (does not count, see below) | 23 |
| Speckled Band | 22 | 24 | 26 |
| Man Who Would Be King | 28 | 17 | 19 |
| Lady with the Dog | 27 | 25 | 24 |

Every story now names a price and pays it on at least one line, and plants
two setups paid on the main line (one for the Paw); summaries are 64-69
words a node (76-87 before). Against the sheets:

**Monkey's Paw.** The family is back (a sister), and the price lands: after
the second wish she is well and looks at you "as if you are a person who
once mattered and no longer does". The rule is exact ("exactly three wishes,
each named specifically, granted technically true but emotionally wrong"),
**but the 3.5a rules example was the Paw itself** ("three wishes; each is
granted exactly as worded", against "the paw is hungry"), so that gain may
be copying. The example was replaced (f11c434) and the Paw is being re-run;
until then this row does not count. Still missing: jokes that return as
horror, the worst thing offstage.

**Canterville.** Both setups work as a running gag turned plot device: the
empty chair by the library fire and the Quiet Hours sign, planted at the
first dinner and paid when the family leaves the chair and hangs the sign
as a sincere rule (2 partly, 3 yes). The ghost had no name ("the ghost in
period costume" in 7 nodes), so still no history and nothing to pity;
ghosts who were people are now named (835a5a8). The ending still explains.

**Speckled Band.** One good physical clue (a hairline crack in the pane
that whistles when the wind finds it; 1, yes). But the hidden truth is an
accident (a draft and a heart spasm), so there is no villain, no menace, no
motive and nothing to recoil (3, 4, 5 no), and the price follows oddly from
it (the engagement is broken because the house kept the room sealed).

**Man Who Would Be King** (the drop). The rule is the contract, but its
terms are what happens to the paper (cut in halves, cannot be burned), not
what the signers may not do, which is Kipling's (no women, no liquor; 1,
no); paperwork is back to 0.9. The price is abstract ("the right of one of
you to walk away"); the judge: "dry and procedural", no glory. A death does
come on one line (the partner's body pays the kingdom's first debt). The
first attempt halted at 3.5v with the question's poles swapped; the fresh
loop passed.

**Lady with the Dog.** The dog works (a bridge between your hands, then
gone: the collar in your pocket, the judge's best image), but the second
setup was a message (your wife has the hotel hold your letters), and
letters, tickets and phones filled every node (paperwork 1.0). Setups are
now things to notice, not messages (c3f1d79). The price is a feeling ("the
old self"). It is still one seaside week: 3e capped the span at hours to
days on genre association, though the Kernel asks for something that
changes your life with no easy way out (left for the user to decide).

**What this pass shows.** The cost and the setups now exist in every story,
and two of them are real craft (the Paw's sister, Canterville's chair and
sign). What is still missing is mostly upstream of the outline: a hidden
truth with a culprit (Band), rules of conduct rather than paper mechanics
(King), a span longer than the setting (Lady), the opposition as danger.
The judge's totals moved in both directions and still do not track these.
A held-out check on four kernels never run or tuned on (6, 7, 36, 40) is
queued in stratum-compare/heldout, with the Paw re-run.

## Held-out check (2026-10-06, code f11c434)

Four kernels never run or tuned on (6 cozy, 7 pirates, 36 lodge horror, 40
frontier), with the prompt examples taken from no test kernel, plus the
Monkey's Paw re-run on the neutral rules example.

**Robustness: two of five finished.** The Paw and kernel40 halted at the
premise: the audit found something new each round ("wish-chances is an
abstract count", "the setup is used in the turn it is planted") and any
finding left after two repairs stopped the run; the craft checks added on
2026-10-05 made the checklist longer, so the halts became more frequent
(three of the last eight premises, with the King's). kernel7 failed in the
outline on a Python bug: the quartermaster, already in the cast, was named
as the voice of a new crowd and the check ignored it. Both fixed (6845e7a):
craft notes left after the last repair are kept, not a halt (a premise
that contradicts the Kernel or the brief still halts); a known individual
can take on a crowd's voice. The three are not yet re-run.

**Quality where it finished: the craft generalises.**

| kernel | judge | price paid | setups paid on main | rules with terms | paperwork |
|---|---|---|---|---|---|
| 6, cozy bakery | 26 | yes | 1 of 1 | 3 | 0.00 |
| 36, lodge horror | 22 | yes | 2 of 2 | 3 | 0.11 |

- kernel6: the price is scaled to the genre (the last of the season's
  singing flour goes to the village; the oven is quiet till spring), the
  rules are exact and charming (the flour rises only if you hum the last
  note; open the oven mid-lullaby and the batch cools), the notched rolling
  pin is planted and paid. One abstract node ("the Quiet Supper's rule
  stays open").
- kernel36: the strongest outline the pipeline has made. Exact rules (it
  speaks only in voices it has taken, slightly wrong in rhythm; it cannot
  cross unless a living hand opens a door), a death that costs (the
  injured friend dies, and at dawn his voice answers from the tree line),
  and both setups land (a joke New Year's voice memo returns as a frozen
  phone recording a living friend; the "self-locking" door turns by
  itself). The judge scored it 22, under the cozy story: more evidence its
  totals do not track this. The cast is four friends where the Kernel
  says six.

So far the price, setups and rules hold on stories nothing was tuned for;
the open question is how often a run finishes, which the fixes address and
a re-run of the three will show.

**Re-run of the three (2026-10-06, code 6845e7a): all finished.** The Paw
and kernel40 replayed their premises as accepted with one craft note each
kept; kernel7's crew took the quartermaster as its voice. Five of five
held-out jobs now produce an outline.

| kernel | price paid | setups paid on main | rules with terms | paperwork |
|---|---|---|---|---|
| Monkey's Paw (neutral rules example) | yes | 2 of 2 | 2 | 0.11 |
| 7, pirates | yes | 2 of 2 | 2 | 0.00 |
| 40, frontier | yes | 2 of 2 | 2 | 0.80 |

- **The Paw's exact rule survives the neutral example**: "three wishes,
  one per chance, each comes true in the smallest literal way that
  satisfies the wording; a wish cannot be unmade, only prevented by
  burning the paw before it is named". The family is there (a spouse) and
  the price is the same kind as before (safe, but no longer knows you). So
  the first pass's gain was not copying; it counts. The setups are weak
  (the soldier's eyes rolling back; a click that is not there).
- **kernel7**: the first mate checks the powder hatch from the first node
  and opens it to the frigate's men at the boarding, in front of the crew;
  he is buried at sea. The pirate articles have exact terms (a double share
  for the captain; the crew may vote to hang him). No paperwork.
- **kernel40**: the founder dies in the baron's office when the sheriff
  draws to stop the signing, and the town votes around his body. But
  paperwork is 0.8 (a contract, a fountain pen, a ledger, a deed) and its
  rule is a land claim on paper. With the King (0.9), this is the second
  story where a kernel that names a legal thing (water rights, a contract)
  turns its rules into paper mechanics.

## Judge validation (2026-10-06, code c283ba3)

The reading judge (4e, quoted facts) and the side-by-side comparison
(4f, both orders) on the outlines above: our five reference outlines and
the four held-out kernels, the human outlines, and ours against each human
outline, main lines only.

**The comparison sees what matters.** Over five stories and six questions
(cost, setups, opposition, turn, picture, play) the human outline won 28
of 30, every win holding with the outlines in both orders; 2 were splits
and ours won none. Its reasons are the sheets' craft points: the son's
death paid as the exact compensation (the Paw's turn), the bent poker (the
Band's menace), the contract's terms broken at the crisis (the King), the
woman who does not fade in Moscow (the Lady). One caution: the model knows
these stories (it said Canterville "leans on Wilde's beats"), so fame may
help the classics; the fair test is two pipeline outlines, which is what
it is for.

**The reading judge's facts discriminate weakly.**

| fact | ours (5 refs + 4 held-out) | human (5) | useful? |
|---|---|---|---|
| loss kind | person in all 9 | person 3, feeling 2 | no: a branching outline has a person lost somewhere |
| plants paid | 2-3 | 2-3 | no |
| reversal | none found in any | none found in any | broken: it missed the Paw's and the King's, which 4f named |
| announced | 1-4 (mean 1.9) | 0-2 (mean 0.8) | yes |
| abstractions | 1-6 (mean 3.4) | 2-5 (mean 2.6) | some |

Its best and worst notes stay good ("'takes his right to walk away' states
the cost as a legal abstraction"). So: decisions between versions go to
compare.py; the reading judge is a cheap diagnostic (announced craft and
abstractions, plus its notes), not a measure of quality; its reversal
question needs rework before anything reads it.


## Paperwork across kernels (2026-10-07, code 395645b)

The paper rule (`generator/paper.py`, f3d32e9) is one rule for every kernel: at most a quarter of a step's items on
paper (two more when the Kernel itself names a document), counted at 3.5a, 3.5b, the premise audit and 4b. It was
tested on three kernels besides the King, chosen because their kernels name no paper at all (the King's names a
contract; a fix aimed at it would have been a kernel patch). Outlines only, each against its earlier run; kernel37
(held-out, never run) from scratch. `stratum-compare/global1/` holds the runs and `paper_compare.py`.

| story | paperwork share before | now | premise paper items before / now | the paper checks fired |
|---|---|---|---|---|
| the King (Kernel: "sign a contract") | 0.89 | 0.62 | 13/30 / 7/30 | 3.5b, 4b |
| Lady with the Dog | 1.00 (letters, tickets) | 0.00 | 15/30 / 3/32 | never |
| kernel40 (frontier town) | 0.80 (ledger, deed, contract) | 0.12 | 22/30 / 4/30 | 3.5a (rule terms), 3.5b, 4b |
| kernel37 (heist, held out) | (first run) | 0.08 | - / 0/29 | never |
| Kipling's own outline | 0.25 | | | |

All four judge readings now find a person lost (three) or a bond (the King before), a reversal in the three new
runs, the opposition at work, and two or three setups paid. kernel37 needed no premise repair and halted nowhere.

What it shows: the pull toward paper is the model's (the Lady and kernel40 kernels name none, and their premises
were half paper), and counting it where story material is written works without any kernel-specific instruction.
Lady's drop came with the check never firing, so it belongs to everything since its earlier run (the shared
definitions, the repaired examples), and one run each is one sample. Two things to watch: the King's remaining
paper is the Kernel's own contract, used as a signing scene rather than as conduct (Kipling's contract is central
too, but as terms broken by a body), and the rule counts words, so renamed paper ("the brand book", "the
measurement book" in kernel40) passes it; if that grows, count what an item does (signed, filed, recorded) rather
than what it is called.
