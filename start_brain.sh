#!/bin/bash

brew services start redis

PROJECT="$HOME/market_terminal"

osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 feeds/tick_simulator.py"
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.feature_engine"
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.signal_ranker"
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.execution_engine"
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.trade_logger"
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.live_dashboard"
end tell
APPLESCRIPT
