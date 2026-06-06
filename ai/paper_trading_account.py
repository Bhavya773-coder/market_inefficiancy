class PaperTradingAccount:
    """
    Holds imaginary cash and paper positions for paper trading simulation.
    """

    def __init__(self, starting_cash=100000):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.positions = {}
        self.trade_log = []

    def can_buy(self, estimated_cost):
        """
        Returns True if cash >= estimated_cost.
        """
        return self.cash >= estimated_cost

    def buy(self, symbol, quantity, price, metadata=None):
        """
        Simulates buying an asset.
        Deducts cash, adds to/updates positions, logs the trade.
        """
        cost = quantity * price
        if not self.can_buy(cost):
            return {
                "status": "rejected",
                "reason": "insufficient_cash",
                "symbol": symbol,
                "quantity": quantity,
                "price": price
            }

        self.cash -= cost

        if symbol not in self.positions:
            self.positions[symbol] = {
                "quantity": quantity,
                "average_price": price
            }
        else:
            existing = self.positions[symbol]
            new_qty = existing["quantity"] + quantity
            new_avg_price = ((existing["quantity"] * existing["average_price"]) + cost) / new_qty
            self.positions[symbol] = {
                "quantity": new_qty,
                "average_price": new_avg_price
            }

        trade = {
            "status": "filled",
            "side": "BUY",
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "value": cost,
            "metadata": metadata or {}
        }
        self.trade_log.append(trade)
        return trade

    def sell(self, symbol, quantity, price, metadata=None):
        """
        Simulates selling an asset.
        Verifies holdings, adds cash, reduces/removes position, logs the trade.
        """
        if symbol not in self.positions or self.positions[symbol]["quantity"] < quantity:
            return {
                "status": "rejected",
                "reason": "insufficient_position",
                "symbol": symbol,
                "quantity": quantity,
                "price": price
            }

        existing = self.positions[symbol]
        new_qty = existing["quantity"] - quantity
        if new_qty == 0:
            del self.positions[symbol]
        else:
            self.positions[symbol]["quantity"] = new_qty

        revenue = quantity * price
        self.cash += revenue

        trade = {
            "status": "filled",
            "side": "SELL",
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "value": revenue,
            "metadata": metadata or {}
        }
        self.trade_log.append(trade)
        return trade

    def portfolio_value(self, latest_prices=None):
        """
        Returns the total portfolio value (cash + marked-to-market positions).
        """
        pos_value = 0.0
        for sym, pos in self.positions.items():
            qty = pos["quantity"]
            price = pos["average_price"]
            if latest_prices and sym in latest_prices:
                price = latest_prices[sym]
            pos_value += qty * price
        return self.cash + pos_value

    def to_dict(self):
        """
        Returns a dictionary representation of the paper trading account state.
        """
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "positions": self.positions,
            "trade_log": self.trade_log,
            "portfolio_value": self.portfolio_value()
        }
