# Strategy Review Request — stratus-if Interactive Fiction Generation Pipeline

I'm building a multi-stage, local-model-only pipeline that turns a free-text
"Kernel" (a short blurb describing a desired interactive story) into a full
node-based interactive fiction graph, ending in generated per-room prose.
I want an outside architectural read on the plan before we sink more design
time into the unbuilt stages. I'm attaching:

1. `strategy.txt` — the authoritative planning document. It's a working
   doc with inline changelog and process notes at the top; the numbered
   pipeline (steps 1–17) is the actual plan.
2. `step3_consolidated_design_lessons.md` — patterns we've extracted from
   building and adversarially testing the first several sub-fields of step 3
   (evidence-basis tiers, ceiling/floor rules, calibration-example pitfalls,
   etc). Treat section 6 of this doc ("what's settled — don't relitigate")
   as fixed unless you see a genuinely compelling reason to revisit it.
3. The existing prompts provided in a tarball so
   you can see the actual shape of a prompt we run against the model —
   system prompt, definitions, evidence-basis rules, output JSON schema,
   calibration examples, kernel slot.
4. A tarball of ~27 test kernels with the full per-field outputs and raw
   thinking traces from a local model (Qwen3, via Ollama) run against the
   current prompts.

**Hard constraint, please respect it in any recommendation**: production
inference is local-model-only (Qwen3 class, via Ollama). Nothing you suggest
should assume a frontier-model call in the runtime path — you're reviewing
the design, not proposing we swap the engine.

## How to use the attachments
Read `strategy.txt` and the consolidated lessons doc in full — they're
short and everything else depends on them. For the tarball, you don't need
to read all 27 kernels' full traces line by line; skim for overall shape,
then read a handful in full to ground any specific claim you make (pick
ones that look like edge cases — very sparse one-line kernels, and any
kernel whose trace is unusually long, since long traces are usually where
something's under-specified). Cite specific kernels or stage numbers when
you flag a problem rather than speaking abstractly — that's what makes a
review like this actionable for us.

## Question A — Is the overall strategy reasonable?

Evaluate the 17-step pipeline shape in `strategy.txt` end to end: Kernel
intake → step 3's structural-concept extraction → steps 4–6 (structural/world
shape, branch/framework/state-model generation) → 7–13 (world/character/plot
generation, shortcomings pass, deep expansion, graph finalization) → 14–17
(per-node detail, transitions, prose generation).

Specifically:
- Are there missing phases, or phases that are really two phases pretending
  to be one?
- Is the ordering right — is there information a later stage needs that an
  earlier stage doesn't actually produce, or produces too late to be useful?
- Is the contract-axes/interactive-axes split (fictional content vs.
  mechanics of play, named explicitly in the doc) doing real work, or is it
  organizational sugar?
- We have several genuinely open, unresolved architectural questions
  flagged directly in the doc's changelog and process notes — we'd value
  your independent opinion on each, not just a summary back to us:
  - Chain-vs-blind execution as a general policy for step-3 sub-fields
    (currently blind by default, chaining only case-by-case). Is that the
    right default, and is 3-0a/3-0b/3-0c really the right candidate to break
    it?
  - The 3-0a/3-0b/3-0c "retrofit vs. layer-forward" decision (retrofit
    existing 3b–3g prompts against the new mechanical-contract framing now,
    vs. build 3-0a/b/c and only revisit 3b–3g if a later cross-check finds
    actual drift).
  - Step 6j (the tracked state model: flags, inventory, relationship
    counters) is flagged as the single largest undesigned gap in the whole
    document, currently informed only by soft priors from 3g(iii)/5h/5i,
    none of which are built yet. Does deferring it this long look safe, or
    is it going to force a bigger rewrite the later it goes?
  - Whether the ceiling/floor mechanism-check we developed for one field
    (3-0c's failure model) should be retroactively applied to the fields
    that use ceiling/floor and were built earlier (transgression,
    moral_valence, viewpoint_count) — untested from this angle so far.

For each thing you flag, tell us whether it's major (changes the pipeline
shape) or minor (a tweak within a stage), and what you'd actually do about
it — not just that it's a risk.

## Question B — Where does creative enrichment of thin kernels happen?

We deliberately want kernels to be free-form and often light on detail — a
customer might give us one sentence. We do **not** want that to produce a
thin or generic story. We want fully-formed output: real player agency,
genuine twists, faithful compliance with whatever the kernel *did* specify,
coherent theme and affect delivery, and rich diegetic detail/expansion
beyond what the kernel stated.

Here's a tension we think you should weigh in on directly: the extraction
philosophy we've built for step 3's fields (see the consolidated lessons
doc, sections 2.1–2.2) is deliberately **anti-invention** when a kernel is
sparse — the `no_signal` evidence tier exists specifically to stop the
model from inventing unstated richness, and its fallback values are
explicitly biased toward the gentle/low end rather than something more
fully realized. That's the right call *for extraction* — we don't want a
one-line kernel getting an invented, overconfident affect/theme/transgression
reading. But it means step 3, as designed, will not be the source of the
richness we want in the final story. Something downstream has to add it
deliberately.

Looking at the pipeline as currently sketched, a few stages look like
plausible candidates, and we'd like your read on whether they're sufficient,
correctly placed, or need to be restructured:
- Step 10 ("identify shortcomings") already explicitly separates COHERENCE
  from NOVELTY as two different failure modes and calls for introducing new
  minor events/locations/characters to address gaps — is this actually where
  "make it interesting, not skeletal" should live, or is that too late
  (after structure/plot/characters are already locked in steps 6–9)?
- Steps 4–5 (initial structural/world shape) and step 9c (plot-generation
  requirement checks against affect trajectory, thematic resolution, agency)
  are the other places where invention happens — should *these* stages be
  where a sparse kernel gets deliberately, generously filled in, rather than
  patched later in step 10?
- Should there be a **dedicated new stage or step-3 sub-step** whose entire
  job is "given the extracted (possibly minimal) structural concepts, decide
  what to add that isn't in the kernel at all, in service of the kernel's
  own stated goals" — as opposed to enrichment being an implicit side effect
  of several other stages each doing a bit of it?

Please give us a concrete recommendation: which stage(s), what the field(s)
would actually look like (classification vs. construction, per our existing
flavor taxonomy), how it should be evidenced/scored (does the existing
5-tier evidence-basis scheme even apply to "invented, not extracted"
content, or does that need its own framework), and how you'd propose we
test it — including what an adversarial test kernel for "does this stay
faithful to the kernel while adding real richness" should look like.

## What we want back

Structure your answer as:
1. **Overall verdict** on the pipeline shape (one paragraph).
2. **Major concerns**, if any, each with a specific proposed fix.
3. **Minor concerns**, same format, kept brief.
4. **Direct answers to the four open questions listed under A.**
5. **Your recommendation for B** — stage placement, mechanism, and how you'd
   test it — as its own clearly-marked section.
6. Anything else you noticed in the tarball traces that we didn't ask about
   but should know.

We'd rather have a shorter list of well-grounded, cited findings than a
long list of generic architecture advice — please anchor claims in the
actual documents and traces wherever you can.
