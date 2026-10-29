"""Automated synthesis and generation of Resolver specifications and state assets.

Interactive fiction turns on state: what the player discovers, holds, learns,
and decides. A climax is not a linear corridor where only one exit is offered;
it is a convergence point where the player makes a pivotal commitment, and the
story's outcome resolves conditionally from what they choose and what state
(proof, discoveries, alliances, assets) they hold.

This module provides:
  - generate_resolver_spec(): Model-driven generation using s4_resolver.prompt
  - synthesize_resolver(): Deterministic domain-agnostic synthesis for stub/fallback
  - format_resolver_markdown(): Clean markdown representation for story documents
"""

import os
import re
import json
from typing import Any, Dict, List, Optional

import schemas
from state_resolver import (
    StateAsset,
    ResolverOption,
    ResolverOutcome,
    ResolverSpec,
    load_resolver_specs,
    save_resolver_specs,
)


def _slug(text: str) -> str:
    """Generate a clean identifier slug."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(text or "")).strip("_").lower()
    return s or "target"


def find_convergence_node(story: Dict[str, Any]) -> str:
    """Finds the convergence node on the main line's path."""
    nodes = story.get('nodes') or {}
    if not nodes:
        return 'N01'

    lines = story.get('lines') or {}
    main_line = lines.get('T1') or (list(lines.values())[0] if lines else None)
    main_path = (main_line.get('path') if main_line else None) or list(nodes.keys())

    # 1. Prioritize 'climax' beat along main_path (latest non-ending)
    for nid in reversed(main_path):
        if not nodes.get(nid, {}).get('is_ending') and not nid.startswith('E_'):
            if str(nodes.get(nid, {}).get('beat') or '').lower() == 'climax':
                return nid

    # 2. Check for other climax-adjacent beats along main_path
    for nid in reversed(main_path):
        if not nodes.get(nid, {}).get('is_ending') and not nid.startswith('E_'):
            beat = str(nodes.get(nid, {}).get('beat') or '').lower()
            if beat in ('crisis', 'reversal', 'confrontation', 'gathering'):
                return nid

    # 3. Keywords in node titles along main_path
    keywords = [
        'drawing room', 'gathering', 'confrontation', 'trial', 'climax',
        'verdict', 'reckoning', 'escape', 'council', 'summit', 'gate',
        'vault', 'pass', 'cart', 'final', 'showdown', 'judgment'
    ]
    for nid in reversed(main_path):
        if not nodes.get(nid, {}).get('is_ending') and not nid.startswith('E_'):
            title = str(nodes.get(nid, {}).get('title') or '').lower()
            if any(kw in title for kw in keywords):
                return nid

    # 4. Fallback to last non-ending node along main_path
    non_endings = [nid for nid in main_path if not nodes.get(nid, {}).get('is_ending') and not nid.startswith('E_')]
    if non_endings:
        return non_endings[-1]

    # 5. Absolute fallback
    return list(nodes.keys())[0]


