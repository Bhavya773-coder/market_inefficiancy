#!/bin/bash

cd ~/market_terminal
source venv/bin/activate

echo ""
python3 -m ai.memory_report

echo ""
python3 replay/strategy_report.py

echo ""
python3 replay/blocklist_report.py
