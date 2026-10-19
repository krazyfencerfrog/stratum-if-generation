"""Modular Genre Craft Packs for the Stratum IF pipeline (Issue #53).

Loads genre-specific craft rules, tropes, dilemma shapes, somatic channels,
and companion dynamics from prompts/genres/<genre_id>/, with automatic
cascading fallback to prompts/genres/general/.
"""

import os
import re
from typing import Dict, List, Optional

GENRES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prompts', 'genres')
GENRE_MACRO = re.compile(r'\$\$GENRE_([A-Z_]+)\$\$')

# Standard component files expected in each genre pack
COMPONENTS = {
    'RULES': 'genre_rules.txt',
    'PROMISES': 'promises.txt',
    'PREMISE': 'premise.txt',
    'TURNS': 'turns.txt',
    'CASTING': 'casting.txt',
    'SETTINGS': 'settings.txt',
    'OPTIONS': 'options.txt',
    'PROSE': 'prose.txt',
    'JUDGES': 'judges.txt',
}

_cache: Dict[str, Dict[str, str]] = {}


def available_genres(genres_dir: str = GENRES_DIR) -> List[str]:
    """Returns list of genre identifiers found in prompts/genres/."""
    if not os.path.isdir(genres_dir):
        return []
    return sorted([
        d for d in os.listdir(genres_dir)
        if os.path.isdir(os.path.join(genres_dir, d)) and not d.startswith('.')
    ])


def load_component(genre_id: str, component_key: str, genres_dir: str = GENRES_DIR) -> str:
    """Loads a specific component file for a genre, falling back to 'general'."""
    filename = COMPONENTS.get(component_key.upper(), f"{component_key.lower()}.txt")
    genre_id = (genre_id or 'general').lower().strip()

    # 1. Try target genre pack
    target_path = os.path.join(genres_dir, genre_id, filename)
    if os.path.isfile(target_path):
        with open(target_path, encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                return content

    # 2. Fall back to general pack (if target wasn't already general)
    if genre_id != 'general':
        general_path = os.path.join(genres_dir, 'general', filename)
        if os.path.isfile(general_path):
            with open(general_path, encoding='utf-8') as f:
                return f.read().strip()

    return ""


def load_pack(genre_id: str = 'general', genres_dir: str = GENRES_DIR) -> Dict[str, str]:
    """Loads all components for a genre pack into a dictionary."""
    genre_id = (genre_id or 'general').lower().strip()
    cache_key = f"{genres_dir}:{genre_id}"
    if cache_key not in _cache:
        pack = {}
        for comp_key in COMPONENTS:
            pack[comp_key] = load_component(genre_id, comp_key, genres_dir)
        _cache[cache_key] = pack
    return _cache[cache_key]


def expand(text: str, genre_id: str = 'general', genres_dir: str = GENRES_DIR) -> str:
    """Replaces every $$GENRE_X$$ macro in text with the corresponding component for genre_id."""
    if not text or '$$GENRE_' not in text:
        return text

    genre_id = (genre_id or 'general').lower().strip()

    def replace_macro(match):
        comp_key = match.group(1)
        val = load_component(genre_id, comp_key, genres_dir)
        return val

    return GENRE_MACRO.sub(replace_macro, text)


def clear_cache():
    """Clears the in-memory genre pack cache (used in tests)."""
    _cache.clear()
