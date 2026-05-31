CURRENT DATA SOURCES

Available Today

- Dhan API

Planned Future Sources

- NSE
- MCX
- LME
- COMEX
- Forex
- Crypto
- Steel Physical Markets

Development Rule

Every new data source must be added through a connector.

No direct exchange-specific logic inside:

- execution_engine.py
- signal_ranker.py
- portfolio_manager.py

All market data enters through connectors.