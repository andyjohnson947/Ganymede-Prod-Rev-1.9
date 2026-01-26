"""
SMC Configuration - Paul's Methodology
Based on TradeForexwithPaul's approach

Key Principles:
1. HTF (1H-4H) for bias and Points of Interest (POI)
2. LTF (5m-1m) for precise entries
3. Wait for liquidity sweep INTO POI
4. Market Structure Shift (MSS) on LTF confirms reversal
5. Enter on pullback to LTF imbalance/OB
6. Tight entries for high R:R (3R+ targets)

NO indicators - pure price action.
"""

# =============================================================================
# TIMEFRAME SETUP (Paul's Method)
# =============================================================================

# Higher Timeframe - Used for bias and marking POIs
HTF_TIMEFRAME = 'H1'  # Can also use H4 for bigger picture

# Lower Timeframe - Used for precise entries
LTF_TIMEFRAME = 'M5'  # Can also use M1 for tighter entries

# Optional: Very high timeframe for overall bias
BIAS_TIMEFRAME = 'H4'

# =============================================================================
# POINTS OF INTEREST (POI) - Where We Look for Trades
# =============================================================================

# POI Types to track on HTF
POI_TYPES = {
    'previous_highs': True,       # Previous swing highs (liquidity above)
    'previous_lows': True,        # Previous swing lows (liquidity below)
    'session_highs': True,        # London/NY session highs
    'session_lows': True,         # London/NY session lows
    'equal_highs': True,          # Equal highs (obvious liquidity)
    'equal_lows': True,           # Equal lows (obvious liquidity)
    'imbalance_zones': True,      # FVG / Imbalance areas
    'order_blocks': True,         # Supply/Demand zones
}

# Swing detection for highs/lows
SWING_LOOKBACK_HTF = 7   # Bars to confirm swing high/low on HTF
SWING_LOOKBACK_LTF = 5   # Bars to confirm swing high/low on LTF

# Equal highs/lows tolerance (how close = "equal")
EQUAL_LEVEL_TOLERANCE = 0.0003  # 0.03% = ~3 pips on most pairs

# =============================================================================
# SESSION TIMES (GMT) - For Session High/Low POIs
# =============================================================================

SESSIONS = {
    'london': {
        'start': 8,   # 08:00 GMT
        'end': 16,    # 16:00 GMT
        'enabled': True
    },
    'new_york': {
        'start': 13,  # 13:00 GMT
        'end': 21,    # 21:00 GMT
        'enabled': True
    },
    'asian': {
        'start': 0,   # 00:00 GMT
        'end': 8,     # 08:00 GMT
        'enabled': True
    }
}

# Track previous day's high/low
TRACK_PREVIOUS_DAY_HL = True

# Track previous week's high/low
TRACK_PREVIOUS_WEEK_HL = True

# =============================================================================
# LIQUIDITY SWEEP DETECTION (Critical for Entry)
# =============================================================================

# Liquidity must be taken BEFORE entry is valid
LIQUIDITY_SWEEP_REQUIRED = True

# What counts as a sweep:
# - Price runs ABOVE highs (for shorts) or BELOW lows (for longs)
# - This is the "trap" phase where retail stops get hit

# Sweep confirmation
SWEEP_MUST_CLOSE_BACK = True  # Price must close back inside after sweep
SWEEP_MIN_PENETRATION_PIPS = 2  # Minimum pips beyond level to count as sweep

# =============================================================================
# MARKET STRUCTURE SHIFT (MSS) - Entry Confirmation
# =============================================================================

# After liquidity sweep, wait for MSS on LTF
MSS_REQUIRED = True

# MSS = Break of internal structure in OPPOSITE direction to sweep
# If price swept highs (bearish setup): MSS = break of recent LTF low
# If price swept lows (bullish setup): MSS = break of recent LTF high

# MSS must be a clear break (close beyond, not just wick)
MSS_CLOSE_CONFIRMATION = True

# Number of LTF bars to look back for structure
MSS_LOOKBACK_BARS = 20

# =============================================================================
# ENTRY RULES (Tight Entry for High R:R)
# =============================================================================

# Entry method after MSS confirmed:
ENTRY_METHOD = 'pullback'  # Options: 'pullback', 'break', 'immediate'

# Pullback entry - wait for price to retrace to:
PULLBACK_TO = 'imbalance'  # Options: 'imbalance', 'ob', '50_fib', 'breaker'

# If no pullback within X bars, skip the trade
MAX_BARS_FOR_PULLBACK = 10

