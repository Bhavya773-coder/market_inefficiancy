from ai.market_event import MarketEvent
from ai.price_change_detector import PriceChangeDetector
from ai.reaction_event import ReactionEvent
from ai.lag_detector import LagDetector
from ai.opportunity_adapter import OpportunityAdapter
from ai.opportunity_validator import OpportunityValidator
from ai.paper_trade_candidate_factory import PaperTradeCandidateFactory
from ai.paper_trading_engine import PaperTradingEngine

class LivePaperTradingMonitor:
    """
    Reusable orchestrator connecting opportunity detection logic to PaperTradingEngine.
    """

    def __init__(self, reference_symbol, target_symbol, engine=None, min_gap_percent=0.05):
        self.reference_symbol = reference_symbol
        self.target_symbol = target_symbol
        self.min_gap_percent = min_gap_percent
        
        self.price_change_detector = PriceChangeDetector()
        self.lag_detector = LagDetector()
        self.opportunity_adapter = OpportunityAdapter()
        self.opportunity_validator = OpportunityValidator()
        self.candidate_factory = PaperTradeCandidateFactory()
        
        self.engine = engine if engine is not None else PaperTradingEngine()
        
        self.stats = {
            "ticks_processed": 0,
            "opportunities_found": 0,
            "opportunities_valid": 0,
            "candidates_created": 0,
            "entries_allowed": 0,
            "entries_rejected": 0,
            "paper_buys": 0,
            "paper_sells": 0,
            "take_profits": 0,
            "stop_losses": 0,
            "holds": 0
        }

    def _update_exit_stats(self, exit_report):
        if not exit_report:
            return
        decision = exit_report.get("decision")
        if decision:
            action = decision.get("action")
            if action == "TAKE_PROFIT":
                self.stats["take_profits"] += 1
            elif action == "STOP_LOSS":
                self.stats["stop_losses"] += 1
            elif action == "HOLD":
                self.stats["holds"] += 1
        
        execution = exit_report.get("execution")
        if execution and execution.get("status") == "filled" and execution.get("side") == "SELL":
            self.stats["paper_sells"] += 1

    def process_tick_pair(self, previous_reference_event, current_reference_event, previous_target_event, current_target_event, quantity=1):
        """
        Processes a single tick pair for reference and target instruments.
        """
        # 1. Increment ticks_processed
        self.stats["ticks_processed"] += 1

        # 2. Detect price changes
        ref_change = self.price_change_detector.detect(current_reference_event, previous_reference_event)
        tgt_change = self.price_change_detector.detect(current_target_event, previous_target_event)

        # 3. Convert changes to ReactionEvent
        ref_reaction = ReactionEvent.from_price_change(ref_change) if ref_change else None
        tgt_reaction = ReactionEvent.from_price_change(tgt_change) if tgt_change else None

        # 4. Detect lag
        lag_result = self.lag_detector.detect(ref_reaction, tgt_reaction, min_gap_percent=self.min_gap_percent)

        # 5. If no lag/opportunity, check exit and return
        if lag_result is None or lag_result.get("is_lagging") is False:
            exit_report = self.engine.process_price_update(self.target_symbol, current_target_event.price)
            self._update_exit_stats(exit_report)
            return {
                "status": "no_opportunity",
                "reference_change": ref_change,
                "target_change": tgt_change,
                "lag_result": lag_result,
                "opportunity": None,
                "validation_result": None,
                "candidate": None,
                "entry_report": None,
                "exit_report": exit_report,
                "account": self.engine.account_state(),
                "stats": self.stats
            }

        # 6. Enrich lag_result
        lag_result = lag_result.copy()
        lag_result["mock"] = False
        lag_result["data_source"] = current_target_event.metadata.get("data_source", "unknown") if current_target_event.metadata else "unknown"
        lag_result["target_price"] = current_target_event.price

        # 7. Convert to Opportunity
        opportunity = self.opportunity_adapter.from_lag_result(lag_result)

        # 8. Increment opportunities_found
        if opportunity:
            self.stats["opportunities_found"] += 1
        else:
            exit_report = self.engine.process_price_update(self.target_symbol, current_target_event.price)
            self._update_exit_stats(exit_report)
            return {
                "status": "no_opportunity",
                "reference_change": ref_change,
                "target_change": tgt_change,
                "lag_result": lag_result,
                "opportunity": None,
                "validation_result": None,
                "candidate": None,
                "entry_report": None,
                "exit_report": exit_report,
                "account": self.engine.account_state(),
                "stats": self.stats
            }

        # 9. Validate opportunity
        validation_result = self.opportunity_validator.validate(opportunity)
        if validation_result.get("is_valid") is True:
            self.stats["opportunities_valid"] += 1
        else:
            return {
                "status": "invalid_opportunity",
                "reference_change": ref_change,
                "target_change": tgt_change,
                "lag_result": lag_result,
                "opportunity": opportunity.to_dict(),
                "validation_result": validation_result,
                "candidate": None,
                "entry_report": None,
                "exit_report": None,
                "account": self.engine.account_state(),
                "stats": self.stats
            }

        # 10. Create PaperTradeCandidate
        candidate = self.candidate_factory.from_validated_opportunity(validation_result)
        if candidate:
            self.stats["candidates_created"] += 1
        else:
            return {
                "status": "candidate_missing",
                "reference_change": ref_change,
                "target_change": tgt_change,
                "lag_result": lag_result,
                "opportunity": opportunity.to_dict(),
                "validation_result": validation_result,
                "candidate": None,
                "entry_report": None,
                "exit_report": None,
                "account": self.engine.account_state(),
                "stats": self.stats
            }

        # 11. Process candidate through PaperTradingEngine
        entry_report = self.engine.process_candidate(candidate, quantity=quantity, price=current_target_event.price)

        # 12. Update entry action stats
        decision = entry_report.get("decision")
        if decision and decision.get("action") == "BUY_ALLOWED":
            self.stats["entries_allowed"] += 1
        else:
            self.stats["entries_rejected"] += 1

        # 13. Update paper buy stats
        execution = entry_report.get("execution")
        if execution and execution.get("status") == "filled" and execution.get("side") == "BUY":
            self.stats["paper_buys"] += 1

        # 14. Always process exit update after entry check
        exit_report = self.engine.process_price_update(self.target_symbol, current_target_event.price)

        # 15. Update exit stats
        self._update_exit_stats(exit_report)

        # 16. Return full report
        return {
            "status": "opportunity_processed",
            "reference_change": ref_change,
            "target_change": tgt_change,
            "lag_result": lag_result,
            "opportunity": opportunity.to_dict(),
            "validation_result": validation_result,
            "candidate": candidate.to_dict(),
            "entry_report": entry_report,
            "exit_report": exit_report,
            "account": self.engine.account_state(),
            "stats": self.stats
        }

    def update_exit_only(self, symbol, current_price):
        """
        Updates the exit checking logic only.
        """
        exit_report = self.engine.process_price_update(symbol, current_price)
        self._update_exit_stats(exit_report)
        return {
            "stage": "exit",
            "exit_report": exit_report,
            "account": self.engine.account_state(),
            "stats": self.stats
        }

    def summary(self):
        """
        Returns a summary of stats and account state.
        """
        return {
            "stats": self.stats,
            "account": self.engine.account_state()
        }
