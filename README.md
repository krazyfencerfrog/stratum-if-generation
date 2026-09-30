# stratum-if-generation
story/content generator for the stratum-if engine

A user supplies a short story premise (a kernel); a multi-step pipeline of
local-LLM prompts analyzes it, builds a premise with a real obstacle, names a
cast and draws a room map, and then lays down story lines (a main line, then
one divergent line per iteration) as nodes: sections of play in a subset of
rooms, with exits reached through what the player did. See
`docs/step4_design.md` for the current pipeline and `CLAUDE.md` for the file
conventions.

## Setup

```
python -m venv .env
pip install -e .
```

Create `generator/dynamic_config.py` (not committed) that returns the LLM
client, e.g.

```python
import os
from ollama_client import OllamaClient

def get_client():
    if os.environ.get("STRATUM_CLIENT") == "stub":
        from stub_client import StubClient      # model-free plumbing test
        return StubClient()
    return OllamaClient(model=os.environ.get("STRATUM_MODEL", "qwen3:8b"),
                        options={"num_ctx": 32768})
```

`num_ctx` matters: the later prompts carry 8–12k tokens of instructions and
upstream JSON, and an Ollama server at its default window truncates silently.

## Running

```
cd generator
python main.py --story-id=kernel1 < ../tests/kernels/kernel1.txt       # whole pipeline
python main.py --story-id=foo --rating=PG-13 --stop-after=3.5 < k.txt   # rating filter, stop after 3.5
python main.py --story-id=kernel1 --max-iterations=2 < ...             # cap step-4 story lines (default 4)
./todo.sh                                                              # all 30 test kernels
STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt   # no model
```

Output lands in `stories/<story_id>/`; every model call is saved and skipped on
rerun, so an interrupted run resumes where it stopped. Delete a step's output
file to redo that step (and its downstream dependants). Final step-4 output is
`<id>_s4_story.json` and `<id>_s4_story.md`.

Story directories written before 2026-09-29 use older schemas; the pipeline
names the stale file and stops. Delete the directory for a fresh run.
