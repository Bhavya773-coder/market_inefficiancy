from ai.quote_freshness_validator import QuoteFreshnessValidator

def main():
    validator = QuoteFreshnessValidator()
    
    timestamp_a = "04/06/2026 12:55:50"
    timestamp_b = "04/06/2026 12:55:16"
    
    # Test 34s gap with 10s limit
    res_diff = validator.timestamps_close(timestamp_a, timestamp_b, max_gap_seconds=10)
    print(f"Close 34s gap with 10s limit: {res_diff}")
    
    # Test same timestamp with 10s limit
    res_same = validator.timestamps_close(timestamp_a, timestamp_a, max_gap_seconds=10)
    print(f"Close same timestamp with 10s limit: {res_same}")

if __name__ == "__main__":
    main()
