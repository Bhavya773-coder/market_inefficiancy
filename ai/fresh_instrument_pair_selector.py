class FreshInstrumentPairSelector:
    """
    Ranks and selects candidate instrument pairs based on update frequency,
    local staleness, receive gap, and provider timestamp gap.
    """
    def __init__(self, quote_buffer):
        self.quote_buffer = quote_buffer

    def rank_pairs(self, candidate_pairs, now=None):
        ranked = []
        
        for pair in candidate_pairs:
            ref = pair["reference"]
            tgt = pair["target"]
            
            p_status = self.quote_buffer.pair_status(
                ref["exchange"], ref["security_id"],
                tgt["exchange"], tgt["security_id"],
                now=now
            )
            
            ref_stat = p_status["reference"]
            tgt_stat = p_status["target"]
            
            both_active = p_status["both_active"]
            pair_is_synchronized = p_status["pair_is_synchronized"]
            local_receive_gap = p_status["local_receive_gap_seconds"]
            provider_ts_gap = p_status["provider_timestamp_gap_seconds"]
            blocking_reasons = p_status["blocking_reasons"]
            
            ref_updates = ref_stat["update_count"]
            tgt_updates = tgt_stat["update_count"]
            ref_changes = ref_stat["price_change_count"]
            tgt_changes = tgt_stat["price_change_count"]
            
            minimum_update_count = min(ref_updates, tgt_updates)
            combined_update_count = ref_updates + tgt_updates
            combined_price_change_count = ref_changes + tgt_changes
            reference_local_age_seconds = ref_stat["local_age_seconds"]
            target_local_age_seconds = tgt_stat["local_age_seconds"]
            
            # Deterministic scoring
            score = 100.0
            
            has_quotes = ref_stat["has_quote"] and tgt_stat["has_quote"]
            if not has_quotes:
                score -= 100.0
            if not both_active:
                score -= 50.0
            if not pair_is_synchronized:
                score -= 50.0
                
            if local_receive_gap is not None:
                score -= min(20.0, local_receive_gap)
                
            if provider_ts_gap is not None:
                score -= min(20.0, provider_ts_gap)
                
            # Count other blocking reasons (-10 for each unique reason not already handled directly)
            known_reasons = {
                "reference_inactive", "target_inactive",
                "local_receive_gap_too_large", "provider_timestamp_gap_too_large",
                "missing_quotes_for_one_or_both_instruments"
            }
            other_reasons = 0
            for r in blocking_reasons:
                is_known = False
                for kr in known_reasons:
                    if kr in r:
                        is_known = True
                        break
                if not is_known:
                    other_reasons += 1
            score -= other_reasons * 10.0
            
            # Activity rewards
            score += min(10.0, float(combined_update_count))
            score += min(5.0, float(combined_price_change_count))
            
            # Clamp final score
            score = max(0.0, min(100.0, float(score)))
            
            ranked.append({
                "pair": pair,
                "both_active": both_active,
                "pair_is_synchronized": pair_is_synchronized,
                "local_receive_gap_seconds": local_receive_gap,
                "provider_timestamp_gap_seconds": provider_ts_gap,
                "minimum_update_count": minimum_update_count,
                "combined_update_count": combined_update_count,
                "combined_price_change_count": combined_price_change_count,
                "reference_local_age_seconds": reference_local_age_seconds,
                "target_local_age_seconds": target_local_age_seconds,
                "blocking_reasons": blocking_reasons,
                "score": score
            })
            
        def sort_key(item):
            # Sort: synchronized first, then highest score, then highest updates, then stable symbols
            pair_config = item["pair"]
            ref_sym = pair_config["reference"].get("symbol", "")
            tgt_sym = pair_config["target"].get("symbol", "")
            return (
                -1 if item["pair_is_synchronized"] else 0,
                -item["score"],
                -item["combined_update_count"],
                ref_sym,
                tgt_sym
            )
            
        ranked.sort(key=sort_key)
        return ranked

    def select_best(self, candidate_pairs, now=None):
        """
        Selects the highest ranked synchronized active pair.
        """
        rankings = self.rank_pairs(candidate_pairs, now=now)
        if not rankings:
            return {
                "selected": None,
                "rankings": [],
                "reason": "no_synchronized_active_pair"
            }
            
        best = rankings[0]
        if best["pair_is_synchronized"]:
            return {
                "selected": best["pair"],
                "rankings": rankings,
                "reason": "synchronized_pair_selected"
            }
        
        return {
            "selected": None,
            "rankings": rankings,
            "reason": "no_synchronized_active_pair"
        }
