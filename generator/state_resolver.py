"""Domain-agnostic state resolver and asset matrix for Stratum IF.

Interactive fiction turns on state: what the player discovers, holds, learns,
and decides. This module models convergence points (Resolvers) where pivotal
commitments are resolved against the game's Information & Asset state rather
than along predetermined linear tracks.

Universal IF concepts:
  - StateAsset: An item, observation, testimony, or deduced fact.
  - ResolverOption: An actionable decision offered at a convergence scene.
  - ResolverOutcome: A rule mapping (Choice + State Assets) -> Ending / Consequence.
  - ResolverSpec: Complete specification for a scene's resolution.
"""

from dataclasses import dataclass, field
import json
import os
import re
from typing import Any, Dict, List, Optional


@dataclass
class StateAsset:
    """A discrete unit of knowledge, physical evidence, or leverage."""
    id: str
    kind: str  # 'item', 'observation', 'testimony', 'fact'
    label: str
    subject: Optional[str] = None  # entity or theme this asset relates to
    description: str = ''
    state_condition: str = ''  # engine expression, e.g. "has('stub')" or "flags.heard_valet"
    # Where this asset is acquired in the story:
    scene_id: Optional[str] = None
    action_id: Optional[str] = None
    effects: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'kind': self.kind,
            'label': self.label,
            'subject': self.subject,
            'description': self.description,
            'state_condition': self.state_condition,
            'scene_id': self.scene_id,
            'action_id': self.action_id,
            'effects': self.effects,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'StateAsset':
        return cls(
            id=d['id'],
            kind=d.get('kind', 'fact'),
            label=d.get('label', ''),
            subject=d.get('subject'),
            description=d.get('description', ''),
            state_condition=d.get('state_condition', ''),
            scene_id=d.get('scene_id'),
            action_id=d.get('action_id'),
            effects=d.get('effects') or [],
        )


@dataclass
class ResolverOption:
    """A choice presented to the player at the convergence moment."""
    id: str
    label: str
    verb: str = 'talk'
    target: Optional[str] = None
    detail: Optional[str] = None
    intent_flag: str = ''
    text: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'verb': self.verb,
            'target': self.target,
            'detail': self.detail,
            'intent_flag': self.intent_flag,
            'text': self.text,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ResolverOption':
        return cls(
            id=d['id'],
            label=d.get('label', ''),
            verb=d.get('verb', 'talk'),
            target=d.get('target'),
            detail=d.get('detail'),
            intent_flag=d.get('intent_flag', ''),
            text=d.get('text', ''),
        )


@dataclass
class ResolverOutcome:
    """An outcome resolved from a choice and supporting state assets."""
    id: str
    target: str  # scene id or ending id
    condition: str  # engine expression
    kind: str = 'ending'  # 'ending' or 'default'
    title: str = ''
    summary: str = ''
    frame: Optional[Dict[str, Any]] = None
    resolutions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            'id': self.id,
            'target': self.target,
            'condition': self.condition,
            'kind': self.kind,
            'title': self.title,
            'summary': self.summary,
            'resolutions': self.resolutions,
        }
        if self.frame:
            d['frame'] = self.frame
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ResolverOutcome':
        return cls(
            id=d['id'],
            target=d.get('target', ''),
            condition=d.get('condition', 'true'),
            kind=d.get('kind', 'ending'),
            title=d.get('title', ''),
            summary=d.get('summary', ''),
            frame=d.get('frame'),
            resolutions=d.get('resolutions') or [],
        )


@dataclass
class ResolverSpec:
    """Complete specification for a convergence point."""
    scene_id: str
    moment_id: str
    dimension: str  # e.g. 'accusation', 'escape_route', 'faction_allegiance'
    neutral_option_id: Optional[str] = None
    assets: List[StateAsset] = field(default_factory=list)
    options: List[ResolverOption] = field(default_factory=list)
    outcomes: List[ResolverOutcome] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'scene_id': self.scene_id,
            'moment_id': self.moment_id,
            'dimension': self.dimension,
            'neutral_option_id': self.neutral_option_id,
            'assets': [a.to_dict() for a in self.assets],
            'options': [o.to_dict() for o in self.options],
            'outcomes': [c.to_dict() for c in self.outcomes],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ResolverSpec':
        return cls(
            scene_id=d['scene_id'],
            moment_id=d['moment_id'],
            dimension=d.get('dimension', 'convergence'),
            neutral_option_id=d.get('neutral_option_id'),
            assets=[StateAsset.from_dict(a) for a in d.get('assets', [])],
            options=[ResolverOption.from_dict(o) for o in d.get('options', [])],
            outcomes=[ResolverOutcome.from_dict(c) for c in d.get('outcomes', [])],
        )


