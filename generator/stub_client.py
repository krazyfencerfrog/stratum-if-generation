"""A model-free LlmClient for exercising the pipeline's plumbing.

It recognizes each prompt by a distinctive phrase and returns a
schema-valid canned answer, so `main.py` and `step4.py` can be run end to
end (every step, every file, every loop) in seconds with no Ollama server.
It proves that placeholders are filled, outputs parse, validators accept
the documented shapes, repair loops fire and terminate, and step 4's
bookkeeping (lines, nodes, exits, state, computed checks) holds together.
It proves nothing about story quality.

Use it via dynamic_config:

    STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt

Scenario knobs (environment variables):

    STUB_PREMISE_HARD_ROUNDS=1   3.5v returns hard_issues this many times
                                 before returning clean (tests 3.5r)
    STUB_PREMISE_ALWAYS_HARD=1   3.5v never comes back clean (tests the halt)
    STUB_SPINE_FLAGGED_ROUNDS=1  3.75v returns flagged this many times
    STUB_BAD_NODE=N02            that node's first build carries a menu
                                 interaction and an unreachable exit (tests
                                 the computed checks and node repair)
    STUB_REVIEW_FLAG_FIRST=1     4d flags the newest node on review round 0
    STUB_REJOIN_ON=3             the line built on this iteration rejoins the
                                 main line's ending node
    STUB_NOTHING_ON=4            4c reports nothing_worth_building on this
                                 iteration
    STUB_STOP_AFTER=3            4d says stop after this iteration
"""

