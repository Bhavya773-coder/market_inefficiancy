NEXT BUILD

Connector Interface

Purpose

Standardize all incoming market data.

Required Fields

source
asset
bid
ask
last_price
currency
timestamp
liquidity_score

Rule

Every future connector must return the same structure.

Examples

Dhan Connector
MCX Connector
Steel Connector
Forex Connector
Crypto Connector

Success Condition

The inefficiency engine can consume data from any source without knowing where it came from.