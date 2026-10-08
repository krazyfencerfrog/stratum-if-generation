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
import playtest                                         # noqa: E402

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
    check(any("'open'" in n for n in notes), f'one-use story verb not noted: {notes}')
    check(not any('introduced' in n for n in notes), f'demo names someone unintroduced: {notes}')


@test
def validator_notes_unintroduced_characters():
    data = demo_data()
    data['scenes']['S02']['opening'] = [{'text': 'The line snaps and the boat drifts toward the gates.'}]
    _, notes = validate(Story(data))
    check(any('S02.closer' in n and 'Pell Szeto' in n for n in notes), f'unintroduced Pell not noted: {notes}')


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
    untie = next(c for c in root['children'] if c['label'] == 'Untie')
    check([c['label'] for c in untie['children']] == ['the stern line'] and 'id' in untie['children'][0],
          f'trivial collapse should keep Untie -> the stern line as a level: {untie}')
    wait = next(c for c in root['children'] if c['label'] == 'Wait')
    check('id' in wait, f'Wait (nothing to choose) did not collapse: {wait}')
    labels_all = [c['label'] for c in eng.menu(collapse='all')['children']]
    check('Untie › the stern line' in labels_all, f"collapse='all' did not merge the single option: {labels_all}")
    eng.act('go:cabin')
    talk = next(c for c in eng.menu()['children'] if c['label'] == 'Talk')
    check([c['label'] for c in talk['children']] == ['Lazlo Brandt'] and len(talk['children'][0]['children']) == 2,
          f'one person, two topics should give Talk -> Lazlo Brandt -> two topics: {talk}')
    talk_all = next(c for c in eng.menu(collapse='all')['children'] if c['label'].startswith('Talk'))
    check(talk_all['label'] == 'Talk › Lazlo Brandt', f"collapse='all': {talk_all['label']}")
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
            untie = {'S01.try_untie', 'S01.untie_blocked', 'S01.cast_off'}
            check(eng.state.room != 'stern_deck' or untie & set(ids(eng)), 'no way to work the line on the stern deck')
            check(not eng.state.flags.get('answered_ledger') or eng.state.room != 'stern_deck'
                  or 'S01.cast_off' in ids(eng), 'ledger answered but cast off missing')
            eng.act(rng.choice([o for o in ids(eng) if o != 'S01.cast_off']))


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
    view = play(cold, ['S01.try_untie', 'S01.untie_blocked', 'S01.mock_fear', 'S01.cast_off'])
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
def history_records_and_rewinds_to_any_point():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    check(len(eng.history) == 1 and any('Mira died' in t for t in eng.history[0]['text']), 'no starting entry')
    play(eng, ['go:cabin', 'talk:lazlo:the_ledger', 'S01.price_fear', 'look', 'go:stern_deck'])
    labels = [h['label'] for h in eng.history]
    check(labels == ['(the beginning)', 'Go › down the cabin steps', 'Talk › Lazlo Brandt › about the ledger',
                     'Talk › Lazlo Brandt › about what a nuisance costs', 'Go › up the steps to the stern deck'],
          f'history labels (look takes no time and is not recorded): {labels}')
    check(len(eng.history) == len(eng.timeline), 'history and timeline out of step')
    check('shoulders come down' in ' '.join(eng.history[3]['text']), 'history lost the text of a step')
    eng.rewind_to(2)
    check(len(eng.history) == 3 and eng.state.arc('lazlo_nerve') == (0, 0) and 'S01.mock_fear' in ids(eng),
          'rewind_to did not restore the state after entry 2')
    for bad in (2, 9, -1):
        try:
            eng.rewind_to(bad)
            raise AssertionError(f'rewind_to({bad}) was accepted')
        except EngineError:
            pass
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'h.save')
        eng.save(path)
        other = Engine(Story(demo_data()))
        other.start()
        other.load(path)
        check(other.history == eng.history, 'history did not survive a save')


# ---------------------------------------------------------------- playtest

def shift_package(at_least, share):
    """One scene, three choices that each move `s` up or down, and a pattern
    shift to ending SHIFT; otherwise ending PLAIN once all three are made."""
    inter = []
    for k in range(3):
        for d in ('up', 'down'):
            inter.append({'id': f'c{k}{d}', 'verb': 'talk', 'object': 'ann', 'detail': f'q{k}{d}',
                          'detail_label': f'answer {k} {d}', 'when': f'not flags.done{k}', 'once': True,
                          'text': f'You answer {d}.', 'effects': [{'set': f'done{k}'}, {'move': 's', 'dir': d}]})
    return {
        'format': 'stratum-story/1', 'story_id': 'shift', 'title': 'shift',
        'states': {'s': {'meaning': 'test'}},
        'world': {'rooms': {'hall': {'name': 'the hall', 'description': [{'text': 'A hall.'}]}},
                  'objects': {}, 'characters': {'ann': {'name': 'Ann', 'description': [{'text': 'Ann.'}],
                                                         'topics': {}}}},
        'scenes': {'S1': {'rooms': ['hall'], 'cast': {'ann': 'hall'}, 'interactions': inter,
                          'exits': [{'to': 'SHIFT', 'when': f"pattern('s','up',{at_least},{share})"},
                                    {'to': 'PLAIN', 'when': 'flags.done0 and flags.done1 and flags.done2'}]}},
        'start': {'scene': 'S1', 'room': 'hall'},
        'endings': {'SHIFT': {'text': [{'text': 'Shifted.'}]}, 'PLAIN': {'text': [{'text': 'Plain.'}]}},
    }


