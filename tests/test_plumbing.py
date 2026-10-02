#!/usr/bin/env python3
"""Plumbing tests: no test framework, no model, about ten seconds.

    python tests/test_plumbing.py            # from the repo root, or anywhere
    python tests/test_plumbing.py --keep     # leave the test story directories
    python tests/test_plumbing.py -k linear  # only tests whose name contains "linear"

Runs the whole pipeline on the stub client (generator/stub_client.py) under
every scenario the stub can stage, and asserts what must hold whatever a
model writes: the story graph's invariants (generator/checks.py), the
premise repair loop, informed retries, the circuit-breaker fallback,
resume-by-files, the schema stamp. Then exercises the Ollama client
against a fake server (streaming, the thinking field, breakers, structured
outputs, stats), the computed checks against deliberately broken stories,
and the small pure helpers.

Run it before spending model hours: it proves the plumbing, and nothing
about story quality. Exit code 0 means every test passed.
"""

import argparse
import contextlib
import glob
import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, 'generator')
STORIES = os.path.join(ROOT, 'stories')
KERNELS = os.path.join(ROOT, 'tests', 'kernels')
PREFIX = 'zzt_'

sys.path.insert(0, GEN)
import checks            # noqa: E402
import brief             # noqa: E402
import frameworks        # noqa: E402
import schemas           # noqa: E402
import stats as stats_mod  # noqa: E402
from llm_client import LlmCallError   # noqa: E402
from ollama_client import OllamaClient  # noqa: E402

TESTS = []
used_prompts = set()


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond, message):
    if not cond:
        raise AssertionError(message)


# ---------------------------------------------------------------- running the pipeline

def story_dir(name):
    return os.path.join(STORIES, PREFIX + name)


def run(name, kernel='kernel1', args=(), env=None, fresh=True, expect=0):
    """Run main.py on the stub. Returns (returncode, stdout+stderr)."""
    if fresh:
        shutil.rmtree(story_dir(name), ignore_errors=True)
    e = dict(os.environ)
    for k in list(e):
        if k.startswith('STUB_'):
            del e[k]
    e['STRATUM_CLIENT'] = 'stub'
    e.update(env or {})
    with open(os.path.join(KERNELS, f'{kernel}.txt'), 'rb') as f:
        proc = subprocess.run([sys.executable, 'main.py', f'--story-id={PREFIX}{name}', *args],
                              cwd=GEN, env=e, stdin=f, capture_output=True)
    out = proc.stdout.decode() + proc.stderr.decode()
    check(proc.returncode == expect, f'{name}: exit code {proc.returncode}, expected {expect}\n{out[-3000:]}')
    stats_path = os.path.join(story_dir(name), f'{PREFIX}{name}_run_stats.json')
    if os.path.isfile(stats_path):
        for c in json.load(open(stats_path))['calls']:
            used_prompts.add(c['prompt_file'])
    return proc.returncode, out


def load(name, suffix):
    with open(os.path.join(story_dir(name), f'{PREFIX}{name}_{suffix}'), encoding='utf-8') as f:
        return json.load(f) if suffix.endswith('.json') else f.read()


def calls(name):
    return load(name, 'run_stats.json')['calls']


def assert_story_ok(name, min_lines=1):
    story = load(name, 'story.json')
    result = checks.check_story(story)
    check(not result['findings'], f'{name}: broken invariants: {result["findings"]}')
    check(story['checks']['findings'] == [], f'{name}: the saved document records findings')
    check(story['schema_version'] == stats_mod.SCHEMA_VERSION, 'schema_version missing from the story document')
    check(len(story['lines']) >= min_lines, f'{name}: {len(story["lines"])} line(s), expected at least {min_lines}')
    for nid, node in story['nodes'].items():
        check(node['summary'] and node['title'], f'{name}: node {nid} was never filled')
        check(node['where'] and all(w in story['locations'] for w in node['where']), f'{name}: node {nid} has no resolved location')
        check(all(w in story['characters'] for w in node['who']), f'{name}: node {nid} has an unresolved character')
        for banned in ('interactions', 'exits', 'requires', 'sets', 'fixtures', 'state'):
            check(banned not in node, f'{name}: node {nid} carries "{banned}", which belongs to a later stage')
    md = load(name, 'story.md')
    check('## Lines x beats' in md and '## Nodes' in md, f'{name}: story.md is missing sections')
    return story


# ---------------------------------------------------------------- pipeline scenarios

@test
def basic_run_and_resume():
    run('basic')
    story = assert_story_ok('basic', min_lines=2)
    check(story['framework']['id'] in frameworks.framework_ids(), 'no framework chosen')
    check(any(e['kind'] == 'branch' and e['trigger']['text'] for e in story['edges']), 'no branch edge carries a trigger')
    grid = story['grid']
    check(set(grid['rows']) == set(story['lines']), 'the grid does not have one row per line')
    check(all(c['mode'] == 'no_think' for c in calls('basic') if c['step'] in ('s2', 's3_5c', 's3_5v', 's3_8')),
          'a classify-class call ran with thinking on')
    check(all(c['mode'] == 'think' for c in calls('basic') if c['step'] in ('s3_5a', 's4a', 's4b', 's4c', 's4d')),
          'a build-class call ran with thinking off')
    n_calls = len(calls('basic'))
    n_logs = len(glob.glob(os.path.join(story_dir('basic'), '*.log')))
    before = load('basic', 'story.json')
    _, out = run('basic', fresh=False)
    check(len(calls('basic')) == n_calls, 'a rerun made model calls')
    check(len(glob.glob(os.path.join(story_dir('basic'), '*.log'))) == n_logs, 'a rerun wrote new logs')
    check('no model calls this session' in out, 'the rerun did not report zero calls')
    check(load('basic', 'story.json') == before, 'a rerun changed the story document')