# Entry must be TIGHT - this creates high R:R
# Enter at edge of imbalance/OB, not middle

# =============================================================================
# IMBALANCE / FAIR VALUE GAP (FVG)
# =============================================================================

# Imbalance = gap between candle 1 high and candle 3 low (or vice versa)
IMBALANCE_MIN_SIZE_PIPS = 3  # Minimum gap size to be valid

# Use imbalance as entry zone on LTF
USE_LTF_IMBALANCE_ENTRY = True

# =============================================================================
# STOP LOSS PLACEMENT (Paul's Tight SL for High R:R)
# =============================================================================

# SL goes JUST beyond the liquidity sweep high/low
# This is intentionally VERY TIGHT - creates 10R-50R+ potential
SL_BEYOND_SWEEP_PIPS = 2  # Pips beyond the sweep point (tight!)

# If price RE-SWEEPS the level after entry = trade is INVALID
# Exit immediately - idea is wrong
RESWEEP_INVALIDATES_TRADE = True

# =============================================================================
# TAKE PROFIT / TARGETS (Opposite-Side Liquidity)
# =============================================================================

# Primary targets = OPPOSITE SIDE LIQUIDITY
# - Previous highs/lows
# - Session range highs/lows
# - Major HTF structure points
TARGET_OPPOSITE_LIQUIDITY = True

# Partial profit levels (R multiples)
PARTIAL_TP_LEVELS = {
    'secure': 1.0,    # First partial at 1R to reduce risk
    'profit': 3.0,    # Second partial at 3R
    'runner': None,   # Let runner go to full liquidity target
}

# Partial close percentages
PARTIAL_CLOSE = {
    'secure': 30,     # Close 30% at 1R (secures some profit)
    'profit': 40,     # Close 40% at 3R (bank profits)
    'runner': 30,     # Let 30% run for big move (10R-50R potential)
}

# Move SL to breakeven after first partial
MOVE_SL_TO_BE_AFTER_PARTIAL = True

# Minimum R:R - don't take trades with less potential
MIN_RISK_REWARD = 3.0  # Only take 3R+ setups

# =============================================================================
# RISK MANAGEMENT (Paul's Asymmetric R:R Approach)
# =============================================================================

# Fixed % risk per trade - VERY SMALL
RISK_PER_TRADE_PERCENT = 0.5  # 0.5% risk per trade

# High win rate NOT required with this strategy
# Strategy relies on ASYMMETRIC R:R (small losses, big wins)
# Expected win rate: 30-40% is fine with 10R+ winners

# Losses are EXPECTED and accepted quickly
# If trade doesn't work immediately after entry, it's probably wrong

# Maximum loss per day (as % of account)
MAX_DAILY_LOSS_PERCENT = 2.0  # Stop trading after 2% daily loss

# Maximum consecutive losses before pause
MAX_CONSECUTIVE_LOSSES = 4

# =============================================================================
# TRADE RULES (No Chasing!)
# =============================================================================

# NEVER chase price - wait for it to come to your POI
NO_CHASE_RULE = True

# If price moves away from POI without triggering entry, wait for next setup
# Don't FOMO in

# Bias only valid AFTER liquidity taken
BIAS_REQUIRES_LIQUIDITY = True

# =============================================================================
# FILTERING / AVOIDING BAD TRADES
# =============================================================================

# Don't trade if:
AVOID_NEWS_EVENTS = True  # Around high-impact news
AVOID_SESSION_CLOSE = True  # Last 30 mins of session
AVOID_FRIDAY_AFTERNOON = True  # After 14:00 GMT Friday
AVOID_SUNDAY_OPEN = True  # First 2 hours of week

# Maximum trades per day
MAX_TRADES_PER_DAY = 3

# Maximum trades per session
MAX_TRADES_PER_SESSION = 2

# =============================================================================
# DATA REQUIREMENTS
# =============================================================================

MIN_BARS_REQUIRED = {
    'H4': 100,   # ~16 days
    'H1': 200,   # ~8 days
    'M15': 400,  # ~4 days
    'M5': 500,   # ~1.7 days
    'M1': 1000,  # ~16 hours
}

# =============================================================================
# DEBUG / LOGGING
# =============================================================================

SMC_DEBUG = False
LOG_POI_DETECTION = True
LOG_LIQUIDITY_SWEEPS = True
LOG_MSS_DETECTION = True
LOG_ENTRY_SIGNALS = True
