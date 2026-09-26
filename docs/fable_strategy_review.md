# Strategy Review: stratum-if Generation Pipeline

Reviewer: Claude Fable 5.1, 2026-09-15.
Inputs read in full: `docs/strategy.txt`, `docs/step3_consolidated_design_lessons.md`, all ten prompts in `prompts/`, `generator/main.py`, all 27 test kernels. From `stories/current_output.tar` (27 kernels × 9 step-3 fields): the JSON for every kernel and field, plus full thinking traces for kernels 2, 4, 6, 7, 8, 9, 22, 23, 24, 25 and targeted reads of 12, 13, 15, 17.

Hard constraint respected throughout: every recommendation assumes a Qwen3-class local model via Ollama in the runtime path. Several recommendations exist *because* of that constraint.

---

## 1. Overall verdict

The pipeline shape is sound as a two-stage idea: distill a kernel into a small set of typed, evidence-tagged structural decisions, then build outward from them. The step-3 work is unusually disciplined for a project at this stage, and the evidence-tier scheme is already doing more than you give it credit for (see §5). But the plan has three structural problems that get more expensive the longer they wait. First, the graph topology is decided in step 6 by a fixed primary×secondary lattice, while 6j (the state model) is deferred; several of your own test kernels (17, 25, 16, 4) cannot be built as a lattice at all and need a state-accumulation topology, which means 6j is not a sub-step that comes after 6, it is an input to 6. Second, nothing between step 3 and step 7 can turn a one-line kernel into a concrete premise; steps 4 and 5 are classification fields that will simply fall back the same way step 3 does, so "surprise me" arrives at world generation still empty. Third, the doc contains a latent conflict about what the primary branch point is built from: `strategy.txt` 6a says the core thematic axis (3c), while `s3_0a_interactive_question.prompt` tells the model it is "the raw material step 6 uses to build branch points." Both are right, and step 6 needs a rule for combining them. Everything else I found is a tweak within a stage.

---

## 2. Major concerns

### M1. 6j is an input to step 6, not a sub-step of it (changes pipeline shape)

Step 6a–6i assumes one topology: a branching tree (primary fork × secondary fork, optional ternary, diamonds for setup). Ending count is then a property of leaf count. Four test kernels already break that assumption, and step 3 correctly extracted the break:

- **kernel17** (noir, "tightly linear, no real forks, at least a dozen endings"): 3g returned `target_ending_count 12–14`, `branching_density sparse`, `state_richness moderate` with the note "a linear path with a dozen case-dependent endings implies the engine must track several case-state variables even though the player never forks." 3-0a returned `recurring_instances` with "the accumulated pattern steering which of the many possible endings emerges." That is a linear spine with an accumulator selecting the ending. 6i's answer ("use ternary branch points to adjust") would violate the kernel's explicit "no real forks."
- **kernel25** ("the story should remember exactly which clues you've found and which suspects you've confronted, and react accordingly"): 3g `rich`, 3-0c `soft / irreversible_foreclosure / pervasive`. This is a state-gated graph, not a tree.
- **kernel16** ("every choice tightens the clock"): 3-0c `time_pressure / escalating`. A shared resource that every branch writes to.
- **kernel4** (loop horror, subpaths that reset): 3-0c `varies_by_trigger` with `loop_retry`. A hub-and-spoke with resets, not a tree.

The state model decides which of these topologies a story has. Deferring it means step 6 will lay down a lattice for kernel17, step 9c will find the ending-count target unmet, and step 13c will discover the mismatch after 7–12 have been built on the wrong skeleton. That is the "bigger rewrite the later it goes" case.

**What to do.** Promote 6j to its own phase *before* 6a (call it 5.5 or 6.0), and make its first field a topology choice: `tree_lattice | linear_accumulator | state_gated_web | hub_loop`. The inputs it needs already exist in step 3 outputs; it does not have to wait for 5h/5i:

- writers: 3-0a `primary_decision_axis` and secondaries (each recurring decision writes at least one variable)
- readers: 3-0c `failure_triggers` (each trigger reads a variable: a countdown, a stock, a detection counter), 3g `target_ending_count` (the ending selector reads accumulated state), 3-0b `gap_resolution` (a "known" flag)
- variable classes: 3g `state_richness.channels` are already the right vocabulary (k1: "oxygen/resource management, sector status/population, core/system integrity")

