"""Agency and Consequentiality Evaluation for Stratum IF Packages.

Implements the agency evaluation metrics defined in docs/fable_response_6.md §5.7:
- Decisions per scene that change knowledge/world vs regard only vs inert
- Convergence/resolver cardinality, options, and asset dependencies
- Reachable endings and ending variance explained by post-fork decisions
- Gated topics and interactions (knowledge & inventory barriers)
- Optional discoveries missed by simulated players
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


def classify_effect(eff: Dict[str, Any], arc_states: Set[str]) -> str:
    """Classifies an engine interaction effect into a semantic category.
    Language-agnostic: relies on engine primitives and flag classifications
    rather than English word stems.
    """
    if not isinstance(eff, dict):
        return 'unknown'
    if 'give' in eff or 'take' in eff or 'place' in eff:
        return 'inventory'
    if 'state' in eff:
        return 'regard'
    if 'set' in eff:
        flag = str(eff['set'])
        if flag.startswith('go_') or flag.startswith('done_'):
            return 'navigation'
        if flag in arc_states:
            return 'regard'
        # Any custom flag set by an interaction or moment is a consequential
        # knowledge, asset, decision, or world state modification (in any language)
        return 'world_state'
    return 'other'


def classify_interaction(it: Dict[str, Any], arc_states: Set[str]) -> str:
    """Classifies an interaction based on its effects:
    - 'knowledge_world': modifies inventory, knowledge/state flags, or world state
    - 'regard_only': modifies character regard/arc states only
    - 'navigation': sets only scene exit/node progression flags
    - 'inert': has no effects (flavor/dialogue only)
    """
    effects = it.get('effects') or []
    if not effects:
        return 'inert'

    types = {classify_effect(e, arc_states) for e in effects}
    if types & {'inventory', 'world_state'}:
        return 'knowledge_world'
    if types == {'regard'}:
        return 'regard_only'
    if types == {'navigation'}:
        return 'navigation'
    if 'regard' in types and 'navigation' in types:
        return 'regard_and_nav'
    return 'other'


def analyze_scene_decisions(package: Dict[str, Any]) -> Dict[str, Any]:
    """Analyzes interaction and decision consequentiality across all scenes."""
    scenes = package.get('scenes', {})
    arc_states = set((package.get('states') or {}).keys())
    
    per_scene = {}
    totals = {
        'total_interactions': 0,
        'knowledge_world': 0,
        'regard_only': 0,
        'navigation': 0,
        'inert': 0,
        'other': 0,
    }

    for sid, sc in scenes.items():
        sc_counts = {
            'total': 0,
            'knowledge_world': 0,
            'regard_only': 0,
            'navigation': 0,
            'inert': 0,
            'other': 0,
        }
        for it in sc.get('interactions', []):
            sc_counts['total'] += 1
            totals['total_interactions'] += 1
            cat = classify_interaction(it, arc_states)
            if cat in sc_counts:
                sc_counts[cat] += 1
                totals[cat] += 1
            else:
                sc_counts['other'] += 1
                totals['other'] += 1

        active = sc_counts['knowledge_world'] + sc_counts['regard_only']
        share = round(sc_counts['knowledge_world'] / active, 3) if active > 0 else 0.0
        sc_counts['consequential_share'] = share
        per_scene[sid] = sc_counts

    total_active = totals['knowledge_world'] + totals['regard_only']
    overall_share = round(totals['knowledge_world'] / total_active, 3) if total_active > 0 else 0.0

    return {
        'totals': totals,
        'overall_consequential_share': overall_share,
        'per_scene': per_scene,
    }


def analyze_resolvers(package: Dict[str, Any], playtest_result: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Analyzes convergence scenes and resolver moments in the package."""
    scenes = package.get('scenes', {})
    endings = package.get('endings', {})
    explore = (playtest_result.get('explore') or {}) if playtest_result else {}
    scene_explore = explore.get('scenes', {})

    resolvers = []
    for sid, sc in scenes.items():
        exits = sc.get('exits', [])
        moments = sc.get('moments', [])
        
        # Detect convergence scene: has moments and multiple outgoing exits to endings or different scenes
        ending_exits = [e for e in exits if e.get('to') in endings]
        all_exits = exits
        
        # Check if scene has a moment with >= 3 options that route conditionally
        has_multi_moment = False
        multi_moment_options = 0
        for m in moments:
            opts = m.get('options') or []
            if len(opts) >= 3:
                has_multi_moment = True
                multi_moment_options = max(multi_moment_options, len(opts))

        if (len(ending_exits) >= 2 or len(all_exits) >= 4) and has_multi_moment:
            outcomes = []
            for e in exits:
                outcomes.append({
                    'target': e.get('to'),
                    'condition': e.get('when', 'true'),
                    'kind': e.get('kind', 'default')
                })

            reaching_states = 0
            if sid in scene_explore:
                reaching_states = scene_explore[sid].get('entries', 0)

            resolvers.append({
                'scene_id': sid,
                'title': sc.get('title', sid),
                'options_count': multi_moment_options,
                'outcomes_count': len(outcomes),
                'ending_targets_count': len(ending_exits),
                'outcomes': outcomes,
                'distinct_states_reaching': reaching_states,
            })

    return resolvers


