from ai.learning_memory import LearningMemory

memory = LearningMemory()

class StrategyEngine:

    def momentum(
        self,
        change,
        volatility
    ):

        return (
            abs(change) * 10
            + volatility * 2
        )

    def mean_reversion(
        self,
        change,
        volatility
    ):

        return (
            max(
                0,
                1000 - abs(change)
            )
            + volatility
        )

    def breakout(
        self,
        change,
        volatility
    ):

        if volatility > 500:
            return volatility * 5

        return 0

    def rank_strategies(
        self,
        symbol,
        change,
        volatility,
        regime
    ):

        strategies = {

            "momentum":
            self.momentum(
                change,
                volatility
            ),

            "mean_reversion":
            self.mean_reversion(
                change,
                volatility
            ),

            "breakout":
            self.breakout(
                change,
                volatility
            )
        }

        adjusted = {}

        for strategy, score in strategies.items():

            bias = memory.get_bias(
                symbol,
                strategy,
                regime
            )

            adjusted[
                strategy
            ] = score * (
                1 + bias
            )

        best = max(
            adjusted,
            key=adjusted.get
        )

        return {
            "strategy": best,
            "score": adjusted[best]
        }
