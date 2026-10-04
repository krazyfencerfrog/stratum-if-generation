# Stage A worked example: kernel35, the ghost on the canal boat

Hand-written emulation of what stage A (`docs/later_stages.md` §2) should
produce, written in the local model's voice from the real kernel35 outline
(`stratum-compare/fable5/stories/kernel35_f5/`, Fable 5 branch, 2026-10-04).
It is a design check, not a prompt example: never paste it into a prompt.

Kernel: "A ghost story that is funny and frightening in equal measure. You
inherit a decrepit canal boat with a resident ghost who insists he is still
the captain and will not let the boat leave its mooring. Your only living
companion is your brother-in-law, who came to help you sell it and who wants
his money back more than he wants you safe. I want the ghost to be a real
character, scary when he needs to be, and I want the boat to actually go
somewhere."

The outline it builds on: three lines over seven beats.
- T1 "The Salute at Dawn" (main): N01 Before Dawn, N02 The Snapped Line,
  N03 The Fee Withheld, N04 The Crack in the Dark, N05 The Provisional Sale,
  N06 The Tea Salute, N07 The Lowered Price. Ending: the boat moves under
  the dead captain's name; your authority is the price.
- T2 "The Chain Mark": leaves after N02 (you threw the spare line to the
  lock chain); the boat goes through on your signature; the captain is left
  at the mooring.
