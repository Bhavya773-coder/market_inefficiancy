import time


class PositionManager:

    def __init__(self):

        self.positions = {}

        self.max_position_size = 5

        self.hold_time = 15

    def cleanup(self):

        now = time.time()

        remove = []

        for symbol, trades in self.positions.items():

            active = []

            for t in trades:

                if now - t < self.hold_time:
                    active.append(t)

            self.positions[symbol] = active

            if len(active) == 0:
                remove.append(symbol)

        for symbol in remove:
            del self.positions[symbol]

    def can_trade(self, symbol):

        self.cleanup()

        current = len(
            self.positions.get(symbol, [])
        )

        return current < self.max_position_size

    def add_position(self, symbol):

        self.cleanup()

        if symbol not in self.positions:
            self.positions[symbol] = []

        self.positions[symbol].append(
            time.time()
        )

    def get_position(self, symbol):

        self.cleanup()

        return len(
            self.positions.get(symbol, [])
        )