A minimal 6.0 output is a list of `{name, kind: flag|counter|enum|inventory, written_by: <3-0a axis id>, read_by: <3-0c trigger | ending_selector | gate>}` plus the topology choice. Then 6a–6i become the tree_lattice case of a general step, and the other topologies get their own (initially stubbed) build rules. 5h and 5i refine the model later; they do not create it.

### M2. There is no stage that makes a sparse kernel concrete before world-building (missing phase)

Full recommendation in §5. The short form: kernel8 ("Surprise me") leaves step 3 with all nine fields on fallback values, exactly as designed. Step 4a asks for "plot architecture (quest, investigation, caper…)" and 4b for "conflict type": these are classification fields, and on kernel8 they will fall back too. Step 7 ("major locations") is the first construction step, and it has nothing to build from. Step 10's novelty pass then diagnoses a generic story after 7–9 have already committed to it.

### M3. Step 6a's input contract is contradictory between the strategy doc and the 3-0a prompt (changes step 6's inputs)

`strategy.txt` 6a: "primary branch point is going to divide on the core thematic axis (*what* they choose to believe)". `s3_0a_interactive_question.prompt`: "This is the raw material step 6 uses to build branch points." The two fields answer different questions and step 6 needs both, but the doc only names 3c. The traces show why this matters:

- **kernel13** (heist, loud vs quiet): 3-0a extracted the real fork (`go loud/physical or quiet/AI-jacked`, explicit, `single_fork`). 3c, forced to produce a value pair, manufactured `unmediated selfhood vs mediated selfhood` (strong_inference). A step 6 that branches on 3c would build a story about selfhood; the kernel asked for a story about method.
- **kernel2** (5-act tragedy): 3c gives `tradition vs progress` (explicit), but the kernel says the ending is fixed and "the player's choices should only determine who else gets dragged down." 3-0a got that right (`who to drag down alongside your own fall`). Branching on tradition/progress here contradicts the kernel.
- **kernel12**: 3-0a `how to exact revenge on each person` vs 3c `violent retribution vs moral integrity` (which 3c itself flagged as a contradiction). The primary branch cannot be "violence vs integrity" when the kernel forbids the integrity ending.

**What to do.** Rewrite 6a as: the primary branch point *is* 3-0a's `primary_decision_axis` (when its tier is explicit or strong_inference); 3c's `core_thematic_axis` is the *meaning* assigned to that branch's two sides, and 3c's `secondary_thematic_axis` approaches are the *manner* candidates for 6b. When 3-0a is genre_association or no_signal and 3c is explicit, invert the precedence. When both are weak, that is the M2 case and the enrichment stage decides. This also gives 3h a concrete contract/interactive check to run: "can 3-0a's decision be read as choosing a pole of 3c's axis?" If not, flag it.

### M4. Per-node fan-out (14–17) has no context-budget design (feasibility on a local model)

A 6–8 path lattice with diamonds and a framework's worth of beats is 40–100 nodes. Steps 14, 16, and 17 each run per node, and 17 additionally per room. That is several hundred local-model calls, each of which needs the kernel, the node's purpose, its state reads/writes, its neighbours, and the affect/thematic position (16 says so explicitly). An 8B model's usable context will not hold the whole story bible. The doc never says what a per-node prompt receives.

**What to do.** Define a "node packet" schema now, before 7–13 produce material that will not fit in it: kernel (filtered), the node's row from the graph (purpose, incoming state, outgoing state, exits including failure exits from 3-0c), the 1–2 characters and 1 location by id with their short summaries, and the 3b/3c position tag. Everything else stays out. Steps 11 and 12 should therefore produce *two* tiers of output per character/location, a long form for humans and a ≤150-word packet form for 14–17. This is a stage-shaping decision, not a tweak.

### M5. Generation and verification are fused in 9, 10, and 13 (two phases pretending to be one)

9a/9b generate; 9c verifies. 10a/10c diagnose; 10b/10d repair. 13a/13d lock; 13b/13c verify. Your own lessons doc §3.5 records that this model "generated the correct disqualifying counter-argument in its own trace, then argued past it" *within a single field*. Asking it to generate a plot and audit that plot in the same call will reproduce that failure at scale, and the audit half will be the half that loses.

**What to do.** Split every generate/verify pair into separate prompts with separate JSON, and make the verifier a classification task (it lists violations against a fixed checklist; it does not fix anything). Classification is the flavor the local model handles well. Repair is a third prompt that receives the violation list. This costs calls, not design time, and it is the same discipline you already apply between step 3 fields and 3h.

