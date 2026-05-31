import time

from ai.event_bus import EventBus
from ai.learning_memory import LearningMemory
from ai.strategy_engine import StrategyEngine
from ai.regime_engine import RegimeEngine
from ai.regime_confidence_engine import RegimeConfidenceEngine

bus = EventBus()
memory = LearningMemory()
strategy_engine = StrategyEngine()
regime_engine = RegimeEngine()
confidence_engine = RegimeConfidenceEngine()

bus.create_group("feature_stream", "ranker_group")

print("=== REGIME CONFIDENCE RANKER ===")


def compute_score(msg):
    symbol = msg["symbol"]

    change = float(msg.get("change", 0))
    volatility = float(msg.get("volatility", 0))

    regime = regime_engine.detect(volatility)

    result = strategy_engine.rank_strategies(
        symbol,
        change,
        volatility,
        regime
    )

    strategy = result["strategy"]
    base_score = result["score"]

    symbol_bias = memory.get_bias(symbol)
    strategy_bias = memory.get_bias(symbol, strategy)

    if strategy_bias < -0.05:
        return None

    if symbol_bias < -0.20:
        return None

    regime_multiplier = confidence_engine.multiplier(
        symbol,
        strategy,
        regime
    )

    if regime_multiplier == 0:
        return None

    final_score = (
        base_score
        * (1 + symbol_bias + strategy_bias)
        * regime_multiplier
    )

    return {
        "strategy": strategy,
        "regime": regime,
        "score": final_score,
        "symbol_bias": symbol_bias,
        "strategy_bias": strategy_bias,
        "regime_multiplier": regime_multiplier
    }


while True:
    data = bus.read(
        "feature_stream",
        "ranker_group",
        "ranker_1"
    )

    if data:
        for _, messages in data:
            for _, msg in messages:

                result = compute_score(msg)

                if result is None:
                    print("BLOCKED:", msg["symbol"])
                    continue

                ranked = {
                    "symbol": msg["symbol"],
                    "strategy": result["strategy"],
                    "regime": result["regime"],
                    "score": result["score"],
                    "symbol_bias": result["symbol_bias"],
                    "strategy_bias": result["strategy_bias"],
                    "regime_multiplier": result["regime_multiplier"],
                    "change": float(msg.get("change", 0)),
                    "volatility": float(msg.get("volatility", 0)),
                    "timestamp": time.time()
                }

                bus.publish(
                    "execution_stream",
                    ranked
                )

                print(
                    "RANKED:",
                    ranked
                )