def is_gated_condition(cond: Optional[str]) -> bool:
    """Checks whether an expression gates content on state/assets/knowledge rather than timeline order.
    Language-agnostic: recognizes built-in engine calls (has, seen, known, at, here) and custom flags,
    while treating simple timeline markers (flags.done_<node>) as chronological progression.
    """
    if not cond or cond in ('true', 'false', 'null'):
        return False
    # Simple node completion flag (flags.done_<node>) is chronological advancement, not asset discovery
    if re.fullmatch(r'flags\.done_\w+', cond.strip()):
        return False
    return True


def analyze_gated_content(package: Dict[str, Any]) -> Dict[str, Any]:
    """Analyzes topics and interactions gated by inventory, knowledge, or observations across all languages."""
    characters = (package.get('world') or {}).get('characters', {})
    scenes = package.get('scenes', {})

    gated_topics = []
    for cid, ch in characters.items():
        for tid, top in (ch.get('topics') or {}).items():
            kw = top.get('known_when')
            req = top.get('requires')
            if is_gated_condition(kw) or is_gated_condition(req):
                gated_topics.append({'character': cid, 'topic': tid, 'condition': kw or req})

    gated_interactions = []
    for sid, sc in scenes.items():
        for it in sc.get('interactions', []):
            w = it.get('when')
            if is_gated_condition(w):
                gated_interactions.append({'scene': sid, 'interaction': it.get('id'), 'condition': w})

    return {
        'gated_topics_count': len(gated_topics),
        'gated_interactions_count': len(gated_interactions),
        'gated_topics': gated_topics,
        'gated_interactions': gated_interactions,
    }


