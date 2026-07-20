# Real NSE+BSE security IDs for the same stock, pulled from security_id_list.csv
# on 2026-07-18 (SEM_EXM_EXCH_ID/SEM_INSTRUMENT_NAME=='EQUITY'/SEM_SERIES join on
# SEM_TRADING_SYMBOL). This is a genuine two-market (geographic) inefficiency:
# same instrument, two exchanges, real price gap possible.
#
# No metals/commodities are dual-listed across NSE/BSE (gold/silver/steel
# physical only trade on MCX, a single exchange) -- TATASTEEL/JSWSTEEL/HINDALCO
# below are metal-SECTOR STOCKS, not the commodities themselves.

DUAL_LISTED_STOCKS = [
    {"symbol": "RELIANCE",  "nse_security_id": 2885,  "bse_security_id": 500325},
    {"symbol": "TCS",       "nse_security_id": 11536, "bse_security_id": 532540},
    {"symbol": "INFY",      "nse_security_id": 1594,  "bse_security_id": 500209},
    {"symbol": "HDFCBANK",  "nse_security_id": 1333,  "bse_security_id": 500180},
    {"symbol": "ICICIBANK", "nse_security_id": 4963,  "bse_security_id": 532174},
    {"symbol": "SBIN",      "nse_security_id": 3045,  "bse_security_id": 500112},
    {"symbol": "AXISBANK",  "nse_security_id": 5900,  "bse_security_id": 532215},
    {"symbol": "ITC",       "nse_security_id": 1660,  "bse_security_id": 500875},
    {"symbol": "WIPRO",     "nse_security_id": 3787,  "bse_security_id": 507685},
    {"symbol": "LT",        "nse_security_id": 11483, "bse_security_id": 500510},
    {"symbol": "MARUTI",    "nse_security_id": 10999, "bse_security_id": 532500},
    # Metal-sector stocks (not the metals themselves -- see note above)
    {"symbol": "TATASTEEL", "nse_security_id": 3499,  "bse_security_id": 500470},
    {"symbol": "JSWSTEEL",  "nse_security_id": 11723, "bse_security_id": 500228},
    {"symbol": "HINDALCO",  "nse_security_id": 1363,  "bse_security_id": 500440},
]