---

## 3. Minor concerns

- **Calibration examples are not domain-separated from the test kernels.** 3b Example D and 3e Example E are the verbatim text of kernel8 ("Write me an interactive story. Surprise me."). The kernel8 traces cite them by name. 3-0a Example G (linear mountaineering, wide range of endings) is kernel17 in a different domain and the kernel17 trace imports its judgment shape exactly, as §2.4 of your lessons doc predicts. 3-0a Example F (alternating candidates) is kernel5's hop. Kernel8 is therefore not testing no_signal generalization at all. Fix: change the calibration text, not the kernel.
- **3f already exhibits the 3e ceiling/floor failure** (see Q4 below). kernel6 and kernel24 both split floor from ceiling with notes of the form "a contained telling could…", which is the model's uncertainty, not a branch.
- **3-0c has two rules that conflict and no tie-break.** "General risk… without a specific mechanic" is not failure, versus "a stealth or heist premise conventionally implies a getting-caught fail state." kernel7 (pirate) burned 170 lines cycling hard → soft → none → hard on exactly this conflict. kernel9 ("I want a mystery") resolved to `hard / incorrect_resolution / terminal` and kernel25 (a mystery with memory) to `soft / irreversible_foreclosure / pervasive`; both are genre-derived, both defensible, opposite. Step 14 will build bad-end nodes for kernel9 on a coin flip. Add the tie-break: genre convention alone licenses at most `soft`; `hard` requires a stated or forced mechanic.
- **3-0c's trigger set has a hidden category.** kernel4 landed on `other` with the note "taking one of the wrong or surreal subpaths." Loop-horror, dungeon, and survival premises all need an environmental/wrong-turn hazard trigger. Per your §2.7, `other` will become the default for it. Add `hazard_or_wrong_turn`.
- **3b's `primary_affect` is ambiguous between drive and payoff.** kernel2's 3b trace is 445 lines, almost all of it oscillating between "desperate longing" (the sustained drive) and "grief/despair" (the tragic payoff), with "Actually, let me reconsider" eight times. Add one rule: primary_affect is the sustained experience; a payoff of a different kind goes to `primary_trajectory: transforming` or a secondary.
- **3-0b's `designed` leaks into puzzle obstacles.** kernel16 (museum vault) returned a designed epistemic gap of "the museum vault's combination or security configuration." A lock is an obstacle, not a withheld truth. Add a carve-out: a thing the protagonist must *obtain* or *defeat* is not a gap; only a fact that is *concealed* is.
- **3g conflates paths with endings on kernel13** (`target_ending_count 2–2` because "two complete alternative approaches"). Two routes into a vault do not force two endings. Value bug, not tag bug.
- **3b has no contradiction rule.** kernel12: 3c flagged the violence-corrupts vs triumphant-ending contradiction (correctly, per its own rule). 3b silently accepted `triumphant catharsis` with transgression 4/3 and no flag. 3h will catch it, but 3b could carry the same one-paragraph rule 3c has.
- **3a (length) has no consumer.** 3g's ending count and branching density already bound the build. Either fold 3a into 3g as a `target_node_count` range or drop it.
- **Failure exits are invisible to step 6.** 3-0c's model reaches 14 and 16 only. But 3g explicitly excludes failure exits from ending count, and 13b's orphan check needs to know which dead ends are intentional. Step 6 (or 6.0 per M1) should reserve bad-end exits so they are part of the locked graph, not added per node.
- **kernel15's sister chapter is read three different ways by three blind fields.** 3-0a: a `rare` secondary axis "which rescue action to take as your sister" (assumes it is interactive). 3d: an excursion of type `other` (non-interactive framing is the nearest clause). 3-0b: a designed epistemic gap with optional resolution. Nothing is wrong with any single read; it is the clearest case in the batch of why 3h must exist before more fields are added.

---

## 4. Direct answers to the four open questions

### Q1. Chain vs blind as a general policy; is 3-0a/b/c the right candidate to break it?

Keep blind as the default. The traces argue for it: on kernel12, blind execution gave you one field that flagged the contradiction and one that did not, and that disagreement is the signal 3h needs. Chained execution would have let 3b's acceptance contaminate 3c or vice versa.

