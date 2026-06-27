from ai.paper_trade_simulator import PaperTradeSimulator

class PaperTradingEngine:
    """
    Reusable wrapper around PaperTradeSimulator to handle candidate processing,
    price updates, and account state reporting for paper trading.
    """

    def __init__(self, simulator=None):
        self.simulator = simulator if simulator is not None else PaperTradeSimulator()

    def process_candidate(self, candidate, quantity=1, price=None):
        """
        Process a paper trade candidate by creating and executing an entry decision.
        """
        decision = self.simulator.create_entry_decision(
            candidate,
            quantity=quantity,
            price=price
        )
        execution = self.simulator.execute_entry_decision(decision)
        return {
            "stage": "entry",
            "decision": decision.to_dict() if decision else None,
            "execution": execution,
            "account": self.simulator.account.to_dict()
        }

    def process_price_update(self, symbol, current_price, target_profit_pct=0.50, stop_loss_pct=0.25):
        """
        Process a price update for a symbol, checking if any active position should exit.
        """
        decision = self.simulator.create_exit_decision(
            symbol,
            current_price=current_price,
            target_profit_pct=target_profit_pct,
            stop_loss_pct=stop_loss_pct
        )
        execution = self.simulator.close_position_from_decision(decision)
        return {
            "stage": "exit",
            "decision": decision.to_dict() if decision else None,
            "execution": execution,
            "account": self.simulator.account.to_dict()
        }

    def account_state(self):
        """
        Return the current state of the paper trading account.
        """
        return self.simulator.account.to_dict()
