"""
Average Directional Index (ADX) - Trend Strength Indicator
Used to determine if market is trending or ranging

Uses Wilder's smoothing method to match MT4/MT5/TradingView calculations.
"""

import pandas as pd
import numpy as np


def wilder_smooth(values: pd.Series, period: int) -> pd.Series:
    """
    Wilder's smoothing method (used by MT4/MT5/TradingView)

    Formula:
    - First value: Simple average of first N periods
    - Subsequent: Previous_Smoothed - (Previous_Smoothed / N) + Current_Value

    This is equivalent to EMA with alpha = 1/period but calculated differently
    to match exactly what trading platforms use.
    """
    smoothed = pd.Series(index=values.index, dtype=float)

    # First value is simple average of first 'period' values
    smoothed.iloc[period - 1] = values.iloc[:period].mean()

    # Subsequent values use Wilder's formula
    for i in range(period, len(values)):
        smoothed.iloc[i] = smoothed.iloc[i - 1] - (smoothed.iloc[i - 1] / period) + values.iloc[i]

    return smoothed


def calculate_adx(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculate ADX (Average Directional Index) using Wilder's method

    This matches MT4/MT5/TradingView ADX calculations.

    Args:
        data: DataFrame with 'high', 'low', 'close' columns
        period: Period for ADX calculation (default 14)

    Returns:
        DataFrame with ADX, +DI, -DI columns added
    """
    df = data.copy()

    if len(df) < period + 1:
        df['adx'] = np.nan
        df['plus_di'] = np.nan
        df['minus_di'] = np.nan
        df['atr'] = np.nan
        return df

    # Calculate True Range
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = np.abs(df['high'] - df['close'].shift(1))
    df['low_close'] = np.abs(df['low'] - df['close'].shift(1))
    df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)

    # Calculate Directional Movement
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']

    # Positive and Negative Directional Movement
    df['plus_dm'] = np.where(
        (df['up_move'] > df['down_move']) & (df['up_move'] > 0),
        df['up_move'],
        0
    )
    df['minus_dm'] = np.where(
        (df['down_move'] > df['up_move']) & (df['down_move'] > 0),
        df['down_move'],
        0
    )

    # Smooth TR and DM using Wilder's method
    df['atr'] = wilder_smooth(df['tr'], period)
    smoothed_plus_dm = wilder_smooth(df['plus_dm'], period)
    smoothed_minus_dm = wilder_smooth(df['minus_dm'], period)

    # Calculate +DI and -DI
    df['plus_di'] = 100 * (smoothed_plus_dm / df['atr'])
    df['minus_di'] = 100 * (smoothed_minus_dm / df['atr'])

    # Calculate DX (Directional Index)
    di_sum = df['plus_di'] + df['minus_di']
    di_diff = np.abs(df['plus_di'] - df['minus_di'])
    df['dx'] = np.where(di_sum != 0, 100 * di_diff / di_sum, 0)

    # Calculate ADX (smoothed DX using Wilder's method)
    # ADX smoothing starts after we have enough DX values
    df['adx'] = wilder_smooth(df['dx'], period)

    # Clean up intermediate columns
    df.drop(['high_low', 'high_close', 'low_close', 'tr', 'up_move', 'down_move',
             'plus_dm', 'minus_dm', 'dx'], axis=1, inplace=True)

    return df


def interpret_adx(adx_value: float, plus_di: float, minus_di: float) -> dict:
    """
    Interpret ADX reading and trend direction

    Args:
        adx_value: ADX value
        plus_di: +DI value
        minus_di: -DI value

    Returns:
        Dict with interpretation
    """
    # Determine trend strength
    if adx_value < 20:
        strength = "weak"
        market_type = "ranging"
    elif adx_value < 25:
        strength = "developing"
        market_type = "weak_trend"
    elif adx_value < 40:
        strength = "moderate"
        market_type = "trending"
    elif adx_value < 50:
        strength = "strong"
        market_type = "strong_trend"
    else:
        strength = "very_strong"
        market_type = "very_strong_trend"

    # Determine trend direction
    if plus_di > minus_di:
        direction = "bullish"
    else:
        direction = "bearish"

    # Confidence (higher when DI lines are far apart)
    confidence = abs(plus_di - minus_di)

    return {
        'adx': adx_value,
        'plus_di': plus_di,
        'minus_di': minus_di,
        'strength': strength,
        'market_type': market_type,
        'direction': direction,
        'confidence': confidence,
        'is_ranging': adx_value < 25,
        'is_trending': adx_value >= 25
    }


def analyze_candle_direction(data: pd.DataFrame, lookback: int = 5) -> dict:
    """
    Analyze recent candle direction to confirm trend

    Args:
        data: DataFrame with OHLC data
        lookback: Number of candles to look back

    Returns:
        Dict with candle analysis
    """
    recent = data.tail(lookback)

    # Count bullish vs bearish candles
    bullish_candles = (recent['close'] > recent['open']).sum()
    bearish_candles = (recent['close'] < recent['open']).sum()

    # Calculate average body size
    body_sizes = np.abs(recent['close'] - recent['open'])
    avg_body = body_sizes.mean()

    # Calculate percentage of aligned candles
    total_candles = len(recent)
    bullish_pct = (bullish_candles / total_candles) * 100
    bearish_pct = (bearish_candles / total_candles) * 100

    # Determine if candles are aligned (mostly same direction)
    alignment_threshold = 70  # 70% of candles in same direction

    if bullish_pct >= alignment_threshold:
        alignment = "strong_bullish"
        aligned = True
        direction = "bullish"
    elif bearish_pct >= alignment_threshold:
        alignment = "strong_bearish"
        aligned = True
        direction = "bearish"
    elif bullish_pct >= 60:
        alignment = "weak_bullish"
        aligned = False
        direction = "bullish"
    elif bearish_pct >= 60:
        alignment = "weak_bearish"
        aligned = False
        direction = "bearish"
    else:
        alignment = "mixed"
        aligned = False
        direction = "neutral"

    return {
        'lookback': lookback,
        'bullish_candles': bullish_candles,
        'bearish_candles': bearish_candles,
        'bullish_pct': bullish_pct,
        'bearish_pct': bearish_pct,
        'alignment': alignment,
        'aligned': aligned,
        'direction': direction,
        'avg_body': avg_body
    }


def should_trade_based_on_trend(
    adx_value: float,
    plus_di: float,
    minus_di: float,
    candle_data: pd.DataFrame,
    candle_lookback: int = 5,
    adx_threshold: float = 25,
    allow_weak_trends: bool = True
) -> tuple[bool, str]:
    """
    Determine if we should trade based on trend analysis

    Args:
        adx_value: Current ADX value
        plus_di: Current +DI value
        minus_di: Current -DI value
        candle_data: Recent candle data
        candle_lookback: Number of candles to analyze
        adx_threshold: ADX threshold for "trending" market
        allow_weak_trends: Allow trading in weak trends (ADX 20-25)

    Returns:
        Tuple of (should_trade, reason)
    """
    # Get ADX interpretation
    adx_info = interpret_adx(adx_value, plus_di, minus_di)

    # Get candle alignment
    candle_info = analyze_candle_direction(candle_data, candle_lookback)

    # Rule 1: Strong trend (ADX > 40) = NO TRADE
    if adx_value > 40:
        return False, f"Strong trend detected (ADX: {adx_value:.1f}) - Mean reversion unsafe"

    # Rule 2: Moderate trend (ADX 25-40) + aligned candles = NO TRADE
    if adx_value >= adx_threshold and candle_info['aligned']:
        return False, f"Trending market (ADX: {adx_value:.1f}) + {candle_info['alignment']} candles - Mean reversion risky"

    # Rule 3: Weak trend (ADX 20-25) = TRADE if candles not strongly aligned
    if 20 <= adx_value < adx_threshold:
        if candle_info['aligned']:
            return False, f"Weak trend (ADX: {adx_value:.1f}) with aligned candles - Proceed with caution"
        else:
            if allow_weak_trends:
                return True, f"Weak trend (ADX: {adx_value:.1f}) + mixed candles - OK to trade"
            else:
                return False, f"Weak trend detected (ADX: {adx_value:.1f}) - Trading disabled"

    # Rule 4: Ranging market (ADX < 20) = TRADE
    if adx_value < 20:
        return True, f"Ranging market (ADX: {adx_value:.1f}) - Ideal for mean reversion"

    # Rule 5: Moderate trend but candles NOT aligned = TRADE (trend may be weakening)
    if adx_value >= adx_threshold and not candle_info['aligned']:
        return True, f"Trend (ADX: {adx_value:.1f}) but mixed candles - Possible reversal"

    # Default: Allow trade
    return True, "Trend analysis passed"
