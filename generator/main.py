#!/usr/bin/python
"""Story generator for the stratum-if engine.

Reads a kernel on stdin and runs the pipeline:

  s1 kernel -> s2 rating filter + shape split (content kernel / shape prefs)
  -> phase 3 extraction (blind, nine steps) -> s3h cross-check
  -> constraint map + story brief (computed)
  -> s3.5 premise: the dramatic engine  [build -> verify (3.5v) -> repair (3.5r) -> re-verify]
  -> s3.75 craft spine                  [build -> verify (3.75v) -> repair (3.75r) -> re-verify]
  -> s3.6 cast (named individuals; every crowd has a representative)
  -> s3.7 world (the room map, levers placed)
  -> step 4 story lines (generator/step4.py: main line -> nodes -> review;
     then one divergent line per iteration)

Every model call is resumable: its output is saved under stories/<id>/ and
skipped on the next run if the file exists. See docs/step4_design.md and
CLAUDE.md for the file naming and how to re-run a step.
"""

import os
import sys
import time
import re
import json
import argparse
import contextlib
from pathlib import Path
import dynamic_config
from brief import build_brief, brief_lite
from step4 import Step4Builder

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(THIS_DIR, "..", "prompts")

# the phase-3 extraction steps, in the order they run, paired with the short
#  field id the later prompts (3h, the brief) refer to them by
STEP3_STEPS = [
    ('s3_0a_interactive_question', '3-0a'),
    ('s3_0b_identity_epistemic',   '3-0b'),
    ('s3_0c_consequence_failure_model', '3-0c'),
    ('s3b_affect',    '3b'),
    ('s3c_theme',     '3c'),
    ('s3d_viewpoint', '3d'),
    ('s3e_timeline',  '3e'),
    ('s3f_setting',   '3f'),
    ('s3g_complexity','3g'),
]

# how an evidence tier reads to the phases that CONSTRUCT rather than extract:
#  a constraint may not be contradicted, a default may be replaced with
#  something more specific, a free variable is theirs to fill.
EVIDENCE_CLASS = {
    'explicit':          'constraint',
    'strong_inference':  'constraint',
    'mixed':             'constraint',
    'genre_association': 'default',
    'no_signal':         'free',
}

# how much each tier constrains the construction phase's TEXTURE budget
CONSTRAINT_WEIGHT = {
    'explicit':         1.0,
    'mixed':            1.0,
    'strong_inference': 0.5,
    'genre_association': 0.0,
    'no_signal':        0.0,
}

BUDGET_RULE = ('weighted constraint_share (explicit 1.0, strong_inference 0.5) '
               '>= 0.5 -> minimal; >= 0.2 -> moderate; otherwise generous')

DEFAULT_RATING = 'UNRATED'
DEFAULT_MAX_REPAIRS = 2

PLACEHOLDER_RE = re.compile(r'\$\$[A-Z0-9_]+\$\$')

SHAPE_TIERS = {
    'endings': ('one', 'few', 'several', 'many', 'unstated'),
    'linearity': ('linear', 'branching', 'unstated'),
    'choice_density': ('sparse', 'moderate', 'dense', 'unstated'),
    'length': ('short', 'medium', 'long', 'unstated'),
}


class PipelineHalt(RuntimeError):
    """Raised when a verify/repair loop exhausts its rounds with a hard
    finding still standing. The pipeline stops rather than building on
    material the verifier says is broken; the message names the files."""


