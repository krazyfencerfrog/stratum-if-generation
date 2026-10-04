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
    check(all(c['mode'] == 'no_think' for c in calls('basic') if c['step'] in ('s2', 's3_5c', 's3_8')),
          'a classify-class call ran with thinking on')
    check(all(c['mode'] == 'think' and c['klass'] == 'audit' for c in calls('basic') if c['step'] == 's3_5v'),
          'the premise audit should run with thinking on, in the audit class')
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
def repair_breakage_is_caught_at_once():
    run('repair_breaks', env={'STUB_PREMISE_HARD_ROUNDS': '1', 'STUB_REPAIR_BREAKS': '1'})
    attempts = [c for c in calls('repair_breaks') if c['step'] == 's3_5r']
    check(len(attempts) == 2 and not attempts[0]['ok'] and attempts[1]['ok'], f'expected a rejected repair and a clean retry: {attempts}')
    check('you choose to' in attempts[0]['error'] and '"choose" is not one of the forms' in attempts[0]['error'],
          f'the complaint should name both new problems: {attempts[0]["error"]}')
    loop = load('repair_breaks', 's3_5_loop.json')
    check(loop['repair_rounds_used'] == 1 and not loop['still_failing'], 'the caught breakage should not cost another round')
    # a retry that is still broken is accepted and left to the audit round, not fatal
    run('repair_breaks_twice', env={'STUB_PREMISE_HARD_ROUNDS': '1', 'STUB_REPAIR_BREAKS': '2'})
    attempts = [c for c in calls('repair_breaks_twice') if c['step'] == 's3_5r']
    check(attempts[1]['ok'] and attempts[1].get('soft_problems'), f'the second broken repair should be accepted with its problems noted: {attempts}')
    loop = load('repair_breaks_twice', 's3_5_loop.json')
    check(any('you choose' in json.dumps(r.get('findings')) for r in loop['rounds']), 'the audit round should then report the menu pick')
    check(not loop['still_failing'], 'the next repair round should clear it')
    assert_story_ok('repair_breaks_twice')


