class PriceChangeDetector:

    def detect(self, current_event, previous_event):
        if current_event is None or previous_event is None:
            return None

        absolute_change = current_event.price - previous_event.price
        
        if previous_event.price == 0:
            percent_change = 0.0
        else:
            percent_change = (absolute_change / previous_event.price) * 100

        if absolute_change > 0:
            direction = "UP"
        elif absolute_change < 0:
            direction = "DOWN"
        else:
            direction = "UNCHANGED"

        return {
            "symbol": current_event.symbol,
            "current_price": current_event.price,
            "previous_price": previous_event.price,
            "absolute_change": absolute_change,
            "percent_change": percent_change,
            "direction": direction,
            "timestamp": current_event.timestamp
        }
