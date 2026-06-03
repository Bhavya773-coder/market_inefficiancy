from ai.reaction_event import ReactionEvent

class ReactionTracker:

    def __init__(self, max_reactions=1000):
        self.reactions = []
        self.max_reactions = max_reactions

    def add(self, reaction):
        self.reactions.append(reaction)
        if len(self.reactions) > self.max_reactions:
            self.reactions.pop(0)
        return reaction

    def latest(self, symbol=None):
        if not self.reactions:
            return None
        if symbol is None:
            return self.reactions[-1]
        for r in reversed(self.reactions):
            if r.symbol == symbol:
                return r
        return None

    def history(self, symbol=None, limit=10):
        if symbol is None:
            return self.reactions[-limit:]
        filtered = [r for r in self.reactions if r.symbol == symbol]
        return filtered[-limit:]

    def movers(self, min_percent_change=0.0):
        return [r for r in self.reactions if abs(r.percent_change) >= min_percent_change]

    def count(self):
        return len(self.reactions)
