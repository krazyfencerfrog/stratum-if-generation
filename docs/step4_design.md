# Pipeline design: verify/repair loops and step 4

This is the current description of everything after phase 3. `strategy.txt` is the
historical plan (its numbered steps 4–17 are superseded from step 4 on); this
document is what `generator/main.py` and `generator/step4.py` actually do, why,
and what is still unvalidated. Read `step3_consolidated_design_lessons.md` first
for the rules every prompt follows.

## 1. Shape of the pipeline

```
s1 kernel
s2 rating filter
phase 3 (blind extraction ×9, chained only where a field is undefined otherwise)
s3h cross-check  ──►  constraint map (computed)
s3.5  premise expansion   ─► s3.5v audit ─► s3.5r repair ─► s3.5v re-audit   (≤ --max-repairs rounds)
s3.75 craft spine         ─► s3.75v audit ─► s3.75r repair ─► s3.75v re-audit
step 4 outline loop, one path per iteration:
    4a_first (iteration 1) | 4a_next (+4c5 craft refresh if it transforms)
    entity_define × new roles  →  beat_generate × new beats
    4d review  →  beat repair × flagged beats  →  4d re-review
    stop when 4d says stop, no candidates remain, or --max-iterations
export: <id>_s4_story.json, <id>_s4_story.md
```

Three standing rules, now enforced in code rather than by hand:

1. **Generation and verification never share a prompt.** Every builder has a
   separate auditor with its own JSON.
2. **Repair is a third call that receives the violation list.** The auditor fixes
   nothing; a repair prompt receives the auditor's findings and returns the whole
   object revised, changed only where the findings point. The auditor then runs
   again on the revision. This is what was missing before this pass: 3.5v and
   3.75v found problems and nothing acted on them.
3. **Counts and lookups are computed, not asked.** The constraint map, the
   step-4 branch-point table, the story digest and the state-variable registry
   are all built in Python from saved JSON. The model is spent on judgment.

## 2. The build/verify/repair loop (`StoryGenerator.run_verified_step`)

Inputs: a build call, a verify call whose replacements are a function of the
current material, a repair call whose replacements are a function of the
current material and the verdict, and `needs_repair(verdict)`.

| step | prefix / file | notes |
|---|---|---|
| build | `s3_5_premise_expansion.json` | the ORIGINAL, never overwritten |
| verify | `s3_5v_fidelity_check.json` | verdict on the original |
| repair n | `s3_5r<n>_premise_repair.json` | `{"repair_log": [...], "revised": {...}}` |
| re-verify n | `s3_5v_r<n>_fidelity_check.json` | verdict on revision n |
| accepted copy | `s3_5_premise_expansion_accepted.json` | what downstream actually read |
| loop record | `s3_5_loop.json` | rounds, sources, verdicts, `still_failing` |

The same scheme applies to 3.75 (`s3_75`, `s3_75v`, `s3_75r<n>`,
`s3_75v_r<n>`). In memory the accepted revision replaces the original under the
build's own key (`self.analysis['s3_5_premise_expansion']`), so 3.75 and step 4
read the repaired premise without knowing a repair happened.

What triggers repair:

- 3.5v: `verdict.value == "hard_issues"`. Soft findings are notes for a human by
  the auditor's own definition; repairing on them caused churn in the archived
  batch (kernel4's soft findings were the auditor objecting to material that was
  correctly withheld). `--repair-on-soft` opts in.