@test
def menu_marks_what_is_new_groups_topics_and_rooms_go_brief():
    data = demo_data()
    eng = Engine(Story(data))
    view = eng.start(seed=1)
    base = data['world']['rooms']['stern_deck']['description'][0]['text'][:30]
    check(base in view['room']['text'], 'the first visit did not give the room in full')
    examine = next(c for c in view['menu']['children'] if c['label'] == 'Examine')
    check(examine.get('new') and all(c.get('new') for c in examine['children']), f'nothing examined yet: {examine}')
    thing = next(c for c in examine['children'] if c.get('id', '').startswith('examine:') and c['id'] != 'examine:you')
    eng.act(thing['id'])
    examine = next(c for c in eng.menu()['children'] if c['label'] == 'Examine')
    again = next(c for c in examine['children'] if c.get('id') == thing['id'])
    check(not again.get('new') and examine.get('new'), f'examined, still new (or the rest lost the mark): {examine}')
    eng.act('go:cabin')
    back = eng.act('go:stern_deck')
    check(base not in back['room']['text'] and back['room']['name'], f"a revisit repeated the base text: {back['room']}")
    check(base in eng.act('look')['room']['text'], 'Look did not give the room in full')
    eng.rewind()
    check(eng.state.room == 'cabin', 'rewind after the brief revisit')
    # many topics: the grouped ones go one level down, the story's own stay on top
    data = demo_data()
    topics = data['world']['characters']['lazlo']['topics']
    for k in range(7):
        topics[f'thing{k}'] = {'label': f'the thing {k}', 'group': 'object', 'says': [{'text': f'Thing {k}.'}]}
    topics['mira_p'] = {'label': 'Mira', 'group': 'person', 'says': [{'text': 'Mira.'}]}
    eng = Engine(Story(data))
    eng.start(seed=1)
    eng.act('go:cabin')
    talk = next(c for c in eng.menu()['children'] if c['label'] == 'Talk')
    lazlo = talk['children'][0]
    labels = [c['label'] for c in lazlo['children']]
    check(labels[-2:] == ['people', 'things'] and len(next(c for c in lazlo['children'] if c['label'] == 'things')['children']) == 7
          and 'about the ledger' in labels, f'topic groups: {labels}')


@test
def names_show_only_once_the_player_knows_them():
    data = demo_data()
    lazlo = data['world']['characters']['lazlo']
    lazlo.update(unnamed='the old man in the oilskin', unnamed_short='the old man')
    lazlo['here'] = [{'text': '{lazlo} sits at the table. You nod to {lazlo}.'}]
    lazlo['topics']['the_ledger']['says'] = [{'text': "'Brandt,' he says. 'Lazlo Brandt.'"}]
    lazlo['topics']['the_logbook']['effects'] = list(lazlo['topics']['the_logbook'].get('effects') or []) + [{'introduce': 'lazlo'}]
    story = Story(data)
    errors, _ = validate(story)
    check(not errors, f'a package with unnamed people: {errors}')
    eng = Engine(story)
    eng.start(seed=1)
    view = eng.act('go:cabin')
    check(view['room']['text'].count('The old man in the oilskin sits at the table. You nod to the old man.') == 1,
          f"text before the introduction (the full label once, then short): {view['room']['text']}")
    talk = next(c for c in view['menu']['children'] if c['label'] == 'Talk')
    check(talk['children'][0]['label'] == 'the old man', f"menu before the introduction: {talk['children'][0]['label']}")
    check(not evaluate("known('lazlo')", eng.state), 'known before the introduction')
    # no effect on the ledger topic: the first conversation is the introduction
    ledger = next(i for p, i in leaves(view['menu']) if i.endswith('the_ledger'))
    view = eng.act(ledger)
    check('Lazlo Brandt sits at the table. You nod to Lazlo Brandt.' in eng.describe()['text'], f"after: {eng.describe()['text']}")
    talk = next(c for c in view['menu']['children'] if c['label'] == 'Talk')
    check(talk['children'][0]['label'] == 'Lazlo Brandt' and evaluate("known('lazlo')", eng.state), 'menu after the introduction')
    eng.rewind()
    check(not evaluate("known('lazlo')", eng.state), 'rewind kept the introduction')
    st = Engine(Story(demo_data()))
    st.start(seed=1)
    check(evaluate("known('lazlo')", st.state), 'a person with no unnamed label is known from the start')
    bad = demo_data()
    bad['world']['characters']['lazlo']['here'] = [{'text': '{nobody} waves.'}]
    bad['world']['characters']['lazlo']['unnamed_short'] = 'x'
    errors, _ = validate(Story(bad))
    check(any('{nobody}' in e for e in errors) and any('unnamed_short without unnamed' in e for e in errors), f'validator: {errors}')


