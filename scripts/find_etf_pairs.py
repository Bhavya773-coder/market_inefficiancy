import pandas as pd

print("Searching for ETF symbols in security_id_list.csv...")

chunk_size = 50000
matching_rows = []

# We want to find Nifty ETFs, Gold ETFs, Bank Nifty ETFs
target_keywords = ["BEES", "SBIETFNIF", "HDFCNIFY", "ICICILIQ", "LIQUIDBEES", "NIFTY50"]

for chunk in pd.read_csv("security_id_list.csv", chunksize=chunk_size, low_memory=False):
    # Filter NSE segment
    eq_chunk = chunk[chunk["SEM_EXM_EXCH_ID"] == "NSE"]
    # Look for matching symbol names or trading symbols in the SEM_TRADING_SYMBOL column
    mask = eq_chunk["SEM_TRADING_SYMBOL"].astype(str).str.contains("|".join(target_keywords), case=False, na=False)
    filtered = eq_chunk[mask]
    if not filtered.empty:
        matching_rows.append(filtered)

if matching_rows:
    df_results = pd.concat(matching_rows)
    print(f"Found {len(df_results)} matching instruments:")
    # Print a nice table of selected columns
    cols = ["SEM_SMST_SECURITY_ID", "SEM_TRADING_SYMBOL", "SEM_INSTRUMENT_NAME", "SEM_SERIES"]
    print(df_results[cols].drop_duplicates().head(60).to_string(index=False))
else:
    print("No matching instruments found.")
