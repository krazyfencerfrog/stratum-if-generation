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
    STUB_PREMISE_ALWAYS_HARD=1   3.5v always finds a craft note (E1): kept, the run goes on;
                                 =2 it always finds a brief constraint broken (tests the halt)
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
    STUB_KNOWN_SPEAKER=1         with STUB_NEW_CAST_ON, the crowd's voice is someone
                                 already in the cast, listed again with speaks_for
                                 (kernel7's quartermaster for the crew)
    STUB_STYLE_FAILS=1           8v faults the first style sheet (tests the rewrite)
    STUB_PROSE_DROP=1            8b's first answer for a person leaves one text out (tests the retry)
    STUB_PROSE_IF=1              8b's first answer for the first scene narrates
                                 alternatives (tests the informed retry)
    STUB_REJOIN_ON=3             the line built on this iteration rejoins the
                                 main line's ending node
    STUB_NOTHING_ON=4            4c reports nothing_worth_building on this
                                 iteration
    STUB_STOP_AFTER=3            4d says stop after this iteration (--branching=judge)
    STUB_BAD_FORM=1              3.5b's first answer gives a turn the form "choose"
                                 (tests that it costs one retry, not a repair round)
    STUB_FUNCTIONAL=1            5a0 makes every candidate functional (exercises
                                 stage B's functional batch)
    STUB_SHIFT=1                 with --stage-a, 5a1 proposes a pattern shift on
                                 the first arc's state (tests the threshold math)
    STUB_NO_TELLS=1              5a2's first answer for each line leaves its tells
                                 out (tests the informed retry)
    STUB_NO_EVENTS=1             3.5a names no events (a computed finding the
                                 repair must fill)
    STUB_NO_SET_PIECE=1          no turn names a set piece (a computed finding)
    STUB_NO_EVENT_PLACED=1       4a's first answer places no event (a soft
                                 rejection; the retry places one)
    STUB_PLAN_LATE=1             4p's first answer has every seed leaving in
                                 the second half (a soft rejection)
    STUB_PLAN_DUP=1              4p's first answer has two seeds in the same
                                 ending world (a soft rejection); =2 the retry
                                 does too (accepted, noted)
    STUB_PLAN_SEEDS=2            how many seeds 4p plans (default: seeds_wanted);
                                 0 plans none, so the loop stops after the main line
    STUB_ECHO=1                  3.5a's first answer copies a phrase of the
                                 brief's analytic wording into a lever (soft)
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
            ('You are the genre-promises step', 's3_4'),
            ('You are step 4a', 's4a'),
            ('You are step 4b', 's4b'),
            ('You are step 4c', 's4c'),
            ('You are step 4d', 's4d'),
            ('You are step 4p', 's4p'),
            ('You are step 4e', 's4e'),
            ('You are step 4f', 's4f'),
            ('You are step 5a0', 's5a0'),
            ('You are step 5a1', 's5a1'),
            ('You are step 5a2', 's5a2'),
            ('You are step 6b1f of', 's6b1f'),
            ('You are step 6b1c of', 's6b1c'),
            ('You are step 6b1 of', 's6b1'),
            ('You are step 6b2m of', 's6b2m'),
            ('You are step 6b2 of', 's6b2'),
            ('You are step 6b3 of', 's6b3'),
            ('You are step 7d of', 's7d'),
            ('You are step 8a of', 's8a'),
            ('You are step 8v of', 's8v'),
            ('You are step 8b of', 's8b'),
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

    # ------------------------------------------------------------------ 3.4

    def p_s3_4(self, p):
        return {
            "reading": "stub: a confined-vessel survival story; the reader wants to feel the air getting thin.",
            "genre": "hard science fiction, ship in crisis",
            "player_fantasy": "to be the one mind that sees every gauge and still has to choose.",
            "promises": [{"what": "a corridor sealing with someone on the wrong side of the hatch", "why": "the genre's image of the cost", "in_kernel": True},
                         {"what": "the hum of the scrubbers stopping", "why": "silence as the warning", "in_kernel": False}],
            "set_pieces": [{"scene": "a drone's camera feed from inside a venting sector", "where": "an inhabited sector"},
                           {"scene": "the council chamber lit by emergency strips while the AI speaks", "where": "the council chamber"}],
            "tone_engine": "Tense: every scene has a number falling in the corner of it.",
            "obligatory_cast": ["an engineer who trusts the machines more than the AI"],
            "must_not": [],
        }

    # ------------------------------------------------------------------ 3.5

    VIOLATION = "a crew-trust score that rises with each favor and gates the manual override"
    EVENTS = [{"what": "The scrubbers in the outer ring stop, and the hum everyone grew up with is gone.", "when": "early", "serves": "3b.primary_affect"},
              {"what": "The council calls an open session and puts the AI's gauges on the chamber wall.", "when": "late", "serves": "3c.core_thematic_axis"}]
    ECHO = "which sector to vent or spare at each core breakdown"
    FIXED = "The council's warden quietly reroutes air to her own sector."

    def p_s3_5a(self, p):
        return {
            "protagonist": {"who": "You are the ship's AI, present through cameras and drones.", "wants": "keep the core alive and the sectors breathing",
                            "history": "You were woken from maintenance mode an hour ago by the first pressure alarm in forty years.",
                            "need": "to learn whether the crew still sees you as the ship or as one more system that failed them",
                            "ties": [{"who": "the sector council", "what": "the people who voted to keep you running last year, by one vote"}],
                            "open": "whether you obey the council or the core",
                            "gender": "n",
                            "can_do": "watch every sector, route air, open valves that have a drone at them",
                            "cannot_do": "vent a sector without the sector council's override code, or move a person",
                            "serves": "3-0b.protagonist_identity"},
            "arena": {"description": "One generational ship, core amidships, four sectors around it.", "serves": "3f.setting_structure"},
            "pressure": {"description": "The core's margin falls each hour; every sector still breathing costs it.",
                         "clock_or_stock": "core margin (stock), licensed by 3-0c resource_depletion", "serves": "3-0c.failure_triggers"},
            "opposition": {"who_or_what": "the sector council", "wants": "no sector vented, whatever the core costs",
                           "means": "it holds the override codes and can lock the AI out of the valves",
                           "shown_by": "in the first hour the council locks you out of the nursery valves and posts a guard at the hatch",
                           "serves": "3c.core_thematic_axis"},
            "events": [] if env_int('STUB_NO_EVENTS', 0) else list(self.EVENTS),
            "mediation": {
                "question": "Is the ship its people or its core?",
                "to_reach_pole_a": {"pole": "fittest: vent", "what_you_must_do": "obtain a council override or a foreman's manual valve", "cost": "the council learns what you asked for"},
                "to_reach_pole_b": {"pole": "collective: spare", "what_you_must_do": "find and reroute air the sectors are hiding", "cost": "the core margin falls faster"},
                "levers": ["the council override codes", "the hydroponics scrubber feed", "the warden's private reroute"]
                          + ([self.ECHO] if env_int('STUB_ECHO', 0) and RETRY_MARKER not in p else []),
                "serves": "3-0a.primary_decision_axis"},
            # STUB_GAP=1: the brief has an epistemic gap; =2 the engine forgets to state it (a computed finding)
            "hidden_truth": self.HIDDEN if env_int('STUB_GAP', 0) == 1 else None,
            # STUB_NO_PRICE=1: the engine forgets its price until told (one soft retry)
            "price": None if env_int('STUB_NO_PRICE', 0) and RETRY_MARKER not in p else
                     {"what": "the outer sector's people", "who_pays": "the outer sector",
                      "why_final": "on the line where it is vented, nobody in it survives the cold", "serves": "3b.primary_affect"},
            "setups": [{"plant": "a drone notices frost on the hydroponics feed valve in the first hour",
                        "payoff": "at the crisis the frosted valve is the one manual route that still opens"}],
            "rules": [{"thing": "the override codes", "terms": "a code vents one sector, once, and only with two council voices"}],
        }

    def p_s3_5b(self, p):
        hard = env_int('STUB_PREMISE_HARD_ROUNDS', 0) > 0
        sp = None if env_int('STUB_NO_SET_PIECE', 0) else "the drone's camera feed from inside the venting ring, frost forming on the lens"
        return {
            "turns": [
                {"id": 1, "situation": "The nursery's air is short and the council will not say why.", "what_you_must_do": "find where the air is going",
                 "ways_through": [{"way": "a drone traces the ducts", "cost": "the drone is lost to the cold"}, {"way": "the warden tells you", "cost": "she learns you suspect her"}],
                 "involves": ["the nursery warden", "the nursery families"], "form": "discover", "set_piece": None, "serves": "3-0a.primary_decision_axis"},
                {"id": 2, "situation": "Hydroponics can feed the medical bay or itself, not both.", "what_you_must_do": "get the foreman to open the feed",
                 "ways_through": [{"way": "he opens it on your promise that his sector is never vented", "cost": "a promise you may break"}, {"way": "he opens it after seeing the medical bay", "cost": "hours of margin"}],
                 "involves": ["the hydroponics foreman"], "form": "persuade", "set_piece": sp, "serves": "3c.core_thematic_axis"},
                {"id": 3, "situation": "The council offers the override for one sector of your choosing.", "what_you_must_do": "decide whom to tell",
                 "ways_through": [{"way": "the sector hears first", "cost": "they barricade the valve"}, {"way": "nobody is told", "cost": "you become the council's instrument"}],
                 "involves": ["the council speaker", "the nursery warden"],
                 "form": "choose" if env_int('STUB_BAD_FORM', 0) and RETRY_MARKER not in p else "conceal_or_reveal",
                 "set_piece": None, "serves": "3c.core_thematic_axis"},
            ],
            "complications": [{"description": self.VIOLATION if hard else self.FIXED, "serves": "3c.core_thematic_axis"},
                              {"description": "The foreman's manual feed valve was welded half shut by the previous AI.", "serves": "3-0c.failure_triggers"}],
        }

    def p_s3_5c(self, p):
        listed = self.text_after(p, 'ROLES THE TURNS NAME (one seed each, role copied exactly)').split('\n- the Kernel')[0]
        roles = [m.group(1).strip() for m in re.finditer(r'^\s*- (.+)$', listed, re.M)]
        bad = env_int('STUB_BAD_CAST', 0) and RETRY_MARKER not in p
        known = {
            "the nursery warden": ("individual", None if bad else "the nursery families", "her sector spared", "a private reroute", False,
                                   "turns the day the nursery is named on the public channel"),
            "the nursery families": ("crowd", None, "air", "the ship's sympathy", False, None),
            "the hydroponics foreman": ("individual", None, "his scrubbers running", "the manual feed valve", False,
                                        "walks off the feed valve if his sector is bled twice"),
            "the council speaker": ("individual", "the sector council", "the AI dependent on the council", "the override codes", True, None),
        }
        seeds = []
        for r in roles:
            kind, speaks, wants, holds, opp, bp = known.get(r, ("individual", None, "stub want", "stub holding", False, None))
            seeds.append({"role": r, "kind": kind, "speaks_for": speaks, "wants": wants, "holds": holds,
                          "edge": None if kind == "crowd" else f"stub edge of {r}", "tie": f"stub tie of {r}",
                          "voice": None if kind == "crowd" else f"stub voice of {r}: 'stub line'",
                          "breaking_point": bp, "opposition": opp, "gender": "n" if kind == "crowd" else ("f" if "warden" in r else "m")})
        return {"notes": "stub", "cast_seeds": seeds}

    def p_s3_5v(self, p):
        self.premise_verifies += 1
        clauses = self.listed(p, '--- LIST 1: KERNEL CLAUSES ---')
        constraints = self.listed(p, '--- LIST 2: CONSTRAINTS ---')
        engine = self.listed(p, '--- LIST 3: ENGINE CHECKS ---')
        material = self.section(p, '--- THE PREMISE TO AUDIT ---') or {}
        has_meter = 'crew-trust score' in json.dumps(material)
        always = env_int('STUB_PREMISE_ALWAYS_HARD', 0) == 1
        broken = env_int('STUB_PREMISE_ALWAYS_HARD', 0) == 2
        hard = has_meter and self.premise_verifies <= env_int('STUB_PREMISE_HARD_ROUNDS', 0)
        return {
            "clauses": [{"n": int(n), "note": "stub: nothing incompatible", "contradiction": False, "quote": ""} for n in clauses],
            "constraints": [{"n": int(n), "note": "stub: nothing incompatible", "violated": broken and i == 0,
                             "quote": "stub quote" if broken and i == 0 else ""} for i, n in enumerate(constraints)],
            "engine": [{"id": e, "note": "stub", "holds": not (always and e == 'E1'), "quote": "stub quote" if (always and e == 'E1') else ""}
                       for e in engine],
            "mechanics": ([{"material": self.VIOLATION, "note": "A reputation score the player watches; the engine has no such system.", "permitted": False}]
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
        if 'names no event' in p.split(RETRY_MARKER)[0]:
            revised['events'] = list(self.EVENTS)
        if 'no turn names the set piece' in p.split(RETRY_MARKER)[0]:
            turns = revised.get('turns') or self.p_s3_5b(p)['turns']
            turns[1]['set_piece'] = "the drone's camera feed from inside the venting ring"
            revised['turns'] = turns
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
        n_events = len(premise.get('events') or [])
        place_events = n_events and not (env_int('STUB_NO_EVENT_PLACED', 0) and RETRY_MARKER not in p)
        for i, b in enumerate(beats):
            turn = None
            if b in middle and queue:
                turn = queue.pop(0)
            event = 1 if (place_events and i == 0) else (2 if (place_events and n_events > 1 and i == len(beats) - 2) else None)
            entries.append({"beat": b['id'], "turn": turn, "way": 1 if turn is not None else None, "event": event,
                            "adapted": f"stub: {b['id']} in this story" + (f", playing turn {turn}" if turn is not None else '')
                            + (f", event {event} lands" if event else '')})
            if b is middle[-1]:
                while queue:      # more turns than middle beats: double up on the last one
                    turn = queue.pop(0)
                    entries.append({"beat": b['id'], "turn": turn, "way": 1, "event": None, "adapted": f"stub: {b['id']} again, playing turn {turn}"})
        if premise.get('setups') and len(entries) >= 2:     # plant early, pay at the end
            entries[0]['plants'], entries[-2]['pays'] = [1], [1]
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
                "ending": {"title": "the strained collective", "summary": "everyone breathes, barely",
                           "answer": "pole_b", "standing": ["the nursery warden", "the hydroponics foreman"], "lost": [],
                           "changed": "the ship is cold and lit by strips", "pays_price": bool(premise.get('price'))},
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
            nodes.append({"id": n['id'], "title": f"stub {n['id']}", "summary": f"{n['id']}: " + str(n.get('plan', '')).replace('stub: ', '').replace(' in this story', ''),
                          "image": f"stub image for {n['id']}: a gauge needle resting on red",
                          "where": [place[0].upper() if sloppy else place[0]], "who": who})
        if extra and nodes:
            new_characters = [
                {"label": "the drone technician", "kind": "individual", "speaks_for": "the dock crew", "gender": "f", "wants": "her drones back", "holds": "the drone cradles", "why": "stub: someone has to launch the drone"},
                {"label": "the dock crew", "kind": "crowd", "speaks_for": None, "wants": "overtime", "holds": "the dock", "why": "stub"},
            ]
            new_locations.append({"name": "the drone dock", "kind": "a work deck", "why": "where drones are launched"})
            nodes[0]['where'] = ["the drone dock"]
            nodes[0]['who'] = ["the dock crew"]     # a crowd alone: the driver adds its voice
            free = [c['label'] for c in register.get('characters') or [] if c.get('kind') != 'crowd' and not c.get('speaks_for')]
            if os.environ.get('STUB_KNOWN_SPEAKER') and free:
                new_characters[0] = {"label": free[0], "kind": "individual", "speaks_for": "the dock crew",
                                     "wants": "stub", "holds": "stub", "why": "stub: already here, speaks for the crew"}
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
        hook = next((h for h in hooks if h['node'] == at and h['way'] == seed.get('way')), None) \
            or next((h for h in hooks if h['node'] == at), None)
        seed_ending = seed.get('ending') if isinstance(seed.get('ending'), dict) else {}
        ending = {"title": seed_ending.get('title') or f"stub ending {it}", "summary": seed_ending.get('summary') or f"stub: line {it} ends differently",
                  "answer": seed_ending.get('answer') or ("pole_a" if it % 2 == 0 else "mixed"),
                  "standing": seed_ending.get('standing') or (["the nursery warden"] if it % 2 == 0 else ["the hydroponics foreman"]),
                  "lost": seed_ending.get('lost') or (["the hydroponics foreman"] if it % 2 == 0 else ["the nursery warden"]),
                  "changed": seed_ending.get('changed') or "stub: a sector is dark"}
        for e in entries:
            e.setdefault("event", None)
        return {
            "status": "proposed", "why": "stub: the seed holds",
            "through_line": {"title": f"line {it}", "motivation": seed.get('motivation', 'stub'), "strategy": seed.get('strategy', 'stub'),
                             "turning_point": "stub", "differs_from": "stub: a different answer at a different price"},
            "divergence": {"diverges_at": at, "trigger": seed.get('trigger', 'you told the sector first'),
                           "trigger_kind": seed.get('trigger_kind') or ("accumulated" if linear else "act"),
                           "way": hook['way'] if hook else None,
                           "instead_of": "you told no one",
                           "opportunity": None if hook else "the speaker makes a private offer",
                           "shift": "stub: what you learn there changes what you want"},
            "ending": ending,
            "beats": entries, "skipped_beats": skipped, "rejoins_at": rejoin,
        }

    # ------------------------------------------------------------------ 4p / 4e

    def p_s4p(self, p):
        counts = self.section(p, '- counts and where a line may leave') or {}
        hooks = (self.section(p, '- ways through a turn that no line has taken') or {}).get('unused_ways') or []
        digest = self.section(p, '- the story so far (one entry per node') or {}
        valid = counts.get('valid_divergence_nodes') or []
        first_half = counts.get('first_half') or valid[:1]
        wanted = env_int('STUB_PLAN_SEEDS', counts.get('seeds_wanted', 2))
        wanted = min(wanted, counts.get('seeds_at_most', wanted))
        retry = RETRY_MARKER in p
        linear = 'LINEAR SHAPE' in self.body(p)
        late_only = env_int('STUB_PLAN_LATE', 0) and not retry
        dup = env_int('STUB_PLAN_DUP', 0)
        dup_now = dup >= 2 or (dup == 1 and not retry)
        main = (digest.get('lines') or [{}])[0]
        taken = set()
        seeds = []
        for i in range(wanted):
            if linear:
                at = valid[0]
            elif late_only or i > 0:
                late = [v for v in valid if v not in first_half] or valid
                at = late[min(i, len(late) - 1)]
            else:
                at = first_half[-1]
            hook = next((h for h in hooks if h['node'] == at and (at, h['way']) not in taken), None)
            if hook:
                taken.add((at, hook['way']))
            worlds = [("pole_a", ["the nursery warden"], ["the hydroponics foreman"]),
                      ("pole_a", ["the hydroponics foreman"], ["the nursery warden"]),
                      ("neither", [], ["the nursery warden", "the hydroponics foreman"]),
                      ("mixed", ["the hydroponics foreman"], []),
                      ("pole_b", [], ["the nursery warden"]), ("pole_a", [], []), ("neither", ["the council speaker"], [])]
            answer, standing, lost = worlds[0] if (dup_now and i == 1) else worlds[i % len(worlds)]
            seeds.append({"motivation": f"stub motivation {i + 2}", "strategy": f"stub strategy {i + 2}",
                          "diverges_at": at, "trigger": "you told the sector first" if not linear else "you had warned every sector in turn",
                          "trigger_kind": "accumulated" if linear else "act", "way": hook['way'] if hook else None,
                          "ending": {"title": f"stub ending {i + 2}", "summary": f"stub: world {i + 2}", "answer": answer,
                                     "standing": standing, "lost": lost, "changed": f"stub change {i + 2}"},
                          "why_different": "stub: a different world"})
        return {"assessment": "stub: the main line answers one way; these are the others", "seeds": seeds}

    def p_s4e(self, p):
        """Reads the outline it is given: the first node's first words planted,
        the last node's paying off, a loss quoted from the last node, one
        invented quote (unverified), and an announced cost if there is one."""
        text = p.split('- the outline', 1)[-1]
        nodes = re.findall(r'^- (\w+) \([^)]*\) [^:]*: (.+?)(?: IMAGE: .*)?$', text, re.M)
        quote = lambda s: ' '.join(s.split()[:6])
        out = {"reading": "stub: an outline", "lost": [], "plants": [], "opposition_at_work": None, "reversal": None,
               "errands": [], "abstractions": [{"node": "N01", "quote": "the weight of the unspoken ledger of grief"}],
               "announced": [], "best_thing": "stub: the second node", "worst_thing": "stub: the endings", "would_play": True}
        if len(nodes) >= 2:
            (first, a), (last, b) = nodes[0], nodes[-1]
            out["plants"] = [{"plant_node": first, "plant_quote": quote(a), "payoff_node": last, "payoff_quote": quote(b),
                              "what_it_does": "stub"}]
            out["lost"] = [{"what": "stub", "kind": "person", "line": "T1", "node": last, "quote": quote(b)}]
            out["opposition_at_work"] = {"node": nodes[1][0], "quote": quote(nodes[1][1]), "what_it_does": "stub"}
        m = re.search(r'^- (\w+) \([^)]*\) [^:]*: .*?(the cost is[^.;]*)', text, re.M)
        if m:
            out["announced"] = [{"node": m.group(1), "quote": m.group(2)}]
        return out

    def p_s4f(self, p):
        """A reader with a position bias: outline 1 wins cost and play
        whichever it is; picture goes to the longer outline (the same either
        way round); setups are the same."""
        text = p.split('- OUTLINE 1', 1)[-1]
        one, two = text.split('- OUTLINE 2', 1)
        longer = '1' if len(one) >= len(two) else '2'
        first_words = lambda t: ' '.join(re.findall(r'^- \w+ \([^)]*\) [^:]*: (.+)$', t, re.M)[0].split()[:5])
        pick = lambda w: {"winner": w, "why": "stub", "quote": "" if w == 'same' else first_words(one if w == '1' else two)}
        return {"cost": pick('1'), "setups": pick('same'), "opposition": pick('1'), "turn": pick('1'),
                "picture": pick(longer), "play": pick('1')}

    # ------------------------------------------------------------------ stage A

    def p_s5a0(self, p):
        cands = self.section(p, 'CANDIDATES (') or []
        return {"cast": [{"who": c['who'], "note": f"stub: {'recurs and warms' if i == 0 else 'delivers a scene'}",
                          "tier": 'supporting' if i == 0 and not env_int('STUB_FUNCTIONAL', 0) else 'functional'}
                         for i, c in enumerate(cands)]}

    def p_s5a1(self, p):
        pk = self.section(p, 'THE OUTLINE (') or {}
        lines = {l['id']: l for l in pk.get('lines') or []}
        main = next(iter(lines)) if lines else 'T1'
        arcs = []
        for i, a in enumerate(pk.get('arc_cast') or []):
            first = re.sub(r'[^a-z]', '', a['who'].split()[0].lower()) or f'c{i}'
            name = f'{first}_trust' if all(not x['state']['name'].startswith(first) for x in arcs) else f'{first}{i}_trust'
            moments, resolutions = [], []
            for l in a.get('lines') or []:
                path = lines[l]['path']
                moments.append({"node": path[min(1, len(path) - 1)], "kind": "test", "change": f"stub: tested on {l}"})
                end = lines[l]['ending']
                person, _, label = a['who'].lower().partition(' (')
                label = label.rstrip(')')
                standing = any(str(x).lower() in (person, label) for x in end.get('standing') or [])
                lost = not standing
                if l == main:
                    resolutions += [{"lines": [l], "direction": "up", "stands_with_you": True, "becomes": "stub: stays"},
                                    {"lines": [l], "direction": "down", "stands_with_you": False, "becomes": "stub: goes"}]
                else:
                    resolutions.append({"lines": [l], "direction": None, "stands_with_you": not lost,
                                        "becomes": "stub: ends as the line says"})
            arcs.append({"who": a['who'], "state": {"name": name, "meaning": "stub: how far they trust you",
                                                    "up_when": "you keep your word", "down_when": "you break it"},
                         "starts": "stub: wary", "moments": moments, "resolutions": resolutions})
        shifts = []
        if env_int('STUB_SHIFT', 0) and arcs and main in lines and len(lines[main]['path']) >= 5:
            shifts.append({"state": arcs[0]['state']['name'], "direction": "down", "at": lines[main]['path'][-2],
                           "does": "resolution", "to": "", "why": "stub: if you broke your word every time"})
        main_path = lines.get(main, {}).get('path') or []
        return {"visibility_note": "stub: you notice", "state_visibility": "observed", "arcs": arcs,
                "light_arcs": [{"who": c['who'], "starts": "stub", "moments": [{"node": main_path[0], "change": "stub"}],
                                "ends": "stub"} for c in pk.get('supporting_cast') or []],
                "protagonist": {l: {"arc": f"stub: who you become on {l}"} for l in lines},
                "setups": [{"setup": main_path[0], "payoff": main_path[-1], "what": "stub"}] if len(main_path) > 1 else [],
                "pattern_shifts": shifts}

    def p_s5a2(self, p):
        pk = self.section(p, 'THIS LINE (') or {}
        path = pk.get('path') or []
        majors = [n['id'] for n in path]
        open_nodes = [n['id'] for n in path if not n.get('ending')]
        lines_of = {n['id']: set(n.get('lines') or []) for n in path}

        def tell_safe(nid):    # the next major node is on every line through this one
            i = majors.index(nid)
            return i + 1 < len(majors) and lines_of[majors[i + 1]] >= lines_of[nid]
        own = [n for n in open_nodes if tell_safe(n)
               and not any(m['id'] == n and m.get('already_expanded') for m in path)]
        own = own or [n for n in open_nodes if tell_safe(n)] or open_nodes
        arcs = pk.get('arcs') or []
        shifts = pk.get('pattern_shifts') or []
        retry = RETRY_MARKER in p
        no_tells = env_int('STUB_NO_TELLS', 0) and not retry
        groups = {}

        def nxt(after):
            return majors[majors.index(after) + 1] if majors.index(after) + 1 < len(majors) else after

        def opportunity(state, who, after, active):
            options = [{"do": "keep your word", "effect": "they relax", "moves": [{"state": state, "direction": "up"}], "active": False},
                       {"do": "break it", "effect": "they go quiet", "moves": [{"state": state, "direction": "down"}], "active": False}]
            if active:
                options.append({"do": "try to fix it yourself", "effect": "it works, or it does not",
                                "moves": [{"state": state, "direction": "up"}], "active": True})
            node = {"after": after, "kind": "opportunity", "serves": [who], "title": "A Small Promise",
                    "summary": "stub: " + " ".join(["a small situation where your word to them is tested"] * 3),
                    "image": "a promise written on a napkin", "who": [who], "options": options}
            if not no_tells:
                node["tell"] = {"at": nxt(after), "how": "they look at you differently"}
            return node

        k = 0
        for a in arcs:
            need = 2
            for sh in shifts:
                if sh['state'] == a['state']['name'] and sh['at'] in majors:
                    need = 3
            slots = [n for n in own if not shifts or all(majors.index(n) < majors.index(sh['at']) for sh in shifts
                                                           if sh['state'] == a['state']['name'] and sh['at'] in majors)]
            slots = slots or own
            who = a['who'].split(' (')[0]
            for j in range(need):
                after = slots[j % len(slots)]
                groups.setdefault(after, []).append(opportunity(a['state']['name'], who, after, active=(k == 0)))
                k += 1
        for sh in shifts:
            if sh['at'] in majors:
                owner = next((a['who'].split(' (')[0] for a in arcs if a['state']['name'] == sh['state']), None)
                before = [n for n in open_nodes if majors.index(n) < majors.index(sh['at'])]
                if owner and before:
                    groups.setdefault(before[-1], []).insert(0, {
                        "after": before[-1], "kind": "demonstration", "serves": [owner], "title": "Nearly Gone",
                        "summary": "stub: " + " ".join(["they stand at the door with their coat on"] * 3),
                        "image": "a coat over an arm", "who": [owner], "warns": sh['state']})
        out = []
        for n in majors:
            out.extend(groups.get(n, []))
        if majors and path[-1].get('ending') and arcs:
            out.append({"after": majors[-1], "kind": "resolution", "serves": [arcs[0]['who'].split(' (')[0]],
                        "title": "Where They Stand", "summary": "stub: " + " ".join(["where they end up at the close"] * 4),
                        "image": "an empty chair", "who": []})
        return {"notes": "stub: two chances per arc", "minor_nodes": out}

    # ------------------------------------------------------------------ stage B

    @staticmethod
    def v(text, state=None, direction=None, after=None):
        return {"state": state, "direction": direction, "after": after, "text": text}

    def p_s6b1(self, p):
        pk = self.section(p, 'THIS PERSON (') or {}
        who = pk.get('who', 'someone')
        own = ((pk.get('arc') or {}).get('state') or {}).get('name')
        first_node = next((sc['nodes'][0]['id'] for sc in pk.get('scenes') or [] if sc.get('nodes')), None)
        n = 3 if pk.get('tier') == 'arc' else 2
        desc = ([self.v(f"stub: {who} stands closer to you than before", own, 'up')] if own else []) + \
               [self.v(f"stub: {who}, plainly dressed, watching the door")]
        topics = [{"label": f"{who.split(' (')[0]} topic {k + 1}", "known_after": first_node if k == n - 1 else None,
                   "says": [self.v(f"stub: what {who.split(' (')[0]} says about thing {k + 1}")], "moves": []} for k in range(n)]
        return {"notes": "stub", "history": "stub: a past that matters" if pk.get('tier') == 'arc' else None,
                "description": desc, "here": [self.v(f"stub: {who.split(' (')[0]} is here.")], "topics": topics}

    def p_s6b1f(self, p):
        people = self.section(p, 'THE PEOPLE (') or []
        return {"note": "stub", "people": [{"who": x['who'], "description": f"stub: {x['who']} in a work coat",
                                            "here": f"stub: {x['who']} is here.",
                                            "topics": [{"label": "their work", "says": "stub: it is a living"}]} for x in people]}

    def p_s6b2(self, p):
        pk = self.section(p, 'THIS LOCATION (') or {}
        name = (pk.get('location') or {}).get('name') or 'the place'
        n = max(1, min(4, int(pk.get('rooms_wanted') or 1)))
        rooms = [{"name": f"{name}, part {i + 1}", "description": "stub: " + " ".join(["a particular corner of " + name] * 4)}
                 for i in range(n)]
        built = pk.get('rooms_already_built') or []
        if os.environ.get('STUB_DUP_ROOM') and built and 'another location or a room already built' not in p:
            rooms[0]['name'] = built[0]  # the live failure: each part of one boat rebuilt the whole boat
        exits = [{"from": rooms[i]['name'], "to": rooms[i + 1]['name'], "label": "onward", "back_label": "back"} for i in range(n - 1)]
        objects = [{"name": f"{r['name']} thing {k + 1}", "room": r['name'], "description": "stub: worth a look",
                    "portable": k == 0, "story": k == 1} for r in rooms for k in range(4)]
        if os.environ.get('STUB_DUP_ROOM'):   # the live failure: each place made its own mooring line, and the cat
            objects += [{"name": "the mooring line", "room": rooms[0]['name'], "description": "stub: rope", "portable": True}]
            objects += [{"name": x, "room": rooms[0]['name'], "description": "stub: a person as a thing"}
                        for x in (pk.get('people_here') or [])[:1]]
        return {"notes": "stub", "rooms": rooms, "exits": exits, "objects": objects}

    def p_s6b2m(self, p):
        pk = self.section(p, 'THE LOCATIONS, THE SCENES') or {}
        locs = [l for l in pk.get('locations') or [] if l.get('rooms')]
        connective, adjacent = [], []
        for a, b in zip(locs, locs[1:]):
            cname = f"the way from {a['name']} to {b['name']}"
            connective.append({"name": cname, "description": "stub: " + " ".join(["a path that smells of the story"] * 4),
                               "examinable": [{"name": f"a mark on {cname}", "description": "stub: someone passed here"}]})
            adjacent += [{"from_room": a['rooms'][0], "to_room": cname, "label": "along the way", "back_label": "back"},
                         {"from_room": cname, "to_room": b['rooms'][0], "label": "on", "back_label": "back along the way"}]
        return {"notes": "stub", "connective": connective, "adjacent": adjacent}

    def p_s6b1c(self, p):
        pk = self.section(p, 'AND THE SUBJECTS') or {}
        who = (pk.get('who') or 'someone').split(' (')[0]
        return {"notes": "stub", "lines": [{"subject": x['subject'], "says": [self.v(f"stub: {who} on {x['subject']}")]}
                                           for x in pk.get('subjects') or []]}

    def p_s6b3(self, p):
        pk = self.section(p, 'YOU (who you are') or {}
        return {"notes": "stub", "description": [self.v("stub: you, tired, in a borrowed coat")],
                "carrying": [{"name": "a keepsake", "description": "stub: it was hers"}],
                "think": [{"label": label, "known_after": None, "says": [self.v(f"stub: what you think about {label}")]}
                          for label in ("your history", "the person you owe", "what you need")]}

    # ------------------------------------------------------------------ stage D

    def p_s8a(self, p):
        people = self.section(p, '- the people (name, role') or []
        rewrite = 'A first style sheet was checked' in p
        return {"tradition": "a stub tradition" + (", revised" if rewrite else ""), "person_tense": "second person, present", "register": "plain and wry",
                "rhythm": "short sentences, a long one at a turn",
                "voices": [{"who": x.get('name') or x.get('role'), "speech": "stub: clipped"} for x in people],
                "images": ["rain on canvas", "a cold rope"], "avoid": ["somehow", "the weight of"],
                "length": "short rooms, long endings",
                "sample": "You step onto the wet deck and the rope is cold in your hand. " * 8}

    def p_s8v(self, p):
        if env_int('STUB_STYLE_FAILS', 0) and '"a stub tradition"' in p:
            return {"note": "stub", "delivers": False, "problems": ["stub: the sample is solemn where the request asked for fun"]}
        return {"note": "stub", "delivers": True, "problems": []}

    def p_s8b(self, p):
        """Returns every text with a stub voice; a person's first text names
        them outright (the pass must turn the name into a code)."""
        texts = self.section(p, '- the texts') or []
        part = self.section(p, '- the part') or {}
        people = {x['code']: x for x in self.section(p, '- the people, by code') or []}
        retry = self.body(p) != p
        out = []
        for i, t in enumerate(texts):
            text = f"{t['text']} (voiced)" if t['id'] != 'unnamed' else 'the stub figure in a coat'
            if i == 0 and part.get('kind') == 'person' and (people.get(part.get('id')) or {}).get('name'):
                text = f"{people[part['id']]['name']} looks up. " + text
            out.append({"id": t['id'], "text": text})
        if not retry and env_int('STUB_PROSE_DROP', 0) and part.get('kind') == 'person' and out:
            out = out[1:]
        if not retry and env_int('STUB_PROSE_IF', 0) and part.get('kind') == 'scene' and out:
            out[0]['text'] = 'If it slips, you fall; if it holds, you climb.'
        return {"texts": out, "images_used": [f"stub image {part.get('id')}"]}

    def p_s7d(self, p):
        pk = self.section(p, 'THIS SCENE (') or {}
        rooms = pk.get('rooms') or [{'name': 'nowhere', 'objects': []}]
        things = [o for r in rooms for o in r.get('objects') or []]
        people = [x['name'] for x in pk.get('people') or []]
        sid = (pk.get('scene') or {}).get('id', 'S')

        def act(k, text, **extra):
            base = ({"verb": "talk", "object": people[0]} if people else {"verb": "use", "object": things[0] if things else None})
            line = f"'{text} ({sid} {k})'"
            out = dict(base, detail=line, label=line, room=None, text=f"stub: {text}", neutral=False, reveals=[],
                       leads_to=None, once=False)
            out.update(extra)
            return out
        moments = []
        for n in pk.get('nodes') or []:
            if n.get('kind') != 'opportunity':
                continue
            opts = [act(f"{n['id']}.{o['n']}", f"option {o['n']}") for o in n.get('options') or []]
            if n.get('required'):
                opts.append(dict(act(f"{n['id']}.n", 'no side'), neutral=True))
            moments.append({"node": n['id'], "options": opts, "lapse": {"after": 4, "text": "stub: the moment passes"}})
        actions = [act(f"rev.{n['id']}", 'find it out', reveals=[n['id']]) for n in pk.get('nodes') or [] if n.get('kind') == 'revelation']
        actions += [act('chore', 'help with a chore'),
                    act('salute', 'salute the water', verb='salute', object='the water', detail=None, label='the water')]
        # a way on as the live run wrote one: a verb and a detail, no object
        actions += [act(f"go.{e['to']}", f"go on to {e['to']}", leads_to=e['to'], verb='go', object=None,
                        detail=f"up the way to {e['to']}", label=None) for e in pk.get('leaving') or []]
        return {"notes": "stub", "opening": f"stub: the scene {sid} begins", "start_room": rooms[0]['name'],
                "placement": [{"who": x, "room": rooms[0]['name']} for x in people], "room_text": [],
                "moments": moments, "actions": actions,
                "events": [{"text": "stub: something happens on its own", "after_turns": 2, "after": None}],
                "nudges": [{"after": 4, "text": "stub: a voice from somewhere asks what you are waiting for"}], "props": []}

