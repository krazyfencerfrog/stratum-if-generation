#!/usr/bin/env python3
"""Engine tests: the expression language, package validation, the menu,
play through the hand-written demo, rewind, save and load. No model, no
network, about a second.

    python tests/test_engine.py [-k name]
"""

import argparse
import io
import json
import os
import random
import sys
import tempfile
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, 'engine')
DEMO = os.path.join(ENGINE, 'examples', 'kernel35_demo.json')
sys.path.insert(0, ENGINE)

import expressions                                      # noqa: E402
from expressions import ExpressionError, evaluate       # noqa: E402
from runtime import Engine, EngineError, SaveMismatch, leaves   # noqa: E402
from state import GameState                             # noqa: E402
from story import Story, validate                       # noqa: E402
import cli                                              # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond, message):
    if not cond:
        raise AssertionError(message)


def demo_data():
    with open(DEMO, encoding='utf-8') as f:
        return json.load(f)


def ids(engine):
    return [i for _, i in leaves(engine.menu())]


def play(engine, actions):
    view = None
    for a in actions:
        view = engine.act(a)
    return view


# ---------------------------------------------------------------- expressions

@test
def expressions_evaluate_and_refuse():
    st = GameState()
    st.flags = {'a': True}
    st.stats = {'n': 3}
    st.arcs = {'nerve': {'up': 1, 'down': 3}}
    st.locations = {'key': 'player', 'lamp': 'hall'}
    st.room, st.scene, st.turns_in_scene = 'hall', 'S1', 2
    st.placements = {'ann': 'hall', 'bob': 'yard'}
    cases = {
        'flags.a and not flags.b': True, 'stats.n >= 3': True, 'stats.missing == 0': True,
        "pattern('nerve', 'down', 3, 0.75)": True, "pattern('nerve', 'down', 5, 0.75)": False,
        "pattern('nerve', 'up', 1, 0.5)": False, "moved('nerve') == 4": True, 'stats.nerve_down == 3': True,
        "has('key') and not has('lamp')": True, "at('hall')": True, "here('ann') and not here('bob')": True,
        "in_scene('S1') and turns_in_scene >= 2": True, '1 < stats.n < 5': True, '': True,
    }
    for text, want in cases.items():
        check(evaluate(text, st) == want, f'{text!r} gave {evaluate(text, st)!r}, wanted {want!r}')
    check(evaluate('d(6)', st) == evaluate('d(6)', st), 'randomness is not deterministic within a step')
    for bad in ('().__class__', '__import__("os")', 'open("x")', 'flags["a"]', 'x.y', 'lambda: 1', 'stats.n.real',
                "pattern('nerve', 'sideways', 1, 0.5)", 'flags.a +'):
        try:
            expressions.references(bad)
            evaluate(bad, st)
        except ExpressionError:
            continue
        raise AssertionError(f'{bad!r} was accepted')
    refs = expressions.references("flags.x and pattern('s','up',2,0.6) and has('o') and at('r') and visited('S2')")
    check(refs['flags'] == {'x'} and refs['states'] == {'s'} and refs['objects'] == {'o'}
          and refs['rooms'] == {'r'} and refs['visited'] == {'S2'}, f'references: {refs}')


# ---------------------------------------------------------------- validation

@test
def demo_package_validates():
    errors, notes = validate(Story(demo_data()))
    check(not errors, f'demo has errors: {errors}')
    check(any("'untie'" in n for n in notes), f'one-use story verb not noted: {notes}')