@test
def playtest_explores_the_demo():
    story = Story(demo_data())
    result = playtest.explore(story)
    errors, notes = playtest.explore_findings(story, result)
    check(not errors and not result['truncated'], f'demo exploration: {errors}')
    check(set(result['endings']) == {'END_DEMO'} and len(result['endings']['END_DEMO']) >= 10,
          f"resolution combinations: {result['endings']}")
    i = next(iter(result['endings']['END_DEMO'].values()))
    check(playtest.path_to(result, i), 'no walkthrough')
    curious = playtest.play(story, 'up', runs=40)
    check(set(curious['opportunities_seen']) == {'talk:lake_kaur:the_logbook'} and not curious['unfinished'],
          f"choices in moments are measured by the moment, the rest one by one: {curious['opportunities_seen']}")


@test
def playtest_checks_what_the_menu_shows():
    check(len(cli.KEYS) == playtest.MAX_CHOICES, 'the playtest and the terminal player disagree on menu width')
    data = demo_data()
    s1 = data['scenes']['S01']['interactions']
    twin = dict(next(i for i in s1 if i['id'] == 'S01.cast_off'), id='S01.cast_off_twin')
    s1.append(twin)                     # a second entry labelled exactly like the first
    story = Story(data)
    errors, _ = playtest.explore_findings(story, playtest.explore(story, max_states=300))
    check(any(e.startswith('MENU: scene S01') and 'times' in e for e in errors), f'twin menu entries missed: {errors}')
    eng = Engine(story)
    eng.start(seed=1)
    many = [{'id': f'x{k}', 'verb': 'wave', 'object': None, 'detail': None} for k in range(playtest.MAX_CHOICES + 1)]
    real = eng.options
    eng.options = lambda: real() + [dict(o, object_label=None, detail_label=None) for o in many]
    eng.menu = lambda: {'label': None, 'children': [{'label': f'w{k}', 'id': o['id']} for k, o in enumerate(many)]}
    problems = playtest.menu_problems(eng)
    check(any('more entries than' in p for p in problems) and any('not in the menu' in p for p in problems), f'{problems}')


@test
def playtest_explores_scene_by_scene():
    story = Story(demo_data())
    whole = playtest.explore(story)
    result = playtest.explore_scenes(story)
    errors, _ = playtest.scene_findings(story, result)
    check(not errors and set(result['scenes']) == {'S01', 'S02'}, f'scene-by-scene exploration of the demo: {errors}')
    check(set(result['endings']['END_DEMO']) == set(whole['endings']['END_DEMO']),
          'scene by scene found other resolution combinations than the whole-story search')
    path = next(iter(result['endings']['END_DEMO'].values()))
    eng = Engine(story)
    eng.start(seed=1)
    labels = {}
    for label in path:            # the walkthrough replays: every step is on the menu when it is reached
        labels = {eng.label_of(o): o['id'] for o in eng.options()}
        check(label in labels, f'walkthrough step {label!r} is not offered')
        eng.act(labels[label])
    check(eng.state.ending == 'END_DEMO', 'the walkthrough does not end the story')
    # the stuck state from the test below, found within its scene
    data = demo_data()
    s2 = data['scenes']['S02']['interactions']
    next(i for i in s2 if i['id'] == 'S02.jump')['effects'] = [{'take': 'bow_line'}, {'set': 'jumped'}]
    for it in s2:
        if it['id'] != 'S02.jump':
            it['when'] = 'not flags.reported and not flags.jumped'
    story = Story(data)
    errors, _ = playtest.scene_findings(story, playtest.explore_scenes(story))
    check(any(e.startswith('STUCK') and 'S02' in e and 'jump for it' in e for e in errors), f'stuck state missed: {errors}')
    out = io.StringIO()
    report = playtest.run(story, runs=20, styled_runs=10, out=out, by_scene=True)
    check('explored scene by scene' in out.getvalue() and any(e.startswith('STUCK') for e in report['errors']),
          out.getvalue()[:400])


@test
def seekers_play_the_story_not_the_menu():
    story = Story(demo_data())
    for style in ('seek', 'seek:branch'):
        p = playtest.play(story, style, runs=30)
        check(not p['unfinished'] and p['endings']['END_DEMO'] == 30, f'{style}: {p}')
    random_play = playtest.play(story, 'random', runs=30)
    seek = playtest.play(story, 'seek', runs=30)
    check(seek['mean_actions'] < random_play['mean_actions'], f"seekers wander as much as random play: "
          f"{seek['mean_actions']} vs {random_play['mean_actions']}")