@test
def hidden_truth_and_cast_edges():
    run('gap', env={'STUB_GAP': '1'}, args=['--stop-after=3.5'])
    premise = load('gap', 's3_5_premise_accepted.json')
    check((premise.get('hidden_truth') or {}).get('truth'), 'a brief with an epistemic gap should give a premise with a stated hidden truth')
    loop = load('gap', 's3_5_loop.json')
    check(loop['repair_rounds_used'] == 0, f'a stated hidden truth should not cost a repair round: {loop["rounds"][0]["findings"]}')
    seeds = premise['cast_seeds']
    check(all(s.get('tie') for s in seeds) and all(s.get('edge') for s in seeds if s['kind'] == 'individual'),
          'every seed should carry a tie, and every individual an edge')
    # the engine forgets the truth the brief says is there: a computed finding, filled by the repair
    run('gap_missing', env={'STUB_GAP': '2'}, args=['--stop-after=3.5'])
    loop = load('gap_missing', 's3_5_loop.json')
    check(any(f['where'] == 'hidden_truth' for f in loop['rounds'][0]['findings']), 'a missing hidden truth was not reported')
    check(not loop['still_failing'] and (load('gap_missing', 's3_5_premise_accepted.json').get('hidden_truth') or {}).get('truth'),
          'the repair should have supplied the hidden truth')
    # with no gap the stub engine states none, and the outline shows the cast's edges and ties
    story = open(os.path.join(story_dir('basic'), f'{PREFIX}basic_story.md')).read()
    check('edge: stub edge of' in story and 'tie: stub tie of' in story, 'the story document should show edges and ties')
    check(load('basic', 's3_5_premise_accepted.json').get('hidden_truth') is None, 'no gap, no hidden truth')


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
def loops_rerun_from_a_new_seed():
    run('loop', env={'STUB_LOOP': 's4a'})
    attempts = [c for c in calls('loop') if c['step'] == 's4a']
    check(len(attempts) == 2, f'expected two s4a attempts, got {len(attempts)}')
    check(attempts[0]['breaker'] == 'loop' and attempts[0].get('loop_line') and 'seed' not in attempts[0],
          f'first attempt should be the looped one: {attempts[0]}')
    check(attempts[1]['mode'] == 'think' and attempts[1]['ok'] and attempts[1].get('seed'),
          f'the re-run should keep thinking, from a new seed: {attempts[1]}')
    assert_story_ok('loop')
    # a second loop goes to the class fallback, not to a third seed
    run('loop_again', env={'STUB_LOOP': 's4a', 'STUB_LOOP_ALWAYS': '1'})
    attempts = [c for c in calls('loop_again') if c['step'] == 's4a']
    check([a['mode'] for a in attempts] == ['think', 'think', 'no_think'] and attempts[-1]['ok'],
          f'loop, loop, then thinking off: {[(a["mode"], a["breaker"]) for a in attempts]}')
    _, out = run('loop_off', env={'STUB_LOOP': 's4a'}, args=['--no-breakers'])
    attempts = [c for c in calls('loop_off') if c['step'] == 's4a']
    check(len(attempts) == 1 and attempts[0]['ok'], '--no-breakers should switch loop detection off too')


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
    run('graph', args=['--max-iterations=6', '--branching=judge'],
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
def judge_mode_seeds_one_line_at_a_time():
    run('judge', args=['--branching=judge'], env={'STUB_STOP_AFTER': '3'})
    story = assert_story_ok('judge', min_lines=3)
    check(story['branching'] == 'judge' and story.get('plan') is None, 'judge mode should not run the branch plan')
    cs = calls('judge')
    check([c['step'] for c in cs if c['step'] in ('s4d', 's4p')] == ['s4d', 's4d', 's4d'], f"expected three 4d calls and no 4p: {[c['step'] for c in cs]}")
    check('4d recommended stopping' in story['stop_reason'], story['stop_reason'])
    check(all((l.get('ending') or {}).get('answer') for l in story['lines'].values()), 'every line should state its ending world')


@test
def branch_plan_designs_every_divergence():
    story = assert_story_ok('basic', min_lines=3)
    check(story['branching'] == 'plan' and story['plan'] and len(story['plan']['seeds']) >= 2, 'the branch plan was not stored')
    cs = calls('basic')
    check([c['step'] for c in cs if c['step'] in ('s4d', 's4p')] == ['s4p'], f"plan mode should run 4p once and never 4d: {[c['step'] for c in cs]}")
    main = story['lines']['T1']['path']
    forks = [story['lines'][l]['divergence']['diverges_at'] for l in story['line_order'][1:]]
    check(any(main.index(f) + 1 <= len(main) / 2 for f in forks), f'no line leaves in the first half: {forks} of {main}')
    worlds = {(l['ending']['answer'], tuple(sorted(l['ending']['standing'])), tuple(sorted(l['ending']['lost']))) for l in story['lines'].values()}
    check(len(worlds) == len(story['lines']), 'two lines end in the same world')
    check(all(n.get('image') for n in story['nodes'].values()), 'every node should carry an image')
    check(any(n.get('event') for n in story['nodes'].values()), 'no event was placed on any node')
    md = load('basic', 'story.md')
    check('## Branch plan' in md and 'world left:' in md and 'Image:' in md and '## Events the world brings about' in md, 'story.md is missing the new sections')
    ev = load('basic', 'eval.json')
    check(ev['metrics']['ending_distinctness'] == 1.0 and ev['metrics']['forks_in_first_half'] >= 1 and ev['judge']['total'] == 18,
          f"eval metrics: {ev['metrics']}")
    check(not [c for c in cs if c['step'] == 's4e' and c['mode'] != 'no_think'], 'the outline judge should run with thinking off')
    # the plan's soft rules: all-late forks and duplicate worlds are re-asked once, then accepted
    run('plan_late', env={'STUB_PLAN_LATE': '1'})
    attempts = [c for c in calls('plan_late') if c['step'] == 's4p']
    check(len(attempts) == 2 and not attempts[0]['ok'] and 'second half' in attempts[0]['error'] and attempts[1]['ok'],
          f'an all-late plan should be re-asked once with the complaint: {attempts}')
    run('plan_dup', env={'STUB_PLAN_DUP': '2'})
    attempts = [c for c in calls('plan_dup') if c['step'] == 's4p']
    check(len(attempts) == 2 and 'same world' in attempts[0]['error'] and attempts[1]['ok'] and attempts[1].get('soft_problems'),
          f'a plan with two seeds in one world should be re-asked, then accepted with the problem noted: {attempts}')
    assert_story_ok('plan_dup', min_lines=2)
    # a plan with no seeds stops the loop after the main line
    run('plan_empty', env={'STUB_PLAN_SEEDS': '0'})
    story = assert_story_ok('plan_empty')
    check(len(story['lines']) == 1 and '4p planned no further line' in story['stop_reason'], story['stop_reason'])
    # a seed 4c cannot build is dropped and the next planned seed is tried
    run('plan_skip', env={'STUB_NOTHING_ON': '2', 'STUB_PLAN_SEEDS': '3'}, args=['--max-iterations=5'])
    story = assert_story_ok('plan_skip', min_lines=3)
    check(any(it.get('skipped') for it in story['iterations']) and len(story['lines']) == 3, f"a dropped seed should not end the loop: {story['stop_reason']}")


@test
def premise_events_set_piece_and_echo():
    # missing events and a missing set piece are computed findings the repair fills
    run('noevents', env={'STUB_NO_EVENTS': '1', 'STUB_NO_SET_PIECE': '1'}, args=['--stop-after=3.5'])
    loop = load('noevents', 's3_5_loop.json')
    wheres = {f['where'] for f in loop['rounds'][0]['findings']}
    check({'events', 'turns.set_piece'} <= wheres, f'missing events / set piece were not reported: {wheres}')
    premise = load('noevents', 's3_5_premise_accepted.json')
    check(not loop['still_failing'] and len(premise['events']) == 2 and any(t.get('set_piece') for t in premise['turns']),
          'the repair should have supplied events and a set piece')
    # the brief's own wording copied into a lever is a soft rejection: re-asked once
    run('echo', env={'STUB_ECHO': '1'}, args=['--stop-after=3.5'])
    attempts = [c for c in calls('echo') if c['step'] == 's3_5a']
    check(len(attempts) == 2 and "brief's own wording" in attempts[0]['error'] and attempts[1]['ok'], f'echo check: {attempts}')
    premise = load('echo', 's3_5_premise_accepted.json')
    check(all(s.get('voice') for s in premise['cast_seeds'] if s['kind'] == 'individual'), 'individuals should carry a voice')
    check(any(s.get('breaking_point') for s in premise['cast_seeds']), 'no companion has a breaking point')
    # 4a's first answer places no event: a soft rejection, the retry places one
    run('noplace', env={'STUB_NO_EVENT_PLACED': '1'}, args=['--max-iterations=1'])
    attempts = [c for c in calls('noplace') if c['step'] == 's4a']
    check(len(attempts) == 2 and 'events is placed' in attempts[0]['error'] and attempts[1]['ok'], f'event placement: {attempts}')
    # promises off: the prompts get none and 3.4 never runs
    run('nopromise', args=['--no-promises', '--stop-after=3.5'])
    check(not [c for c in calls('nopromise') if c['step'] == 's3_4'], '3.4 ran under --no-promises')
    check('beat them) ---\nnone' in load('nopromise', 's3_5a_raw_input_prompt.txt'), 'the engine prompt should receive "none" for the promises')
    loop = load('nopromise', 's3_5_loop.json')
    check(not any(f['where'] == 'turns.set_piece' for f in loop['rounds'][0]['findings']), 'no promises, no set-piece finding')


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
        run('graph', args=['--max-iterations=6', '--branching=judge'], env={'STUB_NEW_CAST_ON': '2', 'STUB_REJOIN_ON': '3', 'STUB_NOTHING_ON': '4', 'STUB_STOP_AFTER': '9'})
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
    dup = json.loads(json.dumps(good))
    dup['lines']['T2']['ending'].update(answer='pole_b', standing=['the nursery warden', 'the hydroponics foreman'], lost=[])
    for l in dup['lines'].values():
        l['ending'].update(answer='pole_b', standing=['the nursery warden', 'the hydroponics foreman'], lost=[])
    noted = {f['kind'] for f in checks.check_story(dup)['notes']}
    check({'same_world', 'companions_static'} <= noted, f'same-world endings and static companions were not noted: {noted}')
    told = json.loads(json.dumps(good))
    a = next(n for n in t1 if told['nodes'][n]['turn'] is not None)
    told['nodes'][a]['summary'] = 'The warden bars the nursery hatch while the foreman reads the gauge aloud to the families.'
    told['nodes']['X9'] = dict(told['nodes'][a], id='X9', lines=['T9'], way=2,
                               summary='The warden bars the nursery hatch while the foreman reads the gauge aloud, and you wait.')
    check('repeated_situation' in {f['kind'] for f in checks.check_story(told)['notes']}, 'a retold situation was not noted')


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

    @staticmethod
    def promises_block():
        return 'none'

    @staticmethod
    def tone_line():
        return 'tone: (none stated)'

    def run_prompt(self, prefix, name, repl, prompt_file=None, validator=None, klass=None, schema=None):
        from errors import SoftReject
        answer = json.loads(json.dumps(self.answers[prefix]))
        try:
            validator(answer)
        except SoftReject as e:      # main.py would re-ask once, then accept; here: accept
            self.soft = str(e)
        return answer

    def save_story_json(self, *a):
        pass

    save_story_file = save_story_json


def entry(beat, turn=None, way=None):
    return {'beat': beat, 'turn': turn, 'way': way if turn is None else (way or 1), 'adapted': f'{beat} happens'}


def plan(beats):
    return {'through_line': {'title': 't', 'motivation': 'm', 'strategy': 's', 'turning_point': 'p', 'differs_from': 'd'},
            'ending': {'title': 'e', 'summary': 'e', 'answer': 'pole_a', 'standing': ['the widow'], 'lost': [], 'changed': 'c'},
            'beats': beats, 'skipped_beats': []}


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
def example_copies_are_caught():
    import example_guard, re as _re
    pf = ['s3_5a_engine.prompt', 's3_5b_turns.prompt', 's3_5c_cast.prompt']
    text = open(os.path.join(ROOT, 'prompts', 's3_5b_turns.prompt')).read()
    _, examples = example_guard.split_prompt(text)
    check(examples and 'CALIBRATION' in examples and '$$' not in examples, 'the examples section was not isolated')
    first = _re.search(r'Output:\n(\{.*?\n\})\n', examples, _re.S)
    copied = json.loads(first.group(1))
    hits = example_guard.copied_phrases(copied, pf, ['a ship and its AI'])
    check(len(hits) >= example_guard.MIN_HITS, f'a premise copied from the example went unflagged ({len(hits)} phrases)')
    run('copyguard', args=['--stop-after=3.5'])
    premise = load('copyguard', 's3_5_premise_accepted.json')
    kernel = open(os.path.join(KERNELS, 'kernel1.txt')).read()
    hits = example_guard.copied_phrases(premise, pf, [kernel])
    check(len(hits) < example_guard.MIN_HITS, f'the stub premise was flagged as a copy: {hits[:5]}')


@test
def cast_names_come_from_python():
    import names
    premise = load('basic', 's3_5_premise_accepted.json')
    seeds = premise['cast_seeds']
    named = [s for s in seeds if s.get('name')]
    check(named and all(s['kind'] == 'individual' for s in named), 'individuals should be named, crowds not')
    check(all(not s.get('name') for s in seeds if s['kind'] == 'crowd'), 'a crowd was given a name')
    check(len({s['name'].split()[0] for s in named}) == len(named), 'two people share a given name')
    check(premise.get('name_pool') == 'scifi', f"kernel1 should draw from the scifi pool, got {premise.get('name_pool')}")
    again = [dict(s, name=None) for s in seeds]
    kernel1 = open(os.path.join(KERNELS, 'kernel1.txt')).read()
    names.assign_names(again, f'{PREFIX}basic', [kernel1] + names.premise_texts(premise), premise['name_pool'])
    check([s.get('name') for s in again] == [s.get('name') for s in seeds], 'names are not deterministic for a story id')
    check(names.gender_hint('the foreman', [], own=['walks off if his sector is bled']) == 'm'
          and names.gender_hint('the foreman', ['the foreman says his valve is shut. the warden says her sector is cold.']) == 'm',
          'gender hints should read the seed\'s own fields and only the sentences that name the role')
    check(not names.wants_a_name({'role': 'the dragon', 'kind': 'individual'})
          and not names.wants_a_name({'role': 'the protagonist', 'kind': 'individual'}), 'a dragon or "you" was named')
    check(names.pool_for(open(os.path.join(KERNELS, 'kernel31.txt')).read()) == 'fantasy'
          and names.pool_for(open(os.path.join(KERNELS, 'kernel17.txt')).read()) == 'period', 'genre pools')
    story = open(os.path.join(story_dir('basic'), f'{PREFIX}basic_story.md')).read()
    check(f"{named[0]['name']} ({named[0]['role']})" in story, 'the story document should show name and role together')
    # a node may refer to a person by name, full or first
    from outline import OutlineBuilder
    table = {'C01': {'label': 'the nursery warden', 'name': 'Adaora Prakash'}, 'C02': {'label': 'the speaker', 'name': None}}
    check(OutlineBuilder.match('Adaora Prakash', table, 'label') == 'C01' and OutlineBuilder.match('Adaora', table, 'label') == 'C01',
          'a name did not resolve to its role')


@test
def name_pools_styles_and_races():
    import names
    for kernel, pool in (('A romance in Regency London with a duke.', 'regency'), ('A gladiator in ancient Rome.', 'ancient_roman'),
                         ('A tomb robber in the pyramids of Egypt.', 'ancient_egyptian'), ('A viking raid on a fjord.', 'norse'),
                         ('A ronin in feudal Japan.', 'japanese_historical'), ('A gunslinger in a frontier town.', 'western'),
                         ('An epic fantasy adventure with a dragon.', 'fantasy'), ('A cozy romance with a baker.', 'romance'),
                         ('A 1940s noir detective story.', 'period'), ('Pirates chase a galleon.', 'age_of_sail')):
        check(names.pool_for(kernel) == pool, f'{kernel!r} -> {names.pool_for(kernel)}, expected {pool}')
    seeds = [{'role': 'the thief', 'kind': 'individual', 'gender': 'f'}, {'role': 'the elven archer', 'kind': 'individual', 'gender': 'm'},
             {'role': 'the dwarf locksmith', 'kind': 'individual', 'gender': 'f'}, {'role': 'the goblin fence', 'kind': 'individual'},
             {'role': 'the stone guardian', 'kind': 'individual'}]
    names.assign_names(seeds, 'demo', ['A fantasy heist in a wizard tower.'])
    got = {s['role']: s.get('name') for s in seeds}
    check(got['the dwarf locksmith'] and ' daughter of ' in got['the dwarf locksmith'], f"dwarven patronymic: {got}")
    check(got['the elven archer'] and got['the elven archer'].split()[0] in names.POOLS['elven']['m'], f"elven pool: {got}")
    check(got['the goblin fence'] and len(got['the goblin fence'].split()) == 1, f"monstrous names are single: {got}")
    check(got['the stone guardian'] is None, 'a stone guardian was named')
    check(got['the thief'].split()[0] in names.POOLS['fantasy']['f'] + names.POOLS['fantasy']['n'], f"stated gender: {got}")
    romans = [{'role': f'the daughter {i}', 'kind': 'individual', 'gender': 'f'} for i in range(6)]
    names.assign_names(romans, 'demo', ['ancient Rome'], 'ancient_roman')
    check(len({r['name'].split()[0] for r in romans}) == 6, f"Roman women share a family name: {[r['name'] for r in romans]}")
    jp = [{'role': 'the ronin', 'kind': 'individual', 'gender': 'm'}]
    names.assign_names(jp, 'demo', ['feudal Japan'], 'japanese_historical')
    check(jp[0]['name'].split()[0] in names.POOLS['japanese_historical']['surnames'], f"family name first: {jp}")


@test
def modern_names_keep_a_culture():
    import names
    check(names.with_culture('modern', 'x', ['a wedding planner in Lagos']) == 'modern:west_african', 'Lagos cue ignored')
    check(names.with_culture('modern', 'x', ['a decrepit canal boat']) == 'modern:british', 'canal cue ignored')
    check(names.with_culture('fantasy', 'x', ['a dragon']) == 'fantasy', 'a pool without cultures got one')
    cultures = names.POOLS['modern']['cultures']
    home_hits = coherent = total = 0
    for k in range(40):
        cast = [{'role': f'the witness number {i}', 'kind': 'individual', 'gender': 'fm'[i % 2]} for i in range(6)]
        names.assign_names(cast, f'story{k}', ['a wedding planner in Lagos'], 'modern:west_african')
        for c in cast:
            given, surname = c['name'].split()[0], c['name'].split()[-1]
            total += 1
            home_hits += given in cultures['west_african']['f'] + cultures['west_african']['m']
            coherent += any(given in v['f'] + v['m'] and surname in v['surnames'] for v in cultures.values())
    check(home_hits / total > 0.7, f'home culture share {home_hits / total:.2f}')
    check(coherent / total > 0.85, f'given name and surname from one culture in only {coherent / total:.2f}')


@test
def protagonist_is_named_first():
    import names
    you = {'who': 'You inherited a canal boat.', 'gender': 'm'}
    cast = [{'role': 'your brother-in-law', 'kind': 'individual', 'gender': 'm'}, {'role': 'the lock keeper', 'kind': 'individual', 'gender': 'f'}]
    name = names.name_protagonist(you, 'demo35', 'modern')
    check(name and you['name'] == name and name.split()[0] in names.POOLS['modern']['m'] + names.POOLS['modern']['n'],
          f'a human protagonist should get a name from the pool, gendered: {you}')
    names.assign_names(cast, 'demo35', ['a canal boat'], 'modern', reserved=[name])
    parts = set(name.lower().split())
    check(all(not parts & set(c['name'].lower().split()) for c in cast), f'a cast member shares a name part with you: {name} / {cast}')
    check(names.name_protagonist({'who': 'You are the ship AI.', 'gender': 'n'}, 'demo', 'scifi', human=False) is None,
          'a non-human protagonist was named')
    check(names.name_protagonist(you, 'demo35', 'modern') == name, 'naming is not stable for a protagonist that already has a name')


@test
def playtest_walks_outlines_and_patterns():
    import playtest
    story = json.load(open(os.path.join(story_dir('basic'), f'{PREFIX}basic_story.json')))
    st = playtest.Story(story)
    plays = playtest.playthroughs(st)
    check({p['ending'] for p in plays if p.get('ending')} == set(st.endings), 'the stub story has an unreachable ending')
    check(playtest.check(st, plays) == [], f'the stub story has playtest findings: {playtest.check(st, plays)}')

    def graph(n_opps):
        # n_opps opportunities, each with an up and a down option, then a node whose
        # shift edge fires when the state went down at least 3 times, 3/4 of the time
        nodes, edges = {}, []
        ids = [f'O{i}' for i in range(n_opps)] + ['F', 'END_A', 'END_B']
        for i in range(n_opps):
            nodes[f'O{i}'] = {'title': f'opp {i}', 'options': [{'do': 'warm', 'effects': [{'state': 'trust', 'direction': 'up'}]},
                                                               {'do': 'cold', 'effects': [{'state': 'trust', 'direction': 'down'}]}]}
        nodes['F'] = {'title': 'the fork'}
        nodes['END_A'] = {'title': 'stays', 'is_ending': True}
        nodes['END_B'] = {'title': 'leaves', 'is_ending': True}
        for a, b in zip(ids[:n_opps], ids[1:n_opps + 1]):
            edges.append({'from': a, 'to': b, 'kind': 'continue', 'lines': ['T1'], 'otherwise': []})
        edges.append({'from': 'F', 'to': 'END_A', 'kind': 'continue', 'lines': ['T1'], 'otherwise': []})
        edges.append({'from': 'F', 'to': 'END_B', 'kind': 'branch', 'lines': ['T2'], 'trigger': {'text': 'you were cold to her all night', 'kind': 'accumulated'},
                      'condition': {'state': 'trust', 'direction': 'down', 'at_least': 3, 'share': 0.75}})
        lines = {'T1': {'path': ids[:n_opps + 1] + ['END_A']}, 'T2': {'path': ids[:n_opps + 1] + ['END_B'], 'divergence': {'diverges_at': 'F'}}}
        return playtest.Story({'nodes': nodes, 'edges': edges, 'lines': lines, 'line_order': ['T1', 'T2']})

    st = graph(3)
    down = playtest.playthroughs(st, playtest.styles()['always_down'])
    up = playtest.playthroughs(st, playtest.styles()['always_up'])
    check(all(p['ending'] == 'END_B' for p in down), f'consistent cold play should shift to END_B: {[p["ending"] for p in down]}')
    check(all(p['ending'] == 'END_A' for p in up), 'warm play should never shift')
    findings, report = playtest.shift_checks(st)
    check(findings == [], f'3-of-3 pattern: {findings} {report}')
    findings, report = playtest.shift_checks(graph(4))
    check(any('random playthroughs' in f for f in findings), f'a pattern random play hits about 30% of the time should be flagged: {report}')


@test
def batch_runner_queues_resumes_and_locks():
    import batch, tempfile, threading
    tmp = tempfile.mkdtemp()
    queue = os.path.join(tmp, 'q.json')
    lock = os.path.join(tmp, 'gpu.lock')
    env = {k: v for k, v in os.environ.items() if not k.startswith('STUB_')}
    env['STRATUM_CLIENT'] = 'stub'
    ids = [f'{PREFIX}batch_a', f'{PREFIX}batch_b', f'{PREFIX}batch_bad']
    for sid in ids:
        shutil.rmtree(story_dir(sid[len(PREFIX):]), ignore_errors=True)
    batch.add(queue, [batch.make_job('kernel1', story_id=ids[0]), batch.make_job('kernel32', story_id=ids[1]),
                      batch.make_job('no_such_kernel', story_id=ids[2])])
    check(len(batch.add(queue, [batch.make_job('kernel1', story_id=ids[0])])) == 0, 'a job already queued was queued twice')
    # a job a killed runner left "running" goes back to the queue
    q = batch.load(queue); q['jobs'][1]['status'] = 'running'; batch.save(queue, q)
    said = []
    old = batch.GPU_LOCK
    batch.GPU_LOCK = lock
    try:
        holder = open(lock, 'a+')
        import fcntl
        fcntl.flock(holder, fcntl.LOCK_EX)
        threading.Timer(1.0, lambda: (fcntl.flock(holder, fcntl.LOCK_UN), holder.close())).start()
        with batch.gpu(lock, say=said.append):
            pass
        check(any('waiting for the GPU' in m for m in said), f'a second runner did not wait for the GPU lock: {said}')
        batch.run(queue, env=env, say=said.append)
    finally:
        batch.GPU_LOCK = old
    st = {j['story_id']: j for j in batch.load(queue)['jobs']}
    check(st[ids[0]]['status'] == 'done' and st[ids[1]]['status'] == 'done', f"jobs did not finish: {[(k, v['status'], v.get('error')) for k, v in st.items()]}")
    check(st[ids[2]]['status'] == 'failed' and st[ids[2]]['exit'] not in (0, None), f"a bad job should fail: {st[ids[2]]}")
    check(any('re-queued 1 interrupted' in m for m in said), 'the interrupted job was not re-queued')
    check(os.path.isfile(os.path.join(story_dir('batch_a'), f'{PREFIX}batch_a_story.json')), 'no story from the batch job')
    text, out = batch.report(queue)
    check(ids[0] in text and 'done' in text and os.path.isfile(out), f'report: {text}')
    for sid in ids:
        shutil.rmtree(story_dir(sid[len(PREFIX):]), ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)


@test
def replays_are_stable_and_rejections_kept():
    # a finished premise loop replays as it was, even when today's checks would object to it
    run('drift')
    acc_path = os.path.join(story_dir('drift'), f'{PREFIX}drift_s3_5_premise_accepted.json')
    premise = json.load(open(acc_path))
    premise['turns'][0]['ways_through'][0]['way'] = 'you choose to trace the ducts'   # today's menu-verb check would flag this
    json.dump(premise, open(acc_path, 'w'))
    before = len(calls('drift'))
    run('drift', fresh=False)
    check(len(calls('drift')) == before, f'a replay made {len(calls("drift")) - before} model call(s)')
    # a rejected attempt keeps its output beside the accepted one
    run('kept', env={'STUB_BAD_PLAN': '1'})
    check(os.path.isfile(os.path.join(story_dir('kept'), f'{PREFIX}kept_s4a_i1_raw_output_response_rejected_1.txt')),
          'the rejected 4a answer was not kept')
    # a seed 4c drops leaves no gap in the line numbering
    run('nogap', args=['--max-iterations=4'], env={'STUB_NOTHING_ON': '2'})
    story = load('nogap', 'story.json')
    ids = sorted(story['lines'])
    check(ids == [f'T{i}' for i in range(1, len(ids) + 1)], f'line ids have a gap: {ids}')


@test
def late_forks_are_noted():
    import checks
    main = {'path': ['N01', 'N02', 'N03', 'N04', 'N05', 'N06']}
    late = {'T1': main, 'T2': {'divergence': {'diverges_at': 'N04'}}, 'T3': {'divergence': {'diverges_at': 'N05'}}}
    check(checks.late_forks(late), 'lines that all leave in the second half should be noted')
    early = dict(late, T3={'divergence': {'diverges_at': 'N02'}})
    check(checks.late_forks(early) is None, 'a line that leaves in the first half clears the note')
    nodes = {'N02': {'beat': 'b2', 'turn': 2, 'way': 1, 'lines': ['T1']},
             'T2N01': {'beat': 'b2', 'turn': 2, 'way': 1, 'lines': ['T2']},
             'T3N01': {'beat': 'b2', 'turn': 2, 'way': 2, 'lines': ['T3']}}
    check(checks.repeated_nodes(nodes) == [('N02', 'T2N01')], f'repeated nodes: {checks.repeated_nodes(nodes)}')


@test
def helpers():
    kernel_files = sorted(glob.glob(os.path.join(KERNELS, 'kernel*.txt')))
    check(len(kernel_files) >= 35, f'expected the kernel batch, found {len(kernel_files)}')
    for path in kernel_files:
        text = open(path, encoding='utf-8').read()
        clauses = brief.kernel_clauses(text)
        check(clauses and all(c.strip() for _, c in clauses), f'{os.path.basename(path)}: no clauses')
        check([n for n, _ in clauses] == list(range(1, len(clauses) + 1)), f'{os.path.basename(path)}: clause numbering')
    eval_set = open(os.path.join(KERNELS, 'EVAL_SET.txt'), encoding='utf-8').read().split()
    check(all(os.path.isfile(os.path.join(KERNELS, f'{k}.txt')) for k in eval_set) and 6 <= len(eval_set) <= 10, f'EVAL_SET: {eval_set}')
    quick = open(os.path.join(KERNELS, 'EVAL_QUICK.txt'), encoding='utf-8').read().split()
    check(quick and set(quick) <= set(eval_set), f'EVAL_QUICK must be a subset of EVAL_SET: {quick}')
    targets = brief.shape_targets({'endings': {'tier': 'many'}, 'linearity': 'linear'})
    check(targets['through_lines'] == 6 and targets['default_max_iterations'] == 8, f'shape targets: {targets}')
    check(brief.shape_targets({'endings': {'tier': 'one'}})['default_max_iterations'] == 1, 'one ending, one line')
    for stated, tier in (('6 or 7', 'several'), ('at least five', 'several'), ('a dozen', 'many'), ('one ending', 'one'),
                         ('a single ending', 'one'), ('more than one ending', None), ('at least one of them happy', None),
                         ('two or three', 'few'), ('the verdict should vary', None), ('', None)):
        check(brief.ending_tier_from_stated(stated) == tier, f'tier for {stated!r}')
    b = load('basic', 's3_brief.json')
    lines = brief.brief_lines(b)
    check('3-0a.primary_decision_axis [constraint, inferred]' in lines and 'enrichment_budget' in lines, 'brief_lines lost a field')
    check('3b.tone [constraint]:' in lines, 'an explicit field should not be marked inferred')
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
        elif d.get('implicit_think'):
            # a template that opens <think> in the prompt: reasoning arrives in
            # `response` with no opening tag, closed by </think>
            chunks += [{'response': 'We need to reason here. '[:24] * 4} for _ in range(n_think // 96)]
            if not d.get('never_close'):
                chunks.append({'response': '\n</think>\n\n'})
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

        # template-opened think blocks (no opening tag in the response)
        thinking, response = client.run_prompt(json.dumps({'implicit_think': True, 'thinking_bytes': 960, 'response': '{"a": 5}'}))
        check(response == '{"a": 5}' and thinking.startswith('We need') and client.last_call['thinking_bytes'] > 900,
              f'implicit think block not split: {thinking[:40]!r} / {response!r}')
        thinking, response = client.run_prompt(json.dumps({'implicit_think': True, 'never_close': True, 'thinking_bytes': 192, 'response': ''}))
        check(thinking == '' and response.startswith('We need'), 'an implicit block that never closes is all answer')
        thinking, response = client.run_prompt(json.dumps({'implicit_think': True, 'thinking_bytes': 960, 'response': '{"a": 6}'}), think=False)
        check('</think>' in response, 'with think:false the response is taken as is')
        thinking, response = client.run_prompt(json.dumps({'implicit_think': True, 'thinking_bytes': 200000, 'delay': 0.001}),
                                               limits={'max_thinking_bytes': 3000, 'force_answer': True})
        check(client.last_call.get('forced_answer') and response == '{"forced": true}' and thinking.startswith('We need'),
              f'implicit reasoning should count against the thinking limit and be forced: {client.last_call}')

        loop = ['Let me reconsider the second turn.\n'] * 6
        thinking, response = client.run_prompt(json.dumps({'raw_chunks': ['We have a premise.\n'] + loop * 50, 'delay': 0.002}),
                                               limits={'detect_loops': True, 'max_thinking_bytes': 100000, 'force_answer': True})
        info = client.last_call
        check(info['aborted'] == 'loop' and info.get('loop_line') == 'Let me reconsider the second turn.'
              and not info.get('forced_answer') and response == '' and thinking.count('reconsider') == 5,
              f'a one-line loop should be cut at the fifth repeat, unforced: {info}')
        cycle = ['OK, let me write the JSON now.\n', 'OK.\n', 'Actually, the second turn needs another way.\n',
                 '"way": null,\n', 'Let me re-read the cannot_do once more.\n', 'So the cannot_do is a string, fine.\n']
        client.run_prompt(json.dumps({'raw_chunks': ['Drafting.\n'] + cycle * 40, 'delay': 0.002}), limits={'detect_loops': True})
        check(client.last_call['aborted'] == 'loop', f'a paragraph going round should be cut: {client.last_call}')
        drafted = ['Turn 1, way 1: you open the vent.\n', 'Turn 1, way 2: you hold it.\n', 'Turn 2, way 1: the marshal folds.\n']
        drafted += ['{ "beat": "climax", "turn": null, "way": null },\n', '"provenance": "invented",\n'] * 6
        drafted += ['</think>\n\n{"a": 7}']
        thinking, response = client.run_prompt(json.dumps({'raw_chunks': drafted}), limits={'detect_loops': True})
        check(client.last_call['aborted'] is None and response == '{"a": 7}', f'ordinary reasoning was taken for a loop: {client.last_call}')

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
def ab_harness_replays_from_phase3():
    e = dict(os.environ, STRATUM_CLIENT='stub')
    for k in list(e):
        if k.startswith('STUB_'):
            del e[k]
    base = PREFIX + 'basic'
    n_before = len(calls('basic'))
    proc = subprocess.run([sys.executable, 'ab.py', 'run', '--variant', 'vj', '--kernels', base, '--fresh', '--',
                           '--branching=judge', '--no-outline-judge'], cwd=GEN, env=e, capture_output=True)
    check(proc.returncode == 0, f'ab run failed:\n{proc.stderr.decode()[-2000:]}')
    sid = f'{base}_vj'
    check(len(calls('basic')) == n_before, 'the variant run touched the source directory')
    cs = calls(f'basic_vj')
    check(cs and not [c for c in cs if c['step'].startswith('s3') and c['step'] not in ('s3_4', 's3_5a', 's3_5b', 's3_5c', 's3_5v', 's3_8')],
          f'the variant should start after phase 3: {[c["step"] for c in cs]}')
    check(not [c for c in cs if c['step'] in ('s4p', 's4e')] and [c for c in cs if c['step'] == 's4d'], 'variant flags were not applied')
    story = assert_story_ok('basic_vj', min_lines=2)
    check(story['kernel'] == load('basic', 'story.json')['kernel'], 'the variant did not inherit the kernel')
    proc = subprocess.run([sys.executable, 'ab.py', 'compare', '--variants', 'vj', '--kernels', base], cwd=GEN, env=e, capture_output=True)
    out = proc.stdout.decode()
    check(proc.returncode == 0 and 'worlds' in out and 'means over kernels' in out, f'ab compare:\n{out[-1500:]}')
    proc = subprocess.run([sys.executable, 'ab.py', 'eval', sid], cwd=GEN, env=e, capture_output=True)
    check(proc.returncode == 0 and b'outline metrics' in proc.stdout, 'ab eval')
    # a source without phase 3 is skipped, not run
    proc = subprocess.run([sys.executable, 'ab.py', 'run', '--variant', 'vj', '--kernels', PREFIX + 'nowhere'], cwd=GEN, env=e, capture_output=True)
    check(proc.returncode == 0 and b'no source directory' in proc.stderr, 'a missing source should be skipped with a message')


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
