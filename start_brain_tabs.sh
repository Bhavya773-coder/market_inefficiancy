#!/bin/bash

brew services start redis

PROJECT="$HOME/market_terminal"

osascript <<APPLESCRIPT
tell application "Terminal"
    activate

    set w to do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 feeds/tick_simulator.py"

    delay 1
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.feature_engine" in w

    delay 1
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.signal_ranker" in w

    delay 1
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.execution_engine" in w

    delay 1
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.trade_logger" in w

    delay 1
    do script "cd $PROJECT; source venv/bin/activate; PYTHONPATH=. python3 -m ai.live_dashboard" in w

end tell
APPLESCRIPT