@test
def premise_repair_loop():
    run('repair', env={'STUB_PREMISE_HARD_ROUNDS': '1'})
    loop = load('repair', 's3_5_loop.json')
    check(loop['repair_rounds_used'] == 1 and not loop['still_failing'], f'unexpected loop: {loop}')
    check(loop['rounds'][0]['findings'] and not loop['rounds'][1]['findings'], 'findings did not clear after repair')
    check(loop['rounds'][1]['changed'] == ['complications'], 'repair should have returned only the section it changed')
    original, accepted = load('repair', 's3_5_premise.json'), load('repair', 's3_5_premise_accepted.json')
    check('crew-trust score' in json.dumps(original) and 'crew-trust score' not in json.dumps(accepted), 'the violation was not repaired')
    for key in ('protagonist', 'opposition', 'mediation', 'turns', 'cast_seeds'):
        check(original[key] == accepted[key], f'repair touched {key}, which no finding named')
    assert_story_ok('repair')


@test
def premise_halt():
    _, out = run('halt', env={'STUB_PREMISE_ALWAYS_HARD': '1'}, expect=2)
    check('PIPELINE HALTED' in out, 'no halt message')
    check(load('halt', 's3_5_loop.json')['still_failing'], 'loop.json should record the standing finding')
    check(not os.path.exists(os.path.join(story_dir('halt'), f'{PREFIX}halt_story.json')), 'the outline ran on a failed premise')


@test
def informed_retries():
    run('retry', env={'STUB_BAD_CAST': '1', 'STUB_BAD_PLAN': '1'})
    cs = calls('retry')
    for step in ('s3_5c', 's4a'):
        attempts = [c for c in cs if c['step'] == step]
        check(len(attempts) == 2 and not attempts[0]['ok'] and attempts[1]['ok'], f'{step}: expected a rejected attempt then an accepted one')
    prompt = load('retry', 's4a_i1_raw_input_prompt.txt')
    check('YOUR PREVIOUS ANSWER WAS REJECTED' in prompt and 'are not placed' in prompt, 'the retry was not told what was wrong')
    assert_story_ok('retry')


@test
def sloppy_answers_are_normalized():
    run('sloppy', env={'STUB_SLOPPY': '1'})
    story = assert_story_ok('sloppy', min_lines=2)
    check(len(story['locations']) <= 4, f"name variants were registered as new places: {[l['name'] for l in story['locations'].values()]}")
    check(all(isinstance(n['turn'], (int, type(None))) for n in story['nodes'].values()), 'a turn id stayed a string')


@test
def breaker_falls_back_to_no_think():
    run('breaker', env={'STUB_ABORT': 's4a'})
    attempts = [c for c in calls('breaker') if c['step'] == 's4a']
    check(len(attempts) == 2, f'expected two s4a attempts, got {len(attempts)}')
    check(attempts[0]['breaker'] == 'thinking_bytes' and attempts[0]['mode'] == 'think' and not attempts[0]['ok'], 'first attempt should be the cut one')
    check(attempts[1]['mode'] == 'no_think' and attempts[1]['ok'], 'second attempt should be the no-think fallback')
    check(glob.glob(os.path.join(story_dir('breaker'), f'{PREFIX}breaker_s4a_i1_raw_output_thinking_cut_*.txt')), 'the cut trace was not kept')
    assert_story_ok('breaker')
    # a cut with nothing to fall back to (a call that already runs without thinking) stops the run
    # once, with the partial trace named, instead of repeating the same call
    _, out = run('breaker_dead', env={'STUB_ABORT': 's3_8', 'STUB_ABORT_ALWAYS': '1'}, expect=1)
    attempts = [c for c in calls('breaker_dead') if c['step'] == 's3_8']
    check(len(attempts) == 1 and attempts[0]['breaker'], f'a hopeless cut was retried: {len(attempts)} attempts')
    check('nothing left to fall back to' in out and 'cut_' in out, 'the stop did not say why or where the trace is')


@test
def breaker_forces_the_answer_first():
    run('forced', env={'STUB_FORCE': 's4a'})
    attempts = [c for c in calls('forced') if c['step'] == 's4a']
    check(len(attempts) == 1 and attempts[0]['ok'] and attempts[0].get('forced_answer'),
          f'a forced answer should be accepted in one attempt: {attempts}')
    assert_story_ok('forced')
    run('forced_off', env={'STUB_FORCE': 's4a'}, args=['--no-force-answer'])
    attempts = [c for c in calls('forced_off') if c['step'] == 's4a']
    check(len(attempts) == 1 and not attempts[0].get('forced_answer'), '--no-force-answer still forced')


@test
def craft_spine_opt_in():
    run('craft', env={'STUB_SPINE_FLAGGED_ROUNDS': '1'}, args=['--craft-spine'])
    loop = load('craft', 's3_75_loop.json')
    check(loop['repair_rounds_used'] == 1 and not loop['still_failing'], f'the craft spine should be repaired once: {loop}')
    r0 = load('craft', 's3_75_check_r0.json')
    check(any('index' in f['check'] for f in r0['findings']), f'the index citation was not found by code: {r0}')
    prompt = load('craft', 's4a_i1_raw_input_prompt.txt')
    check('to be answerable to someone' in prompt, 'the main line call did not receive the craft spine')
    assert_story_ok('craft')
    # off by default: no craft files, and the line calls say none
    run('nocraft')
    check(not os.path.exists(os.path.join(story_dir('nocraft'), f'{PREFIX}nocraft_s3_75_craft_spine.json')),
          'the craft spine ran without --craft-spine')
    prompt = load('nocraft', 's4a_i1_raw_input_prompt.txt')
    check('(or none)\nnone' in prompt, 'without --craft-spine the main line should receive "none"')


