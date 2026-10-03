# Run samples, 2026-10-03

Real output of the pipeline on the local model (Qwen3.8 27B IQ3_XS through
Ollama, one RX 9070 XT). Each kernel directory holds:

| file | what it is |
|---|---|
| `<id>_story.md` | the outline: read this first, as a player and a writer would |
| `<id>_s3_brief.json` | phase 3's computed brief: every extracted field with its value and binding |
| `<id>_s3_5_premise_accepted.json` | the premise (engine, turns, complications, cast) the outline was built on |
| `<id>_s3_5_loop.json` | the premise audit and repair rounds: what was flagged, what changed |
| `<id>_run_stats.json` | one record per model call: class, mode, seconds, thinking bytes, breakers, retries |
| `*_raw_output_thinking.txt` | a few raw reasoning traces, to show what the model's thinking looks like |

The kernels are in `tests/kernels/`.

## before_403baa8/ : the pipeline before the story-quality changes

Commit 403baa8 prompts, build limit 25 KB. Full runs from the kernel (phase 3
included), except kernel1 (see below).

| kernel | what it is | time | lines / nodes | what we think |
|---|---|---|---|---|
| kernel31 | epic fantasy quest with a party | 115 min | 4 / 15 | structurally sound, flat as a story: the dragon never acts (phase 3's failure model was relational-only), the plot is a trade in abstract tokens ("the old name", "carry the wake"), the scholar's hidden reason is exposed but never stated, all lines fork in the second half, two endings differ only in who pays a debt |
| kernel32 | comic dungeon crawl, cursed talking sword | 86 min | 3 / 9 | the "dungeon crawl" became one flooded room (setting "single" read as one room); every turn is "keep the sword or put it back"; abstract phrasing ("point the dry step"); the comedy is one laugh; one node retells another |
| kernel17 | noir that must be linear but have a dozen endings | 94 min | 4 / 8 | handled the linear constraint (all forks at the climax, which is what the kernel asked); accumulated triggers used; but only 4 endings (the --max-iterations cap) against "a dozen", and two of them both close the case as a robbery with the lawyer taking the ledger |
| kernel28 | "a mystery; nobody dies and there is no crime" | 85 min | 3 / 10 | a good reading of an adversarial kernel (a quiet bakery mystery, kishotenketsu framework), but all three endings are "the owner signs for a plain counter" with a different meaning for the marked loaf |
| kernel5 | family wedding drama, three sibling viewpoints | 112 min | 4 / 14 | relay structure picked for the three viewpoints; one line leaves early (N02); two endings both close the estate in a private signing; repeated node titles |
| kernel1 | hard sci-fi, generation ship AI (the main test kernel) | 53 min (step 4 only) | 4 / 11 | step 4 at the 25 KB limit on a premise built at 40 KB; the premise loop for this run went through two repairs that introduced a bad form and "you choose to" ways (fixed since: commit abaad0a) |

## after_8ad2d3a/ : the same kernels on the story-quality changes

Commits ed686c0 (story-quality rules), 8ad2d3a (names from Python). 3.5
onward rerun on the SAME phase-3 outputs as the before runs, so the
difference is the premise and outline steps only.

| kernel | time (3.5 on) | lines / nodes | what changed |
|---|---|---|---|
| kernel31 | 79 min | 4 / 15 | lines leave at N01, N02 and T3N01, each with its own middle; the dragon acts (ice cuts the knight, fire breaks the gate); a concrete hidden truth (the vial is the scholar's mother's ashes; speaking the name erases her memory of the party) planted and paid off three ways; four endings in four different worlds; named cast with edges and ties; the audit caught a real kernel violation (party "sent with you" vs "gathered along the way"). Still: two repeated nodes (N02/T3N01, T2N01/T3N02), full names repeated, the thief's leverage never used, "the road spent" vague |
| kernel32 | 59 min | 3 / 10 | a bell tower with five places instead of one room; turns with local goals (get past the gate, open the stair, cross the flood, open the door); concrete objects (iron tally, gate pin, key-iron); a new antagonist (the warden); a clever third ending (the counted return). Still: little comedy, the sword has no personality, the brief's wording repeated ("the sword's stated desire to be returned"), the warden unnamed (a bug in the name picker, fixed since) |
| kernel1 | 63 min | 3 / 8 | no repair round needed; three endings in three different worlds (nursery vented and the public promise broken / every sector kept by going dark and cold / hydroponics vented and the promise kept); named marshals with edges. Still: all lines leave in the second half (the new late_forks note fires; the 4d preference for early divergence did not take here), only three places, the council chair unnamed (same name-picker bug, fixed since) |

Not in these runs (committed after them): 895f52f (repeated_node note, 4c told
to take a different way where another line plays the same turn, first names
after the first mention) and the name picker's head-noun fix.

## limit_test/

kernel1's 4a main line from the same premise at a 25 KB, 40 KB (twice) and
unlimited thinking budget (the unlimited run finished on its own at 89 KB,
14.6 min). The 25 KB one was as good as any; that is why the build limit is
25 KB now.