class StoryGenerator:
    def __init__(self, story_id, max_repairs=DEFAULT_MAX_REPAIRS, repair_on_soft=False,
                 no_think_steps=()):
        self.story_id = story_id
        self.max_repairs = max_repairs
        self.repair_on_soft = repair_on_soft
        self.no_think_steps = set(no_think_steps or ())

        self.story_path_str = os.path.join(THIS_DIR, "..", "stories", self.story_id)
        self.story_path = Path(self.story_path_str)
        self.story_path.mkdir(parents=True, exist_ok=True)

        self.kernel_full = None   # as the user wrote it
        self.kernel = None        # the content kernel every later step reads
        self.shape = {}           # step 2's shape preferences
        self.rating = DEFAULT_RATING
        self.analysis = dict()

    # ------------------------------------------------------------------ files

    def story_file_path(self, file_suffix):
        return os.path.join(self.story_path_str, f'{self.story_id}_{file_suffix}')

    def load_story_file(self, file_suffix):
        value = ''
        path = Path(self.story_file_path(file_suffix))
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                value = f.read()
            if not value:
                raise ValueError(f"{path} exists, but not loaded with valid value")
        return value

    def save_story_file(self, file_suffix, value):
        path = Path(self.story_file_path(file_suffix))
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)

    def save_story_json(self, file_suffix, value):
        self.save_story_file(file_suffix, json.dumps(value, indent=2, ensure_ascii=False))

    def story_create_log(self, file_suffix):
        file_suffix = f"{file_suffix}_{int(time.time()*1000)}.log"
        return Path(self.story_file_path(file_suffix))

    def load_prompt(self, file_name):
        with open(os.path.join(PROMPT_DIR, file_name), encoding="utf-8") as f:
            value = f.read()
        if not value:
            raise ValueError(f"prompt {file_name} not found (or empty) in prompt directory {PROMPT_DIR}")
        return value

    # ------------------------------------------------------------------ json

    def lenient_json_loads(self, text):
        """Tries a straight parse first; on failure, strips markdown fences and
        any prose around the outermost object, then repairs the most common
        small-model slip-ups (smart quotes, trailing commas) and tries again."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        cleaned = text.strip()
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        cleaned = cleaned.replace("“", '"').replace("”", '"')
        cleaned = cleaned.replace("‘", "'").replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        return json.loads(cleaned)

    def analysis_json(self, member_name, indent=2):
        value = self.analysis.get(member_name)
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    @staticmethod
    def to_json(value, indent=2):
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    # ------------------------------------------------------------------ the model call

    def run_prompt(self,
                   prefix,
                   name,
                   replacement_mapping,
                   is_json=True,
                   prompt_file=None,
                   validator=None,
                   retries=1):
        """One resumable model call.

        prefix + name decide the output file (<id>_<prefix>_<name>.json) and
        the in-memory key (self.analysis['<prefix>_<name>']). The prompt file
        defaults to <prefix>_<name>.prompt. Returns the parsed output.

        validator(parsed) may raise ValueError to reject a structurally wrong
        answer; the call is retried up to `retries` times. A saved output
        that fails the validator is reported as stale (the schema changed
        under it) and named, so the file can be deleted."""
        output_file_name = f'{prefix}_{name}.{"json" if is_json else "txt"}'
        output_member_name = f'{prefix}_{name}'
        prompt_file_name = prompt_file or f'{prefix}_{name}.prompt'
        print(f'out: {output_file_name}')
        val = self.load_story_file(output_file_name)
        if val:
            parsed = self.lenient_json_loads(val) if is_json else val
            if validator is not None and is_json:
                try:
                    validator(parsed)
                except (ValueError, KeyError, TypeError) as e:
                    raise ValueError(
                        f"{self.story_file_path(output_file_name)} no longer matches the schema this "
                        f"pipeline expects ({e}). Delete it (and everything downstream of it) to re-run."
                    )
            self.analysis[output_member_name] = parsed
            return parsed

        prompt = self.load_prompt(prompt_file_name)
        for k, v in replacement_mapping.items():
            if v is None:
                v = 'none'
            prompt = prompt.replace(k, v)
        leftover = sorted(set(PLACEHOLDER_RE.findall(prompt)))
        if leftover:
            raise ValueError(f"{prompt_file_name}: unfilled placeholders {leftover} for {output_member_name}")

        call_kwargs = {}
        if prefix in self.no_think_steps or output_member_name in self.no_think_steps:
            call_kwargs['think'] = False

        last_error = None
        for attempt in range(retries + 1):
            log_path = self.story_create_log(prefix)
            with open(log_path, "w", encoding="utf-8") as f:
                with contextlib.redirect_stdout(f):
                    client = dynamic_config.get_client()
                    (thinking, response) = client.run_prompt(prompt, **call_kwargs)
                    self.save_story_file(f'{prefix}_raw_output_thinking.txt', thinking or '')
                    self.save_story_file(f'{prefix}_raw_output_response.txt', response or '')
            try:
                if is_json:
                    parsed = self.lenient_json_loads(response)
                    if validator is not None:
                        validator(parsed)
                else:
                    parsed = response
            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
                last_error = e
                print(f'  attempt {attempt + 1} for {output_member_name} rejected: {e}')
                continue
            self.analysis[output_member_name] = parsed
            if is_json:
                self.save_story_json(output_file_name, parsed)
            else:
                self.save_story_file(output_file_name, parsed)
            return parsed

        raise ValueError(
            f"{output_member_name}: model output failed validation after "
            f"{retries + 1} attempts (last error: {last_error}); see "
            f"{self.story_file_path(prefix + '_raw_output_response.txt')}"
        )

    # ------------------------------------------------------------------ s1 / s2

    def s1_take_kernel(self, kernel):
        self.kernel_full = self.load_story_file('s1_kernel.txt')
        if not self.kernel_full:
            self.kernel_full = kernel
            if not self.kernel_full:
                raise ValueError("could not find kernel (check stdin)")
            self.save_story_file('s1_kernel.txt', self.kernel_full)
        self.kernel = self.kernel_full

    def s2_apply_rating(self, rating=DEFAULT_RATING):
        """Content-rating filter over the kernel, when a rating is given."""
        saved = self.load_story_file('s2_rating.txt')
        if saved:
            self.rating = saved
        else:
            self.rating = rating or DEFAULT_RATING
        if self.rating != 'UNRATED':
            rated = self.run_prompt('s2', 'rated_kernel', {
                '$$KERNEL$$': self.kernel_full,
                '$$TARGET_RATING$$': self.rating,
            }, is_json=False, prompt_file='s2_filter.prompt')
            self.kernel = rated.strip()
        else:
            self.kernel = self.kernel_full
        if not saved:
            self.save_story_file('s2_rating.txt', self.rating)

    def validate_shape(self, parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        content = parsed.get('content_kernel')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('content_kernel must be a non-empty string')
        if len(content) > len(self.kernel) * 1.15 + 40:
            raise ValueError('content_kernel is longer than the kernel; it may only remove shape clauses')
        shape = parsed.get('shape')
        if not isinstance(shape, dict):
            raise ValueError('shape must be an object')
        endings = shape.get('endings')
        if not isinstance(endings, dict):
            shape['endings'] = endings = {'tier': 'unstated', 'stated': ''}
        for key, allowed in SHAPE_TIERS.items():
            value = endings.get('tier') if key == 'endings' else shape.get(key)
            value = str(value or 'unstated').lower().strip()
            if value not in allowed:
                value = 'unstated'
            if key == 'endings':
                endings['tier'] = value
            else:
                shape[key] = value
        shape.setdefault('removed_clauses', [])

    def s2_split_shape(self):
        """Separate the kernel's shape preferences (ending count, branchiness,
        length) from its content. Every later step reads the content kernel;
        the shape reaches only step 4 as a soft target."""
        rated = self.kernel
        parsed = self.run_prompt('s2', 'shape', {'$$KERNEL$$': rated},
                                 prompt_file='s2_shape_split.prompt', validator=self.validate_shape)
        self.shape = parsed['shape']
        self.kernel = parsed['content_kernel'].strip()
        self.save_story_file('s2_kernel.txt', self.kernel)

    # ------------------------------------------------------------------ phase 3 helpers

    def step3_bundle(self):
        bundle = dict()
        for member_name, field_id in STEP3_STEPS:
            if member_name in self.analysis:
                bundle[field_id] = self.analysis[member_name]
        return bundle

    def step3_bundle_json(self):
        return json.dumps(self.step3_bundle(), indent=2, ensure_ascii=False)

    def build_constraint_map(self):
        """Walk every scored judgment in the phase-3 bundle and sort it by
        evidence tier into constraint / default / free, then derive 3.5's
        texture budget from the mix. Computed, not asked."""
        fields = dict()

        def walk(node, path):
            if isinstance(node, dict):
                basis = node.get('evidence_basis')
                if isinstance(basis, str):
                    fields[path] = {
                        'evidence_basis': basis,
                        'class': EVIDENCE_CLASS.get(basis, 'default'),
                    }
                for key, value in node.items():
                    if key in ('evidence_basis', 'note'):
                        continue
                    if isinstance(value, (dict, list)):
                        walk(value, f'{path}.{key}' if path else key)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    if isinstance(item, (dict, list)):
                        walk(item, f'{path}[{index}]')

        for member_name, field_id in STEP3_STEPS:
            if member_name in self.analysis:
                walk(self.analysis[member_name], field_id)

        counts = dict()
        for entry in fields.values():
            counts[entry['evidence_basis']] = counts.get(entry['evidence_basis'], 0) + 1
        total = len(fields)
        constraints = sum(1 for e in fields.values() if e['class'] == 'constraint')
        weighted = sum(CONSTRAINT_WEIGHT.get(e['evidence_basis'], 0.0) for e in fields.values())
        share = (weighted / total) if total else 0.0
        if share >= 0.5:
            budget = 'minimal'
        elif share >= 0.2:
            budget = 'moderate'
        else:
            budget = 'generous'

        constraint_map = {
            'fields': fields,
            'counts': counts,
            'total_scored_judgments': total,
            'constraint_count': constraints,
            'constraint_share': round(share, 3),
            'suggested_budget': budget,
            'budget_rule': BUDGET_RULE,
        }
        self.analysis['s3h_constraint_map'] = constraint_map
        self.save_story_json('s3h_constraint_map.json', constraint_map)
        return constraint_map

    def build_story_brief(self):
        """The compact digest every later prompt reads instead of the bundle:
        each field's value and binding class, the cross-check's resolutions,
        the budget. Recomputed every run."""
        brief = build_brief(self.step3_bundle(), self.analysis.get('s3h_constraint_map'),
                            self.analysis.get('s3h_cross_check'))
        self.analysis['s3_brief'] = brief
        self.save_story_json('s3_brief.json', brief)
        return brief

    # ------------------------------------------------------------------ build / verify / repair

    def run_verified_step(self,
                          build_prefix, build_name, build_replacements,
                          verify_prefix, verify_name, verify_replacements,
                          repair_prefix, repair_name, repair_prompt_file, repair_replacements,
                          needs_repair, build_validator=None, verify_validator=None):
        """build -> verify, then up to self.max_repairs rounds of repair ->
        re-verify while needs_repair(verdict). The repair prompt returns
        {"repair_log", "revised"}; the revised object replaces the build
        output under the build's own key, so downstream reads the accepted
        version without knowing a repair happened.

        Files: <build>.json is the ORIGINAL; repairs <repair_prefix><n>_...;
        re-checks <verify_prefix>_r<n>_...; accepted copy <build>_accepted.json;
        <build_prefix>_loop.json records the rounds. Halts (PipelineHalt) if
        the last verdict still needs repair."""
        member = f'{build_prefix}_{build_name}'
        verify_member = f'{verify_prefix}_{verify_name}'
        verify_prompt_file = f'{verify_prefix}_{verify_name}.prompt'

        current = self.run_prompt(build_prefix, build_name, build_replacements,
                                  validator=build_validator)
        verdict = self.run_prompt(verify_prefix, verify_name, verify_replacements(current),
                                  validator=verify_validator)
        rounds = [{'round': 0, 'source': f'{build_prefix}_{build_name}.json',
                   'verdict': self._verdict_summary(verdict)}]

        def repair_validator(parsed):
            if not isinstance(parsed, dict) or 'revised' not in parsed:
                raise ValueError('repair output must carry a "revised" object')
            if not isinstance(parsed['revised'], dict):
                raise ValueError('"revised" must be an object')
            missing = [k for k in current.keys() if k not in parsed['revised']]
            if missing:
                raise ValueError(f'"revised" is missing top-level keys {missing}')
            if build_validator is not None:
                build_validator(parsed['revised'])

        n = 0
        while needs_repair(verdict) and n < self.max_repairs:
            n += 1
            repaired = self.run_prompt(f'{repair_prefix}{n}', repair_name,
                                       repair_replacements(current, verdict),
                                       prompt_file=repair_prompt_file,
                                       validator=repair_validator)
            current = repaired['revised']
            self.analysis[member] = current
            verdict = self.run_prompt(f'{verify_prefix}_r{n}', verify_name,
                                      verify_replacements(current),
                                      prompt_file=verify_prompt_file,
                                      validator=verify_validator)
            self.analysis[verify_member] = verdict
            rounds.append({'round': n,
                           'source': f'{repair_prefix}{n}_{repair_name}.json#revised',
                           'repair_log': repaired.get('repair_log', []),
                           'verdict': self._verdict_summary(verdict)})

        still_failing = needs_repair(verdict)
        loop = {
            'accepted_source': rounds[-1]['source'],
            'accepted_copy': f'{build_prefix}_{build_name}_accepted.json',
            'repair_rounds_used': n,
            'max_repairs': self.max_repairs,
            'still_failing': still_failing,
            'rounds': rounds,
        }
        self.save_story_json(f'{build_prefix}_{build_name}_accepted.json', current)
        self.save_story_json(f'{build_prefix}_loop.json', loop)
        if still_failing:
            raise PipelineHalt(
                f"{member}: verifier still reports a repair-worthy verdict after "
                f"{n} repair round(s). Inspect {self.story_file_path(build_prefix + '_loop.json')} "
                f"and the last {verify_member} output, fix the prompt or the material, then delete "
                f"the loop's files to re-run it."
            )
        return current, verdict

    @staticmethod
    def _verdict_summary(verdict):
        if isinstance(verdict, dict) and isinstance(verdict.get('verdict'), dict):
            return verdict['verdict']
        return verdict

    def premise_needs_repair(self, verdict):
        value = (verdict.get('verdict') or {}).get('value', '')
        if value == 'hard_issues':
            return True
        return self.repair_on_soft and value == 'soft_issues'

    def craft_spine_needs_repair(self, verdict):
        value = (verdict.get('verdict') or {}).get('value', '')
        return value == 'flagged'

    # ------------------------------------------------------------------ validators

    @staticmethod
    def require_keys(*keys):
        def validate(parsed):
            if not isinstance(parsed, dict):
                raise ValueError('expected a JSON object')
            missing = [k for k in keys if k not in parsed]
            if missing:
                raise ValueError(f'missing keys {missing}')
        return validate

    def validate_premise(self, parsed):
        self.require_keys('enrichment_budget', 'protagonist', 'arena', 'pressure', 'opposition',
                          'mediation', 'turns', 'cast_seeds', 'complications', 'withheld',
                          'fidelity_check')(parsed)
        turns = parsed.get('turns')
        if not isinstance(turns, list) or len(turns) < 2:
            raise ValueError('turns must be a list of at least two turns')
        for i, t in enumerate(turns):
            if not isinstance(t, dict):
                raise ValueError('each turn must be an object')
            t.setdefault('id', i + 1)
        seeds = parsed.get('cast_seeds')
        if not isinstance(seeds, list) or not seeds:
            raise ValueError('cast_seeds must be a non-empty list')
        med = parsed.get('mediation')
        if not isinstance(med, dict) or not med.get('question'):
            raise ValueError('mediation needs a question')

    def validate_craft_spine(self, parsed):
        if isinstance(parsed, dict) and parsed.get('status') == 'blocked':
            raise PipelineHalt(
                f"3.75 refused to build: {parsed.get('reason')} / {parsed.get('hard_findings_summary')}"
            )
        self.require_keys('invention_ceiling', 'want_need_tension', 'irony_mode',
                          'escalation_shape', 'setup_payoff_pairs')(parsed)

    @staticmethod
    def validate_cast(parsed):
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        chars = parsed.get('characters')
        if not isinstance(chars, list) or not chars:
            raise ValueError('characters must be a non-empty list')
        names = []
        for c in chars:
            if not isinstance(c, dict) or not c.get('name'):
                raise ValueError('each character needs a name')
            if c['name'] in names:
                raise ValueError(f'duplicate character name {c["name"]}')
            names.append(c['name'])
        crowds = parsed.get('crowds')
        if crowds is None:
            parsed['crowds'] = crowds = []
        if not isinstance(crowds, list):
            raise ValueError('crowds must be a list')
        for crowd in crowds:
            if not isinstance(crowd, dict):
                raise ValueError('each crowd must be an object')
            reps = [r for r in (crowd.get('representatives') or []) if r in names]
            if not reps:
                raise ValueError(f'crowd {crowd.get("name")} has no representative among the characters')
            crowd['representatives'] = reps
        parsed.setdefault('protagonist_name', None)

    def validate_world(self, parsed):
        """Rejects a map with no rooms or duplicate ids; normalizes the rest
        (drops unknown connections and names, makes connections mutual)."""
        if not isinstance(parsed, dict):
            raise ValueError('expected an object')
        rooms = parsed.get('rooms')
        if not isinstance(rooms, list) or len(rooms) < 2:
            raise ValueError('rooms must be a list of at least two rooms')
        ids = []
        for r in rooms:
            if not isinstance(r, dict) or not r.get('id') or not r.get('name'):
                raise ValueError('each room needs an id and a name')
            if r['id'] in ids:
                raise ValueError(f'duplicate room id {r["id"]}')
            ids.append(r['id'])
        cast = self.analysis.get('s3_6_cast') or {}
        names = {c.get('name') for c in (cast.get('characters') or []) if isinstance(c, dict)}
        by_id = {r['id']: r for r in rooms}
        for r in rooms:
            conns = [c for c in (r.get('connections') or []) if isinstance(c, str) and c in by_id and c != r['id']]
            r['connections'] = conns
            r['usually_here'] = [n for n in (r.get('usually_here') or []) if n in names]
            r.setdefault('fixtures', [])
        for r in rooms:
            for c in r['connections']:
                if r['id'] not in by_id[c]['connections']:
                    by_id[c]['connections'].append(r['id'])
        parsed.setdefault('protagonist_presence', {})
        parsed.setdefault('levers_placed', [])

    # ------------------------------------------------------------------ the pipeline

    def run_phase3(self):
        replace_kernel_only = {'$$KERNEL$$': self.kernel}
        self.run_prompt('s3_0a', 'interactive_question', replace_kernel_only)
        self.run_prompt('s3_0b', 'identity_epistemic', replace_kernel_only)
        self.run_prompt('s3_0c', 'consequence_failure_model', replace_kernel_only)
        self.run_prompt('s3b', 'affect', replace_kernel_only)
        self.run_prompt('s3c', 'theme', replace_kernel_only)
        self.run_prompt('s3d', 'viewpoint', replace_kernel_only)
        self.run_prompt('s3e', 'timeline', replace_kernel_only)
        self.run_prompt('s3f', 'setting', {
            '$$VIEWPOINT_EXCURSIONS_JSON$$': self.analysis_json('s3d_viewpoint'),
            '$$KERNEL$$': self.kernel
        })
        # 3g is chained, not blind: branching density and tracked state aren't
        #  well-defined without the decision (3-0a) and the failure model (3-0c).
        self.run_prompt('s3g', 'complexity', {
            '$$INTERACTIVE_QUESTION_JSON$$': self.analysis_json('s3_0a_interactive_question'),
            '$$FAILURE_MODEL_JSON$$': self.analysis_json('s3_0c_consequence_failure_model'),
            '$$KERNEL$$': self.kernel
        })
        # 3h: the phase's own cross-check. Classification only; fixes nothing.
        self.run_prompt('s3h', 'cross_check', {
            '$$STEP3_BUNDLE_JSON$$': self.step3_bundle_json(),
            '$$KERNEL$$': self.kernel
        })
        self.build_constraint_map()
        self.build_story_brief()

    def run_premise_expansion(self, avoid_list='none'):
        """3.5 build, 3.5v audit, 3.5r repair on hard findings, re-audit."""
        brief = self.analysis_json('s3_brief')

        def verify_repl(current):
            return {
                '$$BRIEF_JSON$$': brief,
                '$$PREMISE_EXPANSION_JSON$$': self.to_json(current),
                '$$KERNEL$$': self.kernel
            }

        def repair_repl(current, verdict):
            return {
                '$$BRIEF_JSON$$': brief,
                '$$PREMISE_EXPANSION_JSON$$': self.to_json(current),
                '$$FIDELITY_CHECK_JSON$$': self.to_json(verdict),
                '$$KERNEL$$': self.kernel
            }

        return self.run_verified_step(
            's3_5', 'premise_expansion', {
                '$$BRIEF_JSON$$': brief,
                '$$AVOID_LIST$$': avoid_list,
                '$$KERNEL$$': self.kernel
            },
            's3_5v', 'fidelity_check', verify_repl,
            's3_5r', 'premise_repair', 's3_5r_premise_repair.prompt', repair_repl,
            needs_repair=self.premise_needs_repair,
            build_validator=self.validate_premise,
            verify_validator=self.require_keys('clause_findings', 'constraint_findings',
                                               'mechanic_findings', 'engine_findings', 'verdict'),
        )

    def run_craft_spine(self):
        """3.75 build, 3.75v audit, 3.75r repair on a flagged verdict, re-audit."""
        base = {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_JSON$$': self.analysis_json('s3_brief'),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
        }

        def verify_repl(current):
            repl = dict(base)
            repl['$$CRAFT_SPINE_JSON$$'] = self.to_json(current)
            return repl

        def repair_repl(current, verdict):
            repl = dict(base)
            repl['$$CRAFT_SPINE_JSON$$'] = self.to_json(current)
            repl['$$CRAFT_SPINE_FIDELITY_JSON$$'] = self.to_json(verdict)
            return repl

        return self.run_verified_step(
            's3_75', 'craft_spine', base,
            's3_75v', 'fidelity_check', verify_repl,
            's3_75r', 'craft_spine_repair', 's3_75r_craft_spine_repair.prompt', repair_repl,
            needs_repair=self.craft_spine_needs_repair,
            build_validator=self.validate_craft_spine,
            verify_validator=self.require_keys('clause_findings', 'mechanic_findings', 'verdict'),
        )

    def budget(self):
        premise = self.analysis.get('s3_5_premise_expansion') or {}
        return str((premise.get('enrichment_budget') or {}).get('level', 'moderate'))

    def run_cast(self):
        """3.6: the named cast; every crowd gets a representative."""
        return self.run_prompt('s3_6', 'cast', {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_LITE_JSON$$': self.to_json(brief_lite(self.analysis.get('s3_brief'))),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }, validator=self.validate_cast)

    def run_world(self):
        """3.7: the room map, drawn once, with the premise's levers placed."""
        fields = ((self.analysis.get('s3_brief') or {}).get('fields') or {})
        setting_fields = {k: fields.get(k) for k in ('3f.setting_structure', '3f.setting_scale',
                                                       '3d.viewpoint_handoff', '3d.viewpoint_excursions',
                                                       '3e.timeline_structure', '3-0b.protagonist_identity')}
        return self.run_prompt('s3_7', 'world', {
            '$$KERNEL$$': self.kernel,
            '$$BRIEF_LITE_JSON$$': self.to_json(brief_lite(self.analysis.get('s3_brief'))),
            '$$SETTING_FIELDS_JSON$$': self.to_json(setting_fields),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
            '$$CAST_JSON$$': self.analysis_json('s3_6_cast'),
            '$$ENRICHMENT_BUDGET$$': self.budget(),
        }, validator=self.validate_world)

    def run_step4(self, max_iterations, max_repair_nodes):
        builder = Step4Builder(self, max_iterations=max_iterations, max_repair_nodes=max_repair_nodes)
        return builder.run()