@test
def rejoin_new_cast_and_nothing():
    run('graph', args=['--max-iterations=6'],
        env={'STUB_NEW_CAST_ON': '2', 'STUB_REJOIN_ON': '3', 'STUB_NOTHING_ON': '4', 'STUB_STOP_AFTER': '9'})
    story = assert_story_ok('graph', min_lines=3)
    check(len(story['lines']) == 3, f"expected 3 lines, got {len(story['lines'])}")
    check('4c found the seed did not hold' in story['stop_reason'], f"stop reason: {story['stop_reason']}")
    t3 = story['lines']['T3']
    check(t3['rejoins_at'] == story['lines']['T1']['path'][-1], 'T3 should rejoin the main ending')
    check(any(e['kind'] == 'rejoin' for e in story['edges']), 'no rejoin edge')
    check(t3['ending']['node'] == story['lines']['T1']['ending']['node'], 'a rejoined line ends where the line it rejoins ends')
    labels = {c['label'] for c in story['characters'].values()}
    check({'the drone technician', 'the dock crew'} <= labels, 'new characters were not registered')
    crowd_node = next(n for n in story['nodes'].values() if any(story['characters'][c]['label'] == 'the dock crew' for c in n['who']))
    check(any(story['characters'][c]['label'] == 'the drone technician' for c in crowd_node['who']), 'a crowd was left without its voice')
    check(any('without a voice' in w for w in story['warnings']), 'the auto-added representative was not reported')
    check('the drone dock' in {l['name'] for l in story['locations'].values()}, 'the new location was not registered')


@test
def linear_shape():
    run('linear', kernel='kernel17')
    story = assert_story_ok('linear', min_lines=2)
    check(story['shape']['linear'], 'kernel17 should be linear')
    main = story['lines']['T1']
    for lid in story['line_order'][1:]:
        line = story['lines'][lid]
        check(line['divergence']['diverges_at'] == main['path'][-2], f'{lid} forks before the last node of a linear story')
        check(len(line['new_nodes']) == 1 and line['divergence']['trigger_kind'] == 'accumulated', f'{lid} is not a single accumulated ending')
        check(line['path'][:-1] == main['path'][:-1], f'{lid} does not share the whole road')


@test
def one_line_and_overrides():
    run('one', args=['--max-iterations=1', '--framework=three_act'])
    story = assert_story_ok('one')
    check(len(story['lines']) == 1 and story['framework']['id'] == 'three_act', 'override or cap not honored')
    fills = [c['prefix'] for c in calls('one') if c['step'] == 's4b']
    check(fills == ['s4b_i1', 's4b_i1_p2'], f'a seven-node line should be filled in two calls, got {fills}')
    second = load('one', 's4b_i1_p2_raw_input_prompt.txt')
    check('"already_told"' in second and story['nodes']['N04']['summary'] in second, 'the second fill call was not shown what the first one wrote')
    check(not [c for c in calls('one') if c['step'] == 's4d'], 'the judge ran with no line left to build')
    run('rated', args=['--rating=PG-13', '--stop-after=3.8'])
    check(not os.path.exists(os.path.join(story_dir('rated'), f'{PREFIX}rated_story.json')), '--stop-after=3.8 ran the outline')
    check(os.path.isfile(os.path.join(story_dir('rated'), f'{PREFIX}rated_s3_8_framework.json')), '3.8 did not run')
    run('nothink', args=['--no-think-steps=s4b', '--think-steps=s3_8', '--max-iterations=1'])
    modes = {c['step']: c['mode'] for c in calls('nothink')}
    check(modes['s4b'] == 'no_think' and modes['s3_8'] == 'think', f'think overrides not honored: {modes}')


@test
def stale_directories_fail_loudly():
    d = story_dir('stale')
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    open(os.path.join(d, f'{PREFIX}stale_s4a_i1_main_line.json'), 'w').write('{}')
    _, out = run('stale', fresh=False, expect=2)
    check('older pipeline schema' in out and 'rm -f' in out, 'an unstamped old directory did not say what to delete')
    shutil.rmtree(d)
    os.makedirs(d)
    open(os.path.join(d, f'{PREFIX}stale_pipeline.json'), 'w').write('{"schema_version": 3}')
    _, out = run('stale', fresh=False, expect=2)
    check('schema 3' in out, 'a directory stamped with another schema was accepted')
    # phase-3 outputs alone are adopted
    run('adopt', args=['--stop-after=3'])
    os.remove(os.path.join(story_dir('adopt'), f'{PREFIX}adopt_pipeline.json'))
    n = len(calls('adopt'))
    run('adopt', fresh=False, args=['--stop-after=3'])
    check(len(calls('adopt')) == n, 'adopting a phase-3 directory re-ran phase 3')
    check(load('adopt', 'pipeline.json')['schema_version'] == stats_mod.SCHEMA_VERSION, 'the adopted directory was not stamped')
    # a saved file that no longer matches its validator is named
    run('stalefile', args=['--max-iterations=1'])
    path = os.path.join(story_dir('stalefile'), f'{PREFIX}stalefile_s4a_i1_main_line.json')
    open(path, 'w').write('{"nodes": []}')
    proc = subprocess.run([sys.executable, 'main.py', f'--story-id={PREFIX}stalefile', '--max-iterations=1'], cwd=GEN,
                          env=dict(os.environ, STRATUM_CLIENT='stub'), stdin=subprocess.DEVNULL, capture_output=True)
    check(proc.returncode != 0 and b'no longer matches the schema' in proc.stderr, 'a stale saved file was not named')


@test
def every_prompt_is_exercised():
    have = {os.path.basename(p) for p in glob.glob(os.path.join(ROOT, 'prompts', '*.prompt'))}
    unused = have - used_prompts
    check(not unused, f'prompts no scenario exercised: {sorted(unused)}')
    for p in have:
        text = open(os.path.join(ROOT, 'prompts', p), encoding='utf-8').read()
        check('kernel1' not in text.lower(), f'{p} mentions kernel1')


# ---------------------------------------------------------------- computed checks on broken stories

def kinds(story):
    return {f['kind'] for f in checks.check_story(story)['findings']}