@test
def playtest_finds_stuck_states_and_missed_choices():
    data = demo_data()
    # the jump uses up the bow line without ending the scene, and the other answers close
    s2 = data['scenes']['S02']['interactions']
    jump = next(i for i in s2 if i['id'] == 'S02.jump')
    jump['effects'] = [{'take': 'bow_line'}, {'set': 'jumped'}]
    for it in s2:
        if it['id'] != 'S02.jump':
            it['when'] = 'not flags.reported and not flags.jumped'
    story = Story(data)
    errors, _ = playtest.explore_findings(story, playtest.explore(story))
    check(any(e.startswith('STUCK') and 'S02' in e and 'jump for it' in e for e in errors), f'stuck state missed: {errors}')
    # an ungated way forward makes the ledger choice missable (with its moment removed, nothing holds the scene)
    data = demo_data()
    data['scenes']['S01']['moments'] = [m for m in data['scenes']['S01']['moments'] if m['id'] != 'S01.ledger']
    s1 = data['scenes']['S01']['interactions']
    next(i for i in s1 if i['id'] == 'S01.cast_off')['when'] = 'true'
    for it in s1:
        if it['id'] in ('S01.try_untie', 'S01.untie_blocked'):
            it['when'] = 'false'
    story = Story(data)
    plays = [playtest.play(story, 'up', runs=60)]
    _, notes = playtest.play_findings(story, plays)
    check(any('S01.price_fear' in n and 'curious plays' in n for n in notes), f'missable choice not noted: {notes}')
    check(not any('the_logbook' in n for n in notes), 'an optional discovery was noted')


@test
def playtest_measures_pattern_shifts():
    loose = Story(shift_package(1, 0.5))       # one 'up' answer is enough: random play shifts often
    plays = [playtest.play(loose, s, runs=200) for s in ('random', 's:up')]
    errors, _ = playtest.play_findings(loose, plays)
    check(any('pattern shift S1 -> SHIFT' in e and 'not clear enough' in e for e in errors), f'loose shift passed: {errors}')
    strict = Story(shift_package(3, 0.75))     # all three up: 1 in 8 random plays
    plays = [playtest.play(strict, s, runs=400) for s in ('random', 's:up', 's:down')]
    errors, notes = playtest.play_findings(strict, plays)
    rate = plays[0]['shift_rates'][('S1', 'SHIFT')]
    check(not errors and 0.05 < rate < 0.2, f'strict shift: rate {rate}, {errors}')
    check(plays[1]['shift_rates'][('S1', 'SHIFT')] == 1.0 and plays[2]['shift_rates'][('S1', 'SHIFT')] == 0.0,
          f"styles: {[p['shift_rates'] for p in plays]}")


# ---------------------------------------------------------------- moments, time, seen, think, weight

@test
def moments_gate_and_lapse():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    play(eng, ['S01.try_untie', 'S01.untie_blocked'])
    check(eng.state.scene == 'S01' and 'S01.ledger' in eng.state.moments, 'the required moment was not opened')
    eng.state.flags['cast_off'] = True          # even with the exit's own condition true...
    eng.act('look')
    eng.act('examine:stern_line')
    check(eng.state.scene == 'S01', 'a required moment did not hold the scene')
    eng.state.flags['cast_off'] = False
    eng.act('S01.put_off')
    check('S01.price_fear' not in ids(eng) and 'S01.ledger' in eng.state.used, 'answering did not close the moment')
    view = eng.act('S01.cast_off')
    check(eng.state.scene == 'S02', 'the scene did not move on once the moment was answered')
    # an optional moment lapses after its count, with its own effect
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    play(eng, ['go:cabin', 'S01.kettle_on'])
    texts = []
    for a in ['examine:kettle', 'examine:lazlo', 'examine:you']:
        texts += eng.act(a)['text']
    check(any('drinks both cups' in t for t in texts) and eng.state.flags.get('refused_tea'), f'no lapse: {texts}')
    check('S01.tea_yes' not in ids(eng), 'a lapsed moment is still offered')
    # an offered, unanswered optional moment lapses when the scene ends
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    play(eng, ['go:cabin', 'S01.kettle_on', 'talk:lazlo:the_ledger', 'S01.price_fear', 'go:stern_deck'])
    view = eng.act('S01.cast_off')
    check(eng.state.scene == 'S02' and 'S01.tea' in eng.state.used and eng.state.flags.get('refused_tea'),
          'leaving the scene did not lapse the open tea moment')


@test
def time_passes_only_when_something_changes():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    for a in ['examine:you', 'think:mira', 'examine:stern_line']:
        eng.act(a)
    check(eng.state.turns == 0 and eng.state.actions == 3, f'free actions took time: {eng.state.turns}')
    eng.act('go:cabin')
    check(eng.state.turns == 1, 'moving took no time')
    eng.act('S01.kettle_on')
    check(eng.state.turns == 2, 'an action that changed something took no time')
    eng.act('wait')
    check(eng.state.turns == 3, 'waiting took no time')
    data = demo_data()
    next(i for i in data['scenes']['S01']['interactions'] if i['id'] == 'S01.read_ledger')['takes_time'] = True
    eng = Engine(Story(data))
    eng.start(seed=1)
    play(eng, ['go:cabin', 'talk:lazlo:the_ledger'])
    before = eng.state.turns
    eng.act('S01.read_ledger')
    check(eng.state.turns == before + 1, 'takes_time did not override the computed rule')