def slugify(name):
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--story-id", default='', help="identifier for the story, used for directory and file naming (note will be slugified)")
    parser.add_argument("--rating", default=DEFAULT_RATING, help="(step2 input) US Film Rating to respect for generated story")
    parser.add_argument("--max-repairs", type=int, default=DEFAULT_MAX_REPAIRS,
                        help="repair rounds allowed per build/verify loop (3.5, 3.75) before halting (default 2)")
    parser.add_argument("--repair-on-soft", action="store_true",
                        help="also send 3.5v soft_issues verdicts to repair (default: hard_issues only)")
    parser.add_argument("--max-iterations", type=int, default=4,
                        help="step 4: maximum story lines to build, main line included (default 4)")
    parser.add_argument("--max-repair-nodes", type=int, default=4,
                        help="step 4: maximum nodes rebuilt per review round (default 4)")
    parser.add_argument("--no-think-steps", default='',
                        help="comma-separated call prefixes to run with the model's thinking disabled "
                             "(e.g. s2); needs a client that honors it")
    parser.add_argument("--stop-after", default='',
                        help="stop after this step: 2, 3, 3.5, 3.75, 3.7 (default: run through step 4)")
    args = parser.parse_args()

    story_id = slugify(args.story_id)
    if not story_id:
        story_id = f'story_{int(time.time())}'

    gen = StoryGenerator(story_id=story_id, max_repairs=args.max_repairs,
                         repair_on_soft=args.repair_on_soft,
                         no_think_steps=[s.strip() for s in args.no_think_steps.split(',') if s.strip()])

    print('enter kernel and close stdin:')

    gen.s1_take_kernel(sys.stdin.read())
    gen.s2_apply_rating(rating=args.rating)

    try:
        gen.s2_split_shape()
        if args.stop_after == '2':
            sys.exit(0)

        gen.run_phase3()
        if args.stop_after == '3':
            sys.exit(0)

        # 3.5: the first step that CONSTRUCTS. Builds the dramatic engine
        #  (protagonist, pressure, opposition, mediation, turns, cast seeds).
        gen.run_premise_expansion()
        if args.stop_after == '3.5':
            sys.exit(0)

        # 3.75: craft devices over the verified premise, same loop shape.
        gen.run_craft_spine()
        if args.stop_after == '3.75':
            sys.exit(0)

        # 3.6 / 3.7: the cast and the map, once, before any story line.
        gen.run_cast()
        gen.run_world()
        if args.stop_after == '3.7':
            sys.exit(0)

        # step 4: main line, then one divergent line per iteration.
        gen.run_step4(max_iterations=args.max_iterations,
                      max_repair_nodes=args.max_repair_nodes)
    except PipelineHalt as halt:
        print(f'\nPIPELINE HALTED: {halt}', file=sys.stderr)
        sys.exit(2)
