class OpportunityValidator:
    """
    Validates whether an Opportunity object is good enough to pass forward for paper trading.
    """

    def validate(self, opportunity):
        """
        Validates the given Opportunity object.
        Returns a dict containing 'is_valid', 'reason', and the opportunity dict representation.
        """
        if opportunity is None:
            return {
                "is_valid": False,
                "reason": "opportunity_missing",
                "opportunity": None
            }

        try:
            opp_dict = opportunity.to_dict()
        except AttributeError:
            # If it doesn't support to_dict(), handle it gracefully or treat as invalid/missing
            return {
                "is_valid": False,
                "reason": "opportunity_missing",
                "opportunity": None
            }

        # 1. Check confidence > 0
        confidence = opp_dict.get("confidence")
        if confidence is None or confidence <= 0:
            return {
                "is_valid": False,
                "reason": "confidence_not_positive",
                "opportunity": opp_dict
            }

        # 2. Check score > 0
        score = opp_dict.get("score")
        if score is None or score <= 0:
            return {
                "is_valid": False,
                "reason": "score_not_positive",
                "opportunity": opp_dict
            }

        # 3. Check metadata exists and is not empty
        metadata = opp_dict.get("metadata")
        if not metadata:
            return {
                "is_valid": False,
                "reason": "metadata_missing",
                "opportunity": opp_dict
            }

        # 4. Reject if metadata contains "mock": True
        if metadata.get("mock") is True:
            return {
                "is_valid": False,
                "reason": "mock_data_rejected",
                "opportunity": opp_dict
            }

        # 5. Check metadata["is_lagging"] is True
        if metadata.get("is_lagging") is not True:
            return {
                "is_valid": False,
                "reason": "not_lagging",
                "opportunity": opp_dict
            }

        # 6. Check metadata["same_direction"] is True
        if metadata.get("same_direction") is not True:
            return {
                "is_valid": False,
                "reason": "direction_mismatch",
                "opportunity": opp_dict
            }

        # 7. Check metadata["reaction_gap"] > 0
        reaction_gap = metadata.get("reaction_gap")
        if reaction_gap is None or reaction_gap <= 0:
            return {
                "is_valid": False,
                "reason": "reaction_gap_not_positive",
                "opportunity": opp_dict
            }

        return {
            "is_valid": True,
            "reason": "valid_opportunity",
            "opportunity": opp_dict
        }