def synthesize_resolver(
    story: Dict[str, Any],
    brief: Optional[Dict[str, Any]] = None,
    promises: Optional[Dict[str, Any]] = None,
) -> ResolverSpec:
    """Deterministically synthesizes a domain-agnostic ResolverSpec.

    Works across any genre (mysteries, sci-fi, fantasy, survival, heists) by
    analyzing the premise engine, turns, opposition, and cast seeds.
    """
    nodes = story.get('nodes') or {}
    node_order = story.get('node_order') or list(nodes.keys())
    premise = story.get('premise') or {}
    cast_seeds = premise.get('cast_seeds') or []
    characters = story.get('characters') or {}
    hidden_truth = premise.get('hidden_truth')
    turns = premise.get('turns') or []
    opposition = premise.get('opposition') or {}
    mediation = premise.get('mediation') or {}
    protagonist = premise.get('protagonist') or {}

    conv_node_id = find_convergence_node(story)
    scene_id = f"S_{conv_node_id}"
    moment_id = f"m_{conv_node_id}_resolver"

    lines = story.get('lines') or {}
    main_line = lines.get('T1') or (list(lines.values())[0] if lines else None)
    main_path = (main_line.get('path') if main_line else None) or list(nodes.keys())
    main_ending_nid = main_path[-1] if main_path else conv_node_id
    success_target = f"E_{main_ending_nid}"

    # Determine earlier nodes suitable for asset placement
    earlier_nodes = [
        nid for nid in main_path
        if nid != conv_node_id and not nodes.get(nid, {}).get('is_ending')
    ]
    if not earlier_nodes:
        earlier_nodes = [conv_node_id]

    prot_name = str(protagonist.get('name') or protagonist.get('who') or '').lower()

    # -------------------------------------------------------------------------
    # Case A: Investigation / Whodunit / Betrayal (hidden_truth is present)
    # -------------------------------------------------------------------------
    if hidden_truth and isinstance(hidden_truth, dict) and hidden_truth.get('truth'):
        truth_text = str(hidden_truth.get('truth') or '')
        dimension = 'accusation'

        # Candidate characters
        candidates = []
        for cid, char in characters.items():
            cname = char.get('name') or char.get('label') or cid
            if cname.lower() in prot_name or prot_name in cname.lower():
                continue
            # Skip deceased victim if named
            if 'dead' in cname.lower() or 'victim' in cname.lower():
                continue
            candidates.append((cid, cname))

        if not candidates and cast_seeds:
            for i, seed in enumerate(cast_seeds):
                slabel = seed.get('label') or f"person_{i+1}"
                if slabel.lower() not in prot_name:
                    candidates.append((f"seed_{i+1}", slabel))

        # Detect the true perpetrator from hidden_truth text
        true_cid, true_name = candidates[0] if candidates else ('c_culprit', 'The Suspect')
        for cid, cname in candidates:
            # Check for name or label match in truth description
            first_name = cname.split()[0]
            if first_name.lower() in truth_text.lower():
                true_cid, true_name = cid, cname
                break

        # Define state assets
        assets = [
            StateAsset(
                id='physical_proof',
                kind='item',
                label='Crucial Physical Evidence',
                subject=true_name,
                description=f'Concrete physical proof tied directly to {true_name}.',
                state_condition="has('physical_proof')",
                scene_id=f"S_{earlier_nodes[0]}",
                effects=[{'take': 'physical_proof'}]
            ),
            StateAsset(
                id='witness_testimony',
                kind='testimony',
                label='Witness Testimony',
                subject=true_name,
                description='An eyewitness or timeline account refuting the official alibi.',
                state_condition="flags.knows_testimony",
                scene_id=f"S_{earlier_nodes[min(1, len(earlier_nodes)-1)]}",
                effects=[{'set': 'knows_testimony'}]
            ),
        ]

        # Options
        options = []
        for cid, cname in candidates:
            slug = _slug(cname)
            options.append(ResolverOption(
                id=f"opt_accuse_{slug}",
                label=f"Accuse {cname}",
                verb="talk",
                target=cid if cid in characters else None,
                detail=f"'{cname}.'",
                intent_flag=f"accuse_{slug}",
                text=f"You step forward before the gathering and name {cname}."
            ))

        # Neutral silence option
        neutral_opt = ResolverOption(
            id="opt_silence",
            label="Remain silent",
            verb="wait",
            target="silence",
            detail=None,
            intent_flag="silence",
            text="You keep your silence and let the moment pass."
        )
        options.append(neutral_opt)

        # Outcomes
        outcomes = []
        true_slug = _slug(true_name)

        # 1. Proven Conviction
        outcomes.append(ResolverOutcome(
            id="outcome_conviction",
            target=success_target,
            condition=f"flags.accuse_{true_slug} and (has('physical_proof') or flags.knows_testimony)",
            kind="ending",
            title=f"The Conviction of {true_name}",
            summary=f"You produce the proof and testimony. Faced with undeniable facts, {true_name} cannot escape accountability. Justice is done."
        ))

        # 2. Unproven Accusation
        outcomes.append(ResolverOutcome(
            id="outcome_unproven",
            target=f"E_{conv_node_id}_unproven",
            condition=f"flags.accuse_{true_slug}",
            kind="ending",
            title=f"The Unproven Claim",
            summary=f"You name {true_name}, but without proof in hand, the company dismisses your words as baseless malice."
        ))

        # 3. Mistaken Accusations (other candidates)
        for cid, cname in candidates:
            slug = _slug(cname)
            if slug == true_slug:
                continue
            outcomes.append(ResolverOutcome(
                id=f"outcome_wrong_{slug}",
                target=f"E_wrong_{slug}",
                condition=f"flags.accuse_{slug}",
                kind="ending",
                title=f"The Undoing of {cname}",
                summary=f"You cast your accusation upon {cname}. An innocent party suffers disgrace, while the true culprit walks free."
            ))

        # 4. Silence
        outcomes.append(ResolverOutcome(
            id="outcome_silence",
            target="E_silence",
            condition="flags.silence",
            kind="ending",
            title="The Silence at Noon",
            summary="You keep your silence. The truth remains buried, and the cost of hesitation is paid in full."
        ))

        return ResolverSpec(
            scene_id=scene_id,
            moment_id=moment_id,
            dimension=dimension,
            neutral_option_id=neutral_opt.id,
            assets=assets,
            options=options,
            outcomes=outcomes
        )

    # -------------------------------------------------------------------------
    # Case B: Adventure / Sci-Fi / Survival / Fantasy (Non-whodunit)
    # -------------------------------------------------------------------------
    dimension = 'pivotal_choice'
    mediation_q = mediation.get('question') if isinstance(mediation, dict) else None

    # Derive candidates from turns, cast, or mediation poles
    candidates = []
    if turns and isinstance(turns[-1], dict) and turns[-1].get('ways'):
        for i, w in enumerate(turns[-1].get('ways', [])):
            wsum = w.get('summary') or f"Strategy {i+1}"
            candidates.append((f"way_{i+1}", wsum))
    elif characters:
        for cid, char in characters.items():
            cname = char.get('name') or char.get('label') or cid
            if cname.lower() not in prot_name:
                candidates.append((cid, f"Ally with {cname}"))

    if not candidates:
        candidates = [
            ("pole_a", "Choose the collective good and stand fast"),
            ("pole_b", "Risk all for individual salvation")
        ]

    # Primary asset
    primary_asset = StateAsset(
        id='critical_key',
        kind='item',
        label='Master Override / Keystone',
        subject='climax',
        description='The essential asset or cipher needed to execute the final commitment.',
        state_condition="has('critical_key')",
        scene_id=f"S_{earlier_nodes[0]}",
        effects=[{'take': 'critical_key'}]
    )
    assets = [primary_asset]

    options = []
    for cid, label in candidates:
        slug = _slug(cid)
        verb = "talk" if ("c" in cid.lower() or "ally" in label.lower() or cid in characters) else "use"
        options.append(ResolverOption(
            id=f"opt_choose_{slug}",
            label=label[:45],
            verb=verb,
            target=cid if cid in characters else "path",
            detail=None,
            intent_flag=f"choose_{slug}",
            text=f"You commit your path: {label}."
        ))

    # Neutral retreat / hesitation option
    neutral_opt = ResolverOption(
        id="opt_retreat",
        label="Hold back / Retreat",
        verb="wait",
        target="retreat",
        detail=None,
        intent_flag="retreat",
        text="You refuse to commit, retreating from the precipice."
    )
    options.append(neutral_opt)

    outcomes = []
    first_slug = _slug(candidates[0][0])

    # 1. Prepared Success with Asset
    outcomes.append(ResolverOutcome(
        id=f"outcome_prepared_{first_slug}",
        target=success_target,
        condition=f"flags.choose_{first_slug} and has('critical_key')",
        kind="ending",
        title="Decisive Fulfillment",
        summary="With the critical keystone in hand, your decision holds against the pressure. The trial is won."
    ))

    # 2. Unprepared Attempt
    outcomes.append(ResolverOutcome(
        id=f"outcome_unprepared_{first_slug}",
        target=f"E_{conv_node_id}_unprepared",
        condition=f"flags.choose_{first_slug}",
        kind="ending",
        title="The Desperate Gambit",
        summary="You make your stand, but lacking the necessary preparation, the cost proves devastating."
    ))

    # 3. Other paths
    for cid, label in candidates[1:]:
        slug = _slug(cid)
        outcomes.append(ResolverOutcome(
            id=f"outcome_{slug}",
            target=f"E_{slug}",
            condition=f"flags.choose_{slug}",
            kind="ending",
            title=f"Path: {label[:30]}",
            summary=f"You chose {label}. The world reshapes around your commitment."
        ))

    # 4. Neutral
    outcomes.append(ResolverOutcome(
        id="outcome_retreat",
        target="E_retreat",
        condition="flags.retreat",
        kind="ending",
        title="The Withdrawal",
        summary="You pull back from the moment. What could have been decided is left to the shifting world."
    ))

    return ResolverSpec(
        scene_id=scene_id,
        moment_id=moment_id,
        dimension=dimension,
        neutral_option_id=neutral_opt.id,
        assets=assets,
        options=options,
        outcomes=outcomes
    )


