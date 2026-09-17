# Consolidated Design Lessons — Steps 3b–3e

Synthesizes `step3b_design_lessons.md`, `step3c_design_lessons.md`, `step3d_design_lessons.md`, and `step3e_design_lessons.md` into one reference. Purpose: seed the drafting of 3f, 3g, 3h, and any later phase without re-deriving patterns that already cost a full patch cycle to discover once.

This document captures what's *generalizable*. Step-specific specifics (exact taxonomies, exact kernel numbers, exact wording of a given rule) still live only in the originals — consult them when a pattern below needs its full worked context.

---

## 1. Identify the field's flavor before drafting anything

Three shapes, carrying different risk profiles (first named in `strategy_v2.txt`'s process notes, validated repeatedly in 3c and 3d):

- **Classification** — picks from a small bounded set. Lowest risk of evidence-tier creep. (3b's affect labels, tone descriptors.)
- **Construction** — invents a structure from scratch rather than selecting one. Carries a real, recurring evidence_basis creep risk: the act of building something specific and well-phrased creates pressure to tag it `strong_inference` (forced) rather than admit it's genre convention dressed in the kernel's own nouns. This showed up almost identically across two different fields in the same step (3c's core and secondary thematic axes). **Write the genre-convention/tie-break language into the first draft**, don't wait to discover it through a patch cycle.
- **Scalar-with-downstream-constraint** — a number or range a later phase's math depends on (e.g. target ending count feeding step 6i). Needs harder adversarial testing than either of the above.

A field can look classification-shaped at the top level while hiding a construction-shaped sub-field underneath (flagged for 3-0b's epistemic-state sub-field in `strategy_v2.txt`). Check sub-fields individually — don't let the top-level shape decide the whole field's risk posture.

---

## 2. Core reusable schema patterns

### 2.1 Evidence basis tiers
`explicit → strong_inference → genre_association → mixed → no_signal`. Established in 3b, held up through 3e with refinements:

- `no_signal` describes the **absence of reasoning material**, not the shape of the conclusion. A real judgment that happens to land low/mild via `strong_inference` or `genre_association` is never `no_signal` — reserve it for when the model would otherwise be guessing blind.
- A label formed by **combining** two separately-stated details into a new synthesized reading is `strong_inference`, not `explicit`, even when every underlying word was stated outright.
- `mixed` has two distinct legitimate shapes, not one: (a) compound sub-items that don't share one source, e.g. one tone descriptor stated, one inferred (3b); (b) a two-pole field where only one pole is textually present and the other must be supplied as the necessary complement (3c). A new field needing `mixed` needs a shape-appropriate definition — don't assume either existing shape automatically covers it.
- Construction fields are disproportionately prone to tier creep (see §1). Expect this specifically wherever a field asks the model to invent rather than pick.

### 2.2 `no_signal` fallback design
Fixed, prescribed fallback value per field — never invented per run. Default toward the gentler/lower end of any scale. An undercommitted guess is cheap for downstream phases to build up from; an overcommitted one risks imposing weight the kernel never asked for.

### 2.3 Ceiling/floor (and best-case/worst-case) decomposition

Validated across transgression (3b), moral_valence (3c), and viewpoint counts (3d). **3e found the pattern is not a general-purpose uncertainty hedge**, and this is the single most important through-line to carry forward:

> Left unconstrained, the model will use a ceiling/floor split to express its own uncertainty about a single, non-branching premise — not just to capture genuine branch-to-branch variance in the story. If no choice point or multiple endings are actually described, **floor must equal ceiling at one best estimate, full stop.**

This took three patch rounds to fully isolate in 3e (an inflated ceiling from an invented, unstated career arc → a flawed calibration example modeling the same ungrounded split, then getting cited as precedent by unrelated kernels → a still-too-loose rule that let "6 or 7 endings" license a duration split even though nothing tied those endings to different elapsed time).

**Two-part test for any future ceiling/floor field:**
1. Does this field's true value plausibly depend on which branch of the story you're in? (3c's original question.)
2. What *specific kind* of branch would legitimately move this field — and could the model conflate a different, irrelevant branch-type with that one? (3e's addition. A branch in *ending* isn't automatically a branch in *duration*. A branch in *viewpoint* isn't automatically a branch in *transgression*. Don't assume "the kernel mentions branching" is sufficient on its own — check that the branch is the right kind.)

Other established sub-rules:
- **Structural vs. choice-driven** cost logic (3b): if the cost is forced regardless of player choice, keep floor within one point of ceiling — no path escapes it. If the cost is choice-driven, floor can drop further, down to the scale's gentle end, when a genuinely low-cost path is plausible.
- **Splits are rare by accident** (3d, reconfirmed 3e): across 23–24 kernels spanning naturalistic and loosely-adversarial batches, not one genuine ceiling≠floor split emerged without a kernel purpose-built to contain both a forcing path and an avoiding path. Treat "does this field's floor logic ever actually fire" as its own checklist item requiring at least one deliberately engineered kernel per field — don't assume a large batch will exercise it by chance.

**Resolved (external review, 27-kernel batch)**: the 3e mechanism-check was examined retroactively across all ceiling/floor fields.
- **3f was already failing it** and is now patched: kernel6 and kernel24 both split floor from ceiling on notes of the form "a contained telling could keep it in one place." That is the model's own uncertainty about a non-branching premise, not branch variance. 3f's text already contained the right test; it just didn't say what to do when no branch is cited. It now does: **no citable branch of the right kind → floor equals ceiling, full stop.** Carry that sentence into any future ceiling/floor field's first draft.
- **3b's transgression floors**: the splits in the batch (k1 5/2, k2 4/2, k14 3/1, k12 4/3) all cite a kernel-stated choice in the floor note, so the mechanism holds. k1's 5/2 is the one worth a second look — "might have to vent oxygen" on a ship failing regardless reads structural, which 3b's own rule caps at one point of gap.
- **3c's moral_valence and 3d's viewpoint_count**: no action. Valence splits track 3c's structural/choice-driven rule; viewpoint_count showed no split without a stated handoff.

### 2.4 Calibration examples
- **Domain separation** from every test kernel (3b) prevents pattern-matching instead of generalizing.
- **Examples are load-bearing precedent, not mere illustration** (3e's sharpest addition). The model will cite an example by name and import its *judgment pattern* — not just its labels — into kernels in entirely different domains. Domain separation stops label copying; it does nothing to stop an ungrounded judgment shape from propagating. **Stress-test every new calibration example against the exact rule it's meant to demonstrate before shipping it.** If the example itself doesn't fully comply, expect it to get cited back as license for the very failure it was supposed to prevent.
- **Repair in place over appending new** (3c, 3e): when an example's domain and core teaching are still right and only its tier calibration or grounding is wrong, fix that example directly rather than adding a new one alongside it.

### 2.5 Adjacent-field / sibling-field disambiguation
Three scopes, increasing in cost:

1. **Within-step label leakage** (3b: tone/affect word reuse) — cheapest to catch, same step, same patch cycle.
2. **Cross-step leakage into an existing sibling's territory** (3c: core vs. secondary thematic axis swap; 3e vs. 3a/3d/3f) — needs explicit carve-out language naming the sibling step by function, not just a tighter internal boundary.
3. **Cross-step leakage into a not-yet-drafted sibling's territory** (3d: ship-AI camera-hopping and a day-loop both got absorbed into `viewpoint_excursions` because nothing else in the pipeline's vocabulary could hold them yet) — most expensive. The current step can only defend against this, not actually coordinate a fix, until the missing sibling exists.

**Standing practice**: before drafting any field, check vocabulary/concept overlap against *all* sibling fields — built and unbuilt — not just the ones an analytical pass predicts. Track record so far: 3d predicted 2 of its 3 real collisions in advance; 3e also caught only 2 of 3 (a different pairing each time). Prediction is worth doing every time but isn't sufficient alone — always pair it with the empirical check.

### 2.6 The hidden-third-shape check
Before finalizing a field that looks like a clean binary (or any small closed set), ask whether a real third shape exists at the boundary — not "more/less" of the two named options, but a different kind of thing entirely. 3d's rotating-ensemble-cast kernel (three siblings, no default, no permanent replacement) burned roughly 9x normal trace length flip-flopping between two options that both genuinely didn't fit, until a third option was added. This is a different fix from tightening a boundary between two known options — it requires adding a genuinely new one.

### 2.7 `other` / escape-hatch categories
Only as precise as what it's excluded from. An `other` valve needs unusually precise definitions of what the *named* categories positively exclude, not just what they include — otherwise it silently becomes the default for any mis-scoped or inconvenient signal (3d).

### 2.8 Other portable analytical patterns
- **Depicted events vs. framing device** (3e): when a kernel nests one narrative inside another (retrospectives, found-document conceits, dream framing), judge structure/duration from the depicted events, not the frame — *unless* the frame itself carries independent narrative weight (its own scenes are as developed and consequential as what's being recalled), in which case treat the frame as its own period. Validated cleanly on two different kernels; worth reapplying directly to any future field with this nesting shape.
- **Two-gloss ordinal boundaries are a latent ambiguity** (3e): a tier defined by two different plain-language glosses ("roughly X, meaning Y") may not actually pick out the same threshold. 3e's `generations_plus` conflated "roughly a lifetime or more" with "spans multiple generations" until tightened to a cohort-crossing test. Check that both glosses of any tier boundary agree before shipping.
- **Adult-life-stage analogs for adversarial kernel construction** (3e): when a stress-test kernel needs a "multiple life stages" shape, prefer adult domains (careers, relationships, professional milestones) over childhood-based ones — same structural test, no content-appropriateness cost.

---

## 3. Process principles (workflow level)

1. **Iterate on real model output, not speculation.** Draft → run against real kernels → read the full thinking trace (not just the JSON) → find a concrete failure → make the narrowest fix → re-test only the kernels needed to confirm. Every real fix across all four steps traced back to an actual trace, never a hypothetical.
2. **Purpose-built adversarial kernels are required, not optional.** Naturalistic batches reliably miss: the no-signal case, bare-boundary cases, self-contradiction cases, and (per 3d/3e) ceiling≠floor-forcing cases. Build these on purpose, before or alongside the first batch — don't wait for them to surface naturally.
3. **Predict failure modes analytically before drafting, in two directions:**
   - *Downstream*: find the field's actual consumer in strategy.txt/later phases and check what shape it needs before finalizing the field's shape. Confirmed useful in every step so far — don't assume a plausible-sounding consumer exists just because the shape seems to fit.
   - *Sideways*: check every sibling field, built or unbuilt, for shared vocabulary or conceptual overlap (§2.5).
   Prediction is worth doing every time, but its hit rate has held around 2/3 across two separate steps — always pair it with empirical testing, never rely on prediction alone.
4. **Separate three different bug types** — each needs a different fix:
   - Wrong evidence_basis *tag*, correct *value* (cosmetic) — don't automatically patch these; reserve fixes for wrong values or genuinely runaway trace length.
   - Wrong *value* — always fix.
   - Missing category / hidden third shape (§2.6) — needs a new option added, not a tighter boundary between existing ones.
5. **When a first boundary-clarification patch produces visible engagement but still the wrong final answer**, consider naming the reasoning failure pattern directly in the prompt, rather than re-defining the boundary again. 3c's example: the model generated the correct disqualifying counter-argument in its own trace, then argued past it — fixed only once the prompt named that exact move as a tell that the tie should go the other way.
6. **Trace length is a diagnostic, but its causes need to be told apart before acting.** Infra/save-pipeline duplication bugs (confirmed by diffing saved JSON against raw model response), missing-category flip-flopping (~9x bloat), and genuine warranted density on a kernel stacking multiple real carve-outs at once (3d: 160 coherent lines) all look similar from outside but call for different responses.
7. **Scope new enum/tier values narrowly and give each a worked example**, or the model burns reasoning budget relitigating the boundary in every trace.
8. **Write the stepXX_design_lessons.md before moving to the next step.** Periodically consolidate (this document) to pay down the cost of re-deriving cross-step patterns.

---

## 4. Standing pre-draft checklist

Run this before drafting any new phase-3 sub-step, or any later-phase field with similar shape:

1. Identify the field's flavor (§1) — including any construction-shaped sub-field hiding inside an otherwise classification-shaped field.
2. Find the field's actual downstream consumer(s) by rereading the later phase's own wording — don't assume one exists.
3. Check every sibling field (built *and* unbuilt) for shared vocabulary or conceptual overlap; write explicit carve-out language for any real collision found.
4. Decide chain-vs-blind execution deliberately relative to this field's siblings, and document the reason. Default posture is blind unless a specific contamination or dependency risk is identified for that pair.
5. If the field's true value could plausibly vary by branch: apply the two-part ceiling/floor test (§2.3), and build the "floor = ceiling absent a real branch of the right kind" rule into the first draft — not as a later patch.
6. If the field requires the model to invent/construct rather than select: write genre-convention and tie-break language into the first draft (§1, §2.1).
7. Check any clean-looking binary or small closed set for a hidden third shape (§2.6) before shipping.
8. Design calibration examples with domain separation, then stress-test each one against its own rule before shipping (§2.4). Prefer repairing a flawed example over adding a new one.
9. Build a `no_signal`-equivalent fallback per field: fixed, prescribed, biased low/gentle.
10. Build adversarial kernels on purpose: no-signal case, self-contradiction case, boundary-swap case (if two fields relate hierarchically), and — if ceiling/floor applies — at least one kernel engineered to force a genuine split via a branch of the *specific* kind that field cares about.
11. Run the batch, read full thinking traces, separate tag-bugs from value-bugs from missing-category bugs (§3.4), patch narrowest first, re-test narrow.
12. Write the step's design-lessons doc before moving on.

---

## 5. Open architectural questions

**Resolved by the external review (see `fable_strategy_review.md` and the current changelog in `strategy.txt`):**

- **Chain vs. blind execution** — settled as a rule: **chain only when a field is *undefined* without the other's output; never chain for agreement.** 3f→3d was already the licensed shape (setting footprint isn't well-defined without the required-excursion list); 3g→3-0a/3-0c is the new one (density and tracked state aren't well-defined without the decision and the failure model). Chaining 3-0a/b/c into 3b–3g was rejected because the argument for it was *consistency*, and consistency is 3h's job. Blind execution is what makes disagreement legible — on kernel12 one field flagged the kernel's contradiction and another didn't, and that disagreement is the signal 3h reads.
- **3-0a/b/c retrofit vs. layer forward** — layer forward, with exactly one targeted retrofit: **3d**, which gained a `third_party_pov` excursion type and an interactivity flag. Kernel15's sister chapter was being read three different ways by three blind fields (a rare secondary decision axis, an `other`-typed excursion, and a designed epistemic gap), and 3-0a needs to know whether an excursion is interactive before deciding to mine it for decisions. 3b/3c/3e/3f showed no mechanical-vs-literary drift attributable to the missing contract frame.
- **Ordering**: 3h is built *before* any further phase-3 fields. It is the instrument that tells you whether a retrofit is needed, all its inputs exist, and it is classification-shaped (cheap on this model). Drafting more fields before the cross-check exists is drafting blind.
- **The 3e mechanism-check retroactively** — see §2.3 above; mandatory for 3f, one-pass audit for 3b, no action for 3c/3d.

**Still open:**

- Full clean 27-kernel rerun against the current prompts is not yet done for any step patched in this pass (3b, 3d, 3e, 3f, 3g, 3-0a, 3-0b, 3-0c), and none of the four new prompts (3h, 3.5, 3.5v, 6.0) has been run against a live model at all.
- Full clean 24-kernel rerun of 3e against v4 not yet done — recommended before treating 3e as settled alongside 3b/3c/3d.
- 3c's original open question — does 3c's output ever contradict 3b's, given both run blind? — still not cross-validated.
- `thematic_trajectory` (deferred to step 16 per 3c) — still open, no new evidence gathered since.
- Whether "reasoning past its own correct counter-argument" (§3.5) recurs outside axis-construction — only observed once, in one field shape.

## 6a. New patterns from the external review (portable, not step-specific)

- **The evidence tiers are already a three-way instruction set for every phase that constructs**, and should be read that way rather than as provenance trivia: `explicit`/`strong_inference` = a **constraint** (may not be contradicted), `genre_association` = a **default** (may be replaced with something more specific, and say so), `no_signal` = a **free variable** (should be filled). This is what the constraint map computes, and it is why step 3's posture is better described as *invention deferred with a receipt* than as anti-invention — a genre_association value already is invention, correctly tagged.
- **Construction phases need provenance + `serves`, not evidence_basis.** `evidence_basis` on an invented field would read "invented" every time and mean nothing. Provenance (kernel_stated / kernel_implied / genre_default / invented) plus a `serves` tag naming the extracted decision the item satisfies is the pair that works — and "serves nothing ⇒ doesn't go in" is the only reliable defence against decorative invention.
- **A tie-break is cheaper than a boundary.** Two long traces in the batch (kernel7's 170-line 3-0c cycle, kernel2's 445-line 3b oscillation) were caused by two rules that were each correct and had no stated precedence between them. Where two rules can both fire, write which one wins, in one sentence, rather than refining either definition. 3-0c's "genre convention alone caps presence at soft" and 3b's "the sustained drive wins over the payoff" are both this shape.
- **Calibration examples must be domain-separated from test kernels in *judgment shape*, not just in nouns.** 3-0a's Example G was kernel17 in a different setting (linear graph + wide ending range), and kernel17's trace imported its judgment shape exactly — so the kernel tested nothing. Two examples were verbatim kernel8. Check both axes when writing an example: would any test kernel recognize itself here?
- **Genre convention is evidence that a mechanic exists, never evidence of how hard it bites.** Generalize past 3-0c: when a value has a severity dimension and the only support is convention, cap at the gentle end and say so.
- **Per-node and per-item fan-out needs its input packet designed before the upstream phases produce material.** Otherwise the producing phases write for a human reader and the consuming phase can't fit any of it. Where a phase feeds a fan-out, have it emit two tiers: the long form, and a short packet form keyed by id.

## 6. What's settled — don't relitigate
- `moral_valence`'s qualitative best/worst-case shape (3c).
- The five-tier evidence_basis structure (§2.1) as the default starting point for any new field — apply the refinements above rather than reconsidering the tier set itself.
- Soft min/max ranges over confident exact counts, for any "how many distinct X does this require" field (3d's `viewpoint_count`).