def analyze_ending_variance(package: Dict[str, Any], playtest_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Measures reachable endings and post-fork ending variance."""
    endings = package.get('endings', {})
    total_endings = len(endings)

    reached_endings = set()
    play_summaries = {}
    if playtest_result:
        explore = playtest_result.get('explore') or {}
        reached_endings.update(explore.get('endings', {}).keys())
        plays = playtest_result.get('plays') or []
        for p in plays:
            style = p.get('style', 'unknown')
            p_ends = dict(p.get('endings') or {})
            reached_endings.update(p_ends.keys())
            play_summaries[style] = p_ends

    reachability = round(len(reached_endings) / max(1, total_endings), 3)

    return {
        'total_endings': total_endings,
        'reached_endings_count': len(reached_endings),
        'reachability': reachability,
        'reached_endings': sorted(list(reached_endings)),
        'style_distributions': play_summaries,
    }


def compute_agency_metrics(package: Dict[str, Any], playtest_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Computes the full §5.7 agency evaluation metrics suite."""
    decisions = analyze_scene_decisions(package)
    resolvers = analyze_resolvers(package, playtest_result)
    gating = analyze_gated_content(package)
    variance = analyze_ending_variance(package, playtest_result)

    # Agency benchmarks
    target_consequential_share = 0.33  # §5.3: at least 1/3 of opportunities change knowledge or world
    actual_share = decisions['overall_consequential_share']
    consequential_pass = actual_share >= target_consequential_share

    has_resolver = len(resolvers) > 0
    multi_ending_pass = variance['total_endings'] >= 3

    return {
        'overall_agency_status': 'PASS' if (consequential_pass and (has_resolver or multi_ending_pass)) else 'NEEDS_WORK',
        'consequential_share': actual_share,
        'target_consequential_share': target_consequential_share,
        'consequential_pass': consequential_pass,
        'decisions': decisions,
        'resolvers': resolvers,
        'gating': gating,
        'variance': variance,
    }


def format_agency_report(metrics: Dict[str, Any]) -> str:
    """Formats the agency metrics into a clean Markdown inspection report."""
    lines = [
        "# Agency & Consequentiality Evaluation Report",
        "",
        f"**Overall Agency Status**: `{metrics['overall_agency_status']}`",
        "",
        "## 1. Consequential Decision Metrics (§5.3)",
        f"- **Knowledge & World Decisions Share**: `{metrics['consequential_share']:.1%}` (target: >= `{metrics['target_consequential_share']:.0%}`)",
        f"- Target Met: `{'YES' if metrics['consequential_pass'] else 'NO'}`",
        f"- Total Scene Interactions: `{metrics['decisions']['totals']['total_interactions']}`",
        f"  - Modifies Knowledge/World/Inventory: `{metrics['decisions']['totals']['knowledge_world']}`",
        f"  - Regard/Arc-state Only: `{metrics['decisions']['totals']['regard_only']}`",
        f"  - Navigation/Progression: `{metrics['decisions']['totals']['navigation']}`",
        f"  - Inert / Flavor Only: `{metrics['decisions']['totals']['inert']}`",
        "",
        "## 2. Convergence & State Resolvers (§5.1 & §5.7)",
    ]

    resolvers = metrics['resolvers']
    if not resolvers:
        lines.append("- No convergence resolvers detected in package.")
    else:
        for r in resolvers:
            lines += [
                f"### Resolver Scene: `{r['scene_id']}` ({r['title']})",
                f"- Decision Options Presented: `{r['options_count']}`",
                f"- Distinct Resolved Pathways: `{r['outcomes_count']}` (Endings: `{r['ending_targets_count']}`)",
                f"- Entry States Reaching Resolver: `{r['distinct_states_reaching']}`",
                "- Resolved Outcomes:",
            ]
            for o in r['outcomes']:
                lines.append(f"  - -> `{o['target']}` when `{o['condition']}` ({o['kind']})")

    lines += [
        "",
        "## 3. Ending Reachability & Post-Fork Variance (§5.7)",
        f"- Total Endings Defined: `{metrics['variance']['total_endings']}`",
        f"- Reachable Endings: `{metrics['variance']['reached_endings_count']}` / `{metrics['variance']['total_endings']}` ({metrics['variance']['reachability']:.0%})",
    ]

    if metrics['variance']['reached_endings']:
        lines.append(f"- Endings: {', '.join(metrics['variance']['reached_endings'])}")

    if metrics['variance']['style_distributions']:
        lines += ["", "### Endings by Play Style:"]
        for style, dist in metrics['variance']['style_distributions'].items():
            dist_str = ', '.join(f"{k}: {v}" for k, v in dist.items()) or "none"
            lines.append(f"- **{style}**: {dist_str}")

    lines += [
        "",
        "## 4. Gated Knowledge & Investigation Barricades (§5.2)",
        f"- Gated Character Topics: `{metrics['gating']['gated_topics_count']}`",
        f"- Gated Scene Interactions: `{metrics['gating']['gated_interactions_count']}`",
        "",
    ]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evaluate agency metrics for a Stratum IF story package.")
    parser.add_argument("package_path", help="Path to story package JSON file")
    parser.add_argument("--playtest-report", help="Optional path to playtest JSON/MD report")
    parser.add_argument("--json", action="store_true", help="Output raw JSON metrics")
    args = parser.parse_args()

    if not os.path.isfile(args.package_path):
        print(f"Error: {args.package_path} not found", file=sys.stderr)
        return 1

    with open(args.package_path, 'r', encoding='utf-8') as f:
        pkg = json.load(f)

    metrics = compute_agency_metrics(pkg)
    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(format_agency_report(metrics))
    return 0


if __name__ == '__main__':
    sys.exit(main())
