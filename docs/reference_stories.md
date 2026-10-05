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