- T3 "The Number for the Ghost": leaves after N04 (you took the crack's
  price from Lazlo's ledger); the boat is hauled into the side cut; Lazlo
  walks off with the buyer's cash.

---

## The protagonist (new 3.5a fields, emulated)

Added after the first draft of this example, when it turned out "you" had no
history, need or ties, so the protagonist's arc described what you do, not
who changes. The premise now defines "you" (in between a blank player insert
and a fixed character: a defined situation and relationships, with how you
feel left to the player):

```json
"protagonist": {
  "name": "Teodor Fairweather",
  "gender": "m",
  "who": "You are the new owner of a narrow canal boat, standing on its stern deck before dawn with your brother-in-law already counting the cost of every rope.",
  "history": "Your wife grew up on this boat with her grandfather, the captain; she died last winter and left it to you, and you have not been aboard since her funeral.",
  "wants": "to get the boat under way and sold before dawn",
  "need": "to stop paying for a life that ended with her, without feeling you have sold the last of her",
  "ties": [
    {"who": "your brother-in-law", "what": "your late wife's brother, the last of her family who still calls you, and the one who lent you the money for her funeral"},
    {"who": "the ghost captain", "what": "the man in the photographs she kept on the cabin wall, whom you never met and she never stopped talking about"}
  ],
  "open": "whether you let her family's boat go, or find a way to keep some of it",
  "can_do": "inspect the boat, untie and retie the mooring line, take the helm, sign or refuse the sale papers, pay or refuse the lock fees, answer the ghost directly",
  "cannot_do": "make the boat leave its mooring or enter a lock until the captain's condition on the water is met"
}
```

The name is assigned in Python from the story's pool (modern), before the
cast, so nobody shares a part of it; "you" stays "you" in every summary, and
"Teodor" is what Lazlo calls you when he is angry and what the captain
refuses to call you until the end. Gender and history are decided by the
pipeline: a defined person, not a blank (a different "you" is a different
story).

With that, the same events mean more: Lazlo's money is the funeral loan, so
his ledger is grief and debt at once; the captain's test is a grandfather
deciding whether his granddaughter's husband is fit for her boat, and "Your
watch, mate" is acceptance into a family that is gone. The arcs below are
written against this protagonist.

---

## A0. Arc cast

| character | tier | why (computed unless noted) |
|---|---|---|
| Lazlo Brandt, your brother-in-law | arc | opposition; breaking point; standing varies (stands on T1/T2, lost on T3) |
| Lake Kaur, the ghost captain | arc | breaking point; standing varies (aboard on T1/T3, left at the mooring on T2) |
| Pell Szeto, the lock keeper | supporting | in 5 nodes on 3 lines, stance toward you shifts (judged: "the gates are his and his patience runs out") |
| Stellan Ilunga, the towpath keeper | supporting | in 6 nodes on 3 lines, keeper of the salute rule (judged: "he decides whether the old way is honored") |

Two arc characters, two supporting, no functional. The arc cast is closed.

---

## A1. Arc plan

```json
{
  "state_visibility": {
    "mode": "observed",
    "why": "You are a newcomer who does not know the canal's rules, so nobody tells you where you stand; but both arc characters keep visible records. Lazlo writes everything in his ledger, and a reader can see his nerve in what he writes down. The captain answers through the boat itself: the lamp, the timbers, the wheel. The player reads the ledger and the boat."
  },
  "protagonist": {
    "starts": "You want the boat sold before dawn so you can stop paying for a life that ended with your wife, and you have not let yourself grieve aboard it.",
    "lines": {
      "T1": {"arc": "From owner to keeper: you let her grandfather keep his boat and you keep a place on it; selling becomes letting go without losing her.", "turn_at": "N04", "resolves": "You stand on a moving boat that is no longer only yours, under her family's captain, and that is the part of her you keep."},
      "T2": {"arc": "From inheritor to owner: you take the chain and the papers and close the account; the boat becomes a thing you sold.", "turn_at": "N02", "resolves": "The boat is yours on paper and moving, and the last of her family's ghosts is left on the bank."},
      "T3": {"arc": "From grief to arithmetic: the ghost becomes a number, and so does the brother-in-law who lent you her funeral money.", "turn_at": "N04", "resolves": "The sale is done, the fear is gone, and so is the last of her family that came to help you."}
    }
  },
  "arcs": {
    "C01": {
      "character": "Lazlo Brandt",
      "starts": "Lazlo lent you the money for his sister's funeral and wants it back; he believes the boat is the debt, he is afraid of the ghost, and he hides both the fear and the grief in arithmetic.",
      "moments": [
        {"node": "N01", "lines": ["T1", "T2", "T3"], "kind": "demonstration", "change": "He writes the ghost's delay up as a surcharge: fear turned into a line item."},
        {"node": "N02", "lines": ["T1", "T2", "T3"], "kind": "test", "change": "When the line snaps he screams about the fuel, not about you; whether he trusts your hand on the helm starts here."},
        {"node": "N04", "lines": ["T1", "T3"], "kind": "turn", "change": "He wakes to water in the dark cabin and asks for a price on the fear. The ledger stops being a shield and starts being the only thing he trusts."},
        {"node": "N05", "lines": ["T1"], "kind": "turn", "change": "He signs the provisional note: the moment he would rather lose the boat than stay frightened."},
        {"node": "N06", "lines": ["T1"], "kind": "demonstration", "change": "He spends the lock fee on tea and fuel and will not sit in the cabin again."}
      ],
      "forks": [
        {"after": "N04", "by": "line", "how": "On T3 his ledger becomes the plan, and he leaves with the cash; on T1 the ledger becomes a receipt for what the boat cost."},
        {"after": "N05", "by": "state", "how": "Whether he is still aboard when the boat moves depends on lazlo_nerve."}
      ],
      "resolutions": [
        {"lines": ["T1"], "state": "Still aboard, paying the lowered price himself, and laughing about the receipt he will never get.", "needs": "lazlo_nerve held: you covered for his fear at least twice"},
        {"lines": ["T1"], "state": "Steps off at the lock with his ledger and lets you finish alone; the sale is done but he will not say goodbye.", "needs": "lazlo_nerve lost: you mocked or exposed his fear more often than you covered it"},
        {"lines": ["T2"], "state": "Beside you on the papers as co-signer, satisfied, the chain mark priced and paid.", "needs": null},
        {"lines": ["T3"], "state": "Walks down the towpath with the buyer's cash and his ledger, leaving the boat and you.", "needs": null}
      ],
      "state": {"name": "lazlo_nerve", "meaning": "how far Lazlo believes he can stay aboard without losing his money or his mind", "moves": "up when you take his fear seriously or give his ledger something it can record; down when you laugh at his fear, spend his cash without asking, or side with the ghost against him"}
    },
    "C02": {
      "character": "Lake Kaur",
      "starts": "The captain sees his granddaughter's husband as a stranger who has not earned her boat; he will not let it move until the water has been honored by someone who knows how.",
      "moments": [
        {"node": "N01", "lines": ["T1", "T2", "T3"], "kind": "demonstration", "change": "He says the water is not ready and neither are you: the rule is stated, not explained."},
        {"node": "N02", "lines": ["T1", "T2", "T3"], "kind": "test", "change": "He snaps the line himself to see what you will do with a drifting boat."},
        {"node": "N04", "lines": ["T1", "T3"], "kind": "reveal", "change": "He shows you the crack only the dark reveals: the boat has been dying for years, and he has been keeping it afloat."},
        {"node": "N06", "lines": ["T1"], "kind": "turn", "change": "The salute is made with tea, badly, and he accepts it: he names the course."}
      ],
      "forks": [
        {"after": "N02", "by": "line", "how": "On T2 you choose the chain over his order and he becomes a captain left on the bank."},
        {"after": "N06", "by": "state", "how": "Whether he names you crew or only tolerates you depends on captain_regard."}
      ],
      "resolutions": [
        {"lines": ["T1"], "state": "Names you first mate, the title he gave her when she was nine, and gives you the helm for the last mile.", "needs": "captain_regard earned: you answered his orders in his own terms at least twice"},
        {"lines": ["T1"], "state": "Stands at the helm and names the course without once looking at you.", "needs": "captain_regard not earned"},
        {"lines": ["T2"], "state": "Left at the mooring, saluting a boat that no longer answers him.", "needs": null},
        {"lines": ["T3"], "state": "A shadow in the porthole of a boat sold by the number, aboard but unnamed.", "needs": null}
      ],
      "state": {"name": "captain_regard", "meaning": "how far the captain sees you as crew rather than a usurper", "moves": "up when you answer his orders in nautical terms, keep his rules, or ask him about the boat's history; down when you treat him as a pest, cut lines without leave, or let Lazlo price him"}
    },
    "C03": {
      "character": "Pell Szeto",
      "light": true,
      "starts": "Pell wants the lock cleared and his shift over; to him you are a scheduling problem.",
      "moments": [
        {"node": "N02", "lines": ["T1", "T2", "T3"], "change": "He nearly jams the gates on the drifting boat and decides you are trouble."},
        {"node": "N06", "lines": ["T1"], "change": "He releases the gates for a salute he does not believe in, and is impressed in spite of himself."}
      ],
      "ends": {"T1": "Waves you through and logs the passage as 'weather'.", "T2": "Takes the fee and asks no questions.", "T3": "Takes the buyer's cash for the fee and wants nothing more to do with the boat."}
    },
    "C04": {
      "character": "Stellan Ilunga",
      "light": true,
      "starts": "Stellan keeps the canal's old rules and expects a newcomer to break them.",
      "moments": [
        {"node": "N04", "lines": ["T1", "T3"], "change": "From the bank he warns that the water will not clear until the defect is named; he is the first to treat you as someone who might listen."},
        {"node": "N06", "lines": ["T1"], "change": "He steps back from the towpath: the salute was clumsy, but it was made."}
      ],
      "ends": {"T1": "Steps back and lets the boat pass, the old rule kept.", "T2": "Names the salute for you when you sign, though nobody makes it.", "T3": "Hauls the boat into the side cut himself, the rule broken and him the one who broke it."}
    }
  },
  "setup_payoff": [
    {"setup_node": "N01", "payoff_node": "N06", "what": "Lazlo's tea, which he guards like a fee, becomes the salute.", "lines": ["T1"]},
    {"setup_node": "N04", "payoff_node": "N07", "what": "The crack only the dark shows is where the hull leaks as the boat finally moves.", "lines": ["T1"]}
  ],
  "irony": {"type": "situational", "device": "The man who prices everything is the one whose fear cannot be priced; the captain who will not let the boat leave is the only reason it still floats."}
}
```

---

## A2. Node expansion, line T1

Minor nodes hang between the major ones on T1's path. Ids: the major node,
then a letter (N01a comes after N01). Opportunities show their options and
what each does to state, in plain words; under `observed` visibility nothing
says "Lazlo will remember this", the effect shows up in his ledger and the
boat.

```json
{
  "line": "T1",
  "minor_nodes": [
    {"id": "N01a", "after": "N01", "kind": "revelation", "serves": ["C02"],
     "summary": "In the wheelhouse drawer you find the captain's logbook. The last entry is forty years old and ends mid-sentence: 'Water not ready. Will wait.' The wheel turns a quarter as you close the drawer.",
     "image": "a logbook open on the last line, ink faded brown", "who": ["Lake Kaur"]},

    {"id": "N01b", "after": "N01a", "kind": "opportunity", "serves": ["C01"],
     "summary": "Lazlo Brandt shows you the ledger: the boat already owes him for rope, a lock fee and 'nuisance'. He waits to see what you make of the last line.",
     "image": "the word 'nuisance' underlined twice", "who": ["Lazlo Brandt"],
     "options": [
       {"do": "Ask him what a nuisance costs, and let him tell you", "effect": "lazlo_nerve up: his fear has a column now"},
       {"do": "Tell him the ghost does not take payment", "effect": "lazlo_nerve down: you laughed at the one thing keeping him calm"}
     ]},

    {"id": "N02a", "after": "N02", "kind": "opportunity", "serves": ["C02", "C03"],
     "summary": "The boat has stopped short of the gates. Pell Szeto shouts about the schedule from the lock-side while the captain waits at the wheel for your report, as if you were his crew.",
     "image": "the wheel still turning slowly with no hands on it", "who": ["Lake Kaur", "Pell Szeto"],
     "options": [
       {"do": "Report to the captain: 'Boat held, sir, stern to the lock'", "effect": "captain_regard up: you answered in his terms"},
       {"do": "Shout back to Pell Szeto that the boat stopped itself", "effect": "captain_regard down: you made him a malfunction"}
     ]},

    {"id": "N03a", "after": "N03", "kind": "demonstration", "serves": ["C01"],
     "summary": "Lazlo Brandt counts the fuel cash twice in the cabin and puts a note under the lamp: 'IOU: fear, one night.' He tears it up when he sees you looking.",
     "image": "a torn IOU in the lamplight", "who": ["Lazlo Brandt"]},

    {"id": "N03b", "after": "N03a", "kind": "opportunity", "serves": ["C04"],
     "summary": "On the towpath Stellan Ilunga asks whether you know why the old crews saluted the water. He does not wait long for an answer.",
     "image": "Stellan's lantern swinging over the black water", "who": ["Stellan Ilunga"],
     "options": [
       {"do": "Admit you don't, and ask him", "effect": "Stellan's stance warms; he will name the salute later on lines that reach N06 or T2N04"},
       {"do": "Say it's superstition", "effect": "Stellan's stance cools; he steps back at N06 only after the salute is made"}
     ]},

    {"id": "N04a", "after": "N04", "kind": "opportunity", "serves": ["C01", "C02"],
     "summary": "The crack is leaking into the cabin. The captain stands over it, waiting; Lazlo Brandt is in the doorway in his coat, ledger under his arm, asking what this is going to cost.",
     "image": "dark water spreading toward Lazlo's shoes", "who": ["Lake Kaur", "Lazlo Brandt"],
     "options": [
       {"do": "Ask the captain how long the boat has been dying", "effect": "captain_regard up: you asked about his boat, not your sale"},
       {"do": "Tell Lazlo it's fine and steer him back to bed", "effect": "lazlo_nerve up, captain_regard down: you covered Lazlo's fear and dismissed the captain's warning"},
       {"do": "Laugh, and tell Lazlo to put it in the ledger", "effect": "lazlo_nerve down: you made his fear the joke"}
     ]},

    {"id": "N05a", "after": "N05", "kind": "demonstration", "serves": ["C02"],
     "summary": "As Lazlo Brandt signs the provisional note, every lamp aboard dims at once and the timbers groan along the length of the boat. The captain does not appear. He does not have to.",
     "image": "the signature drying as the lamps go down", "who": ["Lazlo Brandt", "Lake Kaur"]},

    {"id": "N05b", "after": "N05a", "kind": "opportunity", "serves": ["C01"],
     "summary": "Lazlo Brandt puts the pen down and says, very quietly, that he would rather lose the boat than spend another night on it. He is shaking.",
     "image": "Lazlo's hand flat on the papers to stop it shaking", "who": ["Lazlo Brandt"],
     "options": [
       {"do": "Sit with him and say nothing for a while", "effect": "lazlo_nerve up: you saw the fear and did not price it"},
       {"do": "Tell him he signed it, he can live with it", "effect": "lazlo_nerve down"}
     ]},

    {"id": "N06a", "after": "N06", "kind": "resolution", "serves": ["C03", "C04"],
     "summary": "The gates swing open. Pell Szeto writes 'weather' in the lock log and does not meet your eye; on the towpath Stellan Ilunga lowers his lantern to the water, the old salute returned.",
     "image": "the lock log open on the word 'weather'", "who": ["Pell Szeto", "Stellan Ilunga"]},

    {"id": "N07a", "after": "N07", "kind": "resolution", "serves": ["C01"],
     "variants": [
       {"when": "lazlo_nerve held", "summary": "Lazlo Brandt sits on the cabin roof as the boat moves, adding up the lowered price, and asks the captain if he gives receipts. The captain does not answer. Lazlo writes 'no receipt' and laughs.", "image": "Lazlo's ledger open on 'no receipt'"},
       {"when": "lazlo_nerve lost", "summary": "At the last lock Lazlo Brandt steps off with his ledger and his coat and does not look back. The boat moves on without him; his seat on the cabin roof stays empty.", "image": "the empty cabin roof, a pen left behind"}
     ], "who": ["Lazlo Brandt"]},

    {"id": "N07b", "after": "N07a", "kind": "resolution", "serves": ["C02"],
     "variants": [
       {"when": "captain_regard earned", "summary": "Lake Kaur steps back from the wheel and says, 'Your watch, mate.' For the last mile the helm is yours, and the boat answers it.", "image": "your hands on the wheel, his cold beside them"},
       {"when": "captain_regard not earned", "summary": "Lake Kaur names the course and keeps the wheel to the end. You are a passenger on your own boat, and the water does not seem to mind.", "image": "the captain's back, rigid at the wheel"}
     ], "who": ["Lake Kaur"]}
  ],
  "state_moves_on_path": {
    "lazlo_nerve": {"up": ["N01b", "N04a", "N05b"], "down": ["N01b", "N04a", "N05b"]},
    "captain_regard": {"up": ["N02a", "N04a"], "down": ["N02a", "N04a"]}
  }
}
```

---

## What the real model would probably get wrong

From the runs so far, expect:
- **Options that are moral labels**, not acts ("be kind to Lazlo" / "be harsh"): the menu the pipeline exists to avoid. Each option has to be something done or said, and the computed check can only see that it exists, not that it is concrete.
- **Effects stated as numbers or scores** ("lazlo_nerve +1"), which is fine for the engine but wrong for an outline under `observed` visibility; and the reverse, effects so vague no condition can be written from them.
- **Demonstrations that tell instead of show** ("Lazlo is more afraid now").
- **Minor nodes that retell a major node's summary** with a different first line.
- **The same state moved by one opportunity only**, which breaks the "aggregate, never single" rule (caught by the computed check; the retry has to add another).
- **Supporting arcs pasted onto every node** they appear in.

## What writing it showed about the design

- **The kernel's own structure made state visibility easy** (a ledger, a boat that reacts). Not every story will hand us that; A1's `why` should name the device the player reads, or say there isn't one.
- **Opportunities naturally serve two arcs at once** (N04a pits Lazlo against the captain). That is good, and the schema should allow it (it does: `serves` is a list).
- **Resolution variants multiply**: two arc characters with two variants each is four endings-within-the-ending on one line. Fine at outline level; stage D will need to compose them, not enumerate them.
- **Light arcs fit in one or two nodes**: Pell and Stellan read as people with one minor node each (N03b, N06a); that seems the right weight.
- **T1 grew from 7 major nodes to 7 + 12 minor**: about 40-50 words each, so the line is still under 1,000 words of outline. The per-line packet for A2 is the whole line's major nodes plus the arc plan: around 15-20 KB, comparable to today's 4b.
- **Open: should a state fork be able to change the ENDING node itself** (a different N07), or only add resolution variants after it? Here only variants; a strong enough pattern (captain_regard very low across every opportunity) could plausibly earn an accumulated line shift instead.