import json
import os
import re
from llm_client import LlmClient


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class StubClient(LlmClient):

    def __init__(self):
        self.calls = []
        self.premise_verifies = 0
        self.spine_verifies = 0

    def run_prompt(self, prompt, **kwargs):
        kind = self.classify(prompt)
        self.calls.append(kind)
        handler = getattr(self, f'p_{kind}')
        answer = handler(prompt)
        text = answer if isinstance(answer, str) else json.dumps(answer, indent=2)
        print(f'[stub {kind}]' + (' (no think)' if kwargs.get('think') is False else ''))
        return (f'stub reasoning for {kind}', text)

    # ------------------------------------------------------------------ routing

    def classify(self, p):
        head = p[:1500]
        flat = head.replace('\n', ' ')
        checks = [
            ('You are a narrative classification and adaptation engine', 'filter'),
            ('You are the shape-split step', 'shape'),
            ('You are an interactive-contract analyst', 's3_0a'),
            ('identity and epistemic-state analyst', 's3_0b'),
            ('consequence-and-failure analyst', 's3_0c'),
            ('narrative affect analyst', 's3b'),
            ('narrative theme analyst', 's3c'),
            ('viewpoint-structure analyst', 's3d'),
            ('narrative timeline analyst', 's3e'),
            ('narrative setting analyst', 's3f'),
            ('interactivity-complexity analyst', 's3g'),
            ('You are a coherence auditor', 's3h'),
            ('You are a premise builder', 's3_5'),
            ('You are a fidelity auditor', 's3_5v'),
            ('You are the repair step for premise expansion', 's3_5r'),
            ('You are the casting step', 's3_6'),
            ('You are the world step', 's3_7'),
            ('craft-spine construction step', 's3_75'),
            ('verification step for 3.75', 's3_75v'),
            ('repair step for the craft spine', 's3_75r'),
            ('lays down the MAIN LINE', 's4a'),
            ('You build ONE node of an interactive story', 's4b'),
            ('You are step 4c', 's4c'),
            ('You are step 4d', 's4d'),
        ]
        for phrase, kind in checks:
            if phrase in head or phrase in flat:
                return kind
        raise ValueError('stub client does not recognize this prompt: ' + head[:200])

    @staticmethod
    def section(prompt, marker):
        """The JSON block that follows a '- marker' or '--- marker ---' line."""
        i = -1
        for form in ('\n- ' + marker, '\n--- ' + marker, marker):
            i = prompt.find(form)
            if i != -1:
                break
        if i == -1:
            return None
        j = prompt.find('\n', i + 1)
        rest = prompt[j + 1:]
        m = re.search(r'[\[{]', rest)
        if not m or rest[:m.start()].strip().startswith('none'):
            return None
        start = m.start()
        depth = 0
        in_str = False
        esc = False
        for k in range(start, len(rest)):
            c = rest[k]
            if in_str:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c in '[{':
                depth += 1
            elif c in ']}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(rest[start:k + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def text_after(prompt, marker):
        i = prompt.rfind(marker)
        if i == -1:
            return ''
        return prompt[i + len(marker):].strip()

    # ------------------------------------------------------------------ s2

    def p_filter(self, p):
        return p.split('USER KERNEL:')[-1].strip()

    def p_shape(self, p):
        kernel = self.text_after(p, '- the Kernel\n')
        removed = []
        content = kernel
        m = re.search(r',?\s*maybe \d+ or \d+ endings', content)
        if m:
            removed.append(m.group(0).strip(' ,'))
            content = content.replace(m.group(0), '')
        m = re.search(r'I want a lot of branching paths\.?\s*', content)
        if m:
            removed.append(m.group(0).strip())
            content = content.replace(m.group(0), '')
        linear = 'linear' in kernel.lower()
        return {
            'content_kernel': content.strip() or kernel,
            'shape': {
                'endings': {'tier': 'several' if 'ending' in kernel.lower() else 'unstated',
                            'stated': ' / '.join(removed)},
                'linearity': 'linear' if linear else ('branching' if removed else 'unstated'),
                'choice_density': 'unstated',
                'length': 'unstated',
                'removed_clauses': removed,
            },
        }

    # ------------------------------------------------------------------ phase 3

    def p_s3_0a(self, p):
        return {
            "primary_decision_axis": {"label": "which sector to vent or spare", "description": "At each core breakdown, pick the inhabited sector that loses air.", "evidence_basis": "strong_inference"},
            "decision_mechanism": {"shape": "recurring_instances", "evidence_basis": "strong_inference"},
            "secondary_decision_axes": [],
            "decision_landscape": {"shape": "single_axis", "evidence_basis": "strong_inference"}
        }

    def p_s3_0b(self, p):
        return {
            "protagonist_identity": {"type": "systemic_entity", "role_descriptor": "generational-ship AI", "evidence_basis": "explicit"},
            "epistemic_gap": {"present": False, "gap_description": "", "design_status": "not_applicable", "evidence_basis": "strong_inference"},
            "gap_resolution": {"expectation": "not_applicable", "evidence_basis": "strong_inference"}
        }

    def p_s3_0c(self, p):
        return {
            "failure_presence": {"value": "soft", "evidence_basis": "strong_inference"},
            "failure_triggers": {"types": ["resource_depletion"], "evidence_basis": "strong_inference"},
            "failure_cost": {"value": "narrative_setback", "evidence_basis": "strong_inference"},
            "failure_scope": {"value": "pervasive", "evidence_basis": "strong_inference"}
        }

    def p_s3b(self, p):
        return {
            "primary_affect": {"label": "moral dread", "evidence_basis": "strong_inference"},
            "primary_trajectory": {"shape": "escalating", "evidence_basis": "strong_inference"},
            "secondary_affects": [{"label": "claustrophobic tension", "relation": "complementary", "evidence_basis": "explicit"}],
            "tone": {"descriptors": ["claustrophobic", "tense"], "evidence_basis": "explicit"},
            "somatic_address": {"level": 2, "channels": ["life-support telemetry"], "evidence_basis": "strong_inference"},
            "transgression": {"ceiling": {"level": 5, "evidence_basis": "explicit"}, "floor": {"level": 4, "evidence_basis": "strong_inference"}}
        }

    def p_s3c(self, p):
        return {
            "core_thematic_axis": {"pole_a": "survival of the fittest", "pole_b": "collective empathy", "evidence_basis": "explicit"},
            "secondary_thematic_axis": {"approaches": ["cold calculation", "open deliberation"], "evidence_basis": "genre_association"},
            "moral_valence": {"best_case_framing": {"label": "costly survival", "evidence_basis": "strong_inference"},
                              "worst_case_framing": {"label": "hollow efficiency", "evidence_basis": "strong_inference"}}
        }

    def p_s3d(self, p):
        return {
            "viewpoint_handoff": {"ceiling": {"value": "single", "evidence_basis": "explicit"}, "floor": {"value": "single", "evidence_basis": "explicit"},
                                  "count": {"min": 1, "max": 1, "evidence_basis": "explicit"}},
            "viewpoint_excursions": {"ceiling": {"value": "not_indicated", "evidence_basis": "strong_inference"}, "floor": {"value": "not_indicated", "evidence_basis": "strong_inference"},
                                     "types": {"values": [], "evidence_basis": "strong_inference"}, "interactive": {"value": "not_applicable", "evidence_basis": "strong_inference"}}
        }

    def p_s3e(self, p):
        return {
            "timeline_structure": {"category": "single_moment", "evidence_basis": "explicit"},
            "timeline_duration": {"ceiling": {"scale": "hours_to_days", "evidence_basis": "genre_association"}, "floor": {"scale": "hours_to_days", "evidence_basis": "genre_association"}}
        }

    def p_s3f(self, p):
        return {
            "setting_structure": {"ceiling": {"value": "single", "evidence_basis": "explicit"}, "floor": {"value": "single", "evidence_basis": "explicit"}},
            "setting_scale": {"ceiling": {"tier": "city_or_region", "evidence_basis": "strong_inference"}, "floor": {"tier": "city_or_region", "evidence_basis": "strong_inference"}}
        }

    def p_s3g(self, p):
        return {
            "target_ending_count": {"min": 4, "max": 6, "evidence_basis": "no_signal"},
            "branching_density": {"level": "moderate", "evidence_basis": "strong_inference"},
            "state_richness": {"level": "moderate", "channels": ["oxygen stock", "sector status", "core condition"], "evidence_basis": "strong_inference"}
        }

    def p_s3h(self, p):
        checks = []
        kinds = ['contract_contract', 'contract_contract', 'contract_interactive', 'interactive_interactive',
                 'interactive_interactive', 'interactive_interactive', 'contract_interactive', 'contract_interactive',
                 'contract_interactive', 'contract_contract', 'contract_contract', 'contract_interactive']
        for i, k in enumerate(kinds, 1):
            checks.append({"id": f"C{i}", "kind": k, "verdict": "coherent", "summary": "stub", "better_evidenced": "", "resolution": ""})
        return {"checks": checks, "primary_branch_source": {"source": "interactive_question", "rationale": "stub"},
                "unresolved_for_next_phase": []}

    # ------------------------------------------------------------------ 3.5 loop

    VIOLATION = "a crew-trust score that rises with each favor and gates the manual override"

    def premise(self, fixed=False):
        complication = ("The council's warden quietly reroutes air to her own sector." if fixed else self.VIOLATION)
        return {
            "enrichment_budget": {"level": "minimal", "reason": "stub"},
            "protagonist": {"who": "You are the ship's AI, present through cameras and drones.", "wants": "keep the core alive and the sectors breathing",
                            "can_do": "watch every sector, route air, open valves that have a drone at them",
                            "cannot_do": "vent a sector without the sector council's override code, or move a person",
                            "provenance": "kernel_implied", "serves": "3-0b.protagonist_identity"},
            "arena": {"description": "One generational ship, core amidships, four sectors around it.", "provenance": "kernel_stated", "serves": "3f.setting_structure"},
            "pressure": {"description": "The core's margin falls each hour; every sector still breathing costs it.", "clock_or_stock": "core margin (stock), licensed by 3-0c resource_depletion",
                         "provenance": "kernel_implied", "serves": "3-0c.failure_triggers"},
            "opposition": {"who_or_what": "the sector council", "wants": "no sector vented, whatever the core costs", "means": "it holds the override codes and can lock the AI out of the valves",
                           "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "mediation": {
                "question": "Is the ship its people or its core?",
                "to_reach_pole_a": {"pole": "fittest: vent", "what_you_must_do": "obtain a council override or a foreman's manual valve", "cost": "the council learns what you asked for"},
                "to_reach_pole_b": {"pole": "collective: spare", "what_you_must_do": "find and reroute air the sectors are hiding", "cost": "the core margin falls faster"},
                "levers": ["the council override codes", "the hydroponics scrubber feed", "the warden's private reroute"],
                "provenance": "invented", "serves": "3-0a.primary_decision_axis"},
            "turns": [
                {"id": 1, "situation": "The nursery's air is short and the council will not say why.", "what_you_must_do": "find where the air is going",
                 "ways_through": [{"way": "trace the ducts with a drone", "cost": "the drone is lost to the cold"}, {"way": "ask the warden", "cost": "she learns you suspect her"}],
                 "involves": ["the nursery warden"], "form": "discover", "serves": "3-0a.primary_decision_axis"},
                {"id": 2, "situation": "Hydroponics can feed the medical bay or itself, not both.", "what_you_must_do": "get the foreman to open the feed",
                 "ways_through": [{"way": "promise his sector is never vented", "cost": "a promise you may break"}, {"way": "show him the medical bay", "cost": "hours of margin"}],
                 "involves": ["the hydroponics foreman"], "form": "persuade", "serves": "3c.core_thematic_axis"},
                {"id": 3, "situation": "The council offers the override for one sector of your choosing.", "what_you_must_do": "decide whom to tell",
                 "ways_through": [{"way": "tell the sector first", "cost": "they barricade the valve"}, {"way": "tell no one", "cost": "you become the council's instrument"}],
                 "involves": ["the council speaker", "the nursery warden"], "form": "conceal_or_reveal", "serves": "3c.core_thematic_axis"},
            ],
            "cast_seeds": [
                {"role": "the nursery warden", "kind": "individual", "speaks_for": "the nursery families", "wants": "her sector spared", "holds": "a private reroute", "matters_to_turns": [1, 3], "provenance": "invented"},
                {"role": "the hydroponics foreman", "kind": "individual", "speaks_for": None, "wants": "his scrubbers running", "holds": "the manual feed valve", "matters_to_turns": [2], "provenance": "invented"},
                {"role": "the council speaker", "kind": "individual", "speaks_for": "the sector council", "wants": "the AI dependent on the council", "holds": "the override codes", "matters_to_turns": [3], "provenance": "invented"},
                {"role": "the nursery families", "kind": "crowd", "speaks_for": None, "wants": "air", "holds": "the ship's sympathy", "matters_to_turns": [1], "provenance": "invented"},
            ],
            "complications": [{"description": complication, "serves": "3c.core_thematic_axis", "provenance": "invented"}],
            "withheld": [{"item": "names", "reason": "left to casting"}],
            "fidelity_check": [{"clause": "You play as the ship's AI.", "touched": True, "consistent": True}]
        }

    def p_s3_5(self, p):
        return self.premise(fixed=False)

    def p_s3_5v(self, p):
        self.premise_verifies += 1
        hard_rounds = env_int('STUB_PREMISE_HARD_ROUNDS', 0)
        material = self.section(p, 'CONSTRUCTED MATERIAL') or {}
        has_meter = 'crew-trust score' in json.dumps(material)
        hard = (has_meter and self.premise_verifies <= hard_rounds) or env_int('STUB_PREMISE_ALWAYS_HARD', 0) == 1
        findings = []
        if hard:
            findings.append({"status": "violation", "material": self.VIOLATION, "authorized_by": "",
                             "severity": "hard", "note": "A reputation score the player watches; the engine has no such system."})
        return {
            "clause_findings": [{"clause": "You play as the ship's AI.", "touched": True, "contradiction": False, "quote": "", "severity": "", "note": "stub"}],
            "constraint_findings": [],
            "mechanic_findings": findings,
            "engine_findings": [],
            "self_report_disagreements": [],
            "verdict": {"value": "hard_issues" if hard else "clean", "summary": "stub"}
        }

    def p_s3_5r(self, p):
        current = self.section(p, 'THE MATERIAL TO REPAIR') or self.premise()
        revised = json.loads(json.dumps(current))
        revised['complications'] = self.premise(fixed=True)['complications']
        return {"repair_log": [{"finding": self.VIOLATION, "change": "replaced the score with a rerouting complication", "disagreement": ""}],
                "revised": revised}

    # ------------------------------------------------------------------ 3.75 loop

    def spine(self, fixed=False):
        return {
            "invention_ceiling": {"source": "3.5.enrichment_budget", "level": "minimal", "note": "stub"},
            "want_need_tension": {"want": {"pointer": "3.5.protagonist.wants", "restated": "keep the core alive"},
                                  "need": {"description": "to be answerable to someone", "provenance": "invented",
                                           "serves": "3b.secondary_affects: claustrophobic tension" if fixed else "3b.secondary_affects[1] moral complicity"},
                                  "tension": "stub", "enacts_via": "colors how each turn is approached; advisory", "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "irony_mode": {"gap_available": False, "type": "situational", "note": "3-0b.epistemic_gap.present is false", "device": "stub", "resolution_note": "stub", "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "escalation_shape": {"pattern": "compounding", "mechanism": "stub", "transformation_note": None, "new_variable_required": False,
                                 "state_note": "rides the core margin stock", "provenance": "invented", "serves": "3b.primary_trajectory, 3g.state_richness"},
            "setup_payoff_pairs": [{"setup": "turn 1: the warden's private reroute", "payoff": "turn 3: the council's offer", "distance": "two turns", "reinforces": "want_need_tension, irony_mode",
                                    "provenance": "invented", "serves": "3.5.turns: 1 (the nursery's air) and 3 (the council's offer)"}],
            "motif": None
        }

    def p_s3_75(self, p):
        return self.spine(fixed=False)

    def p_s3_75v(self, p):
        self.spine_verifies += 1
        flagged_rounds = env_int('STUB_SPINE_FLAGGED_ROUNDS', 0)
        material = self.section(p, 'the craft spine (3.75), the material to check') or {}
        bad_cite = '[1]' in json.dumps(material)
        flagged = bad_cite and self.spine_verifies <= flagged_rounds
        return {
            "clause_findings": [{"clause": "You play as the ship's AI.", "touched": True, "contradiction": False, "note": "stub"}],
            "mechanic_findings": [
                {"material": "want_need_tension.enacts_via", "authorized_by": "3-0a.primary_decision_axis", "verdict": "authorized", "note": "stub"},
                {"material": "irony_mode", "authorized_by": "3-0b.epistemic_gap", "verdict": "authorized", "note": "gap_available matched present:false"},
                {"material": "escalation_shape", "authorized_by": "3b.primary_trajectory, 3g.state_richness", "verdict": "authorized", "note": "matched escalating"},
                {"material": "setup_payoff_pairs[0]", "authorized_by": "3.5.turns", "verdict": "authorized", "note": "stub"}
            ],
            "self_report_disagreements": ([{"material": "want_need_tension.need.serves", "claimed": "3b.secondary_affects[1] moral complicity",
                                            "found": "index 1 does not exist; index 0 is claustrophobic tension"}] if flagged else []),
            "verdict": {"value": "flagged" if flagged else "clean", "summary": "stub"}
        }

    def p_s3_75r(self, p):
        return {"repair_log": [{"finding": "serves '3b.secondary_affects[1] moral complicity'", "change": "cite by label", "disagreement": ""}],
                "revised": self.spine(fixed=True)}

    # ------------------------------------------------------------------ 3.6 / 3.7

    NAMES = ["Ilse Marrow", "Dov Kessler", "Speaker Quill", "Tamsin Reyes", "Oren Vale", "Petra Lund", "Hal Ondo"]

    def p_s3_6(self, p):
        premise = self.section(p, 'the premise (3.5)') or self.premise(fixed=True)
        seeds = premise.get('cast_seeds') or []
        chars, crowds = [], []
        name_i = 0
        for s in seeds:
            if s.get('kind') == 'crowd':
                crowds.append({"name": s['role'], "who": s.get('wants', ''), "representatives": []})
                continue
            name = self.NAMES[name_i % len(self.NAMES)]
            name_i += 1
            chars.append({"name": name, "role": s['role'], "speaks_for": s.get('speaks_for'),
                          "wants": s.get('wants', ''), "holds": s.get('holds', ''), "stance": "wary",
                          "moved_by": "being shown what the core costs", "voice": "clipped",
                          "topics": ["the air", s.get('holds', 'the ship')], "matters_to_turns": s.get('matters_to_turns', [])})
        for crowd in crowds:
            reps = [c['name'] for c in chars if c.get('speaks_for') == crowd['name']]
            if not reps:
                reps = [chars[0]['name']] if chars else []
                if chars:
                    chars[0]['speaks_for'] = crowd['name']
            crowd['representatives'] = reps
        return {"protagonist_name": "AEGIS", "characters": chars, "crowds": crowds}

    def p_s3_7(self, p):
        cast = self.section(p, 'the cast (3.6)') or {}
        names = [c['name'] for c in cast.get('characters', [])]
        rooms = [
            ("R01", "the core status bay", "where the margin is read", ["the margin readout", "the sector board"], ["R02", "R03", "R05"]),
            ("R02", "the nursery deck", "the warden's sector", ["the crib alcoves", "the private reroute valve"], ["R01", "R04"]),
            ("R03", "the hydroponics scrubber bay", "the foreman's feed valve", ["the scrubber racks", "the manual feed valve"], ["R01", "R04"]),
            ("R04", "the medical bay", "where the air debt is visible", ["the cots", "the intake duct"], ["R02", "R03"]),
            ("R05", "the council chamber", "where the override codes are kept", ["the code locker", "the speaker's desk"], ["R01", "R06"]),
            ("R06", "the drone dock", "where drones are launched", ["the drone cradles"], ["R05"]),
        ]
        out = []
        for i, (rid, name, purpose, fixtures, conns) in enumerate(rooms):
            here = [names[i % len(names)]] if names and i in (1, 2, 4) else []
            out.append({"id": rid, "name": name, "purpose": purpose, "fixtures": fixtures, "connections": conns,
                        "usually_here": here, "protagonist_can": "watch through the camera; operate valves with a drone present"})
        return {"protagonist_presence": {"how": "cameras in every room; two drones", "can_act_on": "valves and doors where a drone is", "cannot_act_on": "people"},
                "rooms": out,
                "levers_placed": [{"lever": "the council override codes", "where": "R05", "as": "a fixture"},
                                  {"lever": "the hydroponics scrubber feed", "where": "R03", "as": "a fixture"},
                                  {"lever": "the warden's private reroute", "where": "R02", "as": "a fixture"}]}

    # ------------------------------------------------------------------ step 4

    def p_s4a(self, p):
        cast = self.section(p, 'the cast (names, roles, wants, holds)') or {}
        world = self.section(p, 'the world (rooms: id, name, purpose, who is usually there; how the protagonist is present)') or {}
        names = [c['name'] for c in cast.get('characters', [])] or ["Ilse Marrow"]
        rooms = [r['id'] for r in world.get('rooms', [])] or ["R01"]

        def node(i, title, goal, turn, rs, cs, extra_open=False, ending=False):
            nid = f"N{i:02d}"
            exits = [] if ending else [{"id": f"{nid}.a", "summary": f"stub state of play after {title}", "leads_to": f"N{i + 1:02d}"}]
            if extra_open and not ending:
                exits.append({"id": f"{nid}.b", "summary": "a different conclusion nobody follows yet", "leads_to": None})
            return {"id": nid, "title": title, "goal": goal, "turn_ref": turn, "rooms": rs, "characters": cs,
                    "pressure": "the margin falls", "what_happens": f"stub: the player works toward {goal}",
                    "exits": exits, "failure_exit": ({"trigger": "resource_depletion", "cost": "narrative_setback", "description": "the margin dips"} if i == 3 else None),
                    "craft_note": "setup" if i == 2 else ("payoff" if i == 4 else "")}
        nodes = [
            node(1, "the alarm", "learn what the margin means", None, rooms[:1], names[:1]),
            node(2, "the missing air", "find where the nursery's air goes", 1, rooms[1:2] or rooms[:1], names[:1], extra_open=True),
            node(3, "the feed", "get the foreman to open the feed", 2, rooms[2:3] or rooms[:1], names[1:2] or names[:1]),
            node(4, "the offer", "decide whom to tell about the override", 3, rooms[4:5] or rooms[:1], names[2:3] or names[:1]),
            node(5, "the ruling", "live with what the ship has become", None, rooms[:1], names[:1], ending=True),
        ]
        return {"through_line": {"id": "T1", "title": "the keeper", "motivation": "keep everyone breathing, then keep the core",
                                 "strategy": "reroute rather than vent", "turning_point": "the council's offer"},
                "nodes": nodes,
                "ending": {"id": "E1", "title": "the strained collective", "summary": "everyone breathes, barely", "earned_by": "rerouting at every turn", "node": "N05"}}

    def p_s4b(self, p):
        outline = self.section(p, "this node's outline entry") or {}
        entities = self.section(p, "this node's rooms (full definitions)") or {}
        revision = self.section(p, 'REVISION (prior version')
        nid = outline.get('id', 'N00')
        bad = (os.environ.get('STUB_BAD_NODE') == nid) and not revision
        rooms_out = []
        set_vars = []
        for r in entities.get('rooms') or [{"id": "R01", "fixtures": ["the margin readout"]}]:
            fixtures = r.get('fixtures') or ["the readout"]
            var = f"{nid.lower()}.{re.sub(r'[^a-z0-9]+', '_', fixtures[0].lower()).strip('_')}_examined"
            interactions = [{"target": fixtures[0], "action": "examine", "requires": [], "result": "stub", "sets": [{"variable": var, "value": "true"}]}]
            set_vars.append(var)
            for ch in entities.get('characters') or []:
                topic = (ch.get('topics') or ['the air'])[0]
                cvar = f"char.{re.sub(r'[^a-z0-9]+', '_', ch['name'].lower())}.{nid.lower()}_talked"
                interactions.append({"target": ch['name'], "action": f"talk:{topic}", "requires": [], "result": "stub", "sets": [{"variable": cvar, "value": "true"}]})
                set_vars.append(cvar)
            if bad:
                interactions.append({"target": "the valve", "action": "choose whether to vent", "requires": [], "result": "stub menu", "sets": []})
            rooms_out.append({"room": r.get('id'), "now": "as defined", "interactions": interactions})
        exits = []
        for i, ex in enumerate(outline.get('exits') or []):
            when = [{"variable": set_vars[min(i, len(set_vars) - 1)], "value": "true"}] if set_vars else []
            if bad and i == 0:
                when = [{"variable": "never.set", "value": "true"}]
            exits.append({"id": ex['id'], "when": when, "transition": "stub transition"})
        shared = outline.get('shared_with') or []
        variants = None
        if shared or (revision and 'variant' in json.dumps(revision).lower()):
            variants = [{"when": [{"variable": set_vars[0], "value": "true"}] if set_vars else [], "variant": "stub variant"}]
        return {"id": nid, "arrival": "stub arrival" + (" (revised)" if revision else ""),
                "rooms": rooms_out,
                "characters": [{"name": ch['name'], "in_room": (rooms_out[0]['room'] if rooms_out else "R01"), "agenda": "stub", "moved_by": "stub"}
                               for ch in entities.get('characters') or []],
                "clock": None, "exits": exits,
                "failure_exit": ({"reached_when": "the margin dips", "cost": outline['failure_exit']['cost'], "rendering": "stub"} if outline.get('failure_exit') else None),
                "ending_variants": variants,
                "design_note": "revised per findings" if revision else ""}

    def p_s4c(self, p):
        digest = self.section(p, 'the story so far') or {}
        shape = self.section(p, 'shape targets (advisory) and iteration') or {}
        it = int(re.search(r'This is iteration (\d+)', p).group(1))
        if env_int('STUB_NOTHING_ON', 0) == it:
            return {"status": "nothing_worth_building", "why": "stub: every candidate is a reskin", "through_line": None,
                    "divergence": None, "modify_nodes": [], "new_nodes": [], "rejoins_at": None, "ending": None}
        nodes = digest.get('nodes') or []
        lines = digest.get('through_lines') or []
        main_path = (lines[0].get('path') if lines else []) or [n['id'] for n in nodes]
        tl = {"id": f"T{it}", "title": f"line {it}", "motivation": f"stub motivation {it}", "strategy": f"stub strategy {it}",
              "differs_from": [{"through_line": l['id'], "how": "stub: different motivation"} for l in lines]}
        if shape.get('linear'):
            final = main_path[-1]
            return {"status": "proposed", "why": "stub", "through_line": tl,
                    "divergence": {"kind": "state_variant", "node": main_path[1] if len(main_path) > 1 else main_path[0], "exit_id": None,
                                   "opportunity": "a second way of playing the same nodes", "how_the_shift_is_explained": "stub"},
                    "modify_nodes": [{"id": main_path[1] if len(main_path) > 1 else main_path[0], "add": "an alternative the player can pursue", "add_exit": None}],
                    "new_nodes": [], "rejoins_at": None,
                    "ending": {"id": f"E{it}", "title": "stub variant ending", "summary": "stub", "earned_by": "stub", "node": final,
                               "when": [{"variable": "stub.alt", "value": "true"}]}}
        rejoin = env_int('STUB_REJOIN_ON', 0) == it
        open_exits = digest.get('open_exits') or []
        new_ids = [f"P{it}_N01"] if rejoin else [f"P{it}_N01", f"P{it}_N02"]
        rooms = sorted({r for n in nodes for r in (n.get('rooms') or [])}) or ["R01"]
        chars = sorted({c for n in nodes for c in (n.get('characters') or [])}) or []
        new_nodes = []
        for i, nid in enumerate(new_ids):
            last = i == len(new_ids) - 1
            exits = [] if (last and not rejoin) else [{"id": f"{nid}.a", "summary": "stub", "leads_to": (main_path[-1] if (last and rejoin) else new_ids[i + 1])}]
            new_nodes.append({"id": nid, "title": f"stub node {nid}", "goal": "stub goal", "turn_ref": 3 if last else 2,
                              "rooms": rooms[:2], "characters": chars[:1], "pressure": "stub", "what_happens": "stub",
                              "exits": exits, "failure_exit": None, "craft_note": ""})
        if open_exits:
            oe = open_exits[0]
            divergence = {"kind": "existing_exit", "node": oe['node'], "exit_id": oe['exit_id'], "opportunity": None,
                          "how_the_shift_is_explained": "stub: the open exit shows the player something new"}
            modify = []
        else:
            node = main_path[1] if len(main_path) > 1 else main_path[0]
            divergence = {"kind": "new_opportunity", "node": node, "exit_id": None,
                          "opportunity": "the speaker makes an offer", "how_the_shift_is_explained": "stub"}
            modify = [{"id": node, "add": "the speaker's offer", "add_exit": {"id": f"{node}.z{it}", "summary": "you took the offer", "leads_to": new_ids[0]}}]
        return {"status": "proposed", "why": "stub", "through_line": tl, "divergence": divergence,
                "modify_nodes": modify, "new_nodes": new_nodes, "rejoins_at": (main_path[-1] if rejoin else None),
                "ending": {"id": f"E{it}", "title": f"stub ending {it}", "summary": "stub", "earned_by": "stub",
                           "node": (main_path[-1] if rejoin else new_ids[-1]), "when": None}}

    def p_s4d(self, p):
        this = self.section(p, 'this iteration') or {}
        shape = self.section(p, 'shape targets (advisory)') or {}
        it, rnd = this.get('iteration', 1), this.get('review_round', 0)
        flag = rnd == 0 and env_int('STUB_REVIEW_FLAG_FIRST', 0)
        new_nodes = this.get('new_node_ids') or []
        built = shape.get('through_lines_built', it)
        target = shape.get('through_lines', 3)
        stop_after = env_int('STUB_STOP_AFTER', 0)
        stop = (stop_after and it >= stop_after) or (not stop_after and built >= target)
        return {
            "earned_choices": {"verdict": "flagged" if flag else "clean",
                               "findings": ([{"issue": "stub: the exit is reached by watching", "node_ids": new_nodes[-1:], "fix": "add an act that earns it"}] if flag else [])},
            "continuity": {"verdict": "clean", "findings": []},
            "cast_and_rooms": {"verdict": "clean", "findings": []},
            "through_line_novelty": {"verdict": "clean", "lines": [{"id": f"T{i}", "device": "stub"} for i in range(1, built + 1)], "findings": []},
            "pacing": {"verdict": "clean", "note": "stub", "findings": []},
            "termination": {"through_lines_built": built, "target": target,
                            "next_seed": (None if stop else {"motivation": "stub next motivation", "strategy": "stub", "diverges_at": "N02", "why_worth_building": "stub"}),
                            "recommendation": "stop" if stop else "continue", "reasoning": "stub"}
        }
