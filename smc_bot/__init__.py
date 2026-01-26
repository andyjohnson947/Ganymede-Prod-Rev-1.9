"""
SMC Trade Bot - Paul's Methodology
Based on TradeForexwithPaul's approach

A standalone Smart Money Concepts trading bot that is separate from the main
Ganymede trading system.

Entry Flow:
1. Mark HTF POIs (previous highs/lows, session levels)
2. Wait for price to raid liquidity INTO the POI
3. Look for MSS (Market Structure Shift) on LTF
4. Enter on pullback to LTF imbalance
5. SL just beyond sweep (tight!)
6. TP at opposite-side liquidity

Usage:
    python -m smc_bot.smc_trade_bot [--test] [--debug] [--symbols EURUSD GBPUSD]
"""

from smc_bot.smc_trade_bot import SMCTradeBot

__all__ = ['SMCTradeBot']
__version__ = '1.0.0'
