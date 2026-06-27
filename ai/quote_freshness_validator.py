from datetime import datetime, timezone

class QuoteFreshnessValidator:
    """
    Validates whether quote/event timestamps are fresh enough and close enough to compare,
    hardened against naive vs aware offset TypeError crashes.
    """

    def parse_timestamp(self, timestamp):
        """
        Parses a string timestamp into a python datetime object.
        Expected format is day/month/year hour:minute:second.
        If timestamp is missing or invalid, returns None.
        """
        if not timestamp:
            return None
        if isinstance(timestamp, datetime):
            return timestamp
        if not isinstance(timestamp, str):
            return None
        try:
            return datetime.strptime(timestamp.strip(), "%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError):
            return None

    def age_seconds(self, timestamp, now=None):
        """
        Calculates the absolute age in seconds.
        If timestamp is invalid, returns None.
        If now is None, uses datetime.now().
        """
        dt = self.parse_timestamp(timestamp)
        if dt is None:
            return None

        if now is None:
            if dt.tzinfo is not None:
                now = datetime.now(timezone.utc)
            else:
                now = datetime.now()
        else:
            parsed_now = self.parse_timestamp(now)
            if parsed_now is not None:
                now = parsed_now
            elif not isinstance(now, datetime):
                return None

        # Hardened timezone alignment
        if dt.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        elif dt.tzinfo is None and now.tzinfo is not None:
            now = now.astimezone(timezone.utc).replace(tzinfo=None)

        return abs((now - dt).total_seconds())

    def is_fresh(self, timestamp, max_age_seconds=30, now=None):
        """
        Returns True if the absolute age of the timestamp is <= max_age_seconds.
        If age is None, returns False.
        """
        age = self.age_seconds(timestamp, now)
        if age is None:
            return False
        return age <= max_age_seconds

    def timestamps_close(self, timestamp_a, timestamp_b, max_gap_seconds=10):
        """
        Returns True if the absolute gap between the two timestamps is <= max_gap_seconds.
        If either timestamp is invalid, returns False.
        """
        dt_a = self.parse_timestamp(timestamp_a)
        dt_b = self.parse_timestamp(timestamp_b)
        if dt_a is None or dt_b is None:
            return False
        
        # Hardened timezone alignment
        if dt_a.tzinfo is not None and dt_b.tzinfo is None:
            dt_b = dt_b.replace(tzinfo=timezone.utc)
        elif dt_a.tzinfo is None and dt_b.tzinfo is not None:
            dt_a = dt_a.replace(tzinfo=timezone.utc)
            
        gap = abs((dt_a - dt_b).total_seconds())
        return gap <= max_gap_seconds