@test
def seen_think_and_weight():
    eng = Engine(Story(demo_data()))
    eng.start(seed=1)
    check('lazlo' not in eng.state.seen and 'think:the_captain' not in ids(eng), 'seen before met')
    eng.act('go:wheelhouse')
    check('lake_kaur' in eng.state.seen and 'think:the_captain' in ids(eng), 'meeting the captain did not unlock the thought')
    check('logbook' not in eng.state.seen, 'a hidden object was seen')
    eng.act('S01.open_drawer')
    check('logbook' in eng.state.seen, 'an object that appeared was not seen')
    play(eng, ['go:stern_deck', 'go:cabin'])
    check('talk:lazlo:the_logbook' in ids(eng), 'a seen-gated conversation did not open')
    check('wet to the knees' not in eng.act('examine:you')['text'][0].lower(), 'the wrong self-description')
    data = demo_data()
    next(i for i in data['scenes']['S01']['interactions'] if i['id'] == 'S01.cast_off')['weight'] = 'major'
    eng = Engine(Story(data))
    eng.start(seed=1)
    play(eng, ['S01.try_untie', 'S01.put_off'])
    leaf = [l for l in leaves_with(eng.menu()) if l.get('id') == 'S01.cast_off']
    check(leaf and leaf[0].get('weight') == 'major', f'weight did not reach the menu: {leaf}')
    out = io.StringIO()
    cli.show_level(eng.menu(), [], out)
    check('◆' not in out.getvalue(), 'the marker showed at the root for a nested choice')
    untie = next(c for c in eng.menu()['children'] if c['label'] == 'Untie')
    out = io.StringIO()
    cli.show_level(untie, ['Untie'], out)
    check('◆' in out.getvalue(), f'the terminal player did not mark the major choice:\n{out.getvalue()}')


def mini(**over):
    """A small package for the reading tests (2026-10-08): two rooms, a pen
    that starts on the desk, two people, one scene with an ending."""
    data = {
        'format': 'stratum-story/1', 'story_id': 'mini', 'title': 'Mini',
        'world': {
            'rooms': {'deck': {'name': 'the stern deck', 'description': [{'text': 'Wet planks. The fountain pen lies on the bench, its nib wet.'}],
                               'exits': [{'to': 'cabin', 'label': 'down to the cabin'}]},
                      'cabin': {'name': 'the cabin',
                                'description': [{'text': 'A narrow green room. The stove ticks.'}],
                                'exits': [{'to': 'deck', 'label': 'up to the deck'}]}},
            'objects': {'pen': {'name': 'the fountain pen', 'location': 'deck', 'portable': True,
                                'description': [{'text': 'A pen.'}]},
                        'saddle': {'name': 'the saddle', 'location': 'deck', 'portable': True,
                                   'description': [{'text': 'Old leather.'}]}},
            'characters': {'C01': {'name': 'Ann Lee', 'gender': 'f', 'description': [{'text': 'Ann.'}],
                                   'here': [{'text': 'Ann Lee is asleep in the cabin, warm by the stove.'}],
                                   'topics': {'money': {'label': 'money', 'says': [{'text': "'Money,' she says."}]}}},
                           'C02': {'name': 'Bo Gray', 'gender': 'm', 'description': [{'text': 'Bo.'}],
                                   'here': [{'text': 'Bo Gray sits by the stove, warming his hands.'},
                                            {'text': 'Bo Gray leans on the rail.'}], 'topics': {}}},
        },
        'scenes': {'S1': {'title': 'One', 'opening': [{'text': 'Rain falls on the deck.'}], 'rooms': ['deck', 'cabin'],
                          'cast': {'C01': 'deck', 'C02': 'deck'},
                          'interactions': [
                              {'id': 'S1.a1', 'verb': 'use', 'object': 'saddle', 'detail': 'set_it_down',
                               'detail_label': 'set the saddle between them', 'text': 'You set it down.'},
                              {'id': 'S1.a2', 'verb': 'take', 'object': 'pen', 'detail': 'saddle', 'text': 'You sign.'},
                              {'id': 'S1.a3', 'verb': 'talk', 'object': 'C01', 'detail': 'what_it_costs',
                               'detail_label': 'what a nuisance costs', 'text': 'She sighs.'},
                              {'id': 'S1.end', 'verb': 'wait', 'object': 'C02', 'text': 'You wait.',
                               'effects': [{'set': 'done'}]}],
                          'exits': [{'to': 'E1', 'when': 'flags.done'}]}},
        'start': {'scene': 'S1', 'room': 'deck'},
        'endings': {'E1': {'title': 'The End', 'text': [{'text': 'It ends.'}],
                           'resolutions': [{'about': 'C01', 'variants': [{'text': 'She is gone, her debt paid.'}]},
                                           {'about': 'C02', 'variants': [{'text': 'He is gone, his debt paid.'}]}]}},
    }
    for k, v in over.items():
        data[k] = v
    return data