@test
def checks_catch_broken_graphs():
    good = load('graph', 'story.json') if os.path.isdir(story_dir('graph')) else None
    if good is None:
        run('graph', args=['--max-iterations=6'], env={'STUB_NEW_CAST_ON': '2', 'STUB_REJOIN_ON': '3', 'STUB_NOTHING_ON': '4', 'STUB_STOP_AFTER': '9'})
        good = load('graph', 'story.json')
    check(not kinds(good), 'the reference story is not clean')

    def mutated(fn):
        s = json.loads(json.dumps(good))
        fn(s)
        return kinds(s)

    t1 = good['lines']['T1']['path']
    t2 = good['lines']['T2']
    check('no_ending' in mutated(lambda s: s['nodes'][t1[-1]].update(is_ending=False)), 'missing ending not caught')
    check('unknown_node' in mutated(lambda s: s['lines']['T1']['path'].append('N99')), 'unknown node not caught')
    check('beats_out_of_order' in mutated(lambda s: s['nodes'][t1[1]].update(beat=s['framework']['beats'][-1]['id'])), 'beat order not caught')
    check('unknown_beat' in mutated(lambda s: s['nodes'][t1[1]].update(beat='nonsense')), 'unknown beat not caught')
    check('beat_uncovered' in mutated(lambda s: s['nodes'][t1[1]].update(beat=s['nodes'][t1[0]]['beat'])), 'uncovered beat not caught')
    check('turn_twice' in mutated(lambda s: s['nodes'][t1[2]].update(turn=s['nodes'][t1[1]]['turn'])), 'repeated turn not caught')
    check('turn_unplaced' in mutated(lambda s: s['nodes'][t1[1]].update(turn=None)), 'unplaced turn not caught')
    check('no_trigger' in mutated(lambda s: s['lines']['T2']['divergence'].update(trigger='')), 'missing trigger not caught')
    check('unreachable_branch' in mutated(lambda s: s['lines']['T2']['divergence'].update(diverges_at=t2['new_nodes'][-1])) or
          'no_divergence' in mutated(lambda s: s['lines']['T2']['divergence'].update(diverges_at='N99')), 'bad divergence not caught')
    check('unknown_location' in mutated(lambda s: s['nodes'][t1[0]].update(where=['L99'])), 'unknown location not caught')
    check('no_location' in mutated(lambda s: s['nodes'][t1[0]].update(where=[])), 'missing location not caught')
    check('unknown_character' in mutated(lambda s: s['nodes'][t1[0]].update(who=['C99'])), 'unknown character not caught')
    crowd = next(cid for cid, c in good['characters'].items() if c['kind'] == 'crowd')
    check('crowd_without_voice' in mutated(lambda s: s['nodes'][t1[0]].update(who=[crowd])), 'crowd without voice not caught')

    def drop_reps(s):
        for c in s['characters'].values():
            c['speaks_for'] = None
    check('crowd_without_representative' in mutated(drop_reps), 'crowd without representative not caught')
    check('ending_mid_path' in mutated(lambda s: s['nodes'][t1[1]].update(is_ending=True)), 'ending mid-path not caught')
    check('orphan_node' in mutated(lambda s: s['nodes'].update(X1=dict(s['nodes'][t1[0]], id='X1'))), 'orphan node not caught')

    def cycle(s):
        s['lines']['T1']['path'] = t1[:2] + [t1[0]] + t1[2:]
    check({'repeated_node', 'cycle'} & mutated(cycle), 'cycle not caught')
    menu = json.loads(json.dumps(good))
    menu['lines']['T2']['divergence']['trigger'] = 'You choose to vent the sector'
    check('menu_trigger' in {f['kind'] for f in checks.check_story(menu)['notes']}, 'a menu-phrased trigger was not noted')


# ---------------------------------------------------------------- the loop's validators, driven directly

class FakeGen:
    """Just enough of StoryGenerator for OutlineBuilder: run_prompt hands
    back a canned answer after running the real validator on it."""

    def __init__(self, answers, beats=None):
        fw = frameworks.framework('three_act')
        self.analysis = {
            'framework': dict(fw, modifier={'id': 'none'}, reading='', why=''),
            's3_brief': {},
            's3_5_premise': {
                'protagonist': {}, 'opposition': {}, 'mediation': {},
                'turns': [{'id': i, 'situation': f's{i}', 'what_you_must_do': 'x', 'involves': [],
                           'ways_through': [{'way': 'a', 'cost': 'c'}, {'way': 'b', 'cost': 'c'}]} for i in (1, 2, 3)],
                'cast_seeds': [{'role': 'the life-support overseer', 'kind': 'individual', 'opposition': True},
                               {'role': 'the widow', 'kind': 'individual'}],
            },
        }
        self.shape, self.kernel, self.story_id, self.answers = {}, 'k', 'fake', answers

    @staticmethod
    def to_json(value, indent=2):
        return json.dumps(value)

    def run_prompt(self, prefix, name, repl, prompt_file=None, validator=None, klass=None, schema=None):
        answer = json.loads(json.dumps(self.answers[prefix]))
        validator(answer)
        return answer

    def save_story_json(self, *a):
        pass

    save_story_file = save_story_json


def entry(beat, turn=None, way=None):
    return {'beat': beat, 'turn': turn, 'way': way if turn is None else (way or 1), 'adapted': f'{beat} happens'}


def plan(beats):
    return {'through_line': {'title': 't', 'motivation': 'm', 'strategy': 's', 'turning_point': 'p', 'differs_from': 'd'},
            'ending': {'title': 'e', 'summary': 'e'}, 'beats': beats, 'skipped_beats': []}


def branch(at, beats, rejoin=None, skipped=()):
    return dict(plan(beats), status='proposed', why='w', rejoins_at=rejoin,
                skipped_beats=[{'beat': b, 'reason': 'r'} for b in skipped],
                divergence={'diverges_at': at, 'trigger': 'you did it', 'trigger_kind': 'act', 'way': None,
                            'instead_of': 'you did not', 'opportunity': None, 'shift': 's'})


def nodes_for(ids, where='the hall', who=()):
    return {'nodes': [{'id': i, 'title': 't', 'summary': 's', 'where': [where], 'who': list(who)} for i in ids],
            'new_locations': [{'name': where, 'kind': 'k', 'why': 'w'}], 'new_characters': []}


MAIN = [entry('setup'), entry('inciting_incident', 1), entry('commitment'), entry('commitment', 2),
        entry('midpoint'), entry('crisis', 3), entry('climax'), entry('resolution')]
LATER = ['midpoint', 'crisis', 'climax', 'resolution']


