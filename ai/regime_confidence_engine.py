from ai.learning_memory import LearningMemory


class RegimeConfidenceEngine:

    def __init__(self):
        self.memory = LearningMemory()

    def multiplier(self, symbol, strategy, regime):
        bias = self.memory.get_bias(
            symbol,
            strategy,
            regime
        )

        if bias >= 0.75:
            return 1.5

        if bias >= 0.25:
            return 1.2

        if bias > -0.05:
            return 1.0

        if bias > -0.50:
            return 0.5

        return 0.0
