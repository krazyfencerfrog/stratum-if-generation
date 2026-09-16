#!/usr/bin/python

import os
import sys
import time
import re
import json
import argparse
import contextlib
from pathlib import Path
import dynamic_config

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_DIR = os.path.join(THIS_DIR, "..", "prompts")

# the phase-3 extraction steps, in the order they run, paired with the short
#  field id the later prompts (3h, 3.5, 6.0) refer to them by
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

def print_usage():
    print("hello")

class StoryGenerator:
    def __init__(self, story_id):
        self.story_id = story_id

        # figure out story dir and make it if needed
        self.story_path_str = os.path.join(THIS_DIR, "..", "stories", self.story_id)
        self.story_path = Path(self.story_path_str)
        self.story_path.mkdir(parents=True, exist_ok=True)
        
        # set defaults, if resuming the specific stage will load from file
        self.kernel = None
        self.rating = DEFAULT_RATING
        self.analysis = dict()

    def load_story_file(self, file_suffix):
        value = ''
        path_str = os.path.join(self.story_path_str,
                                f'{self.story_id}_{file_suffix}')
        path = Path(path_str)
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                value = f.read()
            if not value:
                raise ValueError(
                    f"{path_str} exists, but not loaded with valid value"
                )
        return value

    def save_story_file(self, file_suffix, value):
        path_str = os.path.join(self.story_path_str,
                                f'{self.story_id}_{file_suffix}')
        path = Path(path_str)
        with open(path, "w", encoding="utf-8") as f:
            f.write(value)

    def story_create_log(self, file_suffix):
        file_suffix = f"{file_suffix}_{int(time.time()*1000)}.log"
        path_str = os.path.join(self.story_path_str,
                                f'{self.story_id}_{file_suffix}')
        path = Path(path_str)
        return path
            
    def load_prompt(self, file_name):
        value = ''
        with open(os.path.join(PROMPT_DIR, file_name), encoding="utf-8") as f:
            value = f.read()
        if not value:
            raise ValueError(
                f"prompt {file_name} not found (or empty) in prompt directory {PROMPT_DIR}"
                )
        return value

    def lenient_json_loads(self, text):
        """Tries a straight parse first; on failure, repairs the most common
        small-model slip-ups (smart quotes, trailing commas) and tries once
        more. Lets the second attempt's error propagate if it still fails, so
        the caller sees a real json.JSONDecodeError with a useful message."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        cleaned = text
        cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
        cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # trailing commas
        return json.loads(cleaned)
    
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
        
    def s3(self):
        pass

    def analysis_json(self, member_name, indent=2):
        """Pretty-printed JSON for one saved step's output, for substitution
        into a later step's prompt. Returns "none" when the step hasn't run,
        which every consuming prompt is written to tolerate."""
        value = self.analysis.get(member_name)
        if value is None:
            return 'none'
        return json.dumps(value, indent=indent, ensure_ascii=False)

    def step3_bundle_json(self):
        """All nine phase-3 extractions as one object keyed by field id.
        3h, 3.5 and 6.0 each take the whole bundle rather than nine
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

    def run_prompt(self,
                   prefix,
                   name,
                   replacement_mapping,
                   is_json=True):

        # load the value from previous run
        output_file_name = f'{prefix}_{name}.{"json" if is_json else "txt"}'
        output_member_name = f'{prefix}_{name}'
        prompt_file_name = f'{prefix}_{name}.prompt'
        print(f'out: {output_file_name}')
        val = self.load_story_file(output_file_name)
        if val:
            if is_json:
                self.analysis[output_member_name] = self.lenient_json_loads(val)
            else:
                self.analysis[output_member_name] = val
            return
        
        # load the prompt
        prompt = self.load_prompt(prompt_file_name)

        # now fill in the args
        for k,v in replacement_mapping.items():
            prompt = prompt.replace(k,v)
        
        log_path = self.story_create_log(prefix)
        with open(log_path, "w", encoding="utf-8") as f:
            with contextlib.redirect_stdout(f):
                client = dynamic_config.get_client()
                (thinking,response) = client.run_prompt(prompt)
                self.save_story_file(f'{prefix}_raw_output_thinking.txt', thinking)
                self.save_story_file(f'{prefix}_raw_output_response.txt', response)

                if is_json:
                    # validate the json
                    self.analysis[output_member_name] = self.lenient_json_loads(response)
                    self.save_story_file(output_file_name,
                                         json.dumps(self.analysis[output_member_name], indent=2, ensure_ascii=False))
                else:
                    self.analysis[output_member_name] = response
                    self.save_story_file(output_file_name, self.analysis[output_member_name])
                
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
    args = parser.parse_args()

    story_id = slugify(args.story_id)
    if not story_id:
        story_id = f'story_{int(time.time())}'
    
    gen = StoryGenerator(story_id=story_id)
    
    print('enter kernel and close stdin:')

    gen.s1_take_kernel(sys.stdin.read())
    gen.s2_apply_rating(rating=args.rating)

    replace_kernel_only = {'$$KERNEL$$': gen.kernel}
    gen.run_prompt('s3_0a','interactive_question',replace_kernel_only)
    gen.run_prompt('s3_0b','identity_epistemic',replace_kernel_only)
    gen.run_prompt('s3_0c', 'consequence_failure_model',replace_kernel_only)
    gen.run_prompt('s3b','affect',replace_kernel_only)
    gen.run_prompt('s3c','theme',replace_kernel_only)
    gen.run_prompt('s3d','viewpoint',replace_kernel_only)    
    gen.run_prompt('s3e','timeline',replace_kernel_only)
    gen.run_prompt('s3f','setting', {
        '$$VIEWPOINT_EXCURSIONS_JSON$$': gen.analysis_json('s3d_viewpoint'),
        '$$KERNEL$$': gen.kernel
    })

    # 3g is chained, not blind: branching density and tracked state aren't
    #  well-defined without knowing what the player decides (3-0a) and what
    #  the engine has to recognize as failure (3-0c). Chain only where a
    #  field is undefined without the other's output - never for agreement.
    gen.run_prompt('s3g','complexity', {
        '$$INTERACTIVE_QUESTION_JSON$$': gen.analysis_json('s3_0a_interactive_question'),
        '$$FAILURE_MODEL_JSON$$': gen.analysis_json('s3_0c_consequence_failure_model'),
        '$$KERNEL$$': gen.kernel
    })

    # 3h: the phase's own cross-check. Classification only - it names
    #  conflicts between the nine blind extractions and picks what the
    #  primary branch point is built from; it fixes nothing.
    step3_bundle = gen.step3_bundle_json()
    gen.run_prompt('s3h','cross_check', {
        '$$STEP3_BUNDLE_JSON$$': step3_bundle,
        '$$KERNEL$$': gen.kernel
    })

    # constraint map: computed, not judged - sorts every extracted judgment
    #  into constraint / default / free and sizes 3.5's enrichment budget.
    constraint_map = gen.build_constraint_map()

    # 3.5: the first step that CONSTRUCTS. Turns a sparse kernel into a
    #  concrete premise before any world-building sees it.
    gen.run_prompt('s3_5','premise_expansion', {
        '$$STEP3_BUNDLE_JSON$$': step3_bundle,
        '$$CONSTRAINT_MAP_JSON$$': constraint_map,
        '$$CROSS_CHECK_JSON$$': gen.analysis_json('s3h_cross_check'),
        '$$AVOID_LIST$$': 'none',
        '$$KERNEL$$': gen.kernel
    })

    # 3.5's verification, deliberately a separate call: generation and
    #  audit in one prompt means the audit half loses.
    gen.run_prompt('s3_5v','fidelity_check', {
        '$$CONSTRAINT_MAP_JSON$$': constraint_map,
        '$$PREMISE_EXPANSION_JSON$$': gen.analysis_json('s3_5_premise_expansion'),
        '$$KERNEL$$': gen.kernel
    })

    # steps 4 and 5 (structural shape, world shape) slot in here once built.

    # 6.0: topology and state model. An INPUT to step 6, not a sub-step of
    #  it - several kernels can't be built as a lattice at all.
    gen.run_prompt('s6_0','state_topology', {
        '$$STEP3_BUNDLE_JSON$$': step3_bundle,
        '$$PREMISE_EXPANSION_JSON$$': gen.analysis_json('s3_5_premise_expansion'),
        '$$KERNEL$$': gen.kernel
    })

