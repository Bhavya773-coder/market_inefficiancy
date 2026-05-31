#!/bin/bash

echo ""
echo "=== BRAIN PROCESS STATUS ==="
echo ""

ps aux | grep -E "tick_simulator|feature_engine|signal_ranker|execution_engine|trade_logger|live_dashboard" | grep -v grep

echo ""
echo "=== TMUX SESSIONS ==="
echo ""

tmux ls
