from datetime import datetime

class QuoteSynchronizationMonitor:
    """
    Tracks synchronization reliability over consecutive checks, ensuring
    only genuinely new market updates count towards readiness.
    """
    def __init__(self, required_consecutive_synchronized_checks=3):
        self.required_consecutive_synchronized_checks = int(required_consecutive_synchronized_checks)
        
        self.total_checks = 0
        self.synchronized_checks = 0
        self.consecutive_synchronized_checks = 0
        self.maximum_consecutive_synchronized_checks = 0
        self.last_status = None
        self.last_observed_at = None
        self.last_snapshot_identity = None
        self.duplicate_snapshot_checks = 0

    @property
    def ready(self):
        """
        Returns True if the required number of consecutive synchronized checks is achieved.
        """
        return self.consecutive_synchronized_checks >= self.required_consecutive_synchronized_checks

    def observe(self, pair_status, observed_at):
        """
        Observes a single pair status check. Validates that timestamps are strictly ordered.
        Guards against duplicate snapshot identity checks.
        """
        if not isinstance(observed_at, datetime):
            raise TypeError("observed_at must be a datetime object")
            
        if self.last_observed_at is not None:
            if observed_at <= self.last_observed_at:
                raise ValueError(
                    f"Out of order observation: {observed_at.isoformat()} "
                    f"is not after {self.last_observed_at.isoformat()}"
                )

        snapshot_id = pair_status.get("snapshot_identity")
        is_sync = pair_status.get("pair_is_synchronized", False)
        
        is_duplicate = False
        if snapshot_id is not None and self.last_snapshot_identity is not None:
            if snapshot_id == self.last_snapshot_identity:
                is_duplicate = True
                
        self.total_checks += 1
        
        if is_duplicate:
            self.duplicate_snapshot_checks += 1
            # We do NOT increment consecutive synchronized checks.
            # Consecutive count remains unchanged.
        else:
            if is_sync:
                self.synchronized_checks += 1
                self.consecutive_synchronized_checks += 1
                self.maximum_consecutive_synchronized_checks = max(
                    self.maximum_consecutive_synchronized_checks,
                    self.consecutive_synchronized_checks
                )
            else:
                self.consecutive_synchronized_checks = 0
                
        if snapshot_id is not None:
            self.last_snapshot_identity = snapshot_id
            
        self.last_status = pair_status
        self.last_observed_at = observed_at

    def summary(self):
        """
        Returns a summary dictionary of all counter metrics and readiness.
        """
        return {
            "total_checks": self.total_checks,
            "synchronized_checks": self.synchronized_checks,
            "consecutive_synchronized_checks": self.consecutive_synchronized_checks,
            "maximum_consecutive_synchronized_checks": self.maximum_consecutive_synchronized_checks,
            "duplicate_snapshot_checks": self.duplicate_snapshot_checks,
            "ready": self.ready
        }