def builder(answers):
    from outline import OutlineBuilder
    b = OutlineBuilder(FakeGen(answers), max_iterations=9)
    line, ids = b.apply_main_line(b.main_line())
    b.apply_fill(line, ids, nodes_for(ids))
    return b


def rejected(b, n, seed_at, needle):
    try:
        b.divergence(n, {'diverges_at': seed_at})
    except ValueError as e:
        check(needle in str(e), f'rejected for the wrong reason: {e}')
        return
    check(False, f'a divergence that should be rejected ({needle}) was accepted')


@test
def rejoin_paths_are_checked_whole():
    # T2 leaves N01 and rejoins N04 (same beat as N03, which it skips, turn 2 lives on N04)
    b = builder({'s4a_i1': plan(MAIN), 's4c_i2': branch('N02', [entry('commitment')], rejoin='N04'),
                 # T3 would leave N04 and rejoin T2's own node, whose onward path leads back through N04
                 's4c_i3': branch('N04', [entry('commitment')], rejoin='T2N01')})
    line, ids = b.apply_divergence(2, b.divergence(2, {'diverges_at': 'N02'}))
    b.apply_fill(line, ids, nodes_for(ids))
    check(not checks.check_story(b.story_json())['findings'], 'a plain rejoin broke an invariant')
    rejected(b, 3, 'N04', 'a second time')

    # turn order across a rejoin: T2 = N01, (turn 1), (turn 3), ending; T3 plays turn 2 and rejoins before turn 1
    b = builder({'s4a_i1': plan(MAIN),
                 's4c_i2': branch('N01', [entry('inciting_incident', 1), entry('crisis', 3), entry('resolution')],
                                  skipped=['commitment', 'midpoint', 'climax']),
                 's4c_i3': branch('N01', [entry('inciting_incident', 2)], rejoin='T2N01')})
    line, ids = b.apply_divergence(2, b.divergence(2, {'diverges_at': 'N01'}))
    b.apply_fill(line, ids, nodes_for(ids))
    rejected(b, 3, 'N01', 'out of order')

    # a status with stray whitespace is still a proposal, and is saved clean
    b = builder({'s4a_i1': plan(MAIN), 's4c_i2': dict(branch('N05', [entry('crisis', 3), entry('resolution')], skipped=['climax']), status=' Proposed ')})
    check(b.divergence(2, {'diverges_at': 'N05'})['status'] == 'proposed', 'status was not normalized')
    # a turn written as 2.0 or "2" is turn 2
    b = builder({'s4a_i1': plan([dict(e, turn=('2.0' if e['turn'] == 2 else e['turn'])) for e in MAIN])})
    check(b.nodes['N04']['turn'] == 2, 'a float-formatted turn id was dropped')


@test
def register_names_are_not_merged():
    from outline import OutlineBuilder, norm
    check(norm('Sector A') != norm('Sector B') and norm('the Mill') == norm('mill'), 'norm')
    b = builder({'s4a_i1': plan(MAIN)})
    line = b.lines['T1']
    fill = {'nodes': [{'id': 'N01', 'title': 't', 'summary': 's', 'where': ['Sector B', 'the east gate'], 'who': ["the widow's son", 'the overseer']},
                      {'id': 'N02', 'title': 't', 'summary': 's', 'where': ['Sector A'], 'who': ['the widow']}],
            'new_locations': [{'name': 'Sector A', 'kind': 'k', 'why': 'w'}, {'name': 'Sector B', 'kind': 'k', 'why': 'w'},
                              {'name': 'the west gate', 'kind': 'k', 'why': 'w'}, {'name': 'the east gate', 'kind': 'k', 'why': 'w'}],
            'new_characters': [{'label': "the widow's son", 'kind': 'individual', 'speaks_for': None, 'wants': 'w', 'holds': 'h', 'why': 'y'},
                               {'label': 'the dock crew', 'kind': 'crowd', 'speaks_for': None, 'wants': 'w', 'holds': 'h', 'why': 'y'},
                               {'label': 'the crane driver', 'kind': 'individual', 'speaks_for': 'Dock crew', 'wants': 'w', 'holds': 'h', 'why': 'y'}]}
    b.apply_fill(line, ['N01', 'N02'], fill)
    names = {l['name'] for l in b.locations.values()}
    check({'Sector A', 'Sector B', 'the west gate', 'the east gate'} <= names, f'declared places were merged: {names}')
    labels = {c['label']: cid for cid, c in b.characters.items()}
    check("the widow's son" in labels and labels["the widow's son"] != labels['the widow'], 'a declared character was merged into another')
    n1, n2 = b.nodes['N01'], b.nodes['N02']
    check([b.locations[x]['name'] for x in n1['where']] == ['Sector B', 'the east gate'] and b.locations[n2['where'][0]]['name'] == 'Sector A', 'where resolved to the wrong place')
    who = [b.characters[x]['label'] for x in n1['who']]
    check(who == ["the widow's son", 'the life-support overseer'], f'who resolved wrongly: {who}')
    check(any('was read as the registered character' in w for w in b.warnings), 'a shortened reference was resolved silently')
    # a representative named with a different article or case still counts, in the validators and in the checks
    story = b.story_json()
    check('crowd_without_representative' not in kinds(story), 'checks and validators disagree about who speaks for a crowd')


