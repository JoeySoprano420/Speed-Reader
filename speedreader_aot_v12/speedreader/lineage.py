
class Lineage:
    def __init__(self):
        self.map = {}
    def tag(self, key, value):
        self.map[key] = value
    def get(self, key, default=None):
        return self.map.get(key, default)