def load_resolver_specs(source: Any) -> List[ResolverSpec]:
    """Loads a list of ResolverSpecs from a file path or parsed JSON data."""
    if isinstance(source, (str, os.PathLike)):
        with open(source, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = source
    if isinstance(data, dict):
        if 'resolvers' in data:
            data = data['resolvers']
        else:
            data = [data]
    return [ResolverSpec.from_dict(d) for d in data]


def save_resolver_specs(specs: List[ResolverSpec], path: str) -> None:
    """Saves a list of ResolverSpecs to a JSON file."""
    data = {'resolvers': [s.to_dict() for s in specs]}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def apply_resolver(package: Dict[str, Any], spec: ResolverSpec) -> Dict[str, Any]:
    """Applies a ResolverSpec to a story package draft.

    1. Injects asset acquisition effects into earlier scene interactions.
    2. Replaces the hardcoded single-exit interaction in the convergence scene
       with the Resolver Moment options.
    3. Rewires scene exits to route to the resolved endings conditionally.
    4. Registers the new endings into package['endings'].
    """
    pkg = json.loads(json.dumps(package))  # deep copy
    scenes = pkg.setdefault('scenes', {})
    endings = pkg.setdefault('endings', {})

    # 1. Wire asset acquisition hooks into earlier scene interactions
    for asset in spec.assets:
        if asset.scene_id and asset.action_id and asset.scene_id in scenes:
            sc = scenes[asset.scene_id]
            for it in sc.get('interactions', []):
                if it.get('id') == asset.action_id:
                    existing = it.setdefault('effects', [])
                    for eff in asset.effects:
                        if eff not in existing:
                            existing.append(eff)

    # 2. Transform the convergence scene
    if spec.scene_id not in scenes:
        raise ValueError(f"Convergence scene {spec.scene_id} not found in package.")

    conv_scene = scenes[spec.scene_id]
    conv_scene.setdefault('moments', [])
    conv_scene.setdefault('interactions', [])
    conv_scene.setdefault('exits', [])

    # Remove existing exit-triggering interaction if present
    # (e.g. S_N06.a2 that previously forced a single linear path)
    orig_interactions = conv_scene['interactions']
    conv_scene['interactions'] = [
        it for it in orig_interactions
        if not any(str(eff.get('set', '')).startswith(f"go_{spec.scene_id}__") for eff in (it.get('effects') or []))
    ]

    # Build the Resolver Moment
    opt_ids = []
    for opt in spec.options:
        opt_it = {
            'id': opt.id,
            'verb': opt.verb,
            'object': opt.target,
            'detail': opt.detail,
            'detail_label': opt.label,
            'text': opt.text,
            'effects': [{'set': opt.intent_flag}],
            'once': True,
            'reach': 'any'
        }
        conv_scene['interactions'].append(opt_it)
        opt_ids.append(opt.id)

    # Add the moment
    resolver_moment = {
        'id': spec.moment_id,
        'options': opt_ids,
        'required': True,
        'neutral': spec.neutral_option_id or (opt_ids[-1] if opt_ids else None)
    }
    # Place resolver moment
    conv_scene['moments'].append(resolver_moment)

    # 3. Rewire scene exits
    # Remove existing default/branch exits from this scene to old downstream nodes
    conv_scene['exits'] = []
    for outcome in spec.outcomes:
        conv_scene['exits'].append({
            'to': outcome.target,
            'when': outcome.condition,
            'kind': outcome.kind
        })

    # 4. Register endings in package['endings'] if kind == 'ending'
    for outcome in spec.outcomes:
        if outcome.kind == 'ending' and outcome.target:
            end_data = {
                'title': outcome.title,
                'text': [{'text': outcome.summary}],
                'resolutions': outcome.resolutions
            }
            if outcome.frame:
                end_data['frame'] = outcome.frame
            endings[outcome.target] = end_data

    return pkg
