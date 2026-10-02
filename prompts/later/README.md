# Later-stage prompts (not run)

These prompts were live until 2026-10-01. They are parked, not retired: each
does work the pipeline still needs, at a stage that now comes after the
outline loop. `main.py` loads prompts from `prompts/` only, so nothing here
runs. `docs/later_stages.md` has the design for the stages they belong to;
`generator/later/` holds the code that drove them.

| file | was | belongs to | what changes when it is adapted |
|---|---|---|---|
| `sA_craft_spine.prompt` | 3.75 build | A, beat expansion | Its devices cite outline nodes, not premise turns. `escalation_shape` goes (the framework is the escalation shape). One want/need per line, since each line has its own motivation. **Its Example A is kernel1; replace it before use.** |
| `sA_craft_spine_check.prompt` | 3.75v | A | Two of its four checks are lookups (irony type against `3-0b.epistemic_gap.present`; citations against real node ids) and move into Python. What is left is a short no-think audit, the shape `s3_5v_premise_check.prompt` has now. |
| `sA_craft_spine_repair.prompt` | 3.75r | A | Return only the changed sections, as `s3_5r_premise_repair.prompt` does. |
| `sB_cast.prompt` | 3.6 | B, character buildout | Runs per character (or in small batches) on a packet: the sketch from the register, the nodes the character appears in, how each line ends for them. Emits a long form and a packet form of 150 words or fewer. |
| `sB_world.prompt` | 3.7 | B, setting buildout | Runs per location sketch: the location becomes one to three rooms with fixtures and connections, sized by the nodes that use it. `levers_placed` stays. |
| `sD_node_build.prompt` | 4b | D, per-node room build | Its packet is rebuilt from the story document: the node's summary and expansion, its locations' rooms, its characters' packets, and the plain-language triggers on its outgoing edges, which it turns into `when` conditions. |
| `sD_review.prompt` | 4d | D | Its checks (earned choices, continuity, cast and rooms) judge node interiors, so it reviews stage D's output. Its termination check is gone: `s4d_next_line.prompt` does that job in the loop. |

Lessons that apply when adapting any of them (see
`docs/step3_consolidated_design_lessons.md` §6d): give the call a packet, not
the story; put counts and lookups in Python; return only what changed from a
repair; and decide the call's class (`generator/stats.py`) before writing the
prompt, because the class is its budget.