@test
def menus_read_as_actions_and_fit_their_keys():
    eng = Engine(Story(mini()))
    eng.start()
    paths = {' › '.join(p): i for p, i in leaves(eng.menu())}
    check('Use › the saddle › set the saddle between them' in paths, f'an action label takes no "on": {sorted(paths)}')
    check('Talk › Ann Lee › about what a nuisance costs' in paths, 'a subject keeps its "about"')
    check('Take › the fountain pen › take it' in paths and 'Take › the fountain pen › on the saddle' not in paths
          and paths.get('Take › the fountain pen › take it') == 'take:pen',
          f'the plain action beside a detailed one is "take it", not the object again: {sorted(paths)}')
    import runtime
    check(runtime._unechoed('take the mooring line off the bollard', 'Take', 'the mooring line') == 'off the bollard'
          and runtime._unechoed('take the mooring line', 'Take', 'the mooring line') == 'take the mooring line',
          'a detail does not repeat the verb and object its path says')
    # a long Examine is grouped; a level wider than the keys ends in "more…"
    data = mini()
    for n in range(40):
        data['world']['objects'][f'o{n}'] = {'name': f'thing {n}', 'location': 'deck', 'description': [{'text': 'x'}]}
    eng = Engine(Story(data))
    eng.start()
    examine = next(c for c in eng.menu()['children'] if c['label'] == 'Examine')
    labels = [c['label'] for c in examine['children']]
    check('people' in labels and 'things here' in labels, f'a long Examine groups people and things: {labels}')
    here = next(c for c in examine['children'] if c['label'] == 'things here')
    from menukeys import KEYS
    check(len(here['children']) <= len(KEYS) and here['children'][-1]['label'] == 'more…',
          f'a level wider than the keys ends in more…: {len(here["children"])}')
    every = [i for _, i in leaves(eng.menu())]
    check(all(f'examine:o{n}' in every for n in range(40)), 'nothing is lost behind more…')


@test
def room_text_says_only_what_is_true_now():
    eng = Engine(Story(mini()))
    v = eng.start()
    room = v['room']['text']
    check('asleep in the cabin' not in room and 'by the stove' not in room and 'Bo Gray leans on the rail' in room
          and 'Ann Lee is here' in room,
          f'a here-line naming another room gives way to a plain one: {room}')
    eng.act('take:pen')
    v = eng.act('look')
    check('fountain pen lies on the bench' not in v['room']['text'] and 'Wet planks' in v['room']['text'],
          f'a sentence about a thing that has left the room goes: {v["room"]["text"]}')
    # the scene's own room text placing a person replaces their here-line
    data = mini()
    data['scenes']['S1']['room_text'] = {'deck': [{'text': 'Bo Gray is coiling rope at the stern.'}]}
    v = Engine(Story(data)).start()
    check('leans on the rail' not in v['room']['text'] and 'coiling rope' in v['room']['text'], v['room']['text'])


@test
def a_view_does_not_say_the_same_thing_twice():
    data = mini()
    data['scenes']['S1']['opening'] = [{'text': 'The town meeting has come to the square for the water vote, and the crowd is '
                                                'silent except for the wind moving through the dry grass.'}]
    data['scenes']['S1']['events'] = [{'id': 'S1.e1', 'text': 'The town meeting comes to the square for the water vote, the '
                                                              'crowd silent except for the wind in the dry grass.'}]
    data['world']['rooms']['deck']['description'] = [{'text': 'Wet planks and the the rail.'}]
    v = Engine(Story(data)).start()
    joined = ' '.join(v['text'])
    check(joined.count('water vote') == 1, f'an event restating the opening is not read twice: {v["text"]}')
    check('the the' not in v['room']['text'], 'doubled small words are made single')


@test
def a_lingering_player_is_shown_the_way_on():
    data = mini()
    sc = data['scenes']['S1']
    sc['nudges'] = [{'id': 'S1.n1', 'after': 2, 'text': 'Bo coughs.'}]
    sc['interactions'][-1]['effects'] = [{'set': 'go_S1__E1'}]
    sc['exits'] = [{'to': 'E1', 'when': 'flags.go_S1__E1'}]
    eng = Engine(Story(data))
    eng.start()
    def marked():
        return [i for p, i in leaves(eng.menu()) if _leaf(eng.menu(), i).get('way')]
    check(not marked(), 'no hint before the player lingers')
    for _ in range(5):
        eng.act('wait')
    check(marked() == ['S1.end'], f'after the nudges and two more idle actions the way on is marked: {marked()}')
    wait = next(c for c in eng.menu()['children'] if c['label'] == 'Wait')
    check(wait.get('way'), 'the path to it is marked too')


def _leaf(tree, oid):
    if tree.get('id') == oid:
        return tree
    for c in tree.get('children') or []:
        hit = _leaf(c, oid)
        if hit:
            return hit
    return None


@test
def endings_name_who_each_line_is_about():
    eng = Engine(Story(mini()))
    eng.start()
    v = eng.act('S1.end')
    check(v['ending'] == 'E1' and 'Ann Lee is gone, her debt paid.' in v['text']
          and 'Bo Gray is gone, his debt paid.' in v['text'], f'each resolution says who, and alike lines both stay: {v["text"]}')


def leaves_with(tree):
    if 'id' in tree:
        yield tree
        return
    for c in tree['children']:
        yield from leaves_with(c)


