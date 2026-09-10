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
            filter_prompt = self.load_prompt('step2_filter.txt')

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
    def s3b_determine_affect(self):

        # load the affect
        self.s3b_affect = self.load_story_file('s3b_affect.json')
        if self.s3b_affect:
            self.s3b_affect = self.lenient_json_loads(self.s3b_affect)
            return
        
        # this step is to run an affect-extraction over the kernel
        affect_prompt = self.load_prompt('step3b_affect.txt')

        # now fill in the args
        affect_prompt = affect_prompt.replace('$$KERNEL$$',self.kernel)
        
        log_path = self.story_create_log('s3b')
        with open(log_path, "w", encoding="utf-8") as f:
            with contextlib.redirect_stdout(f):
                client = dynamic_config.get_client()
                (thinking,response) = client.run_prompt(affect_prompt)
                self.save_story_file('s3b_raw_output_thinking.txt', thinking)
                self.save_story_file('s3b_raw_output_response.txt', response)

                # validate the json
                self.s3b_affect = self.lenient_json_loads(response)
                self.save_story_file('s3b_affect.json',
                                     json.dumps(self.s3b_affect, indent=2, ensure_ascii=False))

    def s3c_determine_theme(self):

        # load the theme
        self.s3c_theme = self.load_story_file('s3c_theme.json')
        if self.s3c_theme:
            self.s3c_theme = self.lenient_json_loads(self.s3c_theme)
            return
        
        # this step is to run a theme-extraction over the kernel
        theme_prompt = self.load_prompt('step3c_theme.txt')

        # now fill in the args
        theme_prompt = theme_prompt.replace('$$KERNEL$$',self.kernel)
        
        log_path = self.story_create_log('s3c')
        with open(log_path, "w", encoding="utf-8") as f:
            with contextlib.redirect_stdout(f):
                client = dynamic_config.get_client()
                (thinking,response) = client.run_prompt(theme_prompt)
                self.save_story_file('s3c_raw_output_thinking.txt', thinking)
                self.save_story_file('s3c_raw_output_response.txt', response)

                # validate the json
                self.s3c_theme = self.lenient_json_loads(response)
                self.save_story_file('s3c_theme.json',
                                     json.dumps(self.s3c_theme, indent=2, ensure_ascii=False))

    def s3d_determine_viewpoint(self):

        # load the viewpoint
        self.s3d_viewpoint = self.load_story_file('s3d_viewpoint.json')
        if self.s3d_viewpoint:
            self.s3d_viewpoint = self.lenient_json_loads(self.s3d_viewpoint)
            return
        
        # this step is to run a viewpoint-extraction over the kernel
        viewpoint_prompt = self.load_prompt('step3d_viewpoint.txt')

        # now fill in the args
        viewpoint_prompt = viewpoint_prompt.replace('$$KERNEL$$',self.kernel)
        
        log_path = self.story_create_log('s3d')
        with open(log_path, "w", encoding="utf-8") as f:
            with contextlib.redirect_stdout(f):
                client = dynamic_config.get_client()
                (thinking,response) = client.run_prompt(viewpoint_prompt)
                self.save_story_file('s3d_raw_output_thinking.txt', thinking)
                self.save_story_file('s3d_raw_output_response.txt', response)

                # validate the json
                self.s3d_viewpoint = self.lenient_json_loads(response)
                self.save_story_file('s3d_viewpoint.json',
                                     json.dumps(self.s3d_viewpoint, indent=2, ensure_ascii=False))

    def s3e_determine_timeline(self):

        # load the timeline
        self.s3e_timeline = self.load_story_file('s3e_timeline.json')
        if self.s3e_timeline:
            self.s3e_timeline = self.lenient_json_loads(self.s3e_timeline)
            return
        
        # this step is to run a timeline-extraction over the kernel
        timeline_prompt = self.load_prompt('step3e_timeline.txt')

        # now fill in the args
        timeline_prompt = timeline_prompt.replace('$$KERNEL$$',self.kernel)
        
        log_path = self.story_create_log('s3e')
        with open(log_path, "w", encoding="utf-8") as f:
            with contextlib.redirect_stdout(f):
                client = dynamic_config.get_client()
                (thinking,response) = client.run_prompt(timeline_prompt)
                self.save_story_file('s3e_raw_output_thinking.txt', thinking)
                self.save_story_file('s3e_raw_output_response.txt', response)

                # validate the json
                self.s3e_timeline = self.lenient_json_loads(response)
                self.save_story_file('s3e_timeline.json',
                                     json.dumps(self.s3e_timeline, indent=2, ensure_ascii=False))
                
                