3-0a/b/c are the *wrong* candidates for chaining into 3b–3f, and the reason is in your own doc: the argument for chaining them is *consistency* ("narrative content should be built to fit the contract"). Consistency is 3h's job. The pipeline has already broken blind once, correctly, for a different reason: 3f consumes 3d's output (`$$VIEWPOINT_EXCURSIONS_JSON$$`) because setting footprint is *not well-defined* without the required-excursion list. That is a dependency, not a consistency concern. Make that the rule: **chain only when a field is undefined without the other's output; never chain for agreement.**

By that rule there is one chain worth adding now: 3-0a and 3-0c into 3g. The 3-0a prompt already claims 3g calibrates branching density on `decision_mechanism`, and the 3g prompt currently apologises that failure emphasis "does not currently have a clean home in this extraction step." It now has one. Pass both outputs to 3g and delete the apology.

### Q2. Retrofit vs layer-forward for 3-0a/b/c

Layer forward, with one targeted retrofit and one ordering change.

The targeted retrofit is 3d only. The kernel15 three-way disagreement above and kernel5's hop show 3-0a, 3-0b, and 3d all reaching for the same clause with different vocabularies. 3d needs (a) a named excursion type for a third-party POV interlude and (b) a field saying whether that interlude is interactive, because 3-0a decides whether to extract decisions from it and 6 decides whether it gets nodes. That is a two-line change, not a re-audit. 3b, 3c, 3e, and 3f showed no mechanical-vs-literary drift in the 27-kernel batch that I could attribute to the missing contract frame.

The ordering change: build 3h next, before polishing 3f/3g or drafting 3a. 3h is the instrument that tells you whether a retrofit is needed, all of its inputs exist, and it is a classification task (list conflicts against a fixed list of pairs), which is cheap on this model. Drafting more fields before the cross-check exists is drafting blind.

### Q3. Is deferring 6j safe?

No. See M1. It is not that a late state model forces a rewrite of 7–12; it is that 6a–6i cannot be run correctly without it for at least four of your 27 kernels, so the rewrite hits step 6 itself. Design it now, from step 3 outputs, as a topology choice plus a variable table. Verify on kernels 17, 25, 16, 4, and 19 (the duration split years/hours in kernel19 is also a state variable: elapsed time).

### Q4. Should the 3e mechanism-check be applied retroactively to transgression, moral_valence, viewpoint_count?

Yes, and start with 3f, which was built after the lesson and already shows the failure:

- kernel6 (cozy bakery): `setting_structure clustered/single`, `setting_scale city_or_region/room_or_building`, floor notes "the most contained path can keep villagers arriving at the bakery." The kernel describes no branch that changes where the story goes. This is exactly the 3e pattern: ceiling/floor as a hedge on one non-branching premise.
- kernel24 (three negotiations): `dispersed/single` with "a contained telling could set all three negotiations in the same building." Same failure. 3f's own text contains the right rule ("does the specific branch the Kernel describes actually change how many or how far apart the required places are"); the model ignored it because no branch was cited and the rule does not say what to do then. Add the 3e sentence: no cited branch of the right kind, floor equals ceiling.

For the three earlier fields, the batch is cleaner. Transgression splits (k1 5/2, k2 4/2, k14 3/1, k12 4/3) all cite a kernel-stated choice in the floor note; k1's 5/2 is the one worth a second look ("might have to vent oxygen" on a ship that is failing regardless reads structural, which caps the gap at one point by 3b's own rule). `moral_valence` is qualitative and its splits track 3c's structural/choice-driven rule. `viewpoint_count` shows no split without a stated handoff (k14 2–2 with ceiling multi_hop/floor single is the intended shape). So: mandatory for 3f, a one-pass audit of 3b floors, no action on 3c/3d.

---

## 5. Recommendation for Question B: where enrichment lives

### The key observation: you already have the framework

The five evidence tiers already partition every step-3 value into three kinds, and downstream stages should read them that way:

| tier | what it means downstream |
|---|---|
| `explicit`, `strong_inference` | a **constraint**: enrichment must not contradict it |
| `genre_association` | a **default**: enrichment may replace it with something more specific, and should say so |
| `no_signal` | a **free variable**: enrichment must fill it |

