class PaperPositionExitEvaluator:
    """
    Evaluates whether a paper position should be held, exited for profit, or exited for loss.
    """

    def evaluate(self, symbol, position, current_price, target_profit_pct=0.50, stop_loss_pct=0.25):
        """
        Evaluates the position using profit target and stop loss percentages.
        """
        if position is None:
            return {
                "symbol": symbol,
                "action": "NO_POSITION",
                "reason": "position_missing"
            }

        entry_price = position["average_price"]
        quantity = position["quantity"]
        unrealized_pnl = (current_price - entry_price) * quantity
        
        if entry_price == 0:
            unrealized_pct = 0.0
        else:
            unrealized_pct = ((current_price - entry_price) / entry_price) * 100

        if unrealized_pct >= target_profit_pct:
            action = "TAKE_PROFIT"
            reason = "target_profit_reached"
        elif unrealized_pct <= -stop_loss_pct:
            action = "STOP_LOSS"
            reason = "stop_loss_reached"
        else:
            action = "HOLD"
            reason = "within_bounds"

        return {
            "symbol": symbol,
            "action": action,
            "reason": reason,
            "entry_price": entry_price,
            "current_price": current_price,
            "quantity": quantity,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pct": unrealized_pct
        }