# So I think the process is going to be:
# 1) identify what our core assumptions are for the product
#    (interactive, second person, audience)
# 2*) get a kernel from the user
#    (a blurb containing as much information as the user wants to give
#     regarding the desired story)
#   a) filter kernel to required levels wrt audience
# 3) analyze the kernel to figure out core requirements
#   a) rough minimal and maximal length
#   b) affect extraction (primary, primary trajectory, secondaries, tone, somatic address, transgression level)
#   c) thematic extraction (core thematic axis, secondary thematic axis, moral valence)
#   d) rough viewpoint requirements (single person, multi-person hopping)
#   e) rough timeline requirements/bounds (single time, linear, multiple times, clusterd, ...)
#   f) rough setting requirements/bounds (single overall setting, multiple clustered, multiple dispersed)
#   g) complexity of interactivity (number of possible major endings)
# 4) initial structural shape
#   a) plot architecture (quest, investigation, caper, ...)
#   b) conflict type
#   c) protaganist configuration
#   d) scale of stakes
# 5) initial world shape
#   a) spatial settings
#   b) temporal settings
#   c) ontology / physics
#   d) cosmology / metaphysics
#   e) social order
#   f) technological texture
#   g) threat source
# 6) figure out overall structure
#   a) primary branch point is going to divide on the core thematic axis
#      (*what* they choose to believe) (2 choices)
#   b) secondary branch point is going to divide on *how* they choose to
#      follow the core thematic choice (2-4 choices)
#   c) now this will define between 4-8 main paths through the story
#   d) calculate framework (hero's journey, 5-act tragedy, ...)
#   e) expand framework beats + branches into initial story graph
#   f) identify 1-2 possible beats in graph before primary branch and
#      expand into diamond shaped subpaths, giving the user experiences
#      to inform primary branch decision
#   g) identify 1-2 possible beats in two paths steming from primary branch,
#      before secondary branch point.  replace those beats with diamond shaped
#      subgraphs, where the decisions made in those diamond branches will
#      directly force the users path in the secondary branch
#   h) ternary branch points (if used) will be more varied and relate to
#      the consequences of the two previous branch choices, including the toll
#      the what/how is taking on the character, or *who* the toll is inflicted
#      upon, or a change of conflict type / threat source.
# 7) world generation
#   a) major locations
#   b) location backstory
# 8) character generation
#   a) major characters
#   b) character roles, relations and backstory
# 9) plot generation 
#   a) fill in structure from 6 using major locations and major characters
#   b) ensure consistency in path-based use of locations and characters
#   c) ensure major story requirements met (primary affect, resolution of plot, user agency)
# 10) identify shortcomings
#   a) pacing, character arcs, unaddressed plot references
#   b) introduce new minor events, locations and characters to address these
#   c) identify coherence or (opposite=lack of novelty) and address by adding elements to either reinforce coherence or add novelty
#   d) update story structure to incorporate these new elements
# 11) deep expansion of characters (no new characters, just full build out of existing)
# 12) deep expansion of settings (build out of existing + definition and build out of minor areas like the parts of a larger setting)
# 13) full node-based graph finalization pass
# 14) for each node in graph, identify granular settings available (rooms) and characters directly involved.  Identify purpose of node, what needs to be achieved by it and possible quick exits (bad ends).
# 15) ... (probably node-node transition point identification)
# 16) for each node, full node build out (room connections, interactable objects, goals, transition states to next node or branch)... ensure arc/theme/affect trajectory
# 17) for each node fully define actions in each room, generate prose

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
    gen.s3b_determine_affect()
    gen.s3c_determine_theme()
    gen.s3d_determine_viewpoint()
    gen.s3e_determine_timeline()

