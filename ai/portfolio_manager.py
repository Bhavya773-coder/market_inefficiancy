class PortfolioManager:

    def __init__(self):

        self.max_total_positions = 15

        self.starting_capital = 1000000.0

        self.realized_pnl = 0.0

    def can_open_trade(
        self,
        open_trade_count
    ):

        return (
            open_trade_count
            < self.max_total_positions
        )

    def portfolio_heat(
        self,
        open_trade_count
    ):

        return round(
            open_trade_count
            / self.max_total_positions,
            2
        )

    def record_pnl(
        self,
        pnl
    ):

        self.realized_pnl += pnl

    def equity(self):

        return (
            self.starting_capital
            + self.realized_pnl
        )

    def return_pct(self):

        return round(
            (
                self.realized_pnl
                / self.starting_capital
            ) * 100,
            4
        )
