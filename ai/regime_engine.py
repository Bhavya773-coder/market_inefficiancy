class RegimeEngine:

    def detect(
        self,
        volatility
    ):

        if volatility > 1000:
            return "high_volatility"

        elif volatility > 300:
            return "trending"

        return "calm"
