"""Game state: everything that changes during play, and nothing else.

The story package is read-only; this is the part a save holds and a rewind
restores. Arc states are kept as two counts (up and down), not a net value,
so a condition can ask for a pattern of play rather than a sum.
"""

import copy
import random


class GameState:
    def __init__(self):
        self.scene = None             # current scene id
        self.room = None              # the player's room
        self.ending = None            # set when an ending is reached
        self.flags = {}
        self.stats = {}
        self.arcs = {}                # state name -> {'up': n, 'down': n}
        self.locations = {}           # object id -> room id, character id, 'player' or None
        self.placements = {}          # character id -> room id (set by the scene)
        self.visited = set()          # rooms and scenes entered
        self.used = set()             # interaction ids of `once` interactions already used
        self.fired = set()            # event and nudge ids already fired
        self.turns = 0
        self.turns_in_scene = 0
        self.idle = 0                 # actions in this scene since one last changed anything
        self.seed = random.random()

    # ------------------------------------------------------------ reads

    def arc(self, name):
        a = self.arcs.get(name) or {}
        return a.get('up', 0), a.get('down', 0)

    def stat(self, name):
        """A stat; `<state>_up` and `<state>_down` read an arc state's counts."""
        for direction in ('up', 'down'):
            base = name[:-len(direction) - 1]
            if name.endswith('_' + direction) and base in self.arcs:
                return self.arcs[base].get(direction, 0)
        return self.stats.get(name, 0)

    def where_is(self, character_id):
        return self.placements.get(character_id)

    # ------------------------------------------------------------ writes

    def move_arc(self, name, direction):
        a = self.arcs.setdefault(name, {'up': 0, 'down': 0})
        a['up' if direction == 'up' else 'down'] += 1

    def new_seed(self):
        self.seed = random.random()

    # ------------------------------------------------------------ saves

    def clone(self):
        return copy.deepcopy(self)

    def to_dict(self):
        return {'scene': self.scene, 'room': self.room, 'ending': self.ending, 'flags': dict(self.flags),
                'stats': dict(self.stats), 'arcs': copy.deepcopy(self.arcs), 'locations': dict(self.locations),
                'placements': dict(self.placements), 'visited': sorted(self.visited), 'used': sorted(self.used),
                'fired': sorted(self.fired), 'turns': self.turns, 'turns_in_scene': self.turns_in_scene,
                'idle': self.idle, 'seed': self.seed}

    @staticmethod
    def from_dict(data):
        s = GameState()
        for key in ('scene', 'room', 'ending', 'turns', 'turns_in_scene', 'idle', 'seed'):
            setattr(s, key, data.get(key, getattr(s, key)))
        s.flags = dict(data.get('flags') or {})
        s.stats = dict(data.get('stats') or {})
        s.arcs = copy.deepcopy(data.get('arcs') or {})
        s.locations = dict(data.get('locations') or {})
        s.placements = dict(data.get('placements') or {})
        s.visited = set(data.get('visited') or [])
        s.used = set(data.get('used') or [])
        s.fired = set(data.get('fired') or [])
        return s
