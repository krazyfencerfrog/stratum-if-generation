"""Unit tests for Modular Genre Craft Packs (Issue #53)."""

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
        self.assertIn('romance', genres)
        self.assertIn('fantasy_adventure', genres)

    def test_load_components(self):
        # Romance pack
        romance_rules = genre.load_component('romance', 'RULES')
        self.assertIn('ROMANCE CRAFT RULES', romance_rules)
        self.assertIn('FRUITION', romance_rules)

        romance_casting = genre.load_component('romance', 'CASTING')
        self.assertIn('BREAKING POINT DISCIPLINE', romance_casting)
        self.assertIn('RIVAL', romance_casting)

        # Fantasy adventure pack
        fantasy_rules = genre.load_component('fantasy_adventure', 'RULES')
        self.assertIn('FANTASY ADVENTURE CRAFT RULES', fantasy_rules)
        self.assertIn('EXPEDITION', fantasy_rules)

        fantasy_promises = genre.load_component('fantasy_adventure', 'PROMISES')
        self.assertIn('Campfire on the Road', fantasy_promises)
        self.assertIn('dragon', fantasy_promises.lower())

        # General pack
        gen_rules = genre.load_component('general', 'RULES')
        self.assertIn('GENERAL INTERACTIVE FICTION RULES', gen_rules)

    def test_fallback_behavior(self):
        # Test loading from a non-existent genre falls back to general
        fallback_rules = genre.load_component('non_existent_genre', 'RULES')
        self.assertIn('GENERAL INTERACTIVE FICTION RULES', fallback_rules)

    def test_macro_expansion(self):
        text = "Prefix: $$GENRE_RULES$$ and $$GENRE_CASTING$$."
        expanded = genre.expand(text, 'romance')
        self.assertNotIn('$$GENRE_', expanded)
        self.assertIn('ROMANCE CRAFT RULES', expanded)
        self.assertIn('BREAKING POINT DISCIPLINE', expanded)

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

            # Prompt expansion uses romance genre
            prompt = gen.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt)
            self.assertIn('ROMANCE READER PROMISES GUIDELINES', prompt)
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

            # Prompt expansion uses fantasy_adventure genre
            prompt = gen.load_prompt('s3_4_promises.prompt')
            self.assertNotIn('$$GENRE_', prompt)
            self.assertIn('FANTASY ADVENTURE READER PROMISES GUIDELINES', prompt)
        finally:
            shutil.rmtree(story_path, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