@test
def validator_checks_moments_and_the_rest():
    def broken(mutate, expect):
        data = demo_data()
        mutate(data)
        errors, _ = validate(Story(data))
        check(any(expect in e for e in errors), f'expected an error containing {expect!r}, got {errors}')
    broken(lambda d: d['scenes']['S01']['moments'][0].update(neutral='S01.cast_off'), 'neutral option')
    broken(lambda d: d['scenes']['S01']['moments'][0]['options'].append('S01.nope'), "option 'S01.nope'")
    broken(lambda d: d['scenes']['S01']['moments'][1].pop('lapse'), 'needs a lapse')
    broken(lambda d: d['scenes']['S01']['moments'][0].update(lapse={'after': 3}), 'cannot lapse')
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(when="seen('ghost_ship')"), "seen() names")
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(when="answered('S09.x')"), 'unknown moment')
    broken(lambda d: d['scenes']['S01']['interactions'][0].update(weight='huge'), 'weight must be')
    broken(lambda d: d['protagonist']['think']['mira'].update(says=[]), 'think mira: says nothing')


@test
def terminal_player_runs_a_script():
    out = io.StringIO()
    eng = Engine(Story(demo_data()))
    # stern deck root: 1 Look, 2 Examine, 3 Go, 4 Think, 5 Untie (-> 1 the stern line), 6 Wait, 7 Inventory
    cli.play(eng, ['5', '1', 'q'], out=out)
    text = out.getvalue()
    check('Before you do' in text and eng.state.placements['lazlo'] == 'stern_deck',
          f'scripted play failed:\n{text}')
    out = io.StringIO()
    cli.play(Engine(Story(demo_data())), ['3', 'b', 'x', 'u', 'q'], out=out)
    check("pick an option's key" in out.getvalue() and 'nothing to rewind' in out.getvalue(), out.getvalue())
    # history: go to the cabin (3 Go -> 2 cabin), ask about the ledger, then h and back to point 1
    out = io.StringIO()
    eng = Engine(Story(demo_data()))
    cli.play(eng, ['3', '2', '4', '1', '1', 'h', '1', 'q'], out=out)
    text = out.getvalue()
    check('History:' in text and 'Go › down the cabin steps' in text and 'Talk › Lazlo Brandt › about the ledger' in text,
          f'history listing wrong:\n{text}')
    check('(back to 1' in text and len(eng.history) == 2 and eng.state.room == 'cabin'
          and 'talk:lazlo:the_ledger' in ids(eng), f'going back through history failed:\n{text}')


# ---------------------------------------------------------------- the paned interface (tui.py)

def tui_session(seed=1):
    from ui.session import Session
    s = Session(Engine(Story(demo_data())), save_path=os.path.join(tempfile.mkdtemp(), 'tui.save'))
    s.start(seed=seed)
    return s


def to_entry(session, label):
    i = [c['label'] for c in session.items()].index(label)
    session.select(i)
    session.enter()


@test
def tui_session_menu_acting_and_time():
    s = tui_session()
    check(s.path() == [] and s.items() and s.preview() == s.items()[0]['label'], 'the menu starts at its root')
    s.move(-1)
    check(s.level()['index'] == len(s.items()) - 1, 'up from the top wraps to the bottom')
    to_entry(s, 'Go')
    check(s.path() == ['Go'] and s.back() and s.path() == [], 'into a submenu and back')
    to_entry(s, 'Go')
    s.enter()
    check(len(s.pages) == 2 and s.pages[1][0]['kind'] == 'choice' and any(e['kind'] == 'room' for e in s.pages[1]),
          f'acting adds a page with the choice and the new room: {s.pages[1][:2]}')
    check(s.path() == [] and s.fresh, 'after acting the menu returns to its root and the story opens at the new text')
    to_entry(s, 'Look')
    check(len(s.pages) == 2 and len(s.engine.history) == 2, 'Look adds to the page; no time passes')
    s.unwind()
    check(len(s.pages) == 1 and not s.warn and s.message.startswith('Unwound'), f'unwind trims the pages: {s.message}')
    s.unwind()
    check(s.warn, 'unwinding past the beginning is reported')
    to_entry(s, 'Go'); s.enter()
    to_entry(s, 'Think'); s.enter()
    s.save()
    check(os.path.isfile(s.save_path), 'saved')
    s.rewind_to(0)
    check(len(s.pages) == 1, 'rewind to the beginning')
    s.load()
    check(len(s.pages) == len(s.engine.history) == 3 and not s.warn, f'load rebuilds the pages: {s.message}')
    j = s.journal()
    check(('current', '1. Before Dawn  (now)') in j and any(k == 'section' and t == 'People' for k, t in j), f'journal: {j}')
    here = s.here()
    check(here['title'] and here['chapter'] == 'Before Dawn' and here['carrying'], f'here: {here}')
    check(not s.pick_key('z') and s.pick_key('1'), 'menu keys pick entries that exist')


@test
def tui_draws_every_pane_at_any_size():
    from ui.app import App
    from ui.surface import MemorySurface
    s = tui_session()
    wide = App(s, MemorySurface(30, 110))
    wide.draw()
    text = wide.surface.text()
    for want in ('The Captain Will Not Leave', 'What do you do?', '┌─ Here', 'Story', 'Before dawn, the canal', 'q quit'):
        check(want in text, f'the wide layout lacks {want!r}')
    y, x = wide.surface.find('1 Look')
    check(wide.surface.style_at(y, x + 2) == 'selected', 'the selected entry is highlighted')
    narrow = App(s, MemorySurface(24, 64))
    narrow.draw()
    check('What do you do?' in narrow.surface.text() and '┌─ Here' not in narrow.surface.text(), 'narrow: menu below, no side panel')
    tiny = App(s, MemorySurface(10, 40))
    tiny.draw()
    check('make it at least' in tiny.surface.text(), 'a terminal too small says so')
    for key, title in (('j', 'The story so far'), ('h', 'History: go back'), ('?', 'Help'), ('q', 'Quit?')):
        wide.handle(key)
        wide.draw()
        check(title in wide.surface.text(), f'{key} did not open {title!r}')
        wide.handle('esc')
    wide.handle('tab')
    wide.draw()
    check('┌─ Here' not in wide.surface.text(), 'Tab hides the side panel')


