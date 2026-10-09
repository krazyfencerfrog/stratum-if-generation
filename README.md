# stratum-if-generation
story/content generator for the stratum-if engine

A user supplies a short story premise (a kernel); a multi-step pipeline of
local-LLM prompts analyzes it, reads it for what its genre's audience
expects, builds a premise with a real obstacle (an opposition, events the
world brings about on its own, a cast with voices and breaking points),
chooses a story framework, and then outlines the story one line at a time (a
main line, then a plan of every divergence, then the lines that leave it and
end in different worlds). The result is a story graph: nodes with short
summaries and one image each, where and who; plain-language branch triggers;
rough character and location registers; and a computed evaluation. See
`docs/outline_design.md` for the pipeline, `docs/fable_response_5.md` for
the quality pass and the first-live-run checklist, `docs/fable_response_4.md`
for why the loop has this shape, and `CLAUDE.md` for the file conventions.

Everything runs on a local model through Ollama. The stages after the outline
(beat expansion, character and setting buildout, reconciliation, per-node room
build) are designed in `docs/later_stages.md` and not yet built.

## Setup

```
python -m venv .env
pip install -e .
```

Create `generator/dynamic_config.py` (gitignored) that returns the LLM client:

```python
from ollama_client import OllamaClient

def get_client():
    return OllamaClient(host="http://localhost:11434",
                        model="qwen3.8_27b_q5-128k",
                        keep_alive="30m",
                        idle_timeout=180,
                        max_duration=14400,
                        echo=True,
                        options={"num_ctx": 32768},
                        structured="no_think")
```

- `options={"num_ctx": 32768}`: the largest prompt is about 13k tokens and
  the largest allowed output about 14k, so 32k is enough for every call. A
  much larger window costs memory the model's layers could have used; too
  small a window truncates the prompt silently. `python probe_ollama.py
  --ctx-test 32768` measures the difference on your machine.
- `structured`: `"no_think"` sends JSON schemas only on calls that run with
  thinking off. Run `python probe_ollama.py`; if it reports that structured
  output works with thinking on, set `"always"`.
- Options you set here override the sampler settings the pipeline sends per
  call (`generator/stats.py`).

## Before spending model time

```
python tests/test_plumbing.py        # ~8 s, no model: every code path on the stub client
cd generator
python probe_ollama.py               # a couple of minutes: what your Ollama server supports
```

## Running

```
cd generator
python main.py --story-id=kernel1 < ../tests/kernels/kernel1.txt       # whole pipeline
python main.py --story-id=foo --rating=PG-13 --stop-after=3.5 < k.txt   # rating filter, stop after 3.5
python main.py --story-id=kernel1 --max-iterations=2 < ...             # cap the outline at two lines (default: from the Kernel's ending tier)
python main.py --story-id=kernel1 --framework=seven_point < ...        # choose the story framework yourself
python main.py --story-id=kernel1 --branching=judge --no-promises < ... # the pre-2026-10-04 behaviour, for comparison
python report.py kernel1 --baseline ../docs/baseline_kernel1_run_stats.json   # time and trace size per stage
./todo.sh                                                              # all 35 test kernels
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt   # no model
```

To compare two versions of the prompts on the same phase-3 output (phase 3
is half the run and does not change between them):

```
cd generator
python ab.py run --variant plan  --kernels eval -- --branching=plan          # stories/<kernel>_plan/ for the 8 evaluation kernels
python ab.py run --variant judge --kernels eval -- --branching=judge --no-promises
python ab.py compare --variants plan,judge --kernels eval                    # metrics, judge scores and minutes side by side
```

`--kernels eval` is `tests/kernels/EVAL_SET.txt`; each kernel needs a
`stories/<kernel>/` directory that has run at least through phase 3. Every
finished outline also gets `<id>_eval.json`: computed metrics (where the
lines fork, how many distinct ending worlds, repeated phrases, promise
coverage, ...) and one cheap scoring call.

Output lands in `stories/<story_id>/`. The outline is `<id>_story.md` (to
read) and `<id>_story.json` (the document later stages build on). Every model
call is saved and skipped on rerun, so an interrupted run resumes where it
stopped. Delete a step's output file to redo that step (and its downstream
dependants). `<id>_run_stats.json` records every call attempt.

Each call has a budget. A call whose reasoning trace runs past its limit is
cut off and made to answer from the thinking it has; if that fails, it is
re-run once with thinking off. Reasoning that starts going round in a loop
is cut as soon as it repeats itself and re-run once from a new seed, still
thinking, before that fallback. `report.py` shows which calls did.
`--no-force-answer` skips the forced answer; `--no-breakers` turns the
limits off. `--craft-spine` adds the optional craft-spine step (3.75) after
the premise.

Story directories written by an older version of the pipeline stop the run
with a message saying what to delete; their phase-3 outputs can be kept.