def generate_resolver_spec(
    gen: Any,
    story: Dict[str, Any],
    brief: Optional[Dict[str, Any]] = None,
    promises: Optional[Dict[str, Any]] = None,
    allow_model: bool = True
) -> ResolverSpec:
    """Generates a ResolverSpec for the story.

    If a saved resolver exists on disk, it is loaded (resumable).
    Otherwise, runs model inference via s4_resolver.prompt when available,
    or falls back to deterministic synthesis.
    """
    # 1. Check for existing resolver in story or on disk
    if isinstance(story.get('resolvers'), list) and story['resolvers']:
        return load_resolver_specs(story['resolvers'])[0]

    if hasattr(gen, 'story_file_path'):
        path = gen.story_file_path('resolvers.json')
        if os.path.isfile(path):
            return load_resolver_specs(path)[0]

    # 2. Check if model call is supported and enabled
    is_stub = os.environ.get('STRATUM_CLIENT', '').lower() == 'stub' or type(getattr(gen, 'client', None)).__name__ == 'StubClient'
    if allow_model and not is_stub and hasattr(gen, 'run_prompt') and hasattr(gen, 'client'):
        try:
            premise = story.get('premise') or {}
            nodes = story.get('nodes') or {}
            chars = story.get('characters') or {}
            cardinality = len(chars) if len(chars) >= 3 else 5

            res_dict = gen.run_prompt('s4', 'resolver', {
                '$$KERNEL$$': getattr(gen, 'kernel', ''),
                '$$PREMISE$$': json.dumps(premise, indent=2),
                '$$PROMISES$$': json.dumps(promises or {}, indent=2),
                '$$NODES$$': json.dumps([{'id': nid, 'title': n.get('title'), 'beat': n.get('beat')} for nid, n in nodes.items()], indent=2),
                '$$CAST$$': json.dumps([{'id': cid, 'name': c.get('name'), 'label': c.get('label')} for cid, c in chars.items()], indent=2),
                '$$CARDINALITY$$': str(cardinality),
            }, prompt_file='s4_resolver.prompt', schema=schemas.RESOLVER_SPEC)

            if isinstance(res_dict, dict) and 'options' in res_dict and 'outcomes' in res_dict:
                return ResolverSpec.from_dict(res_dict)
        except Exception:
            # Model failure or schema reject -> fall back to deterministic synthesis
            pass

    # 3. Deterministic synthesis fallback
    return synthesize_resolver(story, brief, promises)


