import pandas as pd

print("Searching for NIFTY ETFs in security_id_list.csv...")

chunk_size = 50000
matching_rows = []

for chunk in pd.read_csv("security_id_list.csv", chunksize=chunk_size, low_memory=False):
    # Filter NSE segment
    eq_chunk = chunk[chunk["SEM_EXM_EXCH_ID"] == "NSE"]
    # Look for matching symbol names or trading symbols in the SEM_TRADING_SYMBOL column
    mask = eq_chunk["SEM_TRADING_SYMBOL"].astype(str).str.contains("NIFTY", case=False, na=False)
    filtered = eq_chunk[mask]
    if not filtered.empty:
        matching_rows.append(filtered)

if matching_rows:
    df_results = pd.concat(matching_rows)
    # Filter only for Series 'EQ' (Equity shares / ETFs)
    df_eq = df_results[df_results["SEM_SERIES"] == "EQ"]
    print(f"Found {len(df_eq)} Nifty ETFs/shares on NSE:")
    cols = ["SEM_SMST_SECURITY_ID", "SEM_TRADING_SYMBOL", "SEM_INSTRUMENT_NAME"]
    print(df_eq[cols].drop_duplicates().to_string(index=False))
else:
    print("No matching Nifty instruments found.")