@test
def malformed_premise_sections_are_rejected_early():
    sys.path.insert(0, GEN)
    import main as pipeline
    good = {'protagonist': {'who': 'w', 'wants': 'w', 'can_do': 'c', 'cannot_do': 'n'}, 'arena': {'description': 'd'},
            'pressure': {'description': 'd'}, 'opposition': {'who_or_what': 'w', 'wants': 'w', 'means': 'm'},
            'mediation': {'question': 'q', 'to_reach_pole_a': {'pole': 'p', 'what_you_must_do': 'd', 'cost': 'c'},
                          'to_reach_pole_b': {'pole': 'p', 'what_you_must_do': 'd', 'cost': 'c'}, 'levers': ['l']}}
    pipeline.StoryGenerator.validate_engine(json.loads(json.dumps(good)))
    bad = json.loads(json.dumps(good))
    bad['mediation']['to_reach_pole_a'] = 'vent: obtain an override'
    try:
        pipeline.StoryGenerator.validate_engine(bad)
        check(False, 'a pole given as a string passed 3.5a')
    except ValueError as e:
        check('must be an object' in str(e), str(e))
    turns = {'turns': [{'situation': 's', 'what_you_must_do': 'd', 'ways_through': [{'way': 'w', 'cost': 'c'}], 'involves': 'the warden', 'form': 'discover'}] * 2}
    turns = json.loads(json.dumps(turns))
    pipeline.StoryGenerator.validate_turns(turns)
    check(turns['turns'][0]['involves'] == ['the warden'], 'involves given as a string was split into characters')
    premise = dict(good, turns=[{'id': 1, 'involves': ['the nursery families', 'the warden']}], complications=[],
                   cast_seeds=[{'role': 'the nursery families', 'kind': 'crowd'}, {'role': 'the warden', 'kind': 'individual'}])
    merged = pipeline.StoryGenerator.merge_premise(premise, {'enrichment_budget': 'x', 'cast_seeds': [
        {'role': 'nursery families', 'kind': 'crowd'}, {'role': 'The warden', 'kind': 'individual', 'speaks_for': 'The nursery families', 'opposition': 'false'}]})
    seeds = {s['role']: s for s in merged['cast_seeds']}
    check(set(seeds) == {'the nursery families', 'the warden'} and seeds['the warden']['speaks_for'] == 'the nursery families'
          and seeds['the warden']['opposition'] is False and seeds['the warden']['matters_to_turns'] == [1], f'repair merge did not canonicalize the cast: {seeds}')
    check(pipeline.as_bool('true') and not pipeline.as_bool('false') and pipeline.as_bool(None, default=True), 'as_bool')


# ---------------------------------------------------------------- pure helpers

@test
def helpers():
    for i in range(1, 31):
        text = open(os.path.join(KERNELS, f'kernel{i}.txt'), encoding='utf-8').read()
        clauses = brief.kernel_clauses(text)
        check(clauses and all(c.strip() for _, c in clauses), f'kernel{i}: no clauses')
        check([n for n, _ in clauses] == list(range(1, len(clauses) + 1)), f'kernel{i}: clause numbering')
    for stated, tier in (('6 or 7', 'several'), ('at least five', 'several'), ('a dozen', 'many'), ('one ending', 'one'),
                         ('a single ending', 'one'), ('more than one ending', None), ('at least one of them happy', None),
                         ('two or three', 'few'), ('the verdict should vary', None), ('', None)):
        check(brief.ending_tier_from_stated(stated) == tier, f'tier for {stated!r}')
    b = load('basic', 's3_brief.json')
    lines = brief.brief_lines(b)
    check('3-0a.primary_decision_axis [constraint]' in lines and 'enrichment_budget' in lines, 'brief_lines lost a field')
    check(len(lines) < len(json.dumps(b, indent=2)) * 0.7, 'brief_lines is not smaller than the JSON')
    check(brief.valid_serves('3-0a.primary_decision_axis', b) and brief.valid_serves('3c', b) and not brief.valid_serves('3x.nope', b), 'valid_serves')
    for s in ('s4b_i2', 's3_5v_r1', 's3_5r2', 's4d_i3'):
        check(stats_mod.step_of(s) in ('s4b', 's3_5v', 's3_5r', 's4d'), f'step_of({s})')
    lib = frameworks.library()
    ids = [f['id'] for f in lib['frameworks']]
    check(len(ids) == len(set(ids)) and frameworks.FALLBACK in ids, 'framework ids')
    for fw in lib['frameworks']:
        beats = [x['id'] for x in fw['beats']]
        check(4 <= len(beats) <= 8 and len(beats) == len(set(beats)), f"{fw['id']}: beats")
        check(fw['beats'][0].get('required', True) and fw['beats'][-1].get('required', True), f"{fw['id']}: first and last beats must be required")
    short = frameworks.shortlist(b, 'a story', 'x')
    check(len(short['candidates']) == 3 and short['candidates'][0]['fits_because'], 'shortlist')
    check({c['id'] for c in frameworks.shortlist(b, 'x', 'a')['candidates']} == {c['id'] for c in frameworks.shortlist(b, 'x', 'b')['candidates']},
          'the shortlist changed with the story id (only its order may)')
    kernel2 = open(os.path.join(KERNELS, 'kernel2.txt'), encoding='utf-8').read()
    check([c['id'] for c in frameworks.shortlist(b, kernel2, 'x')['candidates']] == ['freytag'], 'a named form must be the only candidate')
    check({m['id'] for m in frameworks.available_modifiers(b)} >= {'none', 'countdown'}, 'modifiers')
    json.dumps(schemas.ALL)
    json.dumps(schemas.story_form(['a'], ['none']))
    for path in glob.glob(os.path.join(GEN, '*.py')) + glob.glob(os.path.join(GEN, 'later', '*.py')):
        py_compile.compile(path, doraise=True)


# ---------------------------------------------------------------- the Ollama client against a fake server

