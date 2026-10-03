"""A model-free LlmClient for exercising the pipeline's plumbing.

It recognizes each prompt by a distinctive phrase and returns a
schema-valid canned answer built from the JSON sections of the prompt it
was given, so `main.py` and `outline.py` can be run end to end (every
step, every file, every loop) in seconds with no Ollama server. It proves
that placeholders are filled, outputs parse, validators accept the
documented shapes, the premise repair loop fires and terminates, rejected
answers are re-asked with the complaint, the circuit-breaker fallback
runs, and the outline loop's bookkeeping (lines, nodes, registers, graph
checks) holds together. It proves nothing about story quality.

Use it with STRATUM_CLIENT=stub (main.py selects it; no dynamic_config.py
is needed):

    STRATUM_CLIENT=stub python main.py --story-id=stubtest < ../tests/kernels/kernel1.txt

tests/test_plumbing.py runs every scenario below and asserts the graph
invariants.

Scenario knobs (environment variables):

    STUB_PREMISE_HARD_ROUNDS=1   3.5b invents a score the engine lacks and
                                 3.5v reports it this many times (tests 3.5r)
    STUB_PREMISE_ALWAYS_HARD=1   3.5v never comes back clean (tests the halt)
    STUB_REPAIR_BREAKS=1         3.5r's first answer also rewrites a turn as a
                                 menu pick under an unknown form (tests the
                                 repair validator); =2 its retry does too
                                 (tests that the run goes on to the audit)
    STUB_GAP=1                   the brief has an epistemic gap and the engine
                                 states a hidden truth; =2 the engine omits it
                                 (a computed finding the repair must fill)
    STUB_BAD_CAST=1              3.5c's first answer leaves a crowd without a
                                 representative (tests the informed retry)
    STUB_BAD_PLAN=1              4a's first answer leaves a turn unplaced
                                 (tests the informed retry)
    STUB_SLOPPY=1                answers use beat names for ids, numbers as
                                 strings, labels without their articles
                                 (tests normalization)
    STUB_ABORT=s4a               that step's thinking call reports a tripped
                                 circuit breaker whose forced answer also
                                 failed (tests the no-think fallback); with
                                 STUB_ABORT_ALWAYS=1 its no-think call does
                                 too (tests the stop)
    STUB_LOOP=s4a                that step's first thinking call reports looping
                                 reasoning (tests the re-run from a new seed);
                                 with STUB_LOOP_ALWAYS=1 every thinking call
                                 of that step loops (tests the fallback after)
    STUB_SPINE_FLAGGED_ROUNDS=1  with --craft-spine, 3.75's first build cites by
                                 list index (a computed finding -> 3.75r)
    STUB_FORCE=s4a               that step's thinking call passes its thinking
                                 limit and the client forces the answer
                                 (only when the call allows force_answer)
    STUB_NEW_CAST_ON=2           the line built on this iteration registers a
                                 new character, a new crowd and a new place
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

RETRY_MARKER = '--- YOUR PREVIOUS ANSWER WAS REJECTED ---'


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class StubClient(LlmClient):

    def __init__(self):
        self.calls = []
        self.premise_verifies = 0
        self.repair_breaks = 0
        self.last_call = {}

    def run_prompt(self, prompt, **kwargs):
        kind = self.classify(prompt)
        self.calls.append(kind)
        no_think = kwargs.get('think') is False
        if os.environ.get('STUB_ABORT') == kind and (not no_think or env_int('STUB_ABORT_ALWAYS', 0)):
            thinking = 'stub runaway reasoning. ' * 40
            self.last_call = {'aborted': 'thinking_bytes', 'done_reason': None, 'format_sent': False}
            print(f'[stub {kind}] (circuit breaker)')
            return (thinking, '')
        seeded = 'seed' in (kwargs.get('options') or {})
        if (os.environ.get('STUB_LOOP') == kind and not no_think and (kwargs.get('limits') or {}).get('detect_loops')
                and (not seeded or env_int('STUB_LOOP_ALWAYS', 0))):
            self.last_call = {'aborted': 'loop', 'loop_line': 'Wait, let me re-check the turns.',
                              'done_reason': None, 'format_sent': False}
            print(f'[stub {kind}] (loop)')
            return ('Wait, let me re-check the turns.\n' * 5, '')
        handler = getattr(self, f'p_{kind}')
        answer = handler(prompt)
        text = answer if isinstance(answer, str) else json.dumps(answer, indent=2)
        self.last_call = {'aborted': None, 'done_reason': 'stop', 'format_sent': bool(kwargs.get('format')) and no_think,
                          'prompt_tokens': len(prompt) // 4, 'output_tokens': len(text) // 4}
        if (os.environ.get('STUB_FORCE') == kind and not no_think
                and (kwargs.get('limits') or {}).get('force_answer')):
            self.last_call.update({'forced_answer': True, 'thinking_at_force': 25000})
            print(f'[stub {kind}] (forced answer)')
            return ('stub reasoning that ran past its budget. ' * 40, text)
        print(f'[stub {kind}]' + (' (no think)' if no_think else ''))
        return ('' if no_think else f'stub reasoning for {kind}', text)

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
            ('You are a premise builder', 's3_5a'),
            ('You are the turn builder', 's3_5b'),
            ('You are the cast-sketch step', 's3_5c'),
            ('You are a fidelity auditor', 's3_5v'),
            ('You are the repair step for the premise', 's3_5r'),
            ('craft-spine construction step', 's3_75'),
            ('repair step for the craft spine', 's3_75r'),
            ('You are the story-form step', 's3_8'),
            ('You are step 4a', 's4a'),
            ('You are step 4b', 's4b'),
            ('You are step 4c', 's4c'),
            ('You are step 4d', 's4d'),
        ]
        for phrase, kind in checks:
            if phrase in head or phrase in flat:
                return kind
        raise ValueError('stub client does not recognize this prompt: ' + head[:200])

    @staticmethod
    def body(prompt):
        """The prompt without the retry block main.py appends."""
        i = prompt.find(RETRY_MARKER)
        return prompt if i == -1 else prompt[:i]

    @classmethod
    def section(cls, prompt, marker):
        """The JSON block that follows the LAST line containing `marker`
        (inputs come after the examples in every prompt)."""
        prompt = cls.body(prompt)
        i = prompt.rfind(marker)
        if i == -1:
            return None
        j = prompt.find('\n', i)
        rest = prompt[j + 1:]
        m = re.search(r'[\[{]', rest)
        if not m or rest[:m.start()].strip():
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

    @classmethod
    def text_after(cls, prompt, marker):
        prompt = cls.body(prompt)
        i = prompt.rfind(marker)
        if i == -1:
            return ''
        return prompt[i + len(marker):].strip()

    @classmethod
    def listed(cls, prompt, header, pattern=r'^\s*([A-Za-z]?\d+)\.\s'):
        """Ids of the numbered lines under the last `header` line, up to the
        next '---' header."""
        prompt = cls.body(prompt)
        i = prompt.rfind(header)
        if i == -1:
            return []
        block = prompt[prompt.find('\n', i) + 1:]
        end = block.find('\n---')
        if end != -1:
            block = block[:end]
        return [m.group(1) for m in (re.match(pattern, line) for line in block.split('\n')) if m]

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
        numbers = re.search(r'(\d+ or \d+|a dozen|\d+) (wildly different )?endings', kernel.lower())
        return {
            'reading': 'stub: ' + ('; '.join(removed) or 'no shape clauses'),
            'content_kernel': content.strip() or kernel,
            'shape': {
                'endings': {'tier': 'several' if 'ending' in kernel.lower() else 'unstated',
                            'stated': numbers.group(1) if numbers else ''},
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
            "epistemic_gap": ({"present": True, "gap_description": "what the council is hiding about the air", "design_status": "incidental", "evidence_basis": "explicit"}
                              if env_int('STUB_GAP', 0) else
                              {"present": False, "gap_description": "", "design_status": "not_applicable", "evidence_basis": "strong_inference"}),
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

    # ------------------------------------------------------------------ 3.5

    VIOLATION = "a crew-trust score that rises with each favor and gates the manual override"
    FIXED = "The council's warden quietly reroutes air to her own sector."

    def p_s3_5a(self, p):
        return {
            "protagonist": {"who": "You are the ship's AI, present through cameras and drones.", "wants": "keep the core alive and the sectors breathing",
                            "can_do": "watch every sector, route air, open valves that have a drone at them",
                            "cannot_do": "vent a sector without the sector council's override code, or move a person",
                            "serves": "3-0b.protagonist_identity"},
            "arena": {"description": "One generational ship, core amidships, four sectors around it.", "serves": "3f.setting_structure"},
            "pressure": {"description": "The core's margin falls each hour; every sector still breathing costs it.",
                         "clock_or_stock": "core margin (stock), licensed by 3-0c resource_depletion", "serves": "3-0c.failure_triggers"},
            "opposition": {"who_or_what": "the sector council", "wants": "no sector vented, whatever the core costs",
                           "means": "it holds the override codes and can lock the AI out of the valves", "serves": "3c.core_thematic_axis"},
            "mediation": {
                "question": "Is the ship its people or its core?",
                "to_reach_pole_a": {"pole": "fittest: vent", "what_you_must_do": "obtain a council override or a foreman's manual valve", "cost": "the council learns what you asked for"},
                "to_reach_pole_b": {"pole": "collective: spare", "what_you_must_do": "find and reroute air the sectors are hiding", "cost": "the core margin falls faster"},
                "levers": ["the council override codes", "the hydroponics scrubber feed", "the warden's private reroute"],
                "serves": "3-0a.primary_decision_axis"},
            # STUB_GAP=1: the brief has an epistemic gap; =2 the engine forgets to state it (a computed finding)
            "hidden_truth": self.HIDDEN if env_int('STUB_GAP', 0) == 1 else None,
        }

    def p_s3_5b(self, p):
        hard = env_int('STUB_PREMISE_HARD_ROUNDS', 0) > 0
        return {
            "turns": [
                {"id": 1, "situation": "The nursery's air is short and the council will not say why.", "what_you_must_do": "find where the air is going",
                 "ways_through": [{"way": "a drone traces the ducts", "cost": "the drone is lost to the cold"}, {"way": "the warden tells you", "cost": "she learns you suspect her"}],
                 "involves": ["the nursery warden", "the nursery families"], "form": "discover", "serves": "3-0a.primary_decision_axis"},
                {"id": 2, "situation": "Hydroponics can feed the medical bay or itself, not both.", "what_you_must_do": "get the foreman to open the feed",
                 "ways_through": [{"way": "he opens it on your promise that his sector is never vented", "cost": "a promise you may break"}, {"way": "he opens it after seeing the medical bay", "cost": "hours of margin"}],
                 "involves": ["the hydroponics foreman"], "form": "persuade", "serves": "3c.core_thematic_axis"},
                {"id": 3, "situation": "The council offers the override for one sector of your choosing.", "what_you_must_do": "decide whom to tell",
                 "ways_through": [{"way": "the sector hears first", "cost": "they barricade the valve"}, {"way": "nobody is told", "cost": "you become the council's instrument"}],
                 "involves": ["the council speaker", "the nursery warden"], "form": "conceal_or_reveal", "serves": "3c.core_thematic_axis"},
            ],
            "complications": [{"description": self.VIOLATION if hard else self.FIXED, "serves": "3c.core_thematic_axis"}],
        }

    def p_s3_5c(self, p):
        listed = self.text_after(p, 'ROLES THE TURNS NAME (one seed each, role copied exactly)').split('\n- the Kernel')[0]
        roles = [m.group(1).strip() for m in re.finditer(r'^\s*- (.+)$', listed, re.M)]
        bad = env_int('STUB_BAD_CAST', 0) and RETRY_MARKER not in p
        known = {
            "the nursery warden": ("individual", None if bad else "the nursery families", "her sector spared", "a private reroute", False),
            "the nursery families": ("crowd", None, "air", "the ship's sympathy", False),
            "the hydroponics foreman": ("individual", None, "his scrubbers running", "the manual feed valve", False),
            "the council speaker": ("individual", "the sector council", "the AI dependent on the council", "the override codes", True),
        }
        seeds = []
        for r in roles:
            kind, speaks, wants, holds, opp = known.get(r, ("individual", None, "stub want", "stub holding", False))
            seeds.append({"role": r, "kind": kind, "speaks_for": speaks, "wants": wants, "holds": holds,
                          "edge": None if kind == "crowd" else f"stub edge of {r}", "tie": f"stub tie of {r}", "opposition": opp})
        return {"notes": "stub", "cast_seeds": seeds}

    def p_s3_5v(self, p):
        self.premise_verifies += 1
        clauses = self.listed(p, '--- LIST 1: KERNEL CLAUSES ---')
        constraints = self.listed(p, '--- LIST 2: CONSTRAINTS ---')
        engine = self.listed(p, '--- LIST 3: ENGINE CHECKS ---')
        material = self.section(p, '--- THE PREMISE TO AUDIT ---') or {}
        has_meter = 'crew-trust score' in json.dumps(material)
        always = env_int('STUB_PREMISE_ALWAYS_HARD', 0) == 1
        hard = has_meter and self.premise_verifies <= env_int('STUB_PREMISE_HARD_ROUNDS', 0)
        return {
            "clauses": [{"n": int(n), "note": "stub: nothing incompatible", "contradiction": False, "quote": ""} for n in clauses],
            "constraints": [{"n": int(n), "note": "stub: nothing incompatible", "violated": False, "quote": ""} for n in constraints],
            "engine": [{"id": e, "note": "stub", "holds": not (always and e == 'E1'), "quote": "stub quote" if (always and e == 'E1') else ""}
                       for e in engine],
            "mechanics": ([{"material": self.VIOLATION, "note": "A reputation score the player watches; the engine has no such system."}]
                          if hard else []),
        }

    HIDDEN = {"truth": "the council speaker has been venting the nursery's reserve into her own sector for a month",
              "who_knows": "the nursery warden", "what_it_changes": "the council stops being the side that spares people",
              "serves": "3-0b.epistemic_gap"}

    def p_s3_5r(self, p):
        revised = {"complications": [{"description": self.FIXED, "serves": "3c.core_thematic_axis"}]}
        breaks = env_int('STUB_REPAIR_BREAKS', 0)
        if self.repair_breaks < breaks:
            self.repair_breaks += 1
            turns = self.p_s3_5b(p)['turns']
            turns[2] = dict(turns[2], form='choose',
                            ways_through=[{"way": "you choose to tell the sector first", "cost": "they barricade the valve"},
                                          {"way": "nobody is told", "cost": "you become the council's instrument"}])
            revised['turns'] = turns
        elif 'written as a pick' in p.split(RETRY_MARKER)[0]:
            revised['turns'] = self.p_s3_5b(p)['turns']     # the finding list names the broken turn: restore it
        if 'states no hidden truth' in p.split(RETRY_MARKER)[0]:
            revised['hidden_truth'] = self.HIDDEN
        return {"repair_log": [{"finding": self.VIOLATION, "change": "replaced the score with a rerouting complication", "disagreement": ""}],
                "revised": revised}

    # ------------------------------------------------------------------ 3.8

    # ------------------------------------------------------------------ 3.75 (opt-in)

    def spine(self, fixed=False):
        return {
            "invention_ceiling": {"source": "3.5.enrichment_budget", "level": "minimal", "note": "stub"},
            "want_need_tension": {"want": {"pointer": "3.5.protagonist.wants", "restated": "keep the core alive"},
                                  "need": {"description": "to be answerable to someone", "provenance": "invented",
                                           "serves": "3b.secondary_affects: claustrophobic tension" if fixed else "3b.secondary_affects[1] moral complicity"},
                                  "tension": "stub", "enacts_via": "colors how each turn is approached", "provenance": "invented",
                                  "serves": "3c.core_thematic_axis"},
            "irony_mode": {"gap_available": False, "type": "situational", "note": "3-0b.epistemic_gap.present is false",
                           "device": "stub", "resolution_note": "stub", "provenance": "invented", "serves": "3c.core_thematic_axis"},
            "escalation_shape": {"pattern": "compounding", "mechanism": "stub", "transformation_note": None,
                                 "new_variable_required": False, "state_note": "rides the core margin stock",
                                 "provenance": "invented", "serves": "3b.primary_trajectory"},
            "setup_payoff_pairs": [{"setup": "turn 1: the warden's private reroute", "payoff": "turn 3: the council's offer",
                                    "distance": "two turns", "reinforces": "want_need_tension", "provenance": "invented",
                                    "serves": "3.5.turns: 1 and 3"}],
            "motif": None,
        }

    def p_s3_75(self, p):
        return self.spine(fixed=env_int('STUB_SPINE_FLAGGED_ROUNDS', 0) == 0)

    def p_s3_75r(self, p):
        return {"repair_log": [{"finding": "cites by index", "change": "cite by label", "disagreement": ""}],
                "revised": self.spine(fixed=True)}

    def p_s3_8(self, p):
        candidates = self.section(p, '- CANDIDATES (choose one)') or []
        ids = [c['id'] for c in candidates]
        pick = 'fichtean_curve' if 'fichtean_curve' in ids else ids[0]
        return {"reading": "stub: the story climbs through crises to one answer", "framework": pick,
                "why": "stub (3b.primary_trajectory)", "modifier": "none", "modifier_why": ""}

    # ------------------------------------------------------------------ step 4

    def p_s4a(self, p):
        fw = self.section(p, '- the framework and its beats') or {}
        premise = self.section(p, '- the engine: protagonist') or {}
        beats = fw.get('beats') or []
        turns = [t['id'] for t in premise.get('turns') or []]
        sloppy = env_int('STUB_SLOPPY', 0)
        if env_int('STUB_BAD_PLAN', 0) and RETRY_MARKER not in p:
            turns = turns[:-1]
        entries = []
        middle = beats[1:-1] if len(beats) > 2 else beats
        queue = list(turns)
        for i, b in enumerate(beats):
            turn = None
            if b in middle and queue:
                turn = queue.pop(0)
            entries.append({"beat": b['id'], "turn": turn, "way": 1 if turn is not None else None,
                            "adapted": f"stub: {b['id']} in this story" + (f", playing turn {turn}" if turn is not None else '')})
            if b is middle[-1]:
                while queue:      # more turns than middle beats: double up on the last one
                    turn = queue.pop(0)
                    entries.append({"beat": b['id'], "turn": turn, "way": 1, "adapted": f"stub: {b['id']} again, playing turn {turn}"})
        if sloppy and entries:
            name = {'opening_crisis': 'Opening crisis', 'setup': 'Setup'}.get(entries[0]['beat'])
            if name:
                entries[0]['beat'] = name
            for e in entries:
                if e['turn'] is not None:
                    e['turn'] = str(e['turn'])
                else:
                    e['way'] = 'null'
        return {"through_line": {"title": "the keeper", "motivation": "keep everyone breathing, then keep the core",
                                 "strategy": "reroute rather than vent", "turning_point": "the council's offer"},
                "ending": {"title": "the strained collective", "summary": "everyone breathes, barely"},
                "beats": entries, "skipped_beats": []}

    PLACES = [("the core status bay", "a control space", "where the margin is read"),
              ("the nursery deck", "an inhabited deck", "the warden's sector"),
              ("the scrubber bay", "a work deck", "where the feed valve is"),
              ("the council chamber", "a chamber", "where the override codes are kept")]

    def p_s4b(self, p):
        packet = self.section(p, '- the line, what has already been told, and the nodes to fill') or {}
        register = self.section(p, '- the registers so far') or {}
        line_id = (packet.get('line') or {}).get('id', 'T1')
        it = int(re.sub(r'\D', '', line_id) or 1)
        sloppy = env_int('STUB_SLOPPY', 0)
        labels = [c['label'] for c in register.get('characters') or [] if c.get('kind') != 'crowd']
        known_places = {l['name'] for l in register.get('locations') or []}
        nodes, new_locations, new_characters = [], [], []
        declared = set()
        extra = env_int('STUB_NEW_CAST_ON', 0) == it
        for i, n in enumerate(packet.get('nodes_to_fill') or []):
            place = self.PLACES[(i + it) % len(self.PLACES)]
            if place[0] not in known_places and place[0] not in declared:
                new_locations.append({"name": place[0], "kind": place[1], "why": place[2]})
                declared.add(place[0])
            who = list((n.get('turn') or {}).get('involves') or [])
            if not who and labels:
                who = [labels[(i + it) % len(labels)]]
            if sloppy:
                who = [re.sub(r'^the ', '', w) for w in who]
            nodes.append({"id": n['id'], "title": f"stub {n['id']}", "summary": f"stub summary: {n.get('plan', '')}",
                          "where": [place[0].upper() if sloppy else place[0]], "who": who})
        if extra and nodes:
            new_characters = [
                {"label": "the drone technician", "kind": "individual", "speaks_for": "the dock crew", "wants": "her drones back", "holds": "the drone cradles", "why": "stub: someone has to launch the drone"},
                {"label": "the dock crew", "kind": "crowd", "speaks_for": None, "wants": "overtime", "holds": "the dock", "why": "stub"},
            ]
            new_locations.append({"name": "the drone dock", "kind": "a work deck", "why": "where drones are launched"})
            nodes[0]['where'] = ["the drone dock"]
            nodes[0]['who'] = ["the dock crew"]     # a crowd alone: the driver adds its voice
        return {"nodes": nodes, "new_locations": new_locations, "new_characters": new_characters}

    def p_s4d(self, p):
        counts = self.section(p, '- counts and where a line may leave') or {}
        hooks = (self.section(p, '- ways through a turn that no line has taken') or {}).get('unused_ways') or []
        built = counts.get('lines_built', 1)
        target = counts.get('lines_the_kernel_suggests', 3)
        valid = counts.get('valid_divergence_nodes') or []
        stop_after = env_int('STUB_STOP_AFTER', 0)
        stop = (stop_after and built >= stop_after) or (not stop_after and built >= target) or not valid
        if stop:
            return {"assessment": "stub: every remaining candidate is a reskin", "recommendation": "stop", "seed": None}
        usable = [h for h in hooks if h['node'] in valid]
        at = usable[(built - 1) % len(usable)]['node'] if usable else valid[min(built, len(valid) - 1)]
        return {"assessment": "stub: one answer to the question is still unbuilt", "recommendation": "continue",
                "seed": {"motivation": f"stub motivation {built + 1}", "strategy": f"stub strategy {built + 1}",
                         "diverges_at": at, "trigger": "you told the sector first", "why_different": "stub: a different price"}}

    def p_s4c(self, p):
        digest = self.section(p, '- the story so far (one entry per node)') or {}
        fw = self.section(p, '- the framework and its beats') or {}
        premise = self.section(p, '- the engine: protagonist') or {}
        seed = self.section(p, '- THE SEED for this line') or {}
        hooks = (self.section(p, '- ways through a turn that no line has taken') or {}).get('unused_ways') or []
        it = int(re.search(r'This is iteration (\d+)', p).group(1))
        linear = 'LINEAR SHAPE' in self.body(p)
        if env_int('STUB_NOTHING_ON', 0) == it:
            return {"status": "nothing_worth_building", "why": "stub: the seed is a reskin", "through_line": None,
                    "divergence": None, "ending": None, "beats": [], "skipped_beats": [], "rejoins_at": None}
        beat_ids = [b['id'] for b in fw.get('beats') or []]
        required = [b['id'] for b in fw.get('beats') or [] if b.get('required', True)]
        nodes = {n['id']: n for n in digest.get('nodes') or []}
        lines = digest.get('lines') or []
        at = seed.get('diverges_at')
        parent = next(l for l in lines if at in l['path'])
        prefix = parent['path'][:parent['path'].index(at) + 1]
        taken = [nodes[x]['turn'] for x in prefix if nodes[x].get('turn') is not None]
        remaining = [t['id'] for t in premise.get('turns') or [] if t['id'] not in taken and (not taken or t['id'] > max(taken))]
        at_index = beat_ids.index(nodes[at]['beat'])
        later = beat_ids[at_index + 1:] or beat_ids[-1:]
        rejoin = None
        if linear:
            new_beats = [beat_ids[-1]]
        elif env_int('STUB_REJOIN_ON', 0) == it:
            new_beats = later[:1]
            rejoin = lines[0]['path'][-1]
            if rejoin in prefix or beat_ids.index(nodes[rejoin]['beat']) < beat_ids.index(new_beats[-1]):
                rejoin = None
        else:
            new_beats = later
        entries = []
        for b in new_beats:
            turn = remaining.pop(0) if remaining and (b != beat_ids[-1] or len(new_beats) == 1) and not linear else None
            entries.append({"beat": b, "turn": turn, "way": (2 if turn is not None else None),
                            "adapted": f"stub: {b} on line T{it}" + (f", playing turn {turn}" if turn is not None else '')})
        covered = {nodes[x]['beat'] for x in prefix} | {e['beat'] for e in entries}
        if rejoin:
            covered.add(nodes[rejoin]['beat'])
        skipped = [{"beat": b, "reason": "stub: the line does not pass through it"} for b in required if b not in covered]
        hook = next((h for h in hooks if h['node'] == at), None)
        return {
            "status": "proposed", "why": "stub: the seed holds",
            "through_line": {"title": f"line {it}", "motivation": seed.get('motivation', 'stub'), "strategy": seed.get('strategy', 'stub'),
                             "turning_point": "stub", "differs_from": "stub: a different answer at a different price"},
            "divergence": {"diverges_at": at, "trigger": seed.get('trigger', 'you told the sector first'),
                           "trigger_kind": "accumulated" if linear else "act",
                           "way": hook['way'] if hook else None,
                           "instead_of": "you told no one",
                           "opportunity": None if hook else "the speaker makes a private offer",
                           "shift": "stub: what you learn there changes what you want"},
            "ending": {"title": f"stub ending {it}", "summary": f"stub: line {it} ends differently"},
            "beats": entries, "skipped_beats": skipped, "rejoins_at": rejoin,
        }
