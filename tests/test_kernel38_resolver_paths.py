#!/usr/bin/env python3
"""Comprehensive path testing for kernel38_fable_package_resolved.json.

Verifies:
1. Accuse Carrington WITH stub -> reaches S_N07 -> E_N07 (The Carriage Takes the Major).
2. Accuse Carrington WITHOUT stub -> reaches E_major_unproven (The Word of a Servant).
3. Accuse Millicent Gresham -> reaches E_T2N04 (The Wrong Passenger).
4. Accuse Nathaniel Yardley -> reaches E_wrong_yardley (The Heir in Irons).
5. Accuse Doctor Ashcombe -> reaches E_wrong_ashcombe (The Physician's Disgrace).
6. Accuse Evangeline Davenport -> reaches E_wrong_davenport (The Ward Cast Out).
7. Accuse Cordelia Ormsby -> reaches E_wrong_ormsby (The Widow's Undoing).
8. Accuse Cornelius Ellingham -> reaches E_wrong_ellingham (The Law's Malpractice).
9. Remain silent -> reaches E_silence (The Carriage Leaves at Noon).
"""

import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'engine'))
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from runtime import Engine
from story import Story


def play_to_s_n06(eng, take_stub=True):
    """Walks the engine through S_N01 -> S_N05 to reach S_N06."""
    eng.start()
    assert eng.state.scene == 'S_N01', f"Expected S_N01, got {eng.state.scene}"

    # S_N01: take stub (or not)
    if take_stub:
        eng.act('S_N01.N01a.3')  # take yellow_tallow_stub
    else:
        eng.act('S_N01.N01a.1')  # talk Carrington about fire
    eng.act('S_N01.a1')  # go back_stair -> S_N02
    assert eng.state.scene == 'S_N02', f"Expected S_N02, got {eng.state.scene}"

    # S_N02: dinner (3 required moments)
    eng.act('S_N02.N02a.1')  # clock answer
    eng.act('S_N02.N02b.n')  # Millicent moment neutral
    eng.act('S_N02.N02c.n')  # apron moment neutral
    eng.act('S_N02.a1')  # go service_door -> S_N03
    assert eng.state.scene == 'S_N03', f"Expected S_N03, got {eng.state.scene}"

    # S_N03: rounds walked twice (move to gallery for C02)
    eng.act('go:gallery')
    eng.act('S_N03.N03b.n')  # Mrs Ormsby moment
    eng.act('S_N03.N03c.1')  # Fairbrother moment
    eng.act('S_N03.a3')  # show Fairbrother -> S_N04
    assert eng.state.scene == 'S_N04', f"Expected S_N04, got {eng.state.scene}"

    # S_N04: thaw (2 required moments)
    eng.act('S_N04.N04a.n')  # Lavinia moment
    eng.act('S_N04.N04b.n')  # glass moment neutral
    eng.act('S_N04.a2')  # ready to give account -> S_N05
    assert eng.state.scene == 'S_N05', f"Expected S_N05, got {eng.state.scene}"

    # S_N05: maid's apron (move to stair_foot for S_N05.a2)
    eng.act('S_N05.N05a.1')  # stub was mine
    eng.act('S_N05.N05b.n')  # Ormsby hairpin neutral
    eng.act('go:stair_foot')
    eng.act('S_N05.a2')  # go baize_door -> S_N06
    assert eng.state.scene == 'S_N06', f"Expected S_N06, got {eng.state.scene}"


def test_path(pkg_path, accuse_action, take_stub, expected_ending, title):
    with open(pkg_path, 'r', encoding='utf-8') as f:
        pkg = json.load(f)
    story = Story(pkg)
    eng = Engine(story)

    play_to_s_n06(eng, take_stub=take_stub)

    # In S_N06, answer the required background moments first so exits can settle
    eng.act('S_N06.N06a.n')
    eng.act('S_N06.N06b.n')
    eng.act('S_N06.N06c.n')

    # Now make the pivotal accusation choice
    view = eng.act(accuse_action)

    ending = eng.state.ending
    if not ending and eng.state.scene == 'S_N07':
        # S_N07 is the aftermath scene leading to E_N07; walk to study_end to lock
        eng.act('go:gallery')
        eng.act('go:study_end')
        eng.act('S_N07.a4')  # lock -> triggers E_N07
        ending = eng.state.ending

    assert ending == expected_ending, f"[{title}] Expected ending {expected_ending}, got {ending} (scene: {eng.state.scene})"
    print(f"PASS: [{title}] -> Reached {ending}")


def main():
    if len(sys.argv) > 1:
        pkg_path = sys.argv[1]
    else:
        pkg_draft = os.path.join(THIS_DIR, '..', 'stories', 'kernel38_fable', 'kernel38_fable_package_draft.json')
        pkg_resolved = os.path.join(THIS_DIR, '..', 'stories', 'kernel38_fable', 'kernel38_fable_package_resolved.json')
        pkg_path = pkg_draft if os.path.exists(pkg_draft) else pkg_resolved
    if not os.path.exists(pkg_path):
        print(f"File not found: {pkg_path}")
        return 1

    tests = [
        ('S_N06.accuse_C01', True, 'E_N07', 'Accuse Carrington WITH Proof (Conviction)'),
        ('S_N06.accuse_C01', False, 'E_major_unproven', 'Accuse Carrington WITHOUT Proof (Unproven)'),
        ('S_N06.accuse_C05', True, 'E_T2N04', 'Accuse Millicent Gresham (Wrong Passenger)'),
        ('S_N06.accuse_C03', True, 'E_wrong_yardley', 'Accuse Nathaniel Yardley (Heir in Irons)'),
        ('S_N06.accuse_C04', True, 'E_wrong_ashcombe', "Accuse Dr. Ashcombe (Physician's Disgrace)"),
        ('S_N06.accuse_C06', True, 'E_wrong_davenport', 'Accuse Evangeline Davenport (Ward Cast Out)'),
        ('S_N06.accuse_C07', True, 'E_wrong_ormsby', "Accuse Cordelia Ormsby (Widow's Undoing)"),
        ('S_N06.accuse_C09', True, 'E_wrong_ellingham', "Accuse Cornelius Ellingham (Law's Malpractice)"),
        ('S_N06.accuse_none', True, 'E_silence', 'Remain Silent (Carriage Leaves at Noon)'),
    ]

    print(f"Running {len(tests)} test paths against {os.path.basename(pkg_path)}...")
    passed = 0
    for act, stub, exp, name in tests:
        test_path(pkg_path, act, stub, exp, name)
        passed += 1

    print(f"\nAll {passed}/{len(tests)} paths verified successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