@test
def validator_catches_broken_packages():
    def broken(mutate, expect):
        data = demo_data()
        mutate(data)
        errors, _ = validate(Story(data))
        check(any(expect in e for e in errors), f'expected an error containing {expect!r}, got {errors}')

    broken(lambda d: d['scenes']['S01']['rooms'].append('attic'), "unknown room 'attic'")
    broken(lambda d: d['scenes']['S01']['exits'][0].update(when='flags.never_set'), "flag 'never_set', which nothing sets")
    broken(lambda d: d['scenes']['S01']['exits'][0].update(to='S99'), "unknown scene or ending 'S99'")
    broken(lambda d: d['scenes']['S01']['exits'][0].update(to='END_DEMO'), 'scene S02: not reachable')
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(when="pattern('courage','up',2,0.5)"),
           "undeclared state 'courage'")
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(verb='dance'), "verb 'dance'")
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(when='flags.drawer_open and'), 'syntax error')
    broken(lambda d: d['scenes']['S01']['cast'].update(pell='bow'), "places pell in 'bow'")
    broken(lambda d: d['scenes']['S02'].update(exits=[]), 'scene S02: no exits')
    broken(lambda d: d['scenes']['S02']['interactions'][0]['effects'].append({'move': 'lazlo_nerve'}), "dir 'up' or 'down'")
    broken(lambda d: d['scenes']['S02']['interactions'].append(dict(d['scenes']['S02']['interactions'][0])), 'duplicate id')
    broken(lambda d: d['world']['objects']['kettle'].update(location='attic'), "location 'attic'")


# ---------------------------------------------------------------- the menu

@test
def menu_collapses_and_has_no_dead_options():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    root = eng.menu()
    labels = [c['label'] for c in root['children']]
    check(labels[0] == 'Look' and 'Wait' in labels, f'root verbs: {labels}')
    check('Talk' not in labels, 'Talk shown with nobody on the stern deck')
    check('Untie › the stern line' in labels, f'single-object verb did not collapse: {labels}')
    eng.act('go:cabin')
    talk = next(c for c in eng.menu()['children'] if c['label'].startswith('Talk'))
    check('children' in talk and talk['label'] == 'Talk › Lazlo Brandt',
          f'one person, two topics should give "Talk › Lazlo Brandt" with children: {talk}')
    eng.act('talk:lazlo:the_ledger')
    check('talk:lazlo:the_ledger' not in ids(eng), 'a once topic is still offered')
    check({'S01.price_fear', 'S01.mock_fear'} <= set(ids(eng)), 'the ledger options did not appear')
    eng.act('S01.mock_fear')
    check('S01.price_fear' not in ids(eng), 'the other answer stayed open after one was given')
    # every leaf in every state reached by random play acts without error
    rng = random.Random(7)
    for walk in range(60):
        eng = Engine(Story(demo_data()))
        eng.start(seed=walk)
        for _ in range(40):
            if eng.state.ending:
                break
            leaf_ids = ids(eng)
            check(len(leaf_ids) == len(set(leaf_ids)), f'duplicate leaves: {leaf_ids}')
            eng.act(rng.choice(leaf_ids))


@test
def scene_one_forward_path_is_always_open():
    rng = random.Random(3)
    for walk in range(40):
        eng = Engine(Story(demo_data()))
        eng.start(seed=walk)
        for _ in range(30):
            if eng.state.scene != 'S01':
                break
            options = [o for o in ids(eng) if o != 'S01.cast_off']
            check(eng.state.room != 'stern_deck' or 'S01.cast_off' in ids(eng),
                  'cast off missing on the stern deck')
            eng.act(rng.choice(options))


# ---------------------------------------------------------------- play

@test
def demo_plays_to_endings_shaped_by_state():
    warm = Engine(Story(demo_data()))
    warm.start(seed=1)
    view = play(warm, ['go:cabin', 'talk:lazlo:the_ledger', 'S01.price_fear', 'go:stern_deck', 'go:wheelhouse',
                       'S01.open_drawer', 'S01.read_logbook', 'talk:lake_kaur:the_logbook', 'go:stern_deck',
                       'S01.cast_off', 'go:wheelhouse', 'S02.report'])
    text = ' '.join(view['text'])
    check(view['ending'] == 'END_DEMO' and view['menu'] is None, 'did not end')
    check('almost, on your shoulder' in text and "nerve: holding" in text, f'warm resolutions missing: {text}')
    cold = Engine(Story(demo_data()))
    cold.start(seed=1)
    view = play(cold, ['go:cabin', 'talk:lazlo:the_ledger', 'S01.mock_fear', 'go:stern_deck', 'S01.cast_off'])
    check(view['scene'] == 'S02' and 'shouting the price of diesel at you' in view['room']['text'],
          f"the tell did not follow lazlo_nerve: {view['room']}")
    view = play(cold, ['go:bow', 'take:bow_line', 'S02.jump'])
    text = ' '.join(view['text'])
    check('lamp you did not light goes out' in text and 'looking at the towpath' in text
          and 'gates open a minute longer' in text, f'cold resolutions missing: {text}')


