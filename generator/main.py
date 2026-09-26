#!/usr/bin/python
"""Story generator for the stratum-if engine.

Reads a kernel on stdin and runs the pipeline:

  s1 kernel -> s2 rating filter -> phase 3 extraction (blind, nine steps)
  -> s3h cross-check -> constraint map (computed)
  -> s3.5 premise expansion  [build -> verify (3.5v) -> repair (3.5r) -> re-verify]
  -> s3.75 craft spine       [build -> verify (3.75v) -> repair (3.75r) -> re-verify]
  -> step 4 outline loop     (generator/step4.py: outline -> entities -> beats
                              -> review -> beat repair, iterated per path)

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
from step4 import Step4Builder

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(THIS_DIR, "..", "prompts")

# the phase-3 extraction steps, in the order they run, paired with the short
#  field id the later prompts (3h, 3.5, 3.75, 4) refer to them by
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

# how much each tier actually constrains the construction phase. A stated
#  requirement binds fully; something merely forced by the kernel's details
#  binds half as hard, because it's a reading rather than an instruction.
#  Genre defaults and no_signal fallbacks constrain nothing - they're what
#  3.5 exists to replace.
CONSTRAINT_WEIGHT = {
    'explicit':         1.0,
    'mixed':            1.0,
    'strong_inference': 0.5,
    'genre_association': 0.0,
    'no_signal':        0.0,
}

# thresholds for 3.5's enrichment budget, computed from the weighted share of
#  extracted judgments that constrain rather than defer
BUDGET_RULE = ('weighted constraint_share (explicit 1.0, strong_inference 0.5) '
               '>= 0.5 -> minimal; >= 0.2 -> moderate; otherwise generous')

# by default, don't enforce a floor or ceiling on the kernel,
#  but if specified, can keep things from wandering off
DEFAULT_RATING = 'UNRATED'

# how many repair rounds a build/verify/repair loop gets before the pipeline
#  stops and asks a human to look
DEFAULT_MAX_REPAIRS = 2

PLACEHOLDER_RE = re.compile(r'\$\$[A-Z0-9_]+\$\$')


class PipelineHalt(RuntimeError):
    """Raised when a verify/repair loop exhausts its rounds with a hard
    finding still standing. The pipeline stops rather than building on
    material the verifier says is broken; the message names the files."""


class StoryGenerator:
    def __init__(self, story_id, max_repairs=DEFAULT_MAX_REPAIRS, repair_on_soft=False):
        self.story_id = story_id
        self.max_repairs = max_repairs
        self.repair_on_soft = repair_on_soft

        # figure out story dir and make it if needed
        self.story_path_str = os.path.join(THIS_DIR, "..", "stories", self.story_id)
        self.story_path = Path(self.story_path_str)
        self.story_path.mkdir(parents=True, exist_ok=True)

        # set defaults, if resuming the specific stage will load from file
        self.kernel = None
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
                raise ValueError(
                    f"{path} exists, but not loaded with valid value"
                )
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
        value = ''
        with open(os.path.join(PROMPT_DIR, file_name), encoding="utf-8") as f:
            value = f.read()
        if not value:
            raise ValueError(
                f"prompt {file_name} not found (or empty) in prompt directory {PROMPT_DIR}"
                )
        return value

    # ------------------------------------------------------------------ json

    def lenient_json_loads(self, text):
        """Tries a straight parse first; on failure, strips markdown fences and
        any prose around the outermost object, then repairs the most common
        small-model slip-ups (smart quotes, trailing commas) and tries again.
        Lets the last attempt's error propagate so the caller sees a real
        json.JSONDecodeError with a useful message."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        cleaned = text.strip()
        # ```json ... ``` fences, or a leading/trailing sentence of commentary
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
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
        return json.loads(cleaned)

    def analysis_json(self, member_name, indent=2):
        """Pretty-printed JSON for one saved step's output, for substitution
        into a later step's prompt. Returns "none" when the step hasn't run,
        which every consuming prompt is written to tolerate."""
        value = self.analysis.get(member_name)
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    @staticmethod
    def to_json(value, indent=2):
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    # ------------------------------------------------------------------ s1/s2

    def s1_take_kernel(self, kernel):
        # load the kernel
        self.kernel = self.load_story_file('s1_kernel.txt')
        if not self.kernel:
            self.kernel = kernel
            if not self.kernel:
                raise ValueError(
                    f"could not find kernel (check stdin)"
                )

            # save the kernel if we didn't load it
            self.save_story_file('s1_kernel.txt', self.kernel)

    def s2_apply_rating(self, rating=DEFAULT_RATING):

        # load the rating
        self.rating = self.load_story_file('s2_rating.txt')
        if self.rating:
            # if the rating was saved, then we should be able to load
            # the previous filtered kernel and skip the step
            # load the kernel
            self.kernel = self.load_story_file('s2_kernel.txt')
            if not self.kernel:
                raise ValueError(
                    f"could not find filtered kernel (remove {self.story_id}_s2_rating.txt from story directory)"
                )
            return

        self.rating = rating
        if not self.rating:
            self.rating = DEFAULT_RATING

        # this step is to run a content-rating filter over the kernel
        #  note if the rating is 'UNRATED' it will skip this step
        if self.rating != 'UNRATED':
            filter_prompt = self.load_prompt('s2_filter.prompt')

            # now fill in the args
            filter_prompt = filter_prompt.replace('$$KERNEL$$',self.kernel).replace('$$TARGET_RATING$$',self.rating)
            client = dynamic_config.get_client()
            (thinking,response) = client.run_prompt(filter_prompt)
            self.save_story_file('s2_raw_output_thinking.txt', thinking)
            self.save_story_file('s2_raw_output_response.txt', response)
            self.kernel = response

        self.save_story_file('s2_kernel.txt', self.kernel)
        self.save_story_file('s2_rating.txt', self.rating)

    # ------------------------------------------------------------------ phase 3 helpers

    def step3_bundle_json(self):
        """All nine phase-3 extractions as one object keyed by field id.
        3h, 3.5, 3.75 and 4 each take the whole bundle rather than nine
        placeholders."""
        bundle = dict()
        for member_name, field_id in STEP3_STEPS:
            if member_name in self.analysis:
                bundle[field_id] = self.analysis[member_name]
        return json.dumps(bundle, indent=2, ensure_ascii=False)

    def build_constraint_map(self):
        """Walk every scored judgment in the phase-3 bundle and sort it by
        evidence tier into constraint / default / free, then derive 3.5's
        enrichment budget from the mix. This is deliberately computed here
        rather than asked of the model: it's a count, and the model is
        better spent on the construction it gates."""
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
        weighted = sum(CONSTRAINT_WEIGHT.get(e['evidence_basis'], 0.0)
                       for e in fields.values())
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
        rendered = json.dumps(constraint_map, indent=2, ensure_ascii=False)
        self.analysis['s3h_constraint_map'] = constraint_map
        self.save_story_file('s3h_constraint_map.json', rendered)
        return rendered

    def s3a_determine_length(self):
        # folded into 3g: target_ending_count and branching_density already
        #  bound the build, and nothing downstream consumed a separate length
        #  field. See docs/strategy.txt 3a.
        pass

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
        defaults to <prefix>_<name>.prompt; pass prompt_file when the same
        prompt is run under several prefixes (repair rounds, step-4
        iterations). Returns the parsed output.

        validator(parsed) may raise ValueError to reject a structurally wrong
        answer; the call is then retried up to `retries` times before the
        error propagates."""

        # load the value from previous run
        output_file_name = f'{prefix}_{name}.{"json" if is_json else "txt"}'
        output_member_name = f'{prefix}_{name}'
        prompt_file_name = prompt_file or f'{prefix}_{name}.prompt'
        print(f'out: {output_file_name}')
        val = self.load_story_file(output_file_name)
        if val:
            parsed = self.lenient_json_loads(val) if is_json else val
            self.analysis[output_member_name] = parsed
            return parsed

        # load the prompt
        prompt = self.load_prompt(prompt_file_name)

        # now fill in the args
        for k,v in replacement_mapping.items():
            if v is None:
                v = 'none'
            prompt = prompt.replace(k,v)

        # a placeholder nobody filled is a wiring bug, not something to send
        #  to the model
        leftover = sorted(set(PLACEHOLDER_RE.findall(prompt)))
        if leftover:
            raise ValueError(
                f"{prompt_file_name}: unfilled placeholders {leftover} for {output_member_name}"
            )

        last_error = None
        for attempt in range(retries + 1):
            log_path = self.story_create_log(prefix)
            with open(log_path, "w", encoding="utf-8") as f:
                with contextlib.redirect_stdout(f):
                    client = dynamic_config.get_client()
                    (thinking,response) = client.run_prompt(prompt)
                    self.save_story_file(f'{prefix}_raw_output_thinking.txt', thinking)
                    self.save_story_file(f'{prefix}_raw_output_response.txt', response)
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

    # ------------------------------------------------------------------ build / verify / repair

    def run_verified_step(self,
                          build_prefix, build_name, build_replacements,
                          verify_prefix, verify_name, verify_replacements,
                          repair_prefix, repair_name, repair_prompt_file, repair_replacements,
                          needs_repair, build_validator=None, verify_validator=None):
        """The standing rule: generation and verification never share a
        prompt, and repair is a third call that receives the violation
        list. This runs build -> verify, then up to self.max_repairs rounds
        of repair -> re-verify while needs_repair(verdict) is true.

        verify_replacements(current) and repair_replacements(current, verdict)
        are callables because the material changes between rounds. The
        repair prompt returns {"repair_log": [...], "revised": <same shape as
        the build output>}; the revised object replaces the build output in
        self.analysis under the build's own key, so downstream steps read the
        accepted version without knowing a repair happened.

        Files: <build_prefix>_<build_name>.json is the ORIGINAL build. Repair
        rounds are <repair_prefix><n>_<repair_name>.json and their re-checks
        <verify_prefix>_r<n>_<verify_name>.json. The accepted version is also
        copied to <build_prefix>_<build_name>_accepted.json, and
        <build_prefix>_loop.json records the rounds. To re-run the whole loop,
        delete every file of the build's, verify's and repair's prefix.

        Halts the pipeline (PipelineHalt) if the last verdict still needs
        repair: the later phases assume verified material and would build
        a wrong story on top of a known contradiction."""
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

    # ------------------------------------------------------------------ verdict readers

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

    def validate_craft_spine(self, parsed):
        if isinstance(parsed, dict) and parsed.get('status') == 'blocked':
            raise PipelineHalt(
                f"3.75 refused to build: {parsed.get('reason')} / {parsed.get('hard_findings_summary')}"
            )
        self.require_keys('invention_ceiling', 'want_need_tension', 'irony_mode',
                          'escalation_shape', 'setup_payoff_pairs')(parsed)

    # ------------------------------------------------------------------ the pipeline

    def run_phase3(self):
        replace_kernel_only = {'$$KERNEL$$': self.kernel}
        self.run_prompt('s3_0a','interactive_question',replace_kernel_only)
        self.run_prompt('s3_0b','identity_epistemic',replace_kernel_only)
        self.run_prompt('s3_0c', 'consequence_failure_model',replace_kernel_only)
        self.run_prompt('s3b','affect',replace_kernel_only)
        self.run_prompt('s3c','theme',replace_kernel_only)
        self.run_prompt('s3d','viewpoint',replace_kernel_only)
        self.run_prompt('s3e','timeline',replace_kernel_only)
        self.run_prompt('s3f','setting', {
            '$$VIEWPOINT_EXCURSIONS_JSON$$': self.analysis_json('s3d_viewpoint'),
            '$$KERNEL$$': self.kernel
        })

        # 3g is chained, not blind: branching density and tracked state aren't
        #  well-defined without knowing what the player decides (3-0a) and what
        #  the engine has to recognize as failure (3-0c). Chain only where a
        #  field is undefined without the other's output - never for agreement.
        self.run_prompt('s3g','complexity', {
            '$$INTERACTIVE_QUESTION_JSON$$': self.analysis_json('s3_0a_interactive_question'),
            '$$FAILURE_MODEL_JSON$$': self.analysis_json('s3_0c_consequence_failure_model'),
            '$$KERNEL$$': self.kernel
        })

        # 3h: the phase's own cross-check. Classification only - it names
        #  conflicts between the nine blind extractions and picks what the
        #  primary branch point is built from; it fixes nothing. Its
        #  resolutions are acted on by 3.5 (which builds to the winning
        #  field) and are passed to 3.5v/3.75/4 so a constraint 3h ruled
        #  against is not audited or built against as if it still bound.
        step3_bundle = self.step3_bundle_json()
        self.run_prompt('s3h','cross_check', {
            '$$STEP3_BUNDLE_JSON$$': step3_bundle,
            '$$KERNEL$$': self.kernel
        })

        # constraint map: computed, not judged - sorts every extracted judgment
        #  into constraint / default / free and sizes 3.5's enrichment budget.
        self.build_constraint_map()

    def run_premise_expansion(self, avoid_list='none'):
        """3.5 build, 3.5v audit, 3.5r repair on hard findings, re-audit."""
        step3_bundle = self.step3_bundle_json()
        constraint_map = self.analysis_json('s3h_constraint_map')
        cross_check = self.analysis_json('s3h_cross_check')

        def verify_repl(current):
            return {
                '$$CONSTRAINT_MAP_JSON$$': constraint_map,
                '$$CROSS_CHECK_JSON$$': cross_check,
                '$$PREMISE_EXPANSION_JSON$$': self.to_json(current),
                '$$KERNEL$$': self.kernel
            }

        def repair_repl(current, verdict):
            return {
                '$$STEP3_BUNDLE_JSON$$': step3_bundle,
                '$$CONSTRAINT_MAP_JSON$$': constraint_map,
                '$$CROSS_CHECK_JSON$$': cross_check,
                '$$PREMISE_EXPANSION_JSON$$': self.to_json(current),
                '$$FIDELITY_CHECK_JSON$$': self.to_json(verdict),
                '$$KERNEL$$': self.kernel
            }

        return self.run_verified_step(
            's3_5', 'premise_expansion', {
                '$$STEP3_BUNDLE_JSON$$': step3_bundle,
                '$$CONSTRAINT_MAP_JSON$$': constraint_map,
                '$$CROSS_CHECK_JSON$$': cross_check,
                '$$AVOID_LIST$$': avoid_list,
                '$$KERNEL$$': self.kernel
            },
            's3_5v', 'fidelity_check', verify_repl,
            's3_5r', 'premise_repair', 's3_5r_premise_repair.prompt', repair_repl,
            needs_repair=self.premise_needs_repair,
            build_validator=self.require_keys('enrichment_budget', 'protagonist_situation',
                                              'arena', 'instance_generator', 'complications',
                                              'withheld', 'fidelity_check'),
            verify_validator=self.require_keys('clause_findings', 'constraint_findings',
                                               'mechanic_findings', 'verdict'),
        )

    def craft_spine_inputs(self):
        return {
            '$$KERNEL$$': self.kernel,
            '$$INTERACTIVE_QUESTION_JSON$$': self.analysis_json('s3_0a_interactive_question'),
            '$$EPISTEMIC_GAP_JSON$$': self.analysis_json('s3_0b_identity_epistemic'),
            '$$FAILURE_MODEL_JSON$$': self.analysis_json('s3_0c_consequence_failure_model'),
            '$$AFFECT_JSON$$': self.analysis_json('s3b_affect'),
            '$$THEME_JSON$$': self.analysis_json('s3c_theme'),
            '$$COMPLEXITY_JSON$$': self.analysis_json('s3g_complexity'),
            '$$CROSS_CHECK_JSON$$': self.analysis_json('s3h_cross_check'),
            '$$PREMISE_EXPANSION_JSON$$': self.analysis_json('s3_5_premise_expansion'),
            '$$PREMISE_EXPANSION_FIDELITY_JSON$$': self.analysis_json('s3_5v_fidelity_check'),
        }

    def run_craft_spine(self):
        """3.75 build, 3.75v audit, 3.75r repair on a flagged verdict, re-audit."""
        base = self.craft_spine_inputs()

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

    def run_step4(self, max_iterations, max_repair_beats):
        builder = Step4Builder(self, max_iterations=max_iterations,
                               max_repair_beats=max_repair_beats)
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
    parser.add_argument("--max-iterations", type=int, default=6,
                        help="step 4: maximum outline iterations (paths) to build (default 6)")
    parser.add_argument("--max-repair-beats", type=int, default=6,
                        help="step 4: maximum beats regenerated per review round (default 6)")
    parser.add_argument("--stop-after", default='',
                        help="stop after this step: 3, 3.5, 3.75 (default: run through step 4)")
    args = parser.parse_args()

    story_id = slugify(args.story_id)
    if not story_id:
        story_id = f'story_{int(time.time())}'

    gen = StoryGenerator(story_id=story_id, max_repairs=args.max_repairs,
                         repair_on_soft=args.repair_on_soft)

    print('enter kernel and close stdin:')

    gen.s1_take_kernel(sys.stdin.read())
    gen.s2_apply_rating(rating=args.rating)

    try:
        gen.run_phase3()
        if args.stop_after == '3':
            sys.exit(0)

        # 3.5: the first step that CONSTRUCTS. Turns a sparse kernel into a
        #  concrete premise before any world-building sees it. Verified by a
        #  separate call and repaired by a third; see run_verified_step.
        gen.run_premise_expansion()
        if args.stop_after == '3.5':
            sys.exit(0)

        # 3.75: craft devices over the verified premise, same loop shape.
        gen.run_craft_spine()
        if args.stop_after == '3.75':
            sys.exit(0)

        # step 4: the iterative outline build-out - framework and main path
        #  first, then one unexplored branch per iteration, each iteration
        #  reviewed as a whole story and repaired beat by beat.
        gen.run_step4(max_iterations=args.max_iterations,
                      max_repair_beats=args.max_repair_beats)
    except PipelineHalt as halt:
        print(f'\nPIPELINE HALTED: {halt}', file=sys.stderr)
        sys.exit(2)
