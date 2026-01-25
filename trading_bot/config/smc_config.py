"""
SMC (Smart Money Concepts) Configuration
Multi-Timeframe Order Block Analysis with Liquidity Sweeps
"""

# =============================================================================
# SMC TIMEFRAME HIERARCHY
# =============================================================================

# Higher timeframes for structure and order blocks
SMC_HTF_TIMEFRAMES = ['H4', 'H1']

# Lower timeframe for order blocks (MUST be included in confluence)
SMC_LTF_TIMEFRAME = 'M15'

# Entry timeframe for precision timing
SMC_ENTRY_TIMEFRAME = 'M5'

# =============================================================================
# ORDER BLOCK DETECTION PARAMETERS
# =============================================================================

# Order Block Detection
OB_LOOKBACK = 50  # Bars to look back for order blocks
OB_MIN_BODY_RATIO = 0.5  # Minimum body/range ratio for valid OB candle
OB_MITIGATION_TOUCH = True  # OB is mitigated when price touches (not just closes through)

# Order Block Zone Extension (pips from OB high/low)
OB_ZONE_EXTENSION_PIPS = {
    'H4': 15,   # Wider zones on higher timeframes
    'H1': 10,
    'M15': 5,
    'M5': 3
}

# Maximum Order Blocks to track per timeframe
MAX_ORDER_BLOCKS = 10

# Order Block Validity (bars before expiry)
OB_VALIDITY_BARS = {
    'H4': 30,   # ~5 days
    'H1': 48,   # ~2 days
    'M15': 96,  # ~1 day
    'M5': 144   # ~12 hours
}

# =============================================================================
# BREAK OF STRUCTURE (BOS) / CHANGE OF CHARACTER (ChoCH) PARAMETERS
# =============================================================================

# Swing detection lookback
SWING_LOOKBACK = {
    'H4': 5,    # 5 bars = 20 hours for swing detection
    'H1': 7,    # 7 bars = 7 hours
    'M15': 10,  # 10 bars = 2.5 hours
    'M5': 12    # 12 bars = 1 hour
}

# BOS confirmation (price must close beyond swing)
BOS_CLOSE_CONFIRMATION = True

# ChoCH detection (first lower high in uptrend / first higher low in downtrend)
CHOCH_ENABLED = True

# =============================================================================
# FAIR VALUE GAP (FVG) PARAMETERS
# =============================================================================

# FVG Detection
FVG_LOOKBACK = 30  # Bars to look back for FVGs
FVG_MIN_SIZE_PIPS = {
    'H4': 20,   # Minimum gap size in pips
    'H1': 10,
    'M15': 5,
    'M5': 3
}

# FVG Mitigation (considered filled when price returns)
FVG_MITIGATION_PERCENT = 50  # FVG is mitigated when 50% filled

# =============================================================================
# LIQUIDITY PARAMETERS
# =============================================================================

# Liquidity Pool Detection
LIQUIDITY_LOOKBACK = 50  # Bars for liquidity pool detection
LIQUIDITY_CLUSTER_TOLERANCE = 0.001  # 0.1% - swings within this range form a pool
LIQUIDITY_MIN_TOUCHES = 2  # Minimum touches to form a liquidity pool

# Liquidity Sweep Detection
SWEEP_CONFIRMATION_CANDLES = 1  # Number of candles to confirm sweep
SWEEP_MIN_WICK_RATIO = 0.5  # Minimum wick/body ratio for sweep candle

# Equal Highs/Lows Detection (built-up liquidity)
EQUAL_HIGHS_TOLERANCE = 0.0005  # 0.05% tolerance for "equal" highs/lows
EQUAL_HIGHS_MIN_COUNT = 2  # Minimum equal highs/lows to form a target

# =============================================================================
# CONFLUENCE REQUIREMENTS
# =============================================================================

# Minimum number of timeframe OBs that must align
MIN_TF_CONFLUENCE = 2  # At least 2 timeframes must have aligned OBs

# M15 OB is REQUIRED in confluence (per user request)
M15_OB_REQUIRED = True

# Confluence Zone Tolerance (price must be within this % of zone)
CONFLUENCE_ZONE_TOLERANCE = 0.003  # 0.3%

