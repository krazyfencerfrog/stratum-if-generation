"""Catches output copied from a prompt's calibration examples.

On 2026-10-02 a looping model's forced answer filled a kernel1 premise
with the 3.5 prompts' newspaper example (its question, levers, turns and
cast), and nothing caught it: the computed checks counted complications
and the thinking-off audit passed it. A copy is a lookup, so it is
computed here.

The test: collect the distinctive 4-word phrases (two or more content words) that appear in a prompt's examples
(from its CALIBRATION / ILLUSTRATION heading to its input section), drop
any that also appear in the prompt's own instructions or in the inputs the
call legitimately draws on (kernel, brief, upstream material), and count
how many of the rest the output reuses. Distinct shared phrases at or
above MIN_HITS is a copy.
"""

import os
import re

N = 4
MIN_HITS = 8      # clean outputs score 0-3 (borrowed stock phrasing); a copied premise scored 280
WORD = re.compile(r"[a-z0-9']+")
PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'prompts')
_cache = {}


def words(text):
    return WORD.findall(str(text).lower())


STOP = set("""about after again against also because been before being between both could does doing down during each
from further have having here into just like more most much once only other over same should some such than that their
them then there these they this those through under until very what when where which while will with would your yours
you the and for are but not all any can had has her him his how its may our out own she too was who why""".split())


def content(word):
    return len(word) >= 4 and word not in STOP


def ngrams(text, n=N):
    """Distinctive 4-word phrases: at least two content words, so stock
    phrasing ("by the end you", "it has cost a") never counts."""
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1) if sum(content(x) for x in w[i:i + n]) >= 2}


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def split_prompt(text):
    """(instructions, examples) of a prompt template."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.match(r'\s*(---\s*)?(CALIBRATION|ILLUSTRATION)', l)), None)
    if start is None:
        return text, ''
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith('--- THE') or lines[i].startswith('USER INPUT FOLLOWS') or '$$' in lines[i]),
               len(lines))
    return '\n'.join(lines[:start] + lines[end:]), '\n'.join(lines[start:end])


def example_phrases(prompt_files):
    """4-grams that occur in the examples of these prompts and nowhere in
    their instructions."""
    key = tuple(prompt_files)
    if key not in _cache:
        examples, instructions = set(), set()
        for pf in prompt_files:
            with open(os.path.join(PROMPT_DIR, pf), encoding='utf-8') as f:
                ins, ex = split_prompt(f.read())
            examples |= ngrams(ex)
            instructions |= ngrams(ins)
        _cache[key] = examples - instructions
    return _cache[key]


def copied_phrases(output, prompt_files, context_texts=()):
    """The example phrases this output reuses that its context does not
    explain, sorted; a copy when len(result) >= MIN_HITS."""
    allowed = set()
    for t in context_texts:
        allowed |= ngrams(t)
    out = set()
    for s in strings(output):
        out |= ngrams(s)
    return sorted(' '.join(g) for g in (out & example_phrases(prompt_files)) - allowed)


# ---------------------------------------------------------------- the brief's own wording

BRIEF_N = 5
BRIEF_TEXT_KEYS = ('label', 'description', 'role', 'pole_a', 'pole_b', 'best_case', 'worst_case')


def brief_phrases(brief, n=BRIEF_N):
    """The distinctive n-word phrases of the brief's free-text fields (the
    decision axis and its description, the thematic poles, the protagonist
    role): phase 3's analytic wording, which is not the story's."""
    out = set()
    for entry in ((brief or {}).get('fields') or {}).values():
        if not isinstance(entry, dict):
            continue
        for key in BRIEF_TEXT_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and len(value.split()) >= n:
                out |= ngrams(value, n)
    return out


def brief_echoes(output, brief, n=BRIEF_N):
    """Phrases of n or more words copied from the brief's analytic text
    into a construction output ("the sword's stated desire to be returned"
    became a lever, then a phrase in every node). Sorted, longest first,
    overlapping shorter matches dropped."""
    wanted = brief_phrases(brief, n)
    if not wanted:
        return []
    hits = []
    for s in strings(output):
        w = words(s)
        i = 0
        while i <= len(w) - n:
            if tuple(w[i:i + n]) in wanted:
                j = i + n
                while j < len(w) and tuple(w[j - n + 1:j + 1]) in wanted:
                    j += 1
                hits.append(' '.join(w[i:j]))
                i = j
            else:
                i += 1
    return sorted(set(hits), key=lambda h: (-len(h), h))



def repeated_tics(path_texts, new_ids, exempt_texts=(), min_nodes=3, name_words=()):
    """Verbal tics along one path a player reads: phrases in at least
    `min_nodes` of its node summaries, at least one of them new ("the boat
    slips into the current" three times). path_texts is [(node id, summary)]
    in path order. Phrases that occur in exempt_texts (the kernel, the
    premise, the cast's names and labels: the story's own nouns, like "the
    black name stone") do not count; nor does repetition across lines, which
    no single player reads; nor do phrases with fewer than two content words
    outside people's names ("Euphemia Thackeray watches the"). Returns
    [(phrase, [node ids])], most repeated first."""
    names = {w.lower().replace("'s", '') for w in name_words}
    exempt = set()
    for t in exempt_texts:
        exempt |= ngrams(t)
    where = {}
    for nid, text in path_texts:
        for g in ngrams(text.replace("'s ", ' ')):
            where.setdefault(g, []).append(nid)
    out = []
    for g, ids in where.items():
        ids = sorted(set(ids))
        if sum(1 for w in g if content(w) and w not in names) < 2:
            continue
        if len(ids) >= min_nodes and set(ids) & set(new_ids) and g not in exempt:
            out.append((' '.join(g), ids))
    out.sort(key=lambda x: -len(x[1]))
    return out
