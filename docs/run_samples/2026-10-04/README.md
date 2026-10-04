# Run samples, 2026-10-04

Real output of the pipeline on the local model (Qwen3.8 27B IQ3_XS through
Ollama, one RX 9070 XT), build limit 25 KB. Each directory holds the
outline (`*_story.md`, read first), the outline JSON, `*_eval.json` (the
computed metrics and the 4e judge), the brief, the accepted premise, the
premise audit loop and the run stats. Kernels are in `tests/kernels/`.

`paper` is the share of node summaries that turn on documents, fees and
signatures (`evaluate.py` paperwork_share, added today); `judge` is the 4e
total out of 30 (a weak signal: the same model grading itself).

## fable5_4651810/ : Fable's branch as delivered (fable_response_5)

Overnight 2026-10-03/04, whole pipeline from the kernel except where phase 3
was reused.

| kernel | what it is | time | lines / nodes | worlds | paper | judge | what we think |
|---|---|---|---|---|---|---|---|
| kernel31_f5 | epic fantasy quest with a party | 119 min | 4 / 17 | 3 | 18% | 22 | companions now have breaking points and real stakes, early forks; the magic is still vague ("the old bond", "the smoke of your village"); endings list things as lost |
| kernel32_f5 | comic dungeon crawl, cursed sword | 57 min | 3 / 10 | 3 | 20% | 24 | much better premise than 2026-10-03: the sword's voice is funny, set pieces, a tower that opposes; one of the best of the batch |
| kernel8_f5 | "surprise me" | 71 min | 3 / 9 | 3 | 33% | 26 | after the free-field placeholder fix (557edce) an eerie archive mystery with a strong identity; the judge's top score |
| kernel35_f5 | funny and frightening ghost on a canal boat | 140 min | 3 / 15 | 3 | 73% | 25 | real set pieces (the snapped line and the drift to the lock gates, the crack only the dark shows, the salute); funny voices; but the brother-in-law's ledger, fees and receipts are everywhere. The source of the stage A worked example and the engine's demo |
| kernel34_f5 | court intrigue, a regent's plan on a clock | 123 min | 3 / 10 | 3 | 40% | 19 | the events advance on their own as designed, but the stakes run through seating charts and oath wording: procedure standing in for drama; endings phrased as permutations of one sentence |
| kernel33_f5 | slow-burn romance at a seaside hotel | 123 min | 4 / 16 | 4 | 50% | 20 | four distinct worlds; half its nodes turn on a ledger or letters (not yet read in depth) |

## branch_c8e9028/ : fable-response-5 with this session's changes (batch3)

Code c8e9028: Fable's branch plus free-field placeholders, the protagonist
fields (history, need, ties, open, gender, a Python name), the 20-pool name
generator, the code-review fixes. Kernel35 replayed 3.4 onward from its
saved phase 3; kernels 38 and 39 (new today) ran whole.

| kernel | what it is | time | lines / nodes | worlds | paper | judge | what we think |
|---|---|---|---|---|---|---|---|
| kernel35_b3 | the same ghost-boat kernel | 66 min (from 3.4) | 3 / 9 | 3 | 89% | 24 | the new protagonist section works ("You: ...", history, need, ties), but the premise is weaker than kernel35_f5: its turns are chores (read the standing orders, set the table), lines of five nodes, one breaking point; names were cross-cultural mashups (fixed in b67f48a) |
| kernel38 | Victorian country-house murder | 114 min | 3 / 13 | 3 | 100% | 22 | a strong observer protagonist (the new housekeeper who knows where everyone was), period names, distinct voices, a good wrong-accusation line; but "Nathaniel Vane spreads the signed debt on the table" in four nodes, and a role written as a plot function ("the guest whose secret is easiest to hear"; now soft-rejected) |
| kernel39 | ancient Rome, a freedwoman's bathhouse | 101 min | 3 / 9 | 3 | 100% | 21 | a good premise and Roman names; everything turns on ledgers, contracts and seals; an ending names "the different senator", a placeholder (now soft-rejected) |

## What the day's samples say

- The Fable 5 changes did what they were for: early forks, distinct ending
  worlds, events placed, companions with breaking points, no brief echoes.
- **Paperwork.** Most outlines turn on documents. Traced to the calibration
  examples (a newspaper's loan and contracts, a quartet's entry form, a
  dig's permits) and to the rule that listed "a document, a sum of money"
  among the safe concrete things; rewritten in cba46c3. For scale, Conan
  Doyle's Speckled Band, whose motive is a will, scores 12%, and The
  Canterville Ghost 0% (`tests/kernels/reference/`).
- **The branch looks worse than Fable's on paperwork** (89-100% against
  18-73%; on the one shared kernel, 89% against 73%), and kernel35's premise
  was weaker on the branch. One sample per kernel; the premise A/B
  (4651810 against HEAD, three replays each) and the paperwork replay of
  kernels 35, 38 and 39 through the rewritten examples are queued to tell.
  A suspect: the protagonist history added to the newspaper example ("he
  named you in his will"), one more document in an example made of them.
