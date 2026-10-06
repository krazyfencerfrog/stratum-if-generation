"""Shared definitions for the prompts (prompts/terms.txt).

A prompt writes $$TERM_PRICE$$ and gets the PRICE section whole, so one
meaning (the price is not a way to lose; what a system the engine lacks
is) is written once and every step that uses it reads the same words. On
2026-10-06 the premise builder was taught that a contract's breach is the
story's price while the audit, which defined the same thing in its own
words, read it as a way to lose and halted the run.
"""

import os
import re

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prompts', 'terms.txt')
SECTION = re.compile(r'^=== ([A-Z_]+) ===\s*$', re.M)
TERM = re.compile(r'\$\$TERM_([A-Z_]+)\$\$')
_cache = {}


def load(path=PATH):
    if path not in _cache:
        with open(path, encoding='utf-8') as f:
            text = '\n'.join(l for l in f.read().splitlines() if not l.startswith('#'))
        parts = SECTION.split(text)
        _cache[path] = {name: body.strip() for name, body in zip(parts[1::2], parts[2::2])}
    return _cache[path]


def expand(text, path=PATH):
    """Every $$TERM_X$$ replaced by section X; an unknown term raises."""
    terms = load(path)

    def one(m):
        if m.group(1) not in terms:
            raise ValueError(f'no section {m.group(1)} in {path} (have {sorted(terms)})')
        return terms[m.group(1)]
    return TERM.sub(one, text)
