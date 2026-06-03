from ai.market_event import MarketEvent

class MarketEventStore:

    def __init__(self, max_events=1000):
        self.events = []
        self.max_events = max_events

    def add(self, event):
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events.pop(0)
        return event

    def latest(self, symbol=None):
        if not self.events:
            return None
            
        if symbol is None:
            return self.events[-1]
            
        for event in reversed(self.events):
            if event.symbol == symbol:
                return event
        return None

    def history(self, symbol=None, limit=10):
        if symbol is None:
            return self.events[-limit:]
            
        filtered = [event for event in self.events if event.symbol == symbol]
        return filtered[-limit:]

    def count(self):
        return len(self.events)
