"""The condition language: small, safe, and checkable before play.

Ported from the old stratum-if engine (engine/state/predicates.py) and
extended for the world model. An expression is parsed once with Python's
`ast` and walked by a whitelist evaluator: no attribute access beyond the
namespaces below, no calls beyond the helper functions, no imports, no
indexing. A story's conditions can therefore be validated statically
(every flag, stat, state, object, room and scene they name must exist)
before anyone plays it.

    flags.saw_captain                    a flag (unset flags are false)
    stats.lamp_oil >= 2                  a stat (unset stats are 0)
    not flags.crack_plugged and stats.x > 1
    pattern('lazlo_nerve', 'down', 3, 0.75)   an arc state moved at least 3 times,
                                              at least 75% of the moves 'down'
    moved('lazlo_nerve')                 how many times the state moved (a number)
    has('logbook')                       the player carries it
    at('cabin')                          the player is in that room
    here('lazlo')                        that character is in the player's room
    in_scene('S04')                      the current scene
    visited('wheelhouse')                the room (or scene) has been entered before
    turns, turns_in_scene                actions taken, in total and in this scene
    d(20), chance(0.3)                   deterministic randomness (seeded per step)
"""

import ast
import operator
import random

COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Gt: operator.gt, ast.GtE: operator.ge,
           ast.Lt: operator.lt, ast.LtE: operator.le}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
          ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod}
NAMES = ('turns', 'turns_in_scene', 'True', 'False', 'true', 'false')
FUNCTIONS = ('pattern', 'moved', 'has', 'at', 'here', 'in_scene', 'visited', 'd', 'chance')
NAMESPACES = ('flags', 'stats')


class ExpressionError(ValueError):
    pass


_cache = {}


def parse(text):
    text = str(text if text is not None else 'true').strip() or 'true'
    if text not in _cache:
        try:
            _cache[text] = ast.parse(text, mode='eval').body
        except SyntaxError as e:
            raise ExpressionError(f'syntax error in {text!r}: {e.msg}')
    return _cache[text]


def evaluate(text, state):
    """True or false (or a number, for arithmetic) for `text` in `state`."""
    rng = random.Random(f'{state.seed}|{text}')
    return _eval(parse(text), state, rng, text)


def _eval(node, state, rng, text):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == 'turns':
            return state.turns
        if node.id == 'turns_in_scene':
            return state.turns_in_scene
        if node.id in ('True', 'true'):
            return True
        if node.id in ('False', 'false'):
            return False
        raise ExpressionError(f'unknown name {node.id!r} in {text!r}')
    if isinstance(node, ast.Attribute):
        if not isinstance(node.value, ast.Name) or node.value.id not in NAMESPACES:
            raise ExpressionError(f'only flags.<name> and stats.<name> may be read, in {text!r}')
        if node.value.id == 'flags':
            return bool(state.flags.get(node.attr, False))
        return state.stat(node.attr)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval(v, state, rng, text) for v in node.values)
        return any(_eval(v, state, rng, text) for v in node.values)
    if isinstance(node, ast.UnaryOp):
        value = _eval(node.operand, state, rng, text)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        raise ExpressionError(f'unsupported operator in {text!r}')
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        return BINARY[type(node.op)](_eval(node.left, state, rng, text), _eval(node.right, state, rng, text))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, state, rng, text)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in COMPARE:
                raise ExpressionError(f'unsupported comparison in {text!r}')
            right = _eval(comparator, state, rng, text)
            if not COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
        args = [_eval(a, state, rng, text) for a in node.args]
        return _call(node.func.id, args, state, rng, text)
    raise ExpressionError(f'unsupported expression ({type(node).__name__}) in {text!r}')


def pattern_holds(up, down, direction, at_least, share):
    moves = up + down
    agree = down if direction == 'down' else up
    return moves >= at_least and moves > 0 and agree / moves >= share


def _call(name, args, state, rng, text):
    try:
        if name == 'pattern':
            state_name, direction, at_least, share = args
            up, down = state.arc(state_name)
            return pattern_holds(up, down, direction, at_least, share)
        if name == 'moved':
            up, down = state.arc(args[0])
            return up + down
        if name == 'has':
            return state.locations.get(args[0]) == 'player'
        if name == 'at':
            return state.room == args[0]
        if name == 'here':
            return state.where_is(args[0]) == state.room
        if name == 'in_scene':
            return state.scene == args[0]
        if name == 'visited':
            return args[0] in state.visited
        if name == 'd':
            return rng.randint(1, int(args[0]))
        if name == 'chance':
            return rng.random() < float(args[0])
    except (TypeError, ValueError) as e:
        raise ExpressionError(f'bad arguments to {name}() in {text!r}: {e}')
    raise ExpressionError(f'unknown function {name!r} in {text!r}')


def references(text):
    """What an expression names, for static validation: {'flags': set,
    'stats': set, 'states': set, 'objects': set, 'rooms': set, 'chars': set,
    'scenes': set}. Raises ExpressionError on anything the evaluator would
    refuse."""
    refs = {k: set() for k in ('flags', 'stats', 'states', 'objects', 'rooms', 'chars', 'scenes', 'visited')}
    tree = parse(text)

    def walk(node):
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or node.value.id not in NAMESPACES:
                raise ExpressionError(f'only flags.<name> and stats.<name> may be read, in {text!r}')
            refs[node.value.id].add(node.attr)
            return
        if isinstance(node, ast.Name):
            if node.id not in NAMES:
                raise ExpressionError(f'unknown name {node.id!r} in {text!r}')
            return
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS):
                raise ExpressionError(f'unknown function in {text!r}')
            first = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            target = {'pattern': 'states', 'moved': 'states', 'has': 'objects', 'at': 'rooms', 'here': 'chars',
                      'in_scene': 'scenes', 'visited': 'visited'}.get(node.func.id)
            if target and first is not None:
                refs[target].add(first)
            if node.func.id == 'pattern':
                if len(node.args) != 4:
                    raise ExpressionError(f"pattern() takes (state, 'up'|'down', at_least, share), in {text!r}")
                direction = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
                if direction not in ('up', 'down'):
                    raise ExpressionError(f"pattern() direction must be 'up' or 'down', in {text!r}")
            for a in node.args:
                walk(a)
            return
        allowed = (ast.Constant, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Compare, ast.And, ast.Or, ast.Not, ast.USub,
                   ast.Load, *COMPARE, *BINARY)
        if not isinstance(node, allowed):
            raise ExpressionError(f'unsupported expression ({type(node).__name__}) in {text!r}')
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return refs