@test
def tui_reads_well_at_80_by_24():
    """The common terminal (2026-10-08): the story's title said once, the
    menu tall enough for its verbs, help and quit in the footer, and the
    ending's title whole."""
    from ui.app import App
    from ui.surface import MemorySurface
    data = mini()
    data['scenes']['S1']['title'] = 'Mini'                   # a first chapter named like the story
    for n in range(6):
        data['verbs'] = dict(data.get('verbs') or {}, **{f'v{n}': {'label': f'Verb{n}'}})
        data['scenes']['S1']['interactions'].append({'id': f'S1.v{n}', 'verb': f'v{n}', 'object': 'saddle', 'text': 'x'})
    from ui.session import Session
    s = Session(Engine(Story(data)))
    s.start(seed=1)
    app = App(s, MemorySurface(24, 80))
    app.draw()
    text = app.surface.text()
    check(text.splitlines()[0].count('Mini') == 1, f'the title is said once: {text.splitlines()[0]}')
    shown = [l for l in text.splitlines() if l.startswith('│ ') and l[2:3] in '123456789' and l[3:4] == ' ']
    check(len(shown) >= min(8, len(s.items())), f'the menu shows 8 of its {len(s.items())} entries (the old layout 4): '
                                                 f'{len(shown)}')
    check('? help' in text and 'q quit' in text, 'help and quit fit in the footer at 80 columns')
    data['endings']['E1']['title'] = 'The Lock Is Closed, the Boat Is Going Down the Cut Tonight'
    s = Session(Engine(Story(data)))
    s.start(seed=1)
    s.act('S1.end')
    app = App(s, MemorySurface(30, 110))
    app.draw()
    check('Tonight' in app.surface.text(), 'the ending title wraps rather than being cut')


@test
def tui_keys_mouse_and_the_end():
    from ui.app import App
    from ui.surface import MemorySurface
    s = tui_session()
    app = App(s, MemorySurface(30, 110))
    app.draw()
    first_go = [c['label'] for c in s.items()].index('Go')
    row = next(y for y, i in app.menu_hits.items() if i == first_go)
    app.handle(('mouse', row, app.rects['menu'].x + 3, 'click'))
    check(s.level()['index'] == first_go and s.path() == [], 'a click selects')
    app.handle(('mouse', row, app.rects['menu'].x + 3, 'click'))
    check(s.path() == ['Go'], 'a second click opens')
    app.handle('left')
    app.handle('pgup')
    check(s.scroll > 0, 'PgUp scrolls the story back')
    app.handle('end')
    check(s.scroll == 0, 'End returns to the latest')
    app.handle('#')
    check(s.warn, 'a key that is no choice is reported')
    app.handle('h'); app.handle('up'); app.handle('enter')
    check(s.overlay is None, 'Enter on the current point closes history')
    # play to an ending with the explorer's walkthrough, then n starts again
    result = playtest.explore(s.engine.story)
    end = next(iter(next(iter(result['endings'].values())).values()))
    s.start(seed=1)
    for label in playtest.path_to(result, end):
        oid = next(o['id'] for o in s.engine.options() if s.engine.label_of(o) == label)
        check(s.act(oid) is not None, f'walkthrough step {label}: {s.message}')
    check(s.ended, 'the walkthrough did not reach an ending')
    app.draw()
    check('The end' in app.surface.text() and 'n  play again' in app.surface.text(), 'the end pane')
    app.handle('n')
    check(not s.ended and len(s.pages) == 1, 'n plays again')
    app.handle('q'); app.handle('y')
    check(not app.running, 'q then y quits')


@test
def tui_runs_under_curses():
    import pty
    import select
    import struct
    import fcntl
    import termios
    save = os.path.join(tempfile.mkdtemp(), 'pty.save')
    pid, fd = pty.fork()
    if pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.chdir(ENGINE)
        os.execvp(sys.executable, [sys.executable, 'tui.py', DEMO, '--save', save, '--keys',
                                   'down,down,enter,enter,j,pgdn,esc,h,up,esc,?,esc,tab,u,s,l,q,y'])
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    out, status, end = b'', None, time.time() + 30
    while time.time() < end:
        if select.select([fd], [], [], 0.2)[0]:
            try:
                out += os.read(fd, 65536)
            except OSError:
                pass
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = st
            break
    if status is None:
        os.kill(pid, 9)
    check(status == 0, f'tui.py under curses exited with {status}: {out[-400:]!r}')
    check(b'Quit?' in out and os.path.isfile(save), 'the curses run did not draw the quit prompt or save')


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
