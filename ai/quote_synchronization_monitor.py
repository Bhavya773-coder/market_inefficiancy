from datetime import datetime

class QuoteSynchronizationMonitor:
    """
    Tracks synchronization reliability over consecutive checks.
    """
    def __init__(self, required_consecutive_synchronized_checks=3):
        self.required_consecutive_synchronized_checks = int(required_consecutive_synchronized_checks)
        
        self.total_checks = 0
        self.synchronized_checks = 0
        self.consecutive_synchronized_checks = 0
        self.maximum_consecutive_synchronized_checks = 0
        self.last_status = None
        self.last_observed_at = None

    @property
    def ready(self):
        """
        Returns True if the required number of consecutive synchronized checks is achieved.
        """
        return self.consecutive_synchronized_checks >= self.required_consecutive_synchronized_checks

    def observe(self, pair_status, observed_at):
        """
        Observes a single pair status check. Validates that timestamps are strictly ordered.
        """
        if not isinstance(observed_at, datetime):
            raise TypeError("observed_at must be a datetime object")
            
        if self.last_observed_at is not None:
            if observed_at <= self.last_observed_at:
                raise ValueError(
                    f"Out of order observation: {observed_at.isoformat()} "
                    f"is not after {self.last_observed_at.isoformat()}"
                )

        is_sync = pair_status.get("pair_is_synchronized", False)
        
        self.total_checks += 1
        
        if is_sync:
            self.synchronized_checks += 1
            self.consecutive_synchronized_checks += 1
            self.maximum_consecutive_synchronized_checks = max(
                self.maximum_consecutive_synchronized_checks,
                self.consecutive_synchronized_checks
            )
        else:
            self.consecutive_synchronized_checks = 0
            
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
            "ready": self.ready
        }