@test
def events_once_and_nudges_after_idle():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    seen = []
    for _ in range(9):
        seen += eng.act('wait')['text']
    joined = ' '.join(seen)
    check(joined.count('Are we selling this boat or haunting it') == 1, 'first nudge did not fire exactly once')
    check(joined.count('church bell counts six') == 1, 'second nudge did not fire after more idling')
    check(seen.index(next(t for t in seen if 'haunting' in t)) < seen.index(next(t for t in seen if 'bell' in t)),
          'nudges out of order')
    eng.act('go:wheelhouse')
    texts = eng.act('look')['text'] + eng.act('wait')['text'] + eng.act('wait')['text']
    check(sum('cold enough to see your breath' in t for t in texts) <= 1, 'a once event fired twice')


@test
def look_and_inventory_take_no_time():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    turns = eng.state.turns
    view = eng.act('look')
    check(eng.state.turns == turns and view['room'] is not None, 'look took a turn or showed no room')
    check(len(eng.timeline) == 1, 'look was snapshotted')


# ---------------------------------------------------------------- rewind, save, load

@test
def rewind_save_and_load():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    play(eng, ['go:cabin', 'talk:lazlo:the_ledger', 'S01.price_fear'])
    check(eng.state.arc('lazlo_nerve') == (1, 0), 'arc not moved')
    eng.rewind()
    check(eng.state.arc('lazlo_nerve') == (0, 0) and 'S01.mock_fear' in ids(eng), 'rewind did not restore the choice')
    eng.act('S01.mock_fear')
    check(eng.state.arc('lazlo_nerve') == (0, 1), 'acting after rewind failed')
    fresh = Engine(Story(demo_data()))
    fresh.start()
    try:
        fresh.rewind()
        raise AssertionError('rewind at the start did not refuse')
    except EngineError:
        pass
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'x.save')
        eng.save(path)
        other = Engine(Story(demo_data()))
        other.start()
        other.load(path)
        check(other.state.to_dict() == eng.state.to_dict(), 'load did not restore the state')
        other.rewind()
        check(other.state.arc('lazlo_nerve') == (0, 0), 'the timeline did not survive a save')
        changed = demo_data()
        changed['title'] = 'regenerated'
        try:
            Engine(Story(changed)).load(path)
            raise AssertionError('a save loaded into a regenerated story')
        except SaveMismatch as e:
            check('regenerated' in str(e), f'unclear mismatch message: {e}')


@test
def terminal_player_runs_a_script():
    out = io.StringIO()
    eng = Engine(Story(demo_data()))
    # stern deck root: 1 Look, 2 Examine, 3 Go, 4 Untie, 5 Wait; then in S02 quit
    cli.play(eng, ['4', 'q'], out=out)
    text = out.getvalue()
    check('crack like a pistol shot' in text and eng.state.scene == 'S02', f'scripted play failed:\n{text}')
    out = io.StringIO()
    cli.play(Engine(Story(demo_data())), ['3', 'b', 'x', 'r', 'q'], out=out)
    check('pick a number' in out.getvalue() and 'nothing to rewind' in out.getvalue(), out.getvalue())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', default='', help='run only tests whose name contains this')
    args = parser.parse_args()
    failed = 0
    started = time.time()
    for fn in TESTS:
        if args.k and args.k not in fn.__name__:
            continue
        t = time.time()
        try:
            fn()
            print(f'ok    {fn.__name__} ({time.time() - t:.1f}s)')
        except Exception:
            failed += 1
            print(f'FAIL  {fn.__name__}')
            traceback.print_exc()
    print(f"\n{'ALL PASSED' if not failed else str(failed) + ' FAILED'} in {time.time() - started:.1f}s")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
