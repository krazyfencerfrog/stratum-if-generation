"""A model-free LlmClient for exercising the pipeline's plumbing.

It recognizes each prompt by a distinctive phrase and returns a
schema-valid canned answer, so `main.py` and `step4.py` can be run end to
end (every step, every file, every loop) in seconds with no Ollama server.
It proves that placeholders are filled, outputs parse, validators accept
the documented shapes, repair loops fire and terminate, and step 4's
bookkeeping (paths, roster, state variables, branch table) holds together.
It proves nothing about story quality.

Use it via dynamic_config:

    STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt

Scenario knobs (environment variables) make the loops exercise their
non-trivial branches:

    STUB_PREMISE_HARD_ROUNDS=1   3.5v returns hard_issues this many times
                                 before returning clean (tests 3.5r)
    STUB_SPINE_FLAGGED_ROUNDS=1  3.75v returns flagged this many times
    STUB_REVIEW_FLAG_FIRST=1     4d flags a beat on review round 0 of each
                                 iteration (tests beat repair + re-review)
    STUB_TRANSFORM_ON=2          4a_next chooses "transform" on this
                                 iteration (tests 4c5 craft refresh)
    STUB_RECONVERGE_ON=3         4a_next reconverges onto the main path's
                                 terminal beat on this iteration
    STUB_STOP_AFTER=3            4d says "stop here" after this iteration
    STUB_PREMISE_ALWAYS_HARD=1   3.5v never comes back clean (tests the halt)
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
        self.review_calls = {}

    def run_prompt(self, prompt):
        kind = self.classify(prompt)
        self.calls.append(kind)
        handler = getattr(self, f'p_{kind}')
        answer = handler(prompt)
        text = answer if isinstance(answer, str) else json.dumps(answer, indent=2)
        print(f'[stub {kind}]')
        return (f'stub reasoning for {kind}', text)

    # ------------------------------------------------------------------ routing

    def classify(self, p):
        head = p[:1500]
        if 'You are a narrative classification and adaptation engine' in head:
            return 'filter'
        if 'You are an interactive-contract analyst' in head:
            return 's3_0a'
        if 'identity and epistemic-state analyst' in head:
            return 's3_0b'
        if 'consequence-and-failure analyst' in head:
            return 's3_0c'
        if 'narrative affect analyst' in head:
            return 's3b'
        if 'narrative theme analyst' in head:
            return 's3c'
        if 'viewpoint-structure analyst' in head:
            return 's3d'
        if 'narrative timeline analyst' in head:
            return 's3e'
        if 'narrative setting analyst' in head:
            return 's3f'
        if 'interactivity-complexity analyst' in head:
            return 's3g'
        if 'You are a coherence auditor' in head:
            return 's3h'
        if 'You are a premise builder' in head:
            return 's3_5'
        if 'You are a fidelity auditor' in head:
            return 's3_5v'
        if 'You are the repair step for premise expansion' in head:
            return 's3_5r'
        if 'craft-spine construction step' in head:
            return 's3_75'
        if 'verification step for 3.75' in head:
            return 's3_75v'
        if 'repair step for the craft spine' in head:
            return 's3_75r'
        if 'step 4a, FIRST PASS' in head:
            return 's4a_first'
        if 'step 4a, LATER PASS' in head:
            return 's4a_next'
        if 'define that\nONE entity' in head or 'define that ONE entity' in head.replace('\n', ' '):
            return 's4_entity'
        if "You generate ONE beat's full content" in head:
            return 's4_beat'
        if 'THIS PROMPT IS UNVALIDATED' in head:
            return 's4c5'
        if 'You are step 4d' in head:
            return 's4d'
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
        # find the first { or [ after the marker line and parse to its close
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

    # ------------------------------------------------------------------ s2 / phase 3

    def p_filter(self, p):
        return p.split('USER KERNEL:')[-1].strip()

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
            "timeline_structure": {"category": "linear", "evidence_basis": "explicit"},
            "timeline_duration": {"ceiling": {"scale": "weeks_to_months", "evidence_basis": "genre_association"}, "floor": {"scale": "weeks_to_months", "evidence_basis": "genre_association"}}
        }

    def p_s3f(self, p):
        return {
            "setting_structure": {"ceiling": {"value": "single", "evidence_basis": "explicit"}, "floor": {"value": "single", "evidence_basis": "explicit"}},
            "setting_scale": {"ceiling": {"tier": "city_or_region", "evidence_basis": "strong_inference"}, "floor": {"tier": "city_or_region", "evidence_basis": "strong_inference"}}
        }

    def p_s3g(self, p):
        return {
            "target_ending_count": {"min": 6, "max": 7, "evidence_basis": "explicit"},
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

    # ------------------------------------------------------------------ 3.5 / 3.75 loops

    def premise(self, fixed=False):
        return {
            "enrichment_budget": {"level": "minimal", "reason": "stub"},
            "protagonist_situation": {"description": "You are the ship's AI.", "wants": "keep the core alive", "can_do": "vent or spare sectors",
                                      "provenance": "kernel_implied", "serves": "3-0b.protagonist_identity"},
            "arena": {"description": "One generational ship.", "provenance": "kernel_stated", "serves": "3f.setting_structure"},
            "instance_generator": {
                "framing": "Each breakdown forces a vent-or-spare choice.",
                "instances": [
                    {"role": "the nursery sector", "what_the_decision_looks_like": "vent it, spare it, or ration it", "provenance": "invented"},
                    {"role": "the maintenance sector", "what_the_decision_looks_like": "vent it or spare it", "provenance": "invented"},
                    {"role": "the medical sector", "what_the_decision_looks_like": "vent it or spare it", "provenance": "invented"},
                    {"role": "the command sector", "what_the_decision_looks_like": "vent it or spare it", "provenance": "invented"}
                ],
                "true_state": "The core cannot support every sector." if fixed else "The core cannot support every sector; a sanity meter tracks the AI's guilt.",
                "serves": "3-0a.primary_decision_axis"
            },
            "complications": [{"description": "Spared sectors begin rationing to prove their worth.", "serves": "3c.core_thematic_axis", "provenance": "invented"}],
            "withheld": [{"item": "names", "reason": "left to casting"}],
            "fidelity_check": [{"clause": "You play as the ship's AI.", "touched": True, "consistent": True}]
        }

    def p_s3_5(self, p):
        return self.premise(fixed=False)

    def p_s3_5v(self, p):
        self.premise_verifies += 1
        hard_rounds = env_int('STUB_PREMISE_HARD_ROUNDS', 0)
        material = self.section(p, 'CONSTRUCTED MATERIAL') or {}
        has_meter = 'sanity meter' in json.dumps(material)
        hard = (has_meter and self.premise_verifies <= hard_rounds) or env_int('STUB_PREMISE_ALWAYS_HARD', 0) == 1
        findings = []
        if hard:
            findings.append({"status": "violation", "material": "a sanity meter tracks the AI's guilt", "authorized_by": "",
                             "severity": "hard", "note": "A tracked meter no extracted field authorizes."})
        return {
            "clause_findings": [{"clause": "You play as the ship's AI.", "touched": True, "contradiction": False, "quote": "", "severity": "", "note": "stub"}],
            "constraint_findings": [],
            "mechanic_findings": findings,
            "self_report_disagreements": [],
            "verdict": {"value": "hard_issues" if hard else "clean", "summary": "stub"}
        }

    def p_s3_5r(self, p):
        current = self.section(p, 'THE MATERIAL TO REPAIR') or self.premise()
        revised = json.loads(json.dumps(current))
        revised['instance_generator']['true_state'] = "The core cannot support every sector."
        return {"repair_log": [{"finding": "a sanity meter tracks the AI's guilt", "change": "removed the meter from true_state", "disagreement": ""}],
                "revised": revised}

    def spine(self, fixed=False):
        return {
            "invention_ceiling": {"source": "3.5.enrichment_budget", "level": "minimal", "note": "stub"},
            "want_need_tension": {"want": {"pointer": "3.5.protagonist_situation.wants", "restated": "keep the core alive"},
                                  "need": {"description": "own its judgment", "provenance": "invented",
                                           "serves": "3b.secondary_affects: claustrophobic tension" if fixed else "3b.secondary_affects[1] moral complicity"},
                                  "tension": "stub", "enacts_via": "advisory for node content, not branch-defining", "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "irony_mode": {"gap_available": False, "type": "situational", "note": "stub", "device": "stub", "resolution_note": "stub", "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "escalation_shape": {"pattern": "compounding", "mechanism": "stub", "transformation_note": None, "new_variable_required": False,
                                 "state_note": "rides oxygen stock", "provenance": "invented", "serves": "3b.primary_trajectory, 3g.state_richness"},
            "setup_payoff_pairs": [{"setup": "nursery", "payoff": "maintenance", "distance": "two beats", "reinforces": "want_need_tension, irony_mode",
                                    "provenance": "invented", "serves": "3.5.instance_generator.instances: the nursery sector and the maintenance sector"}],
            "motif": None
        }

    def p_s3_75(self, p):
        return self.spine(fixed=False)

    def p_s3_75v(self, p):
        self.spine_verifies += 1
        flagged_rounds = env_int('STUB_SPINE_FLAGGED_ROUNDS', 0)
        material = self.section(p, 'the material to check') or {}
        bad_cite = '[1]' in json.dumps(material)
        flagged = bad_cite and self.spine_verifies <= flagged_rounds
        return {
            "clause_findings": [{"clause": "You play as the ship's AI.", "touched": True, "contradiction": False, "note": "stub"}],
            "mechanic_findings": [
                {"material": "want_need_tension.enacts_via", "authorized_by": "3-0a.primary_decision_axis", "verdict": "authorized", "note": "stub"},
                {"material": "irony_mode", "authorized_by": "3-0b.epistemic_gap", "verdict": "authorized", "note": "gap_available matched present:false"},
                {"material": "escalation_shape", "authorized_by": "3b.primary_trajectory, 3g.state_richness", "verdict": "authorized", "note": "matched escalating"},
                {"material": "setup_payoff_pairs[0]", "authorized_by": "3.5.instance_generator", "verdict": "authorized", "note": "stub"}
            ],
            "self_report_disagreements": ([{"material": "want_need_tension.need.serves", "claimed": "3b.secondary_affects[1] moral complicity",
                                            "found": "index 1 is claustrophobic tension"}] if flagged else []),
            "verdict": {"value": "flagged" if flagged else "clean", "summary": "stub"}
        }

    def p_s3_75r(self, p):
        return {"repair_log": [{"finding": "serves '3b.secondary_affects[1] moral complicity'", "change": "cite by label", "disagreement": ""}],
                "revised": self.spine(fixed=True)}

    # ------------------------------------------------------------------ step 4

    def p_s4a_first(self, p):
        def beat(i, role, loc, chars, ref=None, branch=None, terminal=False, fail=None):
            return {"id": f"B{i:02d}", "role": role, "content_summary": f"stub summary for {role}", "location": loc,
                    "characters": chars, "instance_ref": ref, "is_branch_point": branch is not None, "branch": branch,
                    "is_terminal": terminal, "failure_exit": fail, "craft_note": ""}
        return {
            "framework_choice": {"value": "Save the Cat", "why": "stub", "eligibility_check": "stub"},
            "ending_mechanism": {"type": "forked_paths",
                                 "selector_variables": [{"name": "orientation", "kind": "enum", "values": ["collective", "fittest"], "written_by_role": "first policy vent"},
                                                        {"name": "concealment", "kind": "flag", "values": ["held", "broken"], "written_by_role": "command confrontation"}],
                                 "note": "stub"},
            "instance_reservation_check": "4 instances; 2 before the first branch point; 2 after",
            "main_path_outline": [
                beat(1, "opening image", "the core chamber", []),
                beat(2, "first vent", "the nursery sector", ["the nursery warden"], ref=0),
                beat(3, "policy fork", "the core chamber", ["the maintenance foreman"], ref=1,
                     branch={"variable": "orientation", "outcome_values": ["collective", "fittest"], "path_follows": "collective"},
                     fail={"trigger": "resource_depletion", "cost": "narrative_setback", "description": "reserve dips"}),
                beat(4, "midpoint", "the medical sector", ["the nursery warden"], ref=2),
                beat(5, "command confrontation", "the command sector", ["the commander"], ref=3,
                     branch={"variable": "concealment", "outcome_values": ["held", "broken"], "path_follows": "held"}),
                beat(6, "final image", "the core chamber", [], terminal=True),
            ]
        }

    def p_s4a_next(self, p):
        table = self.section(p, 'branch-point table') or {}
        it = int(re.search(r'iteration (\d+)', p).group(1))
        candidates = table.get('candidates') or []
        if not candidates:
            return {"status": "no_unexplored_branch_points", "selected": None,
                    "framework_decision": {"keep_or_transform": "keep", "eligibility_check": "", "reasoning": "no branch to build"},
                    "instance_reservation_check": "", "new_branch_outline": [], "reconverges_to": None, "notes": ""}
        c = candidates[-1]
        transform = it == env_int('STUB_TRANSFORM_ON', 0)
        reconverge = it == env_int('STUB_RECONVERGE_ON', 0)
        beats = [
            {"id": f"P{it}_B01", "role": "consequence", "content_summary": "stub", "location": "the core chamber",
             "characters": ["the maintenance foreman"], "instance_ref": None, "is_branch_point": False, "branch": None,
             "is_terminal": False, "failure_exit": None, "craft_note": ""},
            {"id": f"P{it}_B02", "role": "ending", "content_summary": "stub", "location": "a new observation blister",
             "characters": ["a new stowaway"], "instance_ref": 3, "is_branch_point": False, "branch": None,
             "is_terminal": not reconverge, "failure_exit": None, "craft_note": ""},
        ]
        return {"status": "branch_selected",
                "selected": {"beat_id": c['beat_id'], "outcome_value": c['outcome_value'], "why_this_one": "stub"},
                "framework_decision": {"keep_or_transform": "transform" if transform else "keep", "eligibility_check": "stub", "reasoning": "stub"},
                "instance_reservation_check": "stub", "new_branch_outline": beats,
                "reconverges_to": "B06" if reconverge else None, "notes": ""}

    def p_s4c5(self, p):
        return {"branch": "stub",
                "want_need_tension": {"status": "unchanged", "content_if_changed": None, "reasoning": "stub"},
                "irony_mode": {"status": "unchanged", "gap_available_rechecked": True, "content_if_changed": None, "reasoning": "stub"},
                "escalation_shape": {"status": "refreshed", "trajectory_rechecked": "escalating",
                                     "content_if_changed": {"pattern": "compounding_refreshed", "mechanism": "stub", "transformation_note": None,
                                                            "new_variable_required": False, "state_note": "stub", "provenance": "invented",
                                                            "serves": "3b.primary_trajectory"},
                                     "reasoning": "stub"},
                "setup_payoff_pairs": {"status": "unchanged", "content_if_changed": None, "reasoning": "stub"},
                "motif": {"status": "still_null", "content_if_changed": None}}

    def p_s4_entity(self, p):
        req = self.section(p, 'the request') or {}
        roster = self.section(p, 'current roster') or {"characters": {}, "locations": {}}
        role = req.get('role', 'thing')
        name = ' '.join(w.capitalize() for w in re.sub(r'^(the|a|an) ', '', role).split())
        if req.get('kind') == 'location':
            if roster['locations'] and 'core' in role and 'Core Chamber' in roster['locations']:
                return {"decision": "reuse", "existing_entity": "Core Chamber", "why_it_fits": "stub"}
            return {"decision": "new_location", "name": name, "static_objects": ["a valve bank", "a viewport"],
                    "exits": [], "room_properties": {"supports_core_action": True}, "capability_check_note": "stub"}
        if 'stowaway' in role:
            return {"decision": "none_needed", "why": "deliver through the environment"}
        return {"decision": "new_character", "name": name, "baseline_topics": ["air", "the core"], "manner": "stub",
                "grounded_in": "instance role", "local_state": [{"key": f"char.{name.lower().replace(' ', '_')}.warned", "type": "bool", "initial": "false", "traces_to": "stub"}]}

    def p_s4_beat(self, p):
        outline = self.section(p, "this beat's outline entry") or {}
        instance = self.section(p, 'the 3.5 instance this beat dramatizes')
        revision = self.section(p, 'REVISION (prior version')
        bid = outline.get('id', 'B00')
        loc = outline.get('resolved_location') or 'Core Chamber'
        chars = outline.get('resolved_characters') or []
        if outline.get('is_branch_point'):
            branch = outline['branch']
            decision = {"action": f"decide {branch['variable']}",
                        "outcomes": [{"choice": v, "writes": [{"variable": branch['variable'], "value": v}], "meaning": "stub"} for v in branch['outcome_values']]}
            fidelity = {"applies": instance is not None, "source_options_listed": [], "outcomes_offered_count": len(branch['outcome_values']), "narrowed_from_source": "none"}
        elif instance:
            opts = [o.strip() for o in re.split(r',| or ', instance.get('what_the_decision_looks_like', '')) if o.strip()]
            decision = {"action": "act on the sector",
                        "outcomes": [{"choice": o, "writes": [{"variable": f"{bid.lower()}.choice", "value": o}], "meaning": "stub"} for o in opts]}
            fidelity = {"applies": True, "source_options_listed": opts, "outcomes_offered_count": len(opts), "narrowed_from_source": "none"}
        else:
            decision = "none"
            fidelity = {"applies": False, "source_options_listed": [], "outcomes_offered_count": 0, "narrowed_from_source": "none"}
        out = {"id": bid, "location": loc, "characters": chars, "instance_fidelity_check": fidelity,
               "scene": f"stub scene for {bid}" + (" (revised)" if revision else ""),
               "available_actions": ["EXAMINE the valve bank"], "decision": decision,
               "state_effects": [], "reads": [{"variable": "orientation", "condition": "any"}] if outline.get('is_terminal') else [],
               "failure_exit_rendering": ({"reached_by": "stub", "cost": outline['failure_exit']['cost'], "rendering": "stub"} if outline.get('failure_exit') else None),
               "shared_terminal_variants": ([{"when": "orientation = collective", "variant": "stub"}] if outline.get('shared_with_paths') else None),
               "design_note": "revised per findings" if revision else ""}
        return out

    def p_s4d(self, p):
        this = self.section(p, 'this iteration') or {}
        table = self.section(p, 'branch-point table') or {}
        it, rnd = this.get('iteration', 1), this.get('review_round', 0)
        flag = rnd == 0 and env_int('STUB_REVIEW_FLAG_FIRST', 0)
        new_beats = this.get('new_beat_ids') or []
        candidates = table.get('candidates') or []
        stop_after = env_int('STUB_STOP_AFTER', 0)
        stop = (not candidates) or (stop_after and it >= stop_after)
        return {
            "consistency": {"verdict": "flagged" if flag else "clean", "instances_by_path": [],
                            "findings": ([{"issue": "stub orphaned instance", "beat_ids": new_beats[-1:], "affected_paths": [f"P{it}"], "fix": "move the decision here"}] if flag else [])},
            "coherence_and_novelty": {"coherence_verdict": "clean", "novelty_verdict": "clean", "existing_ending_devices": [], "this_iteration_device": "stub",
                                      "reskin_check": "stub", "findings": []},
            "pacing_and_arcs": {"verdict": "clean", "note": "stub", "findings": []},
            "state_validity": {"verdict": "clean", "findings": []},
            "termination": {"endings_built": it, "remaining_candidates": [dict(c, agency_gain="stub", thematic_gain="stub", character_gain="stub",
                                                                              cost_and_redundancy="stub", recommendation="build") for c in candidates],
                            "target_range_status": "below floor",
                            "next_candidate": (None if stop else {"beat_id": candidates[-1]['beat_id'], "outcome_value": candidates[-1]['outcome_value']}),
                            "overall_recommendation": "stop here" if stop else "continue looping", "reasoning": "stub"}
        }
