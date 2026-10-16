"""The worker-process side of playtest.explore_scenes(jobs=N).

A module of its own because a worker imports what it runs by module name,
and the generator loads the engine's playtest.py under another name (its own
generator/playtest.py would shadow it); this one is loaded by path instead.
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    'stratum_engine_playtest', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playtest.py'))
_playtest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_playtest)

_story = _norm = _max_states = None


def init(data, max_states):
    global _story, _norm, _max_states
    _story = _playtest.Story(data)
    _norm = _playtest.Normalizer(_story)
    _max_states = max_states


def explore(sid, entries):
    return _playtest.explore_scene(_story, sid, entries, _norm, _max_states)
