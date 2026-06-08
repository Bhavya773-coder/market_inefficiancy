import pandas as pd
import time
from connectors.dhan_connector import DhanConnector
import pprint

def score_readiness(report):
    pass

def main():
    print("=== DHAN NSE LIVE DISCOVERY SCANNER ===")
    
    # 1. Load CSV
    print("Loading security_id_list.csv...")
    try:
        df = pd.read_csv("security_id_list.csv")
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return

    print(f"Total rows in security master: {len(df)}")

    # 2. Filter SEM_EXM_EXCH_ID == "NSE"
    df_nse = df[df["SEM_EXM_EXCH_ID"] == "NSE"].copy()
    print(f"NSE instruments: {len(df_nse)}")

    # 3. Categorize candidates
    df_nse["SEM_EXCH_INSTRUMENT_TYPE"] = df_nse["SEM_EXCH_INSTRUMENT_TYPE"].astype(str)
    df_nse["SEM_SEGMENT"] = df_nse["SEM_SEGMENT"].astype(str)
    df_nse["SEM_TRADING_SYMBOL"] = df_nse["SEM_TRADING_SYMBOL"].astype(str)

    # ETF instruments: contains "ETF"
    df_etfs = df_nse[df_nse["SEM_EXCH_INSTRUMENT_TYPE"].str.contains("ETF", case=False, na=False)].copy()
    
    # Equity instruments: SEM_SEGMENT == "E" and instrument type in ["ES", "EQ", "ETF"]
    df_equity = df_nse[
        (df_nse["SEM_SEGMENT"] == "E") & 
        (df_nse["SEM_EXCH_INSTRUMENT_TYPE"].isin(["ES", "EQ", "ETF"]))
    ].copy()

    print(f"ETF candidates: {len(df_etfs)}")
    print(f"Equity candidates: {len(df_equity)}")

    # Combine them (ETFs first) and remove duplicates
    df_candidates = pd.concat([df_etfs, df_equity]).drop_duplicates(subset=["SEM_SMST_SECURITY_ID"])
    df_candidates = df_candidates.dropna(subset=["SEM_TRADING_SYMBOL", "SEM_SMST_SECURITY_ID"])
    
    # Clean symbols (remove spaces/etc if any)
    df_candidates = df_candidates[df_candidates["SEM_TRADING_SYMBOL"].str.strip() != ""]

    candidates = []
    for idx, row in df_candidates.iterrows():
        candidates.append({
            "symbol": str(row["SEM_TRADING_SYMBOL"]).strip(),
            "security_id": int(row["SEM_SMST_SECURITY_ID"]),
            "instrument_type": str(row["SEM_EXCH_INSTRUMENT_TYPE"]),
            "custom_symbol": str(row["SEM_CUSTOM_SYMBOL"]) if pd.notna(row["SEM_CUSTOM_SYMBOL"]) else ""
        })

    total_scanned = 0
    working = []
    failed_sample = []
    
    connector = DhanConnector()
    
    # Scan first 100
    scan_limit = min(100, len(candidates))
    print(f"Starting live quote scan for up to {scan_limit} candidates...")

    for i in range(scan_limit):
        candidate = candidates[i]
        symbol = candidate["symbol"]
        security_id = candidate["security_id"]
        
        total_scanned += 1
        print(f"Scanned {total_scanned}/{scan_limit}: Symbol: {symbol}, Security ID: {security_id}")
        
        try:
            quote = connector.get_last_price("NSE_EQ", security_id)
            print(f" -> SUCCESS: Price: {quote.get('last_price')}")
            working.append({
                "symbol": symbol,
                "exchange": "NSE_EQ",
                "security_id": security_id,
                "instrument_type": candidate["instrument_type"],
                "last_price": quote.get("last_price")
            })
            if len(working) >= 5:
                print("Found at least 5 working instruments. Stopping early.")
                break
        except Exception as e:
            failed_sample.append({
                "symbol": symbol,
                "security_id": security_id,
                "error": str(e)
            })
            print(f" -> FAIL: {e}")
            
        time.sleep(0.1)

    print("\n" + "="*50)
    print("WORKING_INSTRUMENTS:")
    pprint.pprint(working)
    
    print("\nFAILED_SAMPLE (First 5):")
    pprint.pprint(failed_sample[:5])
    
    print(f"\nTOTAL_SCANNED: {total_scanned}")
    
    if len(working) >= 2:
        print("READY_FOR_PAIR_TEST: YES")
        ref = working[0]
        tgt = working[1]
        print("Recommended pair:")
        print("reference:")
        pprint.pprint({
            "symbol": ref["symbol"],
            "exchange": "NSE_EQ",
            "security_id": ref["security_id"]
        })
        print("target:")
        pprint.pprint({
            "symbol": tgt["symbol"],
            "exchange": "NSE_EQ",
            "security_id": tgt["security_id"]
        })
    else:
        print("READY_FOR_PAIR_TEST: NO")
        print("Need at least two live-working instruments.")
    print("="*50)

if __name__ == "__main__":
    main()
