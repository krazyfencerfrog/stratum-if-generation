"""Unit tests for Genre Craft System and dynamic extraction unification."""

import os
import sys
import shutil
import unittest
from pathlib import Path

# Add generator directory to path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, '..'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'generator'))

import genre
import main as gen_main


class TestGenrePacks(unittest.TestCase):
    def setUp(self):
        genre.clear_cache()

    def test_available_genres(self):
        genres = genre.available_genres()
        self.assertIn('general', genres)

    def test_load_components(self):
        # General pack components are all present and non-empty
        for c in ('RULES', 'PROMISES', 'PREMISE', 'TURNS', 'CASTING', 'SETTINGS', 'OPTIONS', 'PROSE', 'JUDGES'):
            content = genre.load_component('general', c)
            self.assertGreater(len(content), 20, f"Component {c} missing or too short in general pack")

        gen_rules = genre.load_component('general', 'RULES')
        self.assertIn('GENERAL INTERACTIVE FICTION RULES', gen_rules)

        gen_casting = genre.load_component('general', 'CASTING')
        self.assertIn('DISTINCT AGENTS', gen_casting)
        self.assertIn('BREAKING POINTS', gen_casting)

        gen_premise = genre.load_component('general', 'PREMISE')
        self.assertIn('ACTIVE OPPOSITION', gen_premise)

        gen_turns = genre.load_component('general', 'TURNS')
        self.assertIn('ESCALATING TENSION', gen_turns)

    def test_fallback_behavior(self):
        # Test loading from any genre falls back to general
        for g in ('romance', 'fantasy_adventure', 'sci_fi', 'court_intrigue', 'ghost_story', 'non_existent_genre'):
            fallback_rules = genre.load_component(g, 'RULES')
            self.assertIn('GENERAL INTERACTIVE FICTION RULES', fallback_rules)
            fallback_casting = genre.load_component(g, 'CASTING')
            self.assertIn('DISTINCT AGENTS', fallback_casting)

    def test_macro_expansion(self):
        text = "Prefix: $$GENRE_RULES$$ and $$GENRE_CASTING$$."
        expanded = genre.expand(text, 'romance')
        self.assertNotIn('$$GENRE_', expanded)
        self.assertIn('GENERAL INTERACTIVE FICTION RULES', expanded)
        self.assertIn('DISTINCT AGENTS', expanded)

    def test_generator_genre_override(self):
        story_id = 'test_genre_override'
        story_path = Path(REPO_ROOT) / 'stories' / story_id
        shutil.rmtree(story_path, ignore_errors=True)
        try:
            gen = gen_main.StoryGenerator(story_id=story_id, genre='romance')
            self.assertEqual(gen.genre, 'romance')
            gen.kernel = "A romance at a seaside hotel."
            parsed = gen.s2_classify_genre()
            self.assertEqual(parsed['genre'], 'romance')
            self.assertEqual(gen.genre, 'romance')

            # Prompt expansion uses general craft rules via fallback
            prompt = gen.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt)
            self.assertIn('GENERAL READER PROMISES GUIDELINES', prompt)
        finally:
            shutil.rmtree(story_path, ignore_errors=True)

    def test_generator_auto_classify_stub(self):
        story_id = 'test_genre_auto'
        story_path = Path(REPO_ROOT) / 'stories' / story_id
        shutil.rmtree(story_path, ignore_errors=True)
        try:
            os.environ['STRATUM_CLIENT'] = 'stub'
            gen = gen_main.StoryGenerator(story_id=story_id)
            gen.kernel = "An epic quest with a hedge-witch to stop an old dragon."
            parsed = gen.s2_classify_genre()
            self.assertEqual(parsed['genre'], 'fantasy_adventure')
            self.assertEqual(gen.genre, 'fantasy_adventure')

            # Prompt expansion cleanly replaces genre macros
            prompt = gen.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt)
            self.assertIn('GENERAL READER PROMISES GUIDELINES', prompt)

            # Test sci_fi
            gen_sci = gen_main.StoryGenerator(story_id=f'{story_id}_scifi')
            gen_sci.kernel = "A hard sci-fi story on a generational ship where you play as the ship's AI."
            parsed_sci = gen_sci.s2_classify_genre()
            self.assertEqual(parsed_sci['genre'], 'sci_fi')
            prompt_sci = gen_sci.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt_sci)
            self.assertIn('GENERAL READER PROMISES GUIDELINES', prompt_sci)

            # Test court_intrigue
            gen_court = gen_main.StoryGenerator(story_id=f'{story_id}_court')
            gen_court.kernel = "Court intrigue. You're the tutor to a child king whose uncle, the regent, plots usurpation."
            parsed_court = gen_court.s2_classify_genre()
            self.assertEqual(parsed_court['genre'], 'court_intrigue')
            prompt_court = gen_court.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt_court)
            self.assertIn('GENERAL READER PROMISES GUIDELINES', prompt_court)

            # Test ghost_story
            gen_ghost = gen_main.StoryGenerator(story_id=f'{story_id}_ghost')
            gen_ghost.kernel = "A ghost story on an inherited canal boat with a ghost captain."
            parsed_ghost = gen_ghost.s2_classify_genre()
            self.assertEqual(parsed_ghost['genre'], 'ghost_story')
            prompt_ghost = gen_ghost.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt_ghost)
            self.assertIn('GENERAL READER PROMISES GUIDELINES', prompt_ghost)
        finally:
            for s in ('', '_scifi', '_court', '_ghost'):
                shutil.rmtree(Path(REPO_ROOT) / 'stories' / f'{story_id}{s}', ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
