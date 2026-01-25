"""
SMC (Smart Money Concepts) Indicators
Implements Order Blocks, BOS/ChoCH, FVG, Liquidity, and Swing detection
Inspired by joshyattridge/smart-money-concepts library

Order Blocks are identified as ZONES with:
- top: Upper boundary
- bottom: Lower boundary
- direction: bullish/bearish
- mitigated: Whether zone has been touched/invalidated
- strength: Quality score
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class Zone:
    """Base class for price zones (Order Blocks, FVG, Liquidity)"""
    top: float
    bottom: float
    direction: Direction
    time_created: datetime
    bar_index: int
    mitigated: bool = False
    mitigation_time: Optional[datetime] = None
    strength: float = 1.0
    timeframe: str = ""

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float, tolerance: float = 0.0) -> bool:
        """Check if price is within the zone (with optional tolerance)"""
        tolerance_value = self.size * tolerance
        return (self.bottom - tolerance_value) <= price <= (self.top + tolerance_value)

    def to_dict(self) -> Dict:
        return {
            'top': self.top,
            'bottom': self.bottom,
            'direction': self.direction.value,
            'time_created': self.time_created,
            'bar_index': self.bar_index,
            'mitigated': self.mitigated,
            'mitigation_time': self.mitigation_time,
            'strength': self.strength,
            'timeframe': self.timeframe,
            'midpoint': self.midpoint,
            'size': self.size
        }


@dataclass
class OrderBlock(Zone):
    """Order Block Zone - Institutional supply/demand area"""
    ob_type: str = "ob"  # 'ob' or 'breaker'
    volume: float = 0.0
    tested_count: int = 0

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base.update({
            'ob_type': self.ob_type,
            'volume': self.volume,
            'tested_count': self.tested_count
        })
        return base


@dataclass
class FairValueGap(Zone):
    """Fair Value Gap - Price imbalance zone"""
    gap_type: str = "fvg"  # 'fvg' or 'ifvg' (inverse)
    fill_percent: float = 0.0

    def to_dict(self) -> Dict:
        base = super().to_dict()
        base.update({
            'gap_type': self.gap_type,
            'fill_percent': self.fill_percent
        })
        return base


@dataclass
class LiquidityPool:
    """Liquidity Pool - Clustered swing highs/lows"""
    level: float
    direction: Direction  # BULLISH = buy-side liquidity (highs), BEARISH = sell-side (lows)
    touches: int
    first_touch_time: datetime
    last_touch_time: datetime
    bar_indices: List[int] = field(default_factory=list)
    swept: bool = False
    sweep_time: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            'level': self.level,
            'direction': self.direction.value,
            'touches': self.touches,
            'first_touch_time': self.first_touch_time,
            'last_touch_time': self.last_touch_time,
            'swept': self.swept,
            'sweep_time': self.sweep_time
        }


@dataclass
class SwingPoint:
    """Swing High/Low point"""
    price: float
    time: datetime
    bar_index: int
    direction: Direction  # BULLISH = swing high, BEARISH = swing low

    def to_dict(self) -> Dict:
        return {
            'price': self.price,
            'time': self.time,
            'bar_index': self.bar_index,
            'direction': self.direction.value
        }


@dataclass
class StructureBreak:
    """Break of Structure (BOS) or Change of Character (ChoCH)"""
    break_type: str  # 'bos' or 'choch'
    direction: Direction
    price: float
    time: datetime
    bar_index: int
    swing_broken: SwingPoint

    def to_dict(self) -> Dict:
        return {
            'break_type': self.break_type,
            'direction': self.direction.value,
            'price': self.price,
            'time': self.time,
            'bar_index': self.bar_index,
            'swing_broken': self.swing_broken.to_dict()
        }


class SMCIndicators:
    """
    Smart Money Concepts Indicator Calculator

    Detects:
    - Order Blocks (as zones with top/bottom)
    - Break of Structure (BOS) and Change of Character (ChoCH)
    - Fair Value Gaps (FVG)
    - Liquidity Pools and Sweeps
    - Swing Highs/Lows
    """

    def __init__(
        self,
        swing_lookback: int = 7,
        ob_lookback: int = 50,
        fvg_lookback: int = 30,
        liquidity_lookback: int = 50,
        pip_value: float = 0.0001,
        timeframe: str = "H1"
    ):
        self.swing_lookback = swing_lookback
        self.ob_lookback = ob_lookback
        self.fvg_lookback = fvg_lookback
        self.liquidity_lookback = liquidity_lookback
        self.pip_value = pip_value
        self.timeframe = timeframe

        # Storage for detected structures
        self.swing_highs: List[SwingPoint] = []
        self.swing_lows: List[SwingPoint] = []
        self.order_blocks: List[OrderBlock] = []
        self.fair_value_gaps: List[FairValueGap] = []
        self.liquidity_pools: List[LiquidityPool] = []
        self.structure_breaks: List[StructureBreak] = []

        # Market structure tracking
        self.current_trend: Direction = Direction.NEUTRAL
        self.last_higher_high: Optional[SwingPoint] = None
        self.last_higher_low: Optional[SwingPoint] = None
        self.last_lower_high: Optional[SwingPoint] = None
        self.last_lower_low: Optional[SwingPoint] = None

    def analyze(self, data: pd.DataFrame) -> Dict:
        """
        Perform full SMC analysis on price data

        Args:
            data: DataFrame with OHLCV data (must have: open, high, low, close, volume/tick_volume)

        Returns:
            Dict with all detected SMC structures
        """
        if len(data) < max(self.swing_lookback * 2, 10):
            return self._empty_analysis()

        # Ensure we have datetime index or time column
        if 'time' not in data.columns and not isinstance(data.index, pd.DatetimeIndex):
            # Create time column from index
            data = data.copy()
            data['time'] = data.index

        # Step 1: Detect Swing Highs and Lows
        self.swing_highs, self.swing_lows = self._detect_swings(data)

        # Step 2: Determine Market Structure and detect BOS/ChoCH
        self.structure_breaks = self._detect_structure_breaks(data)

        # Step 3: Detect Order Blocks
        self.order_blocks = self._detect_order_blocks(data)

        # Step 4: Detect Fair Value Gaps
        self.fair_value_gaps = self._detect_fvg(data)

        # Step 5: Detect Liquidity Pools
        self.liquidity_pools = self._detect_liquidity_pools(data)

        # Step 6: Check for Liquidity Sweeps
        self._check_liquidity_sweeps(data)

        # Step 7: Check for mitigated Order Blocks and FVGs
        self._check_mitigation(data)

        return self.get_analysis_summary()

    def _detect_swings(self, data: pd.DataFrame) -> Tuple[List[SwingPoint], List[SwingPoint]]:
        """Detect swing highs and swing lows"""
        swing_highs = []
        swing_lows = []

        lookback = self.swing_lookback

        for i in range(lookback, len(data) - lookback):
            # Check for swing high
            current_high = data.iloc[i]['high']
            is_swing_high = True

            for j in range(i - lookback, i + lookback + 1):
                if j != i and data.iloc[j]['high'] >= current_high:
                    is_swing_high = False
                    break

            if is_swing_high:
                time_val = data.iloc[i]['time'] if 'time' in data.columns else data.index[i]
                swing_highs.append(SwingPoint(
                    price=current_high,
                    time=time_val,
                    bar_index=i,
                    direction=Direction.BULLISH
                ))

            # Check for swing low
            current_low = data.iloc[i]['low']
            is_swing_low = True

            for j in range(i - lookback, i + lookback + 1):
                if j != i and data.iloc[j]['low'] <= current_low:
                    is_swing_low = False
                    break

            if is_swing_low:
                time_val = data.iloc[i]['time'] if 'time' in data.columns else data.index[i]
                swing_lows.append(SwingPoint(
                    price=current_low,
                    time=time_val,
                    bar_index=i,
                    direction=Direction.BEARISH
                ))

        return swing_highs, swing_lows

    def _detect_structure_breaks(self, data: pd.DataFrame) -> List[StructureBreak]:
        """Detect Break of Structure (BOS) and Change of Character (ChoCH)"""
        breaks = []

        if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
            return breaks

        # Combine and sort all swings by time
        all_swings = sorted(
            self.swing_highs + self.swing_lows,
            key=lambda x: x.bar_index
        )

        # Track trend and structure
        trend = Direction.NEUTRAL
        last_swing_high: Optional[SwingPoint] = None
        last_swing_low: Optional[SwingPoint] = None

        for i, swing in enumerate(all_swings):
            if swing.direction == Direction.BULLISH:  # Swing high
                if last_swing_high is not None:
                    # Check for higher high (bullish continuation)
                    if swing.price > last_swing_high.price:
                        if trend == Direction.BULLISH:
                            # BOS - continuation of bullish structure
                            pass  # Normal structure, no break
                        elif trend == Direction.BEARISH:
                            # ChoCH - Bearish to Bullish
                            breaks.append(StructureBreak(
                                break_type='choch',
                                direction=Direction.BULLISH,
                                price=last_swing_high.price,
                                time=swing.time,
                                bar_index=swing.bar_index,
                                swing_broken=last_swing_high
                            ))
                            trend = Direction.BULLISH
                    # Check for lower high (potential bearish ChoCH)
                    elif swing.price < last_swing_high.price and trend == Direction.BULLISH:
                        # First lower high in uptrend = potential ChoCH
                        self.last_lower_high = swing

                last_swing_high = swing

            else:  # Swing low
                if last_swing_low is not None:
                    # Check for lower low (bearish continuation)
                    if swing.price < last_swing_low.price:
                        if trend == Direction.BEARISH:
                            # BOS - continuation of bearish structure
                            breaks.append(StructureBreak(
                                break_type='bos',
                                direction=Direction.BEARISH,
                                price=last_swing_low.price,
                                time=swing.time,
                                bar_index=swing.bar_index,
                                swing_broken=last_swing_low
                            ))
                        elif trend == Direction.BULLISH:
                            # ChoCH - Bullish to Bearish
                            breaks.append(StructureBreak(
                                break_type='choch',
                                direction=Direction.BEARISH,
                                price=last_swing_low.price,
                                time=swing.time,
                                bar_index=swing.bar_index,
                                swing_broken=last_swing_low
                            ))
                            trend = Direction.BEARISH
                    # Check for higher low (potential bullish ChoCH)
                    elif swing.price > last_swing_low.price and trend == Direction.BEARISH:
                        # First higher low in downtrend = potential ChoCH
                        self.last_higher_low = swing

                    # BOS - break of structure
                    if swing.price < last_swing_low.price and trend == Direction.BEARISH:
                        breaks.append(StructureBreak(
                            break_type='bos',
                            direction=Direction.BEARISH,
                            price=last_swing_low.price,
                            time=swing.time,
                            bar_index=swing.bar_index,
                            swing_broken=last_swing_low
                        ))

                last_swing_low = swing

            # Initialize trend if not set
            if trend == Direction.NEUTRAL and last_swing_high and last_swing_low:
                if last_swing_high.bar_index > last_swing_low.bar_index:
                    trend = Direction.BULLISH
                else:
                    trend = Direction.BEARISH

        self.current_trend = trend
        return breaks

    def _detect_order_blocks(self, data: pd.DataFrame) -> List[OrderBlock]:
        """
        Detect Order Blocks

        Bullish OB: Last bearish candle before a strong bullish move (BOS up)
        Bearish OB: Last bullish candle before a strong bearish move (BOS down)
        """
        order_blocks = []

        # Get volume column
        vol_col = 'volume' if 'volume' in data.columns else 'tick_volume'

        # Look for order blocks at structure breaks
        for structure_break in self.structure_breaks:
            break_idx = structure_break.bar_index

            if break_idx < 3 or break_idx >= len(data):
                continue

            if structure_break.direction == Direction.BULLISH:
                # Look for bearish candle before bullish move
                for j in range(break_idx - 1, max(break_idx - 10, 0), -1):
                    candle = data.iloc[j]
                    if candle['close'] < candle['open']:  # Bearish candle
                        # This is a potential bullish order block
                        time_val = data.iloc[j]['time'] if 'time' in data.columns else data.index[j]
                        volume = candle[vol_col] if vol_col in data.columns else 0

                        # Calculate zone boundaries (use candle body)
                        ob_bottom = min(candle['open'], candle['close'])
                        ob_top = max(candle['open'], candle['close'])

                        # Extend zone slightly
                        zone_extension = (ob_top - ob_bottom) * 0.1
                        ob_bottom -= zone_extension
                        ob_top += zone_extension

                        # Calculate strength based on move after OB
                        move_size = abs(data.iloc[break_idx]['high'] - ob_bottom)
                        strength = min(move_size / (ob_top - ob_bottom), 3.0)

                        order_blocks.append(OrderBlock(
                            top=ob_top,
                            bottom=ob_bottom,
                            direction=Direction.BULLISH,
                            time_created=time_val,
                            bar_index=j,
                            strength=strength,
                            timeframe=self.timeframe,
                            volume=volume
                        ))
                        break

            elif structure_break.direction == Direction.BEARISH:
                # Look for bullish candle before bearish move
                for j in range(break_idx - 1, max(break_idx - 10, 0), -1):
                    candle = data.iloc[j]
                    if candle['close'] > candle['open']:  # Bullish candle
                        # This is a potential bearish order block
                        time_val = data.iloc[j]['time'] if 'time' in data.columns else data.index[j]
                        volume = candle[vol_col] if vol_col in data.columns else 0

                        # Calculate zone boundaries (use candle body)
                        ob_bottom = min(candle['open'], candle['close'])
                        ob_top = max(candle['open'], candle['close'])

                        # Extend zone slightly
                        zone_extension = (ob_top - ob_bottom) * 0.1
                        ob_bottom -= zone_extension
                        ob_top += zone_extension

                        # Calculate strength
                        move_size = abs(ob_top - data.iloc[break_idx]['low'])
                        strength = min(move_size / (ob_top - ob_bottom), 3.0)

                        order_blocks.append(OrderBlock(
                            top=ob_top,
                            bottom=ob_bottom,
                            direction=Direction.BEARISH,
                            time_created=time_val,
                            bar_index=j,
                            strength=strength,
                            timeframe=self.timeframe,
                            volume=volume
                        ))
                        break

        # Also detect OBs from significant candles with high volume
        avg_volume = data[vol_col].mean() if vol_col in data.columns else 0
        avg_range = (data['high'] - data['low']).mean()

        for i in range(self.ob_lookback, len(data) - 3):
            candle = data.iloc[i]
            candle_range = candle['high'] - candle['low']
            volume = candle[vol_col] if vol_col in data.columns else 0

            # Skip if already detected as OB
            if any(ob.bar_index == i for ob in order_blocks):
                continue

            # High volume, large range candle
            if volume > avg_volume * 1.5 and candle_range > avg_range * 1.2:
                body = abs(candle['close'] - candle['open'])
                body_ratio = body / candle_range if candle_range > 0 else 0

                # Strong body (not doji)
                if body_ratio > 0.5:
                    is_bullish = candle['close'] > candle['open']
                    time_val = data.iloc[i]['time'] if 'time' in data.columns else data.index[i]

                    # Check if followed by continuation
                    next_candles = data.iloc[i+1:i+4]
                    if is_bullish:
                        continuation = all(next_candles['close'] > candle['close'])
                    else:
                        continuation = all(next_candles['close'] < candle['close'])

                    if continuation:
                        direction = Direction.BULLISH if is_bullish else Direction.BEARISH

                        # For bullish OB, zone is the previous bearish candle
                        # For bearish OB, zone is the previous bullish candle
                        ob_bottom = min(candle['open'], candle['close'])
                        ob_top = max(candle['open'], candle['close'])

                        order_blocks.append(OrderBlock(
                            top=ob_top,
                            bottom=ob_bottom,
                            direction=direction,
                            time_created=time_val,
                            bar_index=i,
                            strength=1.5,
                            timeframe=self.timeframe,
                            volume=volume
                        ))

        return sorted(order_blocks, key=lambda x: x.bar_index, reverse=True)[:10]

    def _detect_fvg(self, data: pd.DataFrame) -> List[FairValueGap]:
        """
        Detect Fair Value Gaps (FVGs)

        Bullish FVG: Candle 1 high < Candle 3 low (gap up)
        Bearish FVG: Candle 1 low > Candle 3 high (gap down)
        """
        fvgs = []

        for i in range(2, len(data)):
            candle1 = data.iloc[i - 2]
            candle2 = data.iloc[i - 1]  # Middle candle (imbalance candle)
            candle3 = data.iloc[i]

            time_val = data.iloc[i - 1]['time'] if 'time' in data.columns else data.index[i - 1]

            # Bullish FVG
            if candle1['high'] < candle3['low']:
                gap_size = candle3['low'] - candle1['high']

                fvgs.append(FairValueGap(
                    top=candle3['low'],
                    bottom=candle1['high'],
                    direction=Direction.BULLISH,
                    time_created=time_val,
                    bar_index=i - 1,
                    strength=gap_size / self.pip_value,
                    timeframe=self.timeframe
                ))

            # Bearish FVG
            elif candle1['low'] > candle3['high']:
                gap_size = candle1['low'] - candle3['high']

                fvgs.append(FairValueGap(
                    top=candle1['low'],
                    bottom=candle3['high'],
                    direction=Direction.BEARISH,
                    time_created=time_val,
                    bar_index=i - 1,
                    strength=gap_size / self.pip_value,
                    timeframe=self.timeframe
                ))

        return sorted(fvgs, key=lambda x: x.bar_index, reverse=True)[:15]

    def _detect_liquidity_pools(self, data: pd.DataFrame) -> List[LiquidityPool]:
        """
        Detect Liquidity Pools (clustered swing highs/lows)

        Buy-side liquidity: Multiple swing highs at similar levels
        Sell-side liquidity: Multiple swing lows at similar levels
        """
        pools = []

        # Cluster swing highs
        if self.swing_highs:
            high_clusters = self._cluster_levels(
                [(sh.price, sh.time, sh.bar_index) for sh in self.swing_highs],
                tolerance=0.001
            )

            for level, touches, times, indices in high_clusters:
                if touches >= 2:
                    pools.append(LiquidityPool(
                        level=level,
                        direction=Direction.BULLISH,  # Buy-side liquidity (above price)
                        touches=touches,
                        first_touch_time=min(times),
                        last_touch_time=max(times),
                        bar_indices=indices
                    ))

        # Cluster swing lows
        if self.swing_lows:
            low_clusters = self._cluster_levels(
                [(sl.price, sl.time, sl.bar_index) for sl in self.swing_lows],
                tolerance=0.001
            )

            for level, touches, times, indices in low_clusters:
                if touches >= 2:
                    pools.append(LiquidityPool(
                        level=level,
                        direction=Direction.BEARISH,  # Sell-side liquidity (below price)
                        touches=touches,
                        first_touch_time=min(times),
                        last_touch_time=max(times),
                        bar_indices=indices
                    ))

        return pools

    def _cluster_levels(
        self,
        points: List[Tuple[float, datetime, int]],
        tolerance: float = 0.001
    ) -> List[Tuple[float, int, List[datetime], List[int]]]:
        """Cluster price points that are close together"""
        if not points:
            return []

        # Sort by price
        sorted_points = sorted(points, key=lambda x: x[0])

        clusters = []
        current_cluster = [sorted_points[0]]

        for point in sorted_points[1:]:
            # Check if point is within tolerance of cluster average
            cluster_avg = sum(p[0] for p in current_cluster) / len(current_cluster)

            if abs(point[0] - cluster_avg) / cluster_avg <= tolerance:
                current_cluster.append(point)
            else:
                # Save current cluster and start new one
                if current_cluster:
                    avg_price = sum(p[0] for p in current_cluster) / len(current_cluster)
                    times = [p[1] for p in current_cluster]
                    indices = [p[2] for p in current_cluster]
                    clusters.append((avg_price, len(current_cluster), times, indices))
                current_cluster = [point]

        # Don't forget last cluster
        if current_cluster:
            avg_price = sum(p[0] for p in current_cluster) / len(current_cluster)
            times = [p[1] for p in current_cluster]
            indices = [p[2] for p in current_cluster]
            clusters.append((avg_price, len(current_cluster), times, indices))

        return clusters

    def _check_liquidity_sweeps(self, data: pd.DataFrame):
        """Check if liquidity pools have been swept"""
        if len(data) < 2:
            return

        latest = data.iloc[-1]
        prev = data.iloc[-2]

        for pool in self.liquidity_pools:
            if pool.swept:
                continue

            if pool.direction == Direction.BULLISH:
                # Buy-side liquidity swept when price goes above and closes below
                if latest['high'] > pool.level and latest['close'] < pool.level:
                    pool.swept = True
                    pool.sweep_time = latest['time'] if 'time' in data.columns else data.index[-1]
                # Also check for wick above
                elif prev['high'] > pool.level and latest['close'] < pool.level:
                    pool.swept = True
                    pool.sweep_time = latest['time'] if 'time' in data.columns else data.index[-1]

            elif pool.direction == Direction.BEARISH:
                # Sell-side liquidity swept when price goes below and closes above
                if latest['low'] < pool.level and latest['close'] > pool.level:
                    pool.swept = True
                    pool.sweep_time = latest['time'] if 'time' in data.columns else data.index[-1]
                # Also check for wick below
                elif prev['low'] < pool.level and latest['close'] > pool.level:
                    pool.swept = True
                    pool.sweep_time = latest['time'] if 'time' in data.columns else data.index[-1]

    def _check_mitigation(self, data: pd.DataFrame):
        """Check if Order Blocks and FVGs have been mitigated"""
        if len(data) < 1:
            return

        latest = data.iloc[-1]
        current_price = latest['close']

        # Check Order Blocks
        for ob in self.order_blocks:
            if ob.mitigated:
                continue

            # OB is mitigated when price returns to the zone
            if ob.contains_price(current_price) or ob.contains_price(latest['high']) or ob.contains_price(latest['low']):
                ob.tested_count += 1

                # Consider mitigated after certain conditions
                if ob.direction == Direction.BULLISH:
                    # Bullish OB mitigated if price closes below the zone
                    if latest['close'] < ob.bottom:
                        ob.mitigated = True
                        ob.mitigation_time = latest['time'] if 'time' in data.columns else data.index[-1]
                else:
                    # Bearish OB mitigated if price closes above the zone
                    if latest['close'] > ob.top:
                        ob.mitigated = True
                        ob.mitigation_time = latest['time'] if 'time' in data.columns else data.index[-1]

        # Check FVGs
        for fvg in self.fair_value_gaps:
            if fvg.mitigated:
                continue

            # Calculate fill percentage
            if fvg.direction == Direction.BULLISH:
                if latest['low'] <= fvg.top:
                    fill_depth = fvg.top - max(latest['low'], fvg.bottom)
                    fvg.fill_percent = (fill_depth / fvg.size) * 100

                    if fvg.fill_percent >= 50:
                        fvg.mitigated = True
                        fvg.mitigation_time = latest['time'] if 'time' in data.columns else data.index[-1]

            elif fvg.direction == Direction.BEARISH:
                if latest['high'] >= fvg.bottom:
                    fill_depth = min(latest['high'], fvg.top) - fvg.bottom
                    fvg.fill_percent = (fill_depth / fvg.size) * 100

                    if fvg.fill_percent >= 50:
                        fvg.mitigated = True
                        fvg.mitigation_time = latest['time'] if 'time' in data.columns else data.index[-1]

    def get_active_order_blocks(self, direction: Optional[Direction] = None) -> List[OrderBlock]:
        """Get non-mitigated order blocks, optionally filtered by direction"""
        obs = [ob for ob in self.order_blocks if not ob.mitigated]
        if direction:
            obs = [ob for ob in obs if ob.direction == direction]
        return obs

    def get_active_fvgs(self, direction: Optional[Direction] = None) -> List[FairValueGap]:
        """Get non-mitigated FVGs, optionally filtered by direction"""
        fvgs = [fvg for fvg in self.fair_value_gaps if not fvg.mitigated]
        if direction:
            fvgs = [fvg for fvg in fvgs if fvg.direction == direction]
        return fvgs

    def get_recent_sweeps(self, lookback_bars: int = 10) -> List[LiquidityPool]:
        """Get recently swept liquidity pools"""
        return [pool for pool in self.liquidity_pools if pool.swept]

    def get_analysis_summary(self) -> Dict:
        """Get summary of all detected SMC structures"""
        return {
            'timeframe': self.timeframe,
            'current_trend': self.current_trend.value,
            'swing_highs': [sh.to_dict() for sh in self.swing_highs[-5:]],
            'swing_lows': [sl.to_dict() for sl in self.swing_lows[-5:]],
            'order_blocks': [ob.to_dict() for ob in self.order_blocks],
            'active_order_blocks': [ob.to_dict() for ob in self.get_active_order_blocks()],
            'fair_value_gaps': [fvg.to_dict() for fvg in self.fair_value_gaps],
            'active_fvgs': [fvg.to_dict() for fvg in self.get_active_fvgs()],
            'liquidity_pools': [lp.to_dict() for lp in self.liquidity_pools],
            'swept_liquidity': [lp.to_dict() for lp in self.get_recent_sweeps()],
            'structure_breaks': [sb.to_dict() for sb in self.structure_breaks[-5:]],
            'counts': {
                'swing_highs': len(self.swing_highs),
                'swing_lows': len(self.swing_lows),
                'total_order_blocks': len(self.order_blocks),
                'active_order_blocks': len(self.get_active_order_blocks()),
                'total_fvgs': len(self.fair_value_gaps),
                'active_fvgs': len(self.get_active_fvgs()),
                'liquidity_pools': len(self.liquidity_pools),
                'swept_pools': len(self.get_recent_sweeps()),
                'structure_breaks': len(self.structure_breaks)
            }
        }

    def _empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'timeframe': self.timeframe,
            'current_trend': 'neutral',
            'swing_highs': [],
            'swing_lows': [],
            'order_blocks': [],
            'active_order_blocks': [],
            'fair_value_gaps': [],
            'active_fvgs': [],
            'liquidity_pools': [],
            'swept_liquidity': [],
            'structure_breaks': [],
            'counts': {
                'swing_highs': 0,
                'swing_lows': 0,
                'total_order_blocks': 0,
                'active_order_blocks': 0,
                'total_fvgs': 0,
                'active_fvgs': 0,
                'liquidity_pools': 0,
                'swept_pools': 0,
                'structure_breaks': 0
            }
        }

    def check_price_in_order_block(self, price: float, tolerance: float = 0.003) -> Optional[OrderBlock]:
        """Check if price is within an active order block"""
        for ob in self.get_active_order_blocks():
            if ob.contains_price(price, tolerance):
                return ob
        return None

    def check_price_in_fvg(self, price: float, tolerance: float = 0.003) -> Optional[FairValueGap]:
        """Check if price is within an active FVG"""
        for fvg in self.get_active_fvgs():
            if fvg.contains_price(price, tolerance):
                return fvg
        return None


def detect_reversal_pattern(data: pd.DataFrame, lookback: int = 3) -> Dict:
    """
    Detect reversal candlestick patterns

    Returns:
        Dict with detected patterns and their directions
    """
    if len(data) < lookback + 1:
        return {'pattern': None, 'direction': None}

    latest = data.iloc[-1]
    prev = data.iloc[-2]

    body = abs(latest['close'] - latest['open'])
    upper_wick = latest['high'] - max(latest['close'], latest['open'])
    lower_wick = min(latest['close'], latest['open']) - latest['low']
    total_range = latest['high'] - latest['low']

    if total_range == 0:
        return {'pattern': None, 'direction': None}

    # Pin Bar Detection
    if lower_wick > body * 2 and upper_wick < body * 0.5:
        # Bullish pin bar (hammer)
        return {'pattern': 'pin_bar', 'direction': 'bullish', 'strength': lower_wick / total_range}

    if upper_wick > body * 2 and lower_wick < body * 0.5:
        # Bearish pin bar (shooting star)
        return {'pattern': 'pin_bar', 'direction': 'bearish', 'strength': upper_wick / total_range}

    # Engulfing Pattern
    prev_body = abs(prev['close'] - prev['open'])
    if body > prev_body * 1.5:
        if latest['close'] > latest['open'] and prev['close'] < prev['open']:
            # Bullish engulfing
            if latest['close'] > prev['open'] and latest['open'] < prev['close']:
                return {'pattern': 'engulfing', 'direction': 'bullish', 'strength': body / prev_body}

        if latest['close'] < latest['open'] and prev['close'] > prev['open']:
            # Bearish engulfing
            if latest['close'] < prev['open'] and latest['open'] > prev['close']:
                return {'pattern': 'engulfing', 'direction': 'bearish', 'strength': body / prev_body}

    # Doji Detection
    if body < total_range * 0.1:
        return {'pattern': 'doji', 'direction': 'neutral', 'strength': 1 - (body / total_range)}

    return {'pattern': None, 'direction': None}


def detect_momentum_slowdown(data: pd.DataFrame, lookback: int = 3) -> Dict:
    """
    Detect momentum slowdown (decreasing candle ranges)

    Returns:
        Dict with slowdown info
    """
    if len(data) < lookback + 1:
        return {'slowdown': False, 'ratio': 1.0}

    ranges = []
    for i in range(-lookback, 0):
        candle = data.iloc[i]
        ranges.append(candle['high'] - candle['low'])

    if len(ranges) < 2:
        return {'slowdown': False, 'ratio': 1.0}

    # Check if ranges are decreasing
    decreasing = all(ranges[i] >= ranges[i+1] for i in range(len(ranges)-1))

    # Calculate ratio of latest to first
    ratio = ranges[-1] / ranges[0] if ranges[0] > 0 else 1.0

    return {
        'slowdown': decreasing and ratio < 0.7,
        'ratio': ratio,
        'ranges': ranges
    }