class FakeOllama(BaseHTTPRequestHandler):
    """Speaks just enough of /api/generate. The prompt is a JSON object of
    directives: thinking_bytes, response, delay (seconds per chunk),
    done_reason, inline_think, reject_format."""
    received = []
    raw_prompts = []
    disconnects = 0
    reject_think = False

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'version': '0.0-fake'}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        FakeOllama.received.append(body)
        if self.path == '/api/show':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'parameters': 'num_ctx 131072', 'capabilities': ['completion', 'thinking'],
                                         'details': {'parameter_size': '27B', 'quantization_level': 'Q5_K_M'}}).encode())
            return
        try:
            d = json.loads(body.get('prompt', '{}').replace('/no_think', ''))
        except json.JSONDecodeError:
            d = {}
        if d.get('reject_all'):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "model not found"}')
            return
        if (d.get('reject_think') or FakeOllama.reject_think) and 'think' in body:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "\\"fake\\" does not support thinking"}')
            return
        if body.get('raw'):
            # the budget-forcing continuation: answer at once, no thinking
            d = {'thinking_bytes': 0, 'response': '{"forced": true}', 'raw_seen': True}
            FakeOllama.raw_prompts.append(body.get('prompt', ''))
        if d.get('reject_format') and 'format' in body:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "invalid format schema"}')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()
        think = body.get('think', True) is not False and not body.get('prompt', '').rstrip().endswith('/no_think')
        n_think = d.get('thinking_bytes', 300) if think else 0
        response = d.get('response', '{"ok": true}')
        chunks = []
        if d.get('inline_think'):
            chunks.append({'response': '<think>' + 'r' * n_think + '</think>'})
        else:
            chunks += [{'thinking': 't' * 100} for _ in range(n_think // 100)]
        chunks += [{'response': response[i:i + 40]} for i in range(0, len(response), 40)]
        if d.get('raw_chunks'):
            chunks = [{'response': c} for c in d['raw_chunks']]
        try:
            for c in chunks:
                if d.get('delay'):
                    time.sleep(d['delay'])
                self.wfile.write((json.dumps(dict(c, done=False)) + '\n').encode())
                self.wfile.flush()
            if d.get('no_done'):
                return
            if d.get('done_delay'):
                time.sleep(d['done_delay'])
            self.wfile.write((json.dumps({'done': True, 'done_reason': d.get('done_reason', 'stop'), 'prompt_eval_count': 123,
                                          'eval_count': 456, 'eval_duration': 2_000_000_000, 'load_duration': 500_000_000}) + '\n').encode())
        except (BrokenPipeError, ConnectionResetError):
            FakeOllama.disconnects += 1


@test
def ollama_client_against_fake_server():
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f'http://127.0.0.1:{server.server_port}'
    try:
        client = OllamaClient(host=host, model='fake', echo=False, idle_timeout=5, max_duration=30, options={'num_ctx': 32768})
        schema = {'type': 'object'}

        thinking, response = client.run_prompt(json.dumps({'thinking_bytes': 500, 'response': '{"a": 1}'}),
                                               format=schema, options={'temperature': 0.6, 'num_ctx': 1}, limits={'num_predict': 99})
        sent = FakeOllama.received[-1]
        check(len(thinking) == 500 and response == '{"a": 1}', 'thinking and response were not separated')
        check('format' not in sent and 'think' not in sent, 'a thinking call sent format or think by default')
        check(sent['options'] == {'temperature': 0.6, 'num_ctx': 32768, 'num_predict': 99}, f"options merge wrong: {sent['options']}")
        info = client.last_call
        check(info['prompt_tokens'] == 123 and info['output_tokens'] == 456 and info['eval_seconds'] == 2.0 and info['done_reason'] == 'stop', f'stats: {info}')
        check(info['aborted'] is None and info['thinking_bytes'] == 500, 'stats bytes')

        thinking, response = client.run_prompt(json.dumps({'response': '{"a": 2}'}), think=False, format=schema)
        sent = FakeOllama.received[-1]
        check(sent.get('think') is False and sent.get('format') == schema and thinking == '', 'think:false or format not sent')
        check(client.last_call['format_sent'] is True, 'format_sent')

        client.structured = 'always'
        client.run_prompt(json.dumps({}), format=schema)
        check('format' in FakeOllama.received[-1], "structured='always' did not send the schema on a thinking call")
        client.structured = 'no_think'

        before = FakeOllama.disconnects
        started = time.time()
        thinking, response = client.run_prompt(json.dumps({'thinking_bytes': 200000, 'delay': 0.002}), limits={'max_thinking_bytes': 3000})
        check(client.last_call['aborted'] == 'thinking_bytes' and 3000 < len(thinking) < 4000 and response == '', f"thinking breaker: {client.last_call}")
        check(time.time() - started < 5, 'the thinking breaker did not cut the call short')
        time.sleep(0.2)
        check(FakeOllama.disconnects > before, 'the server never saw the client hang up')

        thinking, response = client.run_prompt(json.dumps({'thinking_bytes': 200000, 'delay': 0.002}),
                                               format={'type': 'object'},
                                               limits={'max_thinking_bytes': 3000, 'force_answer': True})
        info = client.last_call
        check(response == '{"forced": true}' and info.get('forced_answer') and info['aborted'] is None
              and 3000 < info['thinking_at_force'] < 4000, f'budget forcing: {info}')
        raw = FakeOllama.received[-1]
        check(raw.get('raw') is True and raw.get('format') == {'type': 'object'} and 'think' not in raw
              and FakeOllama.raw_prompts[-1].startswith('<|im_start|>user\n') and '\n</think>\n\n' in FakeOllama.raw_prompts[-1],
              f'forced continuation request: { {k: v for k, v in raw.items() if k != "prompt"} }')

        client.run_prompt(json.dumps({'thinking_bytes': 0, 'response': 'x' * 50000, 'delay': 0.001}), think=False, limits={'max_response_bytes': 2000})
        check(client.last_call['aborted'] == 'response_bytes', 'response breaker')

        client.run_prompt(json.dumps({'thinking_bytes': 100000, 'delay': 0.05}), limits={'max_seconds': 0.4})
        check(client.last_call['aborted'] == 'wall_clock', 'wall-clock breaker')

        client.run_prompt(json.dumps({'done_reason': 'length'}))
        check(client.last_call['done_reason'] == 'length', 'done_reason')

        thinking, response = client.run_prompt(json.dumps({'inline_think': True, 'thinking_bytes': 300, 'response': '{"a": 3}'}))
        check(len(thinking) == 300 and response == '{"a": 3}', f'inline <think> tags not separated: {len(thinking)} / {response!r}')
        client.run_prompt(json.dumps({'inline_think': True, 'thinking_bytes': 300, 'response': '{"a": 3}'}), limits={'max_thinking_bytes': 100})

        notes = io.StringIO()      # the client announces each fallback on stderr; keep the test output clean
        with contextlib.redirect_stderr(notes):
            thinking, response = client.run_prompt(json.dumps({'reject_format': True, 'response': '{"a": 4}'}), think=False, format=schema)
        check(response == '{"a": 4}' and client.structured == 'never' and client.last_call['format_sent'] is False, 'schema rejection fallback')
        check('rejected the output schema' in notes.getvalue(), 'the schema fallback was silent')

        # a server that does not know the model as a thinking model: think:false is refused once,
        # then the soft switch is used and the parameter is never sent again
        soft = OllamaClient(host=host, model='fake', echo=False, idle_timeout=5)
        FakeOllama.reject_think = True
        with contextlib.redirect_stderr(notes):
            thinking, response = soft.run_prompt(json.dumps({'response': '{"a": 5}'}), think=False, format=schema)
        sent = FakeOllama.received[-1]
        check(response == '{"a": 5}' and thinking == '' and 'think' not in sent and sent['prompt'].endswith('/no_think'), 'soft no-think fallback')
        check(soft.think_param is False and 'format' in sent and soft.last_call['soft_no_think'], 'think rejection must not drop the schema')
        n = len(FakeOllama.received)
        soft.run_prompt(json.dumps({'response': '{"a": 6}'}), think=False)
        check(len(FakeOllama.received) == n + 1 and FakeOllama.received[-1]['prompt'].endswith('/no_think'), 'the rejected parameter was sent again')
        thinking, _ = soft.run_prompt(json.dumps({'thinking_bytes': 200}))
        check(len(thinking) == 200 and not FakeOllama.received[-1]['prompt'].endswith('/no_think'), 'a thinking call got the no-think suffix')
        FakeOllama.reject_think = False

        # inline reasoning (servers before 0.9): the answer may start in the same fragment that closes the tag,
        # and the tag may be preceded by whitespace
        thinking, response = client.run_prompt(json.dumps({'raw_chunks': ['\n', '<think>abc', 'def</think>\n\n{', '"a": 7}']}))
        check(thinking == 'abcdef' and response == '{"a": 7}', f'inline split: {thinking!r} / {response!r}')
        client.run_prompt(json.dumps({'raw_chunks': ['\n<think>'] + ['r' * 100] * 50 + ['</think>{"a": 8}']}), limits={'max_response_bytes': 2000})
        check(client.last_call['aborted'] is None, 'inline reasoning was counted as response')
        client.run_prompt(json.dumps({'raw_chunks': ['<think>'] + ['r' * 100] * 50 + ['</think>{}']}), limits={'max_thinking_bytes': 2000})
        check(client.last_call['aborted'] == 'thinking_bytes', 'inline reasoning escaped the thinking breaker')

        # a finished answer is kept even if the deadline passed while its last chunk was in flight
        thinking, response = client.run_prompt(json.dumps({'thinking_bytes': 0, 'response': '{"a": 9}', 'done_delay': 0.3}), think=False, limits={'max_seconds': 0.2})
        check(response == '{"a": 9}' and client.last_call['aborted'] is None, 'a complete answer was discarded at the deadline')

        # a stream that just stops is a transport failure carrying the fragment, not an answer
        try:
            client.run_prompt(json.dumps({'thinking_bytes': 200, 'response': '{"a": 10', 'no_done': True}))
            check(False, 'a stream with no done object was accepted')
        except LlmCallError as e:
            check('ended before the call finished' in str(e) and e.response == '{"a": 10' and len(e.thinking) == 200, f'truncated stream: {e}')

        # a 400 that is not about think or format is an error, and does not switch thinking off
        other = OllamaClient(host=host, model='fake', echo=False, idle_timeout=5)
        try:
            other.run_prompt(json.dumps({'reject_all': True}), think=False)
            check(False, 'an unrelated 400 was swallowed')
        except LlmCallError:
            check(other.think_param is True, 'an unrelated 400 switched the think parameter off')

        dead = OllamaClient(host='http://127.0.0.1:9', model='fake', echo=False, idle_timeout=2)
        try:
            dead.run_prompt('x')
            check(False, 'an unreachable server did not raise')
        except LlmCallError as e:
            check('could not reach ollama' in str(e), f'unexpected error: {e}')

        # the probe runs to completion against the fake
        proc = subprocess.run([sys.executable, 'probe_ollama.py', '--host', host, '--model', 'fake'], cwd=GEN, capture_output=True)
        out = proc.stdout.decode() + proc.stderr.decode()
        check('server version' in out and 'recommended client settings' in out, f'probe output:\n{out[-2000:]}')
    finally:
        server.shutdown()


@test
def report_script():
    proc = subprocess.run([sys.executable, 'report.py', PREFIX + 'breaker', '--baseline', '../docs/baseline_kernel1_run_stats.json'],
                          cwd=GEN, capture_output=True)
    out = proc.stdout.decode() + proc.stderr.decode()
    check(proc.returncode == 0 and 'breaker:thinking_bytes' in out and 'TOTAL' in out and 'baseline' in out, f'report:\n{out[-2000:]}')
    proc = subprocess.run([sys.executable, 'report.py', '--from-logs', story_dir('basic'), '--story-id', PREFIX + 'basic'], cwd=GEN, capture_output=True)
    check(proc.returncode == 0 and b'rebuilt from log timestamps' in proc.stdout, 'report --from-logs')


# ---------------------------------------------------------------- runner

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep', action='store_true', help='keep the test story directories')
    parser.add_argument('-k', default='', help='run only tests whose name contains this')
    args = parser.parse_args()
    failed = 0
    started = time.time()
    for fn in TESTS:
        if args.k and (args.k not in fn.__name__ or fn.__name__ == 'every_prompt_is_exercised'):
            continue        # the prompt-coverage test only means something after every scenario has run
        t = time.time()
        try:
            fn()
            print(f'ok    {fn.__name__} ({time.time() - t:.1f}s)')
        except Exception:
            failed += 1
            print(f'FAIL  {fn.__name__}')
            traceback.print_exc()
    if not args.keep:
        for d in glob.glob(os.path.join(STORIES, PREFIX + '*')):
            shutil.rmtree(d, ignore_errors=True)
    print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'} in {time.time() - started:.1f}s")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