def format_resolver_markdown(spec: ResolverSpec) -> str:
    """Renders a human-readable markdown section for story.md."""
    lines = [
        f"## Climax Convergence: {spec.dimension.capitalize()} Resolver",
        "",
        f"- **Convergence Scene**: `{spec.scene_id}`",
        f"- **Resolver Moment**: `{spec.moment_id}`",
        f"- **Neutral Option**: `{spec.neutral_option_id}`",
        "",
        "### Discoverable State Assets",
        "",
        "| Asset ID | Kind | Label | Where Acquired | Condition / Flag |",
        "|---|---|---|---|---|",
    ]
    for a in spec.assets:
        where = a.scene_id or "earlier scene"
        cond = a.state_condition or "acquired"
        lines.append(f"| `{a.id}` | {a.kind} | {a.label} | `{where}` | `{cond}` |")

    lines.extend([
        "",
        "### Dilemma Options & Resolved Outcomes",
        "",
        "| Option | Intent Flag | Resolved Ending | Condition |",
        "|---|---|---|---|",
    ])
    for opt in spec.options:
        outcomes = [o for o in spec.outcomes if opt.intent_flag in o.condition or (opt.id == spec.neutral_option_id and o.id == 'outcome_silence')]
        if not outcomes:
            lines.append(f"| {opt.label} | `{opt.intent_flag}` | *(default)* | `true` |")
        for o in outcomes:
            lines.append(f"| {opt.label} | `{opt.intent_flag}` | **{o.title}** (`{o.target}`) | `{o.condition}` |")

    lines.append("")
    return "\n".join(lines)
