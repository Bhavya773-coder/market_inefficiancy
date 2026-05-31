import time
import random

from ai.event_bus import EventBus
from ai.learning_memory import LearningMemory
from ai.position_manager import PositionManager
from ai.trade_state_manager import TradeStateManager
from ai.portfolio_manager import PortfolioManager
from ai.position_sizer import PositionSizer
from ai.loss_streak_guard import LossStreakGuard
from ai.exposure_manager import ExposureManager
from ai.equity_memory import EquityMemory

bus = EventBus()

memory = LearningMemory()
positions = PositionManager()
trade_states = TradeStateManager()
portfolio = PortfolioManager()
sizer = PositionSizer()
loss_guard = LossStreakGuard()
exposure = ExposureManager()
equity_memory = EquityMemory()

bus.create_group(
    "execution_stream",
    "exec_group"
)

print("=== EQUITY-AWARE EXPOSURE POSITION ENGINE ===")


def clamp(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def execute_trade(symbol, strategy, regime, score):
    open_count = trade_states.get_open_count()

    if not portfolio.can_open_trade(open_count):
        print("PORTFOLIO BLOCK:", "heat too high")
        return None

    current_symbol_position = positions.get_position(symbol)

    if not exposure.can_add_symbol(current_symbol_position, open_count):
        print(
            "EXPOSURE BLOCK:",
            symbol,
            "share:",
            exposure.symbol_share(current_symbol_position, open_count)
        )
        return None

    if loss_guard.is_blocked(symbol, strategy, regime):
        print(
            "LOSS STREAK BLOCK:",
            symbol,
            strategy,
            regime,
            "streak:",
            loss_guard.get_streak(symbol, strategy, regime)
        )
        return None

    if not positions.can_trade(symbol):
        print("RISK BLOCK:", symbol, "position limit reached")
        return None

    symbol_bias = clamp(memory.get_bias(symbol))
    strategy_bias = clamp(memory.get_bias(symbol, strategy))
    regime_bias = clamp(memory.get_bias(symbol, strategy, regime))

    sizing_bias = clamp(
        (
            symbol_bias
            + strategy_bias
            + regime_bias
        ) / 3
    )

    position_size = sizer.size_for_signal(sizing_bias, score)

    if position_size <= 0:
        print("SIZE BLOCK:", symbol, strategy, regime)
        return None

    slippage = random.uniform(0.1, 2.5)
    fill_probability = max(0.2, 1 - slippage / 3)

    time.sleep(random.uniform(0.2, 1.0))

    if random.random() >= fill_probability:
        return None

    safe_score = min(score, 10000)

    edge = symbol_bias + strategy_bias + regime_bias

    win_probability = max(
        0.2,
        min(
            0.8,
            0.5 + edge / 4
        )
    )

    trade_win = random.random() < win_probability

    base_move = safe_score / 100
    noise = random.uniform(0.5, 1.5)

    if trade_win:
        pnl = base_move * noise * position_size
    else:
        pnl = -(base_move * noise * position_size)

    positions.add_position(symbol)

    state_trade = trade_states.open_trade(
        symbol,
        strategy,
        regime,
        pnl
    )

    loss_guard.record_result(
        symbol,
        strategy,
        regime,
        pnl
    )

    return {
        "event": "OPEN",
        "trade_id": state_trade["id"],
        "status": "OPEN",
        "symbol": symbol,
        "strategy": strategy,
        "regime": regime,
        "score": safe_score,
        "position_size": position_size,
        "sizing_bias": sizing_bias,
        "loss_streak": loss_guard.get_streak(symbol, strategy, regime),
        "symbol_share": exposure.symbol_share(
            positions.get_position(symbol),
            trade_states.get_open_count()
        ),
        "position": positions.get_position(symbol),
        "portfolio_heat": portfolio.portfolio_heat(
            trade_states.get_open_count()
        ),
        "pnl": pnl,
        "win_probability": round(win_probability, 2),
        "trade_win": str(trade_win),
        "symbol_bias": symbol_bias,
        "strategy_bias": strategy_bias,
        "regime_bias": regime_bias,
        "open_trades": trade_states.get_open_count(),
        "equity": portfolio.equity(),
        "return_pct": portfolio.return_pct(),
        "timestamp": time.time()
    }


while True:
    closed_trades = trade_states.close_expired_trades()

    for closed in closed_trades:
        portfolio.record_pnl(
            closed["pnl"]
        )

        equity_memory.record(
            portfolio.equity(),
            portfolio.return_pct()
        )

        close_event = {
            "event": "CLOSE",
            "trade_id": closed["id"],
            "status": "CLOSED",
            "symbol": closed["symbol"],
            "strategy": closed["strategy"],
            "regime": closed["regime"],
            "pnl": closed["pnl"],
            "hold_seconds": closed["hold_seconds"],
            "equity": portfolio.equity(),
            "return_pct": portfolio.return_pct(),
            "timestamp": time.time()
        }

        bus.publish("execution_stream", close_event)
        print("CLOSED:", close_event)

    data = bus.read(
        "execution_stream",
        "exec_group",
        "exec_1"
    )

    if data:
        for _, messages in data:
            for _, msg in messages:
                if msg.get("event") == "CLOSE":
                    continue

                symbol = msg.get("symbol")
                strategy = msg.get("strategy", "unknown")
                regime = msg.get("regime", "unknown")
                score = float(msg.get("score", 0))

                trade = execute_trade(
                    symbol,
                    strategy,
                    regime,
                    score
                )

                if trade:
                    memory.record_trade(symbol, trade["pnl"])
                    memory.record_trade(symbol, trade["pnl"], strategy)
                    memory.record_trade(symbol, trade["pnl"], strategy, regime)

                    bus.publish("execution_stream", trade)

                    print("EXECUTED:", trade)
