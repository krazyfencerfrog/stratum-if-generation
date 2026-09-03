#!/usr/bin/python

class Axis:
    def __init__(self, category, name, description, examples):
        self.category = category
        self.name = name
        self.description = description
        self.examples = examples
        
class FeatureSpace:
    def __init__(self):
        self.axes = []
    def initialize_axes(self):
        current_axes = (
            Axis('structural',
                 'plot architecture', 


if __name__ == "__main__":
    print("no")
