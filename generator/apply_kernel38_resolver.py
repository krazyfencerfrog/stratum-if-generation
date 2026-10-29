#!/usr/bin/env python3
"""Apply the State Resolver spike to stories/kernel38_fable/kernel38_fable_package_draft.json.

Proves:
1. StateAsset tracking (tallow stub, observations, testimony).
2. 7-suspect + silence Resolver Moment in S_N06.
3. State-resolved endings (conviction with proof, unproven without proof,
   innocents accused, silence).
4. Full validation with engine.story.validate.
"""

import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.abspath(os.path.join(THIS_DIR, '..', 'engine'))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from state_resolver import (
    StateAsset, ResolverOption, ResolverOutcome, ResolverSpec, apply_resolver,
    save_resolver_specs
)
from story import Story, validate


def build_kernel38_spec(orig_endings: dict) -> ResolverSpec:
    assets = [
        StateAsset(
            id='yellow_tallow_stub',
            kind='item',
            label='The yellow tallow candle stub',
            subject='C01',
            description='A tallow stub in a room that burns only wax; drawn only by the valet after ten.',
            state_condition="has('yellow_tallow_stub') or flags.has_tallow_stub",
            scene_id='S_N01',
            action_id='S_N01.N01a.3',
            effects=[{'set': 'has_tallow_stub'}]
        ),
        StateAsset(
            id='checked_key_dropped',
            kind='observation',
            label='The key dropped in the doorway',
            subject='C01',
            description='The key was dropped from the hand, not from the lock.',
            state_condition='flags.checked_key_dropped',
            scene_id='S_N01',
            action_id='S_N01.N01a.2',
            effects=[{'set': 'checked_key_dropped'}]
        ),
        StateAsset(
            id='heard_valet_eleven',
            kind='testimony',
            label="Fairbrother's eleven o'clock candle",
            subject='C01',
            description='Fairbrother lit Carrington up the back stair at eleven.',
            state_condition='flags.heard_valet_eleven',
            scene_id='S_N03',
            action_id='S_N03.N03c.1',
            effects=[{'set': 'heard_valet_eleven'}]
        ),
    ]

    options = [
        ResolverOption(
            id='S_N06.accuse_C01',
            label="'Major Carrington.'",
            target='C01',
            detail='major_carrington',
            intent_flag='accused_C01',
            text="You say his name before the whole room: 'Major Lucius Carrington.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C03',
            label="'Mr Nathaniel Yardley.'",
            target='C03',
            detail='nathaniel_yardley',
            intent_flag='accused_C03',
            text="You turn your eyes to the heir: 'Mr Nathaniel Yardley.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C04',
            label="'Doctor Gideon Ashcombe.'",
            target='C04',
            detail='gideon_ashcombe',
            intent_flag='accused_C04',
            text="You look directly at the physician: 'Doctor Gideon Ashcombe.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C05',
            label="'Miss Millicent Gresham.'",
            target='C05',
            detail='millicent_gresham',
            intent_flag='accused_C05',
            text="You point to the fiancée: 'Miss Millicent Gresham.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C06',
            label="'Miss Evangeline Davenport.'",
            target='C06',
            detail='evangeline_davenport',
            intent_flag='accused_C06',
            text="You name the ward: 'Miss Evangeline Davenport.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C07',
            label="'Mrs Cordelia Ormsby.'",
            target='C07',
            detail='cordelia_ormsby',
            intent_flag='accused_C07',
            text="You face the widow: 'Mrs Cordelia Ormsby.'"
        ),
        ResolverOption(
            id='S_N06.accuse_C09',
            label="'Mr Cornelius Ellingham.'",
            target='C09',
            detail='cornelius_ellingham',
            intent_flag='accused_C09',
            text="You address the solicitor: 'Mr Cornelius Ellingham.'"
        ),
        ResolverOption(
            id='S_N06.accuse_none',
            label="'I have no name to give.'",
            target='C01',
            detail='no_name',
            intent_flag='accused_none',
            text="You keep your hands folded in your apron and say quietly, 'I have no name to give.'"
        ),
    ]

    # Resolutions from existing endings can be preserved or adapted
    e_n07_res = orig_endings.get('E_N07', {}).get('resolutions', [])
    e_t2_res = orig_endings.get('E_T2N04', {}).get('resolutions', [])

    outcomes = [
        ResolverOutcome(
            id='outcome_major_convicted',
            target='S_N07',
            condition="flags.accused_C01 and (has('yellow_tallow_stub') or flags.has_tallow_stub)",
            kind='default',
            title='The Carriage Takes the Major',
            summary=(orig_endings.get('E_N07', {}).get('text') or [{'text': ''}])[0].get('text', ''),
            resolutions=e_n07_res
        ),
        ResolverOutcome(
            id='outcome_major_unproven',
            target='E_major_unproven',
            condition="flags.accused_C01 and not (has('yellow_tallow_stub') or flags.has_tallow_stub)",
            kind='ending',
            title='The Word of a Servant',
            summary=(
                "You name Major Carrington before the fire, but when Mr Ellingham asks for proof, "
                "your apron holds only linen and keys. Carrington does not even raise his voice; "
                "he reminds the room of thirty years of honourable service to the Queen, asking whether "
                "an officer's honour is to be weighed against the malicious fancy of a servant fortnighted "
                "in her post. Fairbrother stands by the door with downcast eyes and says nothing. Before noon "
                "your box is set down at the lodge gates; you leave on foot in the thawing slush without a character, "
                "while Carrington watches from the first-floor window, the master's key safe in his waistcoat pocket."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_gresham',
            target='E_T2N04',
            condition="flags.accused_C05",
            kind='ending',
            title='The Wrong Passenger',
            summary=(orig_endings.get('E_T2N04', {}).get('text') or [{'text': ''}])[0].get('text', ''),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_yardley',
            target='E_wrong_yardley',
            condition="flags.accused_C03",
            kind='ending',
            title='The Heir in Irons',
            summary=(
                "You name Nathaniel Yardley, producing his muddy boots and the scrap of debt from the snowdrifts "
                "by the stable yard. The nephew shouts that he was only paying a card-hazard in the loft, but the room "
                "recoils from his fury; Mr Ellingham folds his hands and observes that debts and blood make an ancient story. "
                "Major Carrington steps forward with grim military sorrow, locking the heir in the gun room until the county "
                "constable can force the drifted lane. Nathaniel's inheritance is placed in chancery, Millicent turns her face "
                "to the wall, and the master's true killer stands beside the magistrate's man as the guardian of the household."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_ashcombe',
            target='E_wrong_ashcombe',
            condition="flags.accused_C04",
            kind='ending',
            title="The Physician's Disgrace",
            summary=(
                "You name Doctor Ashcombe, pointing to the melted snow upon his boots in the gun room and his midnight passage "
                "along the gallery. The doctor flushes red and then goes grey; to defend his innocence against the murder he would "
                "have to speak of Mrs Ormsby and the dark corner of the library, and his gentleman's code chokes him. Major Carrington "
                "promptly relieves him of the death certificate, declaring that a medical attendant under suspicion cannot certify "
                "a natural end. Ashcombe is escorted to the morning room under watch, his practice ruined and the widow's reputation "
                "destroyed, while Carrington smiles thinly by the mantel, untouched."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_davenport',
            target='E_wrong_davenport',
            condition="flags.accused_C06",
            kind='ending',
            title='The Ward Cast Out',
            summary=(
                "You name Evangeline Davenport, revealing how her clock was set back and her sworn account of the quarrel shifted "
                "to shield her place in the house. The girl breaks into terrified weeping, clinging to the widow's skirts, but the "
                "drawing room is cold; Carrington proclaims that deceit under an adoptive roof cannot be suffered when a benefactor "
                "lies dead. She is ordered confined to the schoolroom until relatives in the north can be summoned to take her away. "
                "Disinherited, branded as an ingrate and a schemer, her life is broken, while the true assassin carves the roast at dinner."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_ormsby',
            target='E_wrong_ormsby',
            condition="flags.accused_C07",
            kind='ending',
            title="The Widow's Undoing",
            summary=(
                "You name Mrs Ormsby, producing the jet hairpin found below the keyhole and speaking of her midnight prowl outside the "
                "locked study. The widow draws herself up in frozen outrage, but Mr Ellingham's searching questions force the truth of "
                "the forged letter of credit into the open. Carrington deplores the domestic scandal with grave rectitude, declaring "
                "that while a lady may not hang without stronger proof, she must quit the estate before nightfall with only her personal "
                "effects. The family name is permanently stained, and Carrington remains the unquestioned arbiter of the house."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_wrong_ellingham',
            target='E_wrong_ellingham',
            condition="flags.accused_C09",
            kind='ending',
            title="The Law's Malpractice",
            summary=(
                "You name Cornelius Ellingham, citing the draft will concealed in his writing case that would have diminished his "
                "lucrative management of the estate. The solicitor stammers, his legal composure shattered as the gentlemen demand to "
                "see his papers. Carrington demands his keys and impounds his dispatch case on the spot, announcing that the Law Society "
                "shall hear of this breach of trust. Ellingham is ruined and disgraced before the county, but the real crime—the poker struck "
                "in the dark—is buried beneath professional scandal, and Carrington walks free."
            ),
            resolutions=e_t2_res
        ),
        ResolverOutcome(
            id='outcome_silence',
            target='E_silence',
            condition="flags.accused_none",
            kind='ending',
            title='The Carriage Leaves at Noon',
            summary=(
                "You keep your hands folded in your apron and give no name. Major Carrington waits a moment, his eyes scanning the "
                "quiet circle, then nods as if confirmed in what he already knew. 'A sudden seizure of the heart,' he announces, "
                "'brought on by the winter chill, as the doctor will certify.' Mr Ellingham's paper is signed by every gentleman at "
                "the mantel. By noon the snowplows break through from the turnpike; the guests depart in a solemn procession of "
                "broughams and carts. Carrington shakes Fairbrother's hand at the carriage door, tips the groom a sovereign, and leaves "
                "the dead master to his churchyard vault with his secret kept forever."
            ),
            resolutions=e_t2_res
        ),
    ]

    return ResolverSpec(
        scene_id='S_N06',
        moment_id='S_N06.reckoning',
        dimension='accusation',
        neutral_option_id='S_N06.accuse_none',
        assets=assets,
        options=options,
        outcomes=outcomes
    )


def main():
    pkg_path = os.path.join(THIS_DIR, '..', 'stories', 'kernel38_fable', 'kernel38_fable_package_draft.json')
    if not os.path.exists(pkg_path):
        pkg_path = os.path.join(THIS_DIR, '..', 'docs', 'runs', 'kernel38_fable_2026-10-28', 'run', 'kernel38_fable_package_draft.json')

    print(f"Loading package from {pkg_path}...")
    with open(pkg_path, 'r', encoding='utf-8') as f:
        pkg = json.load(f)

    spec = build_kernel38_spec(pkg.get('endings', {}))
    spec_path = os.path.join(THIS_DIR, '..', 'stories', 'kernel38_fable', 'kernel38_fable_resolvers.json')
    save_resolver_specs([spec], spec_path)
    print(f"ResolverSpec saved to {spec_path}...")
    print(f"Applying ResolverSpec to {spec.scene_id} ({len(spec.options)} options, {len(spec.outcomes)} outcomes)...")
    resolved_pkg = apply_resolver(pkg, spec)

    # Validate package with engine Story validator
    print("Validating resolved package with Story.validate()...")
    story = Story(resolved_pkg)
    errors, notes = validate(story)

    print(f"Validation: {len(errors)} error(s), {len(notes)} note(s)")
    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
        return 1

    out_path = os.path.join(THIS_DIR, '..', 'stories', 'kernel38_fable', 'kernel38_fable_package_resolved.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(resolved_pkg, f, indent=2)
    print(f"Resolved package successfully written to {out_path}!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
