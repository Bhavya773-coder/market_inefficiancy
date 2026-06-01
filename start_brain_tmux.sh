#!/bin/bash

brew services start redis

SESSION="brain"
PROJECT="$HOME/market_terminal"

tmux kill-session -t $SESSION 2>/dev/null

tmux new-session -d -s $SESSION -n PRODUCER "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 feeds/tick_simulator.py"

tmux new-window -t $SESSION -n FEATURES "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 -m ai.feature_engine"

tmux new-window -t $SESSION -n RANKER "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 -m ai.signal_ranker"

tmux new-window -t $SESSION -n EXECUTION "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 -m ai.execution_engine"

tmux new-window -t $SESSION -n LOGGER "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 -m ai.trade_logger"

tmux new-window -t $SESSION -n DASHBOARD "cd $PROJECT && source venv/bin/activate && PYTHONPATH=. python3 -m ai.live_dashboard"

tmux attach-session -t $SESSION