# Liquidity Sweep Required for Entry Signal
LIQUIDITY_SWEEP_REQUIRED = True

# =============================================================================
# M5 ENTRY TIMING PARAMETERS
# =============================================================================

# Entry Timing (wait for reversal signs on M5)
M5_ENTRY_LOOKBACK = 6  # Bars to analyze for reversal

# ChoCH on M5 (Change of Character - reversal confirmation)
M5_CHOCH_REQUIRED = True

# Reversal Candle Patterns
REVERSAL_PATTERNS = {
    'pin_bar': True,      # Long wick rejection
    'engulfing': True,    # Engulfing pattern
    'inside_bar': False,  # Inside bar (optional - less reliable)
    'doji': True,         # Indecision candle
}

# Pin Bar Detection
PIN_BAR_WICK_RATIO = 2.0  # Wick must be 2x the body
PIN_BAR_BODY_POSITION = 0.3  # Body must be in upper/lower 30% of range

# Momentum Slowdown Detection
MOMENTUM_SLOWDOWN_BARS = 3  # Check last N bars for decreasing range
MOMENTUM_DECREASE_THRESHOLD = 0.7  # Range must decrease by 30%

# =============================================================================
# M15 ZONE GAUGE (Stay Out Filter)
# =============================================================================

# If price goes straight through M15 OB zone, stay out of market
M15_ZONE_BREACH_BARS = 2  # If price closes beyond OB for 2 bars, zone is invalid
M15_ZONE_BREACH_COOLDOWN = 4  # Wait 4 M15 bars (1 hour) after breach before trading

# =============================================================================
# TRADE MANAGEMENT
# =============================================================================

# Stop Loss Placement
SL_BEYOND_OB_PIPS = {
    'H4': 20,
    'H1': 15,
    'M15': 10,
    'M5': 5
}

# Take Profit Targets (multiples of SL distance)
TP_RATIOS = [1.5, 2.0, 3.0]  # 1.5R, 2R, 3R

# Partial Close at Each TP Level
PARTIAL_CLOSE_PERCENTS = [50, 30, 20]  # Close 50% at TP1, 30% at TP2, 20% at TP3

# =============================================================================
# CONFLUENCE SCORING WEIGHTS
# =============================================================================

SMC_CONFLUENCE_WEIGHTS = {
    # Order Block Weights (by timeframe)
    'h4_ob': 4,       # H4 Order Block (highest weight)
    'h1_ob': 3,       # H1 Order Block
    'm15_ob': 2,      # M15 Order Block (required)

    # BOS/ChoCH Weights
    'h4_bos': 3,      # H4 Break of Structure
    'h1_bos': 2,      # H1 Break of Structure
    'm15_bos': 2,     # M15 Break of Structure
    'choch': 3,       # Change of Character (reversal)

    # FVG Weights
    'h4_fvg': 2,      # H4 Fair Value Gap
    'h1_fvg': 2,      # H1 Fair Value Gap
    'm15_fvg': 1,     # M15 Fair Value Gap

    # Liquidity Weights
    'liquidity_sweep': 4,       # Liquidity sweep occurred
    'equal_highs_lows': 2,      # Equal highs/lows (built-up liquidity)
    'swing_level': 1,           # At swing high/low

    # M5 Entry Weights
    'm5_choch': 3,              # ChoCH on M5
    'm5_reversal_candle': 2,    # Reversal pattern on M5
    'm5_momentum_slowdown': 1,  # Momentum slowing on M5
}

# Minimum confluence score for valid entry
MIN_SMC_CONFLUENCE_SCORE = 8

# Optimal confluence score (high probability setups)
OPTIMAL_SMC_CONFLUENCE_SCORE = 12

# =============================================================================
# VISUAL/DEBUG OUTPUT
# =============================================================================

# Debug output
SMC_DEBUG = False

# Log all detected structures
LOG_SMC_STRUCTURES = True

# =============================================================================
# DATA REQUIREMENTS
# =============================================================================

# Minimum bars required per timeframe
MIN_BARS_REQUIRED = {
    'H4': 100,
    'H1': 200,
    'M15': 500,
    'M5': 1000
}
