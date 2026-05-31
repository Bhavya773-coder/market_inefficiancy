#!/bin/bash

pkill -f tick_simulator.py
pkill -f ai.feature_engine
pkill -f ai.signal_ranker
pkill -f ai.execution_engine
pkill -f ai.trade_logger
pkill -f ai.live_dashboard

echo "Trading brain stopped."

brew services stop redis
