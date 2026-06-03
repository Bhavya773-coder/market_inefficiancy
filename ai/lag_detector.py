class LagDetector:

    def detect(self, reference_reaction, target_reaction, min_gap_percent=0.10):
        if reference_reaction is None or target_reaction is None:
            return None

        reaction_gap = abs(reference_reaction.percent_change) - abs(target_reaction.percent_change)
        same_direction = reference_reaction.direction == target_reaction.direction
        is_lagging = same_direction is True and reaction_gap >= min_gap_percent

        return {
            "reference_symbol": reference_reaction.symbol,
            "target_symbol": target_reaction.symbol,
            "reference_change": reference_reaction.percent_change,
            "target_change": target_reaction.percent_change,
            "reaction_gap": reaction_gap,
            "same_direction": same_direction,
            "is_lagging": is_lagging,
            "timestamp": target_reaction.timestamp
        }