- 3.75v: `verdict.value == "flagged"` (its vocabulary is clean/flagged; flagged
  includes a self-report disagreement such as kernel2's wrong list index).

If the verdict still needs repair after `--max-repairs` rounds (default 2) the
run **halts** with `PipelineHalt` (exit code 2) and names the loop file. The
later phases assume verified material; building on a known contradiction
produces a wrong story, not a slightly worse one. To re-run a loop, delete every
file of its build/verify/repair prefixes (`*_s3_5*` for the premise loop).

3h is unchanged and still fixes nothing, by design: 3.5 already builds to the
field 3h preferred. What changed is that 3h's output now also reaches 3.5v,
3.75, 3.75v and 4a, with the rule that a constraint 3h ruled against is not a
constraint for auditing or building.

## 3. Step 4

### 3.1 Why it is shaped this way

Steps 4–6 of the old plan (plot architecture classification, world shape, a
fixed primary×secondary lattice with a separate topology step) were replaced by
the prompts committed in cf0090d, which were hand-driven in earlier sessions.
They build the story as an outline of beats, one complete path per iteration,
with a review after each. This pass split the two-mode 4a prompt, gave every
prompt real placeholders and a fixed JSON contract, and wrote the driver.

The old 6.0 topology question survives as 4a_first's **ending mechanism**:
`forked_paths` (branch-point beats write selector variables), `accumulated_state`
(no forks; a shared terminal beat reads state, which is kernel17's shape) or
`both`. That is the minimum the driver needs to know how endings are reached; the
full variable table was folded into the state-variable registry step 4 keeps
anyway.

### 3.2 One iteration

1. **Outline.** Iteration 1 runs `s4a_first_outline.prompt` (framework, ending
   mechanism, main path). Iteration n runs `s4a_next_outline.prompt` with the
   story digest, the computed branch-point table and the last review's
   termination judgment; it selects one `(beat_id, outcome_value)` from the
   table's `candidates`, outlines only the new beats, and either ends in a
   terminal beat or reconverges onto an existing one. Selecting an explored value
   fails validation; the call is retried once, then the loop stops.
2. **Craft refresh** (`s4c5`) only if 4a_next chose `transform`. Fields whose
   status is adjusted/refreshed are substituted into a per-path copy of the
   craft spine that this path's beats receive.
3. **Entities.** Each role-level `location` / `characters` string in the new
   outline that is not already mapped runs `s4_entity_define.prompt`. Outcomes:
   `reuse` (mapped to the roster entry), `new_character` / `new_location` (added,
   with the proper name the prompt assigns), `none_needed` (characters only; the
   beat delivers that content through the environment). Matching is by
   normalized string (articles stripped, case-folded), so outlines are told to
   reuse roster names verbatim.
4. **Beats**, in path order, each with `s4_beat_generate.prompt`: the outline
   entry plus path context (previous beat digest, next beat summary, which
   outcome this path follows at a branch point, which other paths share the
   beat), the resolved roster entries, the 3.5 instance it dramatizes, the
   state-variable registry, the craft spine, the failure model. Writes are
   structured (`{"variable","value"}`) and registered as they arrive. A path
   that reconverges onto an existing beat triggers one revision of that beat so
   it varies by the state each arriving path carries.
5. **Review** with `s4d_verify.prompt` over the digest (everything except scene
   prose). Every finding carries `beat_ids`; the driver regenerates those beats
   (up to `--max-repair-beats`) in revision mode, then reviews once more. The
   second review's termination judgment decides whether to continue.

Stop conditions: 4d says `stop here`; the branch table has no candidates;
4a_next reports none; `--max-iterations`.

### 3.3 Files and resumability

Every model call has a unique prefix, so a rerun replays the driver and loads
every file instead of calling the model; the stub test confirms zero calls on
resume and identical state.

| call | prefix |
|---|---|
| first outline | `s4a_i1_first_outline.json` |
| next outline | `s4a_i<n>_next_outline.json` |
| craft refresh | `s4c5_i<n>_craft_refresh.json` |
| entity | `s4e_i<n>_<k>_<role-slug>_entity.json` |
| beat | `s4b_i<n>_<beat-slug>_beat.json`, revisions `…_r<k>_beat.json` |
| review | `s4d_i<n>_verify.json`, re-review `s4d_i<n>_r1_verify.json` |
| assembled story | `s4_story.json`, `s4_story.md` (rewritten every iteration) |

Because state is replayed, deleting one file re-runs exactly that call and
everything the driver derives from it. Deleting an outline file re-runs that
iteration's outline, and the entity/beat files from the old outline will only be
reused where the new outline produces the same ids and roles.

### 3.4 Schemas the code depends on

Outline entry (both 4a prompts):

```json
{"id": "B03", "role": "...", "content_summary": "...",
 "location": "role-level or roster name", "characters": ["..."],
 "instance_ref": 1, "is_branch_point": true,
 "branch": {"variable": "orientation", "outcome_values": ["collective","fittest"], "path_follows": "collective"},
 "is_terminal": false,
 "failure_exit": null | {"trigger": "...", "cost": "terminal|loop_retry|narrative_setback", "description": "..."},
 "craft_note": ""}
```

Beat content: `decision` is `"none"` or `{action, outcomes: [{choice, writes: [{variable, value}], meaning}]}`;
`state_effects` and `reads` are lists of the same shapes; `available_actions` is
non-empty always; `shared_terminal_variants` is a list of `{when, variant}` on
shared beats. `normalize_writes` in `step4.py` tolerates a bare
`"variable = value"` string.

Review: each of the four check sections has `findings: [{issue, beat_ids,
affected_paths, fix}]`; `termination` has `remaining_candidates`,
`next_candidate`, `overall_recommendation` (`continue looping` | `stop here`).

Branch-point table (computed): per branch beat, `outcome_values`, `explored`
(value → paths), `unexplored`; `candidates` flattens the unexplored values;
`unmarked_selector_writes` lists beats that wrote a selector variable without
being outlined as branch points, which 4d must resolve.

## 4. Trace length

The archived batch shows thinking-to-response ratios of 5–17× on the
construction and audit steps, and the traces have a recognisable structure:
restate the inputs, reason, **draft the entire JSON in the trace**, verify it key
by key, then emit it again. The drafted JSON alone is 30–40% of a 3.5/3.5v
trace, and it is verbatim copying. Kernel1's 3.5v trace also spent ~40 lines on
whether `3f.setting_structure` was a valid `serves` tag because the constraint
map lists leaf paths (`3f.setting_structure.ceiling`).

Changes made: every prompt now carries a short REASONING DISCIPLINE block (reason
once, write once; no JSON drafting in the trace; no re-narration of inputs; a
settled field stays settled unless a later finding gives a concrete reason, with
an explicit carve-out that the existing late-objection tie-break rules still
win); the audit prompts add "one sentence per clean check"; and the `serves`
prefix rule is now stated. The reasoning itself was not touched. Measure the
effect on the next batch by comparing thinking word counts per step against
`stories/current_output.tar` before judging the block.

## 5. Testing without a model

`generator/stub_client.py` answers every prompt with a schema-valid canned JSON
(selected by a phrase in the prompt's first lines) and reads the JSON sections of
the prompt it was given, so step 4's bookkeeping is exercised on data that
actually flowed through the placeholders. `STRATUM_CLIENT=stub` in
`dynamic_config.py` selects it; environment knobs make the loops take their
non-trivial branches (repair rounds, halt, transform, reconverge, beat repair,
stop). It proves plumbing, not quality:

```
cd generator
STRATUM_CLIENT=stub STUB_PREMISE_HARD_ROUNDS=1 STUB_SPINE_FLAGGED_ROUNDS=1 \
  STUB_REVIEW_FLAG_FIRST=1 STUB_TRANSFORM_ON=2 STUB_RECONVERGE_ON=3 \
  python3 main.py --story-id=stubtest --max-iterations=5 < ../tests/kernels/kernel1.txt
```

## 6. Unvalidated against a live model (in order of risk)

1. **Every step-4 prompt.** The four originals were calibrated by hand-driven
   runs; the placeholder versions, the schemas and 4a's split have not been run
   against qwen3. First live run: one kernel with `--max-iterations=2`, read the
   4a_first trace and the first 4d trace in full, then fix the narrowest thing.
2. **Repair prompts 3.5r and 3.75r** have never produced a real revision; the
   archived batch had one flagged 3.75v (kernel2) and no hard 3.5v. Kernel28/29
   are the kernels most likely to produce a hard 3.5v finding.
3. **The reasoning-discipline block** could, in principle, suppress a useful
   late reconsideration. The carve-out is written in; check kernel2's 3b and
   kernel7's 3-0c traces (the two known late-objection cases) after the next
   batch.
4. **Context window.** 3.5's prompt is ~10k tokens with the bundle and map;
   4a_next and 4d grow with the story. The Ollama client now accepts
   `options={"num_ctx": …}` (`STRATUM_NUM_CTX` in the local `dynamic_config`);
   a server at its default window truncates silently.
5. **`accumulated_state` stories** (kernel17) run iteration 1 only, with the
   ending count carried by `shared_terminal_variants` on the terminal beat. 4d
   counts variants as endings; nothing has checked that a model actually writes
   enough of them.
6. **Craft refresh (4c5)** was unvalidated before this pass and still is.

## 7. What comes after step 4

Nothing is built past the outline. The old plan's per-node fan-out (14–17) still
applies in spirit: the beat content plus roster entries is already close to the
"node packet" the strategy doc describes, and `s4_story.json` is the input the
next phase (rooms, transitions, prose per beat) should consume.