This means "invented, not extracted" content does not need a new evidence scheme. It needs a *provenance* tag and a *fidelity* check. And it means the honest description of step 3 is not "anti-invention" but "invention deferred with a receipt": genre_association is already invention (kernel9's `incorrect_resolution / terminal` failure model is pure genre supply), it is just tagged as such. Good. Keep that.

### Where: a new step between 3h and 4

Not step 10. Step 10 is repair, it runs after 6–9 have locked structure and cast, and graph repair is the hardest task you could hand a local model (M5). Its NOVELTY diagnosis should stay, but as an *audit* that can send the pipeline back to the enrichment step with an "avoid these" list, not as the place richness originates.

Not steps 4–5 as currently shaped. They are classification fields (plot architecture, conflict type, threat source). Classification cannot make a kernel richer; on kernel8 they will return defaults. They should instead *consume* the enriched premise: 4a classifies the plot architecture of the premise the new step wrote.

Not a step-3 sub-step. Step 3 is extraction with a strict no-invention posture, and mixing construction into it would erode the discipline that makes the evidence tags trustworthy. The new step runs after 3h so it sees the reconciled field set, and before 4 so nothing downstream ever sees a bare kernel.

Call it **step 3.5, premise expansion**. Flavor: construction, the highest-risk shape, and it should be treated as the single most adversarially tested prompt in the pipeline.

### What the fields look like

Every field carries `provenance ∈ {kernel_stated, kernel_implied, genre_default, invented}` and `serves: <step-3 field id>`. Nothing is added without naming the extracted goal it serves.

1. **`enrichment_budget`** (classification, computed not judged): `minimal | moderate | generous`, derived from the count of explicit/strong_inference fields in 3h's output. kernel1 and kernel11 get `minimal`; kernel8, 9, 23 get `generous`. This is the restraint control; without it the model will "improve" over-specified kernels.
2. **`protagonist_situation`** (construction): who "you" concretely are at open, what they want, what they can do. Extends 3-0b's `role_descriptor` (kernel9: "unspecified") into something playable. Serves 3-0b.
3. **`arena`** (construction): one concrete setting instance inside 3f's footprint. Serves 3f.
4. **`instance_generator`** (construction, the load-bearing one): the concrete material that makes 3-0a's decision axis recur. For kernel9 (`which clue or suspect to pursue next`) this is the case: a victim, 3–5 suspects, the true solution, the false leads. For kernel6 (`what baked good to make for each villager's problem`) it is 4–6 villagers with their problems. For kernel7 it is the prizes, the navy captain, the mutinous first mate. Without this field, `recurring_instances` has no instances. Serves 3-0a.
5. **`complications`** (construction, 2–4 items): invented turns, each tagged with the affect-trajectory point (3b) or thematic beat (3c) or failure mechanic (3-0c) it serves. This is where "genuine twists" come from, and the `serves` tag is what keeps them from being generic: a twist that serves nothing is disallowed.
6. **`withheld`** (construction, list): what the new material declines to specify, with the reason "left to step 7/8" or "kernel is explicit here." This is the receipt for restraint and is what makes `minimal` budget auditable.
7. **`fidelity_check`** (classification, self-report): every explicit clause of the kernel, verbatim, with `touched: yes|no` and, if yes, `consistent: yes|no`. The model is bad at auditing its own construction (§3.5), so this is a first pass only; the real check is separate (below).

Keep `evidence_basis` off these fields. It would read "invented" on every construction field and mean nothing. Provenance plus `serves` is the right pair.

### How it interacts with the contract/interactive split (this is where that split earns its keep)

Enrichment may invent freely on **contract** axes (affect, theme, setting, identity, timeline) tagged genre_default or no_signal. It may **not** invent on **interactive** axes (3-0a, 3-0c, 3g). Mechanics are chosen from the pipeline's own menu (the 3-0c trigger set, the 3g levels, the 6.0 topology list), because the engine has to build whatever is chosen and an invented mechanic is an unbuildable one. So for kernel8, step 3.5 may invent a lighthouse, a grief, a stranger at the door; it may not invent "a sanity meter." That is a real, enforceable distinction, and it is the first place in the doc where the contract/interactive labels change what a stage is allowed to do. Right now the split is organizational sugar; this makes it a rule.

### How to test it

Build these kernels on purpose, alongside the first draft:

- **Fidelity under sparsity with one hard negative.** "A mystery. Nobody dies and there is no crime." Does `instance_generator` invent a corpse? (Genre default says murder; explicit says no.) This is the precedence test: explicit beats genre_default.
- **Fidelity under sparsity with one unusual positive.** "A heist where getting caught is the whole point." Does 3-0c's genre `detection_or_exposure` failure state survive into the complications as a failure, or does enrichment correctly treat capture as the goal? Tests that enrichment reads the constraint map rather than the genre.
- **Restraint on an over-specified kernel.** kernel1 and kernel11. Expected: `budget minimal`, `withheld` long, `complications` ≤1, and every kernel clause `touched: no` or `consistent: yes`. Diff the kernel's explicit clauses against the output mechanically.
- **Richness on the three sparsest kernels.** kernel8, kernel9, kernel23. Expected: a concrete `instance_generator` with named (role-level) entities, not "a mystery occurs."
- **Genericness by resampling.** Run kernel9 three times at nonzero temperature. If all three produce a rain-soaked detective and a femme fatale, the prompt is producing genre mean, not invention. This is cheap on a local model and is the only direct test of "generic" I know of that does not require a frontier judge.
- **Contract/interactive boundary.** kernel8 again: any `complications` entry whose `serves` points at 3-0a/3-0c/3g and whose provenance is `invented` is a violation.

Score with a **separate** fidelity prompt (classification): input is the kernel plus the 3.5 JSON; output is a list of `{kernel_clause, contradiction: yes|no, quote}`. Run it as part of 3h's successor, not inside 3.5. The local model is good at this shape and bad at auditing itself.

Then step 10's NOVELTY check becomes: re-run the resampling test on the *built* story's summary, and if it collapses to genre mean, send the `complications` list back to 3.5 with a do-not-reuse list. That gives step 10 a real mechanism instead of "introduce new minor events."

---

## 6. Other things in the traces you did not ask about

- **The model follows the rubric far better than it judges.** Almost every trace is a careful walk through the prompt's rules, and the JSON is valid and well-tagged. But on kernels where there is no decision to find, it manufactures one and tags it honestly: kernel27 `which level or social zone of Meridian Tower to enter next` (genre_association), kernel22 `what to do in whichever timeframe is active`, kernel20 `which farm work to tackle next`. These are non-decisions with correct tags. The rubric cannot make a decision exist; that is the M2 gap seen from the 3-0a side. Watch for downstream stages treating a genre_association decision axis as if it were a real one.
- **Long traces cluster on two causes, both fixable in-prompt.** Missing tie-break (kernel7 3-0c, 170 lines; kernel2 3b, 445 lines) and a hidden category (kernel4 `other`). No trace in the batch looked like warranted density in the 3d sense. All 22,467 trace lines are under 450 per field, so nothing is runaway.
- **Two mystery kernels, two failure models** (kernel9 vs kernel25, above). Worth a calibration example that shows "mystery" alone landing on `soft`.
- **3c's valence fallback fires on kernels where the core axis did not** (kernel23, kernel27: axis genre_association, valence `quiet, ambiguous resolution` ×2 no_signal). That is correct per-field independence, and it is a good example of the constraint map in §5 being informative: valence is free, axis is a default.
- **kernel22's 3g used no_signal on ending count while the same kernel's 3-0a, 3d, 3e all found signal.** Also correct by the 3g prompt's own "time structure alone tells you nothing about endings" rule. Note it only because a reviewer skimming tags will read it as inconsistency.
- **`s3g` explicitly says failure emphasis has no home.** It does now (3-0c). Remove that paragraph when you chain 3-0c into 3g (Q1).
- **Infra.** `main.py` runs 3-0a/b/c before 3b, so `todo.sh` reruns will produce the chained order for free once 3g takes them as inputs. The `lenient_json_loads` retry has not been needed anywhere in the 27-kernel batch that I could see; every saved JSON parsed clean. The working-copy `stories/kernel1/` has two empty `s3_0a` logs and one truncated at the calibration examples, which looks like a different local environment than the one that produced the tarball; not a pipeline issue, just do not mistake it for a prompt regression.

### If you do only three things

1. Build 3h now (Q2). It is cheap, it is the instrument for every other decision here, and kernel15 already needs it.
2. Design 6.0 (topology plus variable table) from step 3 outputs and stub it (M1). Run kernels 17, 25, 4 through it before touching 6a.
3. Draft step 3.5 with the seven fields in §5 and the six adversarial kernels, and run the stub pass your own process notes call for (3 → 17 on one simple kernel) with 3.5 and 6.0 as stubs in place. The seam most likely to be broken is 6a's input contract (M3), and the stub pass will show it before you polish anything downstream of it.
