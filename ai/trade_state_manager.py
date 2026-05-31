import uuid
import time


class TradeStateManager:

    def __init__(self):

        self.open_trades = {}

        self.closed_trades = []

        self.hold_time = 20

    def open_trade(
        self,
        symbol,
        strategy,
        regime,
        pnl
    ):

        trade_id = str(uuid.uuid4())[:8]

        trade = {
            "id": trade_id,
            "symbol": symbol,
            "strategy": strategy,
            "regime": regime,
            "opened_at": time.time(),
            "pnl": pnl,
            "status": "OPEN"
        }

        self.open_trades[trade_id] = trade

        return trade

    def close_expired_trades(self):

        now = time.time()

        closed = []

        for trade_id, trade in list(self.open_trades.items()):

            age = now - trade["opened_at"]

            if age >= self.hold_time:

                trade["status"] = "CLOSED"
                trade["closed_at"] = now
                trade["hold_seconds"] = round(age, 2)

                closed.append(trade)

                self.closed_trades.append(trade)

                del self.open_trades[trade_id]

        return closed

    def get_open_count(self):

        self.close_expired_trades()

        return len(self.open_trades)

    def get_closed_count(self):

        return len(self.closed_trades)
