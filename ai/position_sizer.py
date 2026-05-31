class PositionSizer:

    def __init__(self):
        self.max_size = 5

    def size_for_signal(self, bias, score):

        if bias <= 0:
            return 0

        if score >= 4000 and bias >= 0.50:
            return 5

        if score >= 3000 and bias >= 0.40:
            return 4

        if score >= 2000 and bias >= 0.25:
            return 3

        if score >= 1000 and bias >= 0.10:
            return 2

        if bias > 0:
            return 1

        return 0

    def size_for_bias(self, bias):
        return self.size_for_signal(bias, 0)
