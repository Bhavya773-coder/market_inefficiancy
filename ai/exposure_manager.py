class ExposureManager:

    def __init__(self):
        self.max_symbol_share = 0.40

    def symbol_share(self, symbol_position, total_open):
        if total_open <= 0:
            return 0.0

        return symbol_position / total_open

    def can_add_symbol(self, symbol_position, total_open):
        share = self.symbol_share(symbol_position, total_open)

        return share < self.max_symbol_share
