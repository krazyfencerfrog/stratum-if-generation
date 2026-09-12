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
    def s3a_determine_length(self):
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
        '$$VIEWPOINT_EXCURSIONS_JSON$$': json.dumps(gen.analysis['s3d_viewpoint'],
                                                    indent=2,
                                                    ensure_ascii=False),
        '$$KERNEL$$': gen.kernel
    })
    gen.run_prompt('s3g','complexity',replace_kernel_only)

