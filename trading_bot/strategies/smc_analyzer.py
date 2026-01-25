"""
Multi-Timeframe SMC (Smart Money Concepts) Analyzer
Analyzes H4, H1, M15 timeframes for Order Block confluence
Detects liquidity sweeps and identifies high-probability trade setups

Key Logic:
- H4/H1/M15 Order Blocks must align (at least 2 TFs, M15 required)
- Liquidity sweep must occur for entry signal
- M15 OB zone acts as a gauge - if price goes straight through, stay out
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from indicators.smc_indicators import (
    SMCIndicators,
    OrderBlock,
    FairValueGap,
    LiquidityPool,
    SwingPoint,
    StructureBreak,
    Direction,
    Zone
)

from config.smc_config import (
    SMC_HTF_TIMEFRAMES,
    SMC_LTF_TIMEFRAME,
    SMC_ENTRY_TIMEFRAME,
    SWING_LOOKBACK,
    OB_LOOKBACK,
    MIN_TF_CONFLUENCE,
    M15_OB_REQUIRED,
    CONFLUENCE_ZONE_TOLERANCE,
    LIQUIDITY_SWEEP_REQUIRED,
    M15_ZONE_BREACH_BARS,
    M15_ZONE_BREACH_COOLDOWN,
    SMC_CONFLUENCE_WEIGHTS,
    MIN_SMC_CONFLUENCE_SCORE,
    SMC_DEBUG,
    MIN_BARS_REQUIRED
)


@dataclass
class ConfluenceZone:
    """Represents an area where multiple timeframe OBs align"""
    top: float
    bottom: float
    direction: Direction
    timeframes: List[str]
    order_blocks: List[OrderBlock]
    fvgs: List[FairValueGap]
    confluence_score: float
    liquidity_swept: bool = False
    valid: bool = True
    created_time: datetime = field(default_factory=datetime.now)
    breach_time: Optional[datetime] = None

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def size(self) -> float:
        return self.top - self.bottom

    def contains_price(self, price: float, tolerance: float = 0.003) -> bool:
        """Check if price is within the confluence zone"""
        tolerance_value = self.size * tolerance
        return (self.bottom - tolerance_value) <= price <= (self.top + tolerance_value)

    def to_dict(self) -> Dict:
        return {
            'top': self.top,
            'bottom': self.bottom,
            'midpoint': self.midpoint,
            'size': self.size,
            'direction': self.direction.value,
            'timeframes': self.timeframes,
            'confluence_score': self.confluence_score,
            'liquidity_swept': self.liquidity_swept,
            'valid': self.valid,
            'order_blocks': [ob.to_dict() for ob in self.order_blocks],
            'fvgs': [fvg.to_dict() for fvg in self.fvgs]
        }


class SMCMultiTimeframeAnalyzer:
    """
    Multi-Timeframe SMC Analyzer

    Combines analysis from H4, H1, M15 timeframes to identify
    high-probability confluence zones for trade entries.
    """

    def __init__(self, symbol: str = "EURUSD", pip_value: float = 0.0001):
        self.symbol = symbol
        self.pip_value = pip_value

        # Create SMC indicators for each timeframe
        self.h4_smc = SMCIndicators(
            swing_lookback=SWING_LOOKBACK.get('H4', 5),
            ob_lookback=OB_LOOKBACK,
            pip_value=pip_value,
            timeframe='H4'
        )
        self.h1_smc = SMCIndicators(
            swing_lookback=SWING_LOOKBACK.get('H1', 7),
            ob_lookback=OB_LOOKBACK,
            pip_value=pip_value,
            timeframe='H1'
        )
        self.m15_smc = SMCIndicators(
            swing_lookback=SWING_LOOKBACK.get('M15', 10),
            ob_lookback=OB_LOOKBACK,
            pip_value=pip_value,
            timeframe='M15'
        )
        self.m5_smc = SMCIndicators(
            swing_lookback=SWING_LOOKBACK.get('M5', 12),
            ob_lookback=OB_LOOKBACK,
            pip_value=pip_value,
            timeframe='M5'
        )

        # Storage for analysis results
        self.h4_analysis: Dict = {}
        self.h1_analysis: Dict = {}
        self.m15_analysis: Dict = {}
        self.m5_analysis: Dict = {}

        # Confluence zones
        self.confluence_zones: List[ConfluenceZone] = []

        # M15 zone breach tracking
        self.m15_breach_cooldown_until: Optional[datetime] = None

        # Recent liquidity sweeps
        self.recent_sweeps: List[Dict] = []

    def analyze_all_timeframes(
        self,
        h4_data: pd.DataFrame,
        h1_data: pd.DataFrame,
        m15_data: pd.DataFrame,
        m5_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Perform full SMC analysis across all timeframes

        Args:
            h4_data: H4 OHLCV data
            h1_data: H1 OHLCV data
            m15_data: M15 OHLCV data
            m5_data: M5 OHLCV data (optional, for entry timing)

        Returns:
            Dict with complete multi-timeframe analysis
        """
        # Validate data requirements
        if len(h4_data) < MIN_BARS_REQUIRED.get('H4', 100):
            print(f"[SMC] Insufficient H4 data: {len(h4_data)} bars (need {MIN_BARS_REQUIRED.get('H4', 100)})")
            return self._empty_analysis()

        if len(h1_data) < MIN_BARS_REQUIRED.get('H1', 200):
            print(f"[SMC] Insufficient H1 data: {len(h1_data)} bars (need {MIN_BARS_REQUIRED.get('H1', 200)})")
            return self._empty_analysis()

        if len(m15_data) < MIN_BARS_REQUIRED.get('M15', 500):
            print(f"[SMC] Insufficient M15 data: {len(m15_data)} bars (need {MIN_BARS_REQUIRED.get('M15', 500)})")
            return self._empty_analysis()

        # Step 1: Analyze each timeframe
        if SMC_DEBUG:
            print(f"[SMC] Analyzing H4 timeframe ({len(h4_data)} bars)...")
        self.h4_analysis = self.h4_smc.analyze(h4_data)

        if SMC_DEBUG:
            print(f"[SMC] Analyzing H1 timeframe ({len(h1_data)} bars)...")
        self.h1_analysis = self.h1_smc.analyze(h1_data)

        if SMC_DEBUG:
            print(f"[SMC] Analyzing M15 timeframe ({len(m15_data)} bars)...")
        self.m15_analysis = self.m15_smc.analyze(m15_data)

        if m5_data is not None and len(m5_data) >= MIN_BARS_REQUIRED.get('M5', 100):
            if SMC_DEBUG:
                print(f"[SMC] Analyzing M5 timeframe ({len(m5_data)} bars)...")
            self.m5_analysis = self.m5_smc.analyze(m5_data)

        # Step 2: Find confluence zones
        self.confluence_zones = self._find_confluence_zones()

        # Step 3: Check for liquidity sweeps
        self._check_all_liquidity_sweeps(m15_data)

        # Step 4: Check M15 zone validity (breach detection)
        self._check_m15_zone_breaches(m15_data)

        # Get current price
        current_price = m15_data.iloc[-1]['close']

        return self.get_analysis_summary(current_price)

    def _find_confluence_zones(self) -> List[ConfluenceZone]:
        """
        Find zones where Order Blocks from multiple timeframes align
        """
        confluence_zones = []

        # Get active order blocks from each timeframe
        h4_obs = self.h4_smc.get_active_order_blocks()
        h1_obs = self.h1_smc.get_active_order_blocks()
        m15_obs = self.m15_smc.get_active_order_blocks()

        if SMC_DEBUG:
            print(f"[SMC] Active OBs - H4: {len(h4_obs)}, H1: {len(h1_obs)}, M15: {len(m15_obs)}")

        # M15 OBs are required - start from those
        for m15_ob in m15_obs:
            overlapping_obs = [m15_ob]
            overlapping_tfs = ['M15']
            overlapping_fvgs = []

            # Check for H4 OB overlap
            for h4_ob in h4_obs:
                if self._zones_overlap(m15_ob, h4_ob) and m15_ob.direction == h4_ob.direction:
                    overlapping_obs.append(h4_ob)
                    if 'H4' not in overlapping_tfs:
                        overlapping_tfs.append('H4')

            # Check for H1 OB overlap
            for h1_ob in h1_obs:
                if self._zones_overlap(m15_ob, h1_ob) and m15_ob.direction == h1_ob.direction:
                    overlapping_obs.append(h1_ob)
                    if 'H1' not in overlapping_tfs:
                        overlapping_tfs.append('H1')

            # Check for FVG overlap
            for fvg in self.h4_smc.get_active_fvgs():
                if self._zones_overlap(m15_ob, fvg) and m15_ob.direction == fvg.direction:
                    overlapping_fvgs.append(fvg)

            for fvg in self.h1_smc.get_active_fvgs():
                if self._zones_overlap(m15_ob, fvg) and m15_ob.direction == fvg.direction:
                    overlapping_fvgs.append(fvg)

            for fvg in self.m15_smc.get_active_fvgs():
                if self._zones_overlap(m15_ob, fvg) and m15_ob.direction == fvg.direction:
                    overlapping_fvgs.append(fvg)

            # Check if we have enough confluence
            if len(overlapping_tfs) >= MIN_TF_CONFLUENCE:
                # Calculate the overlapping zone boundaries
                zone_top = min(ob.top for ob in overlapping_obs)
                zone_bottom = max(ob.bottom for ob in overlapping_obs)

                # Ensure valid zone (top > bottom)
                if zone_top > zone_bottom:
                    # Calculate confluence score
                    score = self._calculate_confluence_score(
                        overlapping_tfs, overlapping_obs, overlapping_fvgs
                    )

                    confluence_zone = ConfluenceZone(
                        top=zone_top,
                        bottom=zone_bottom,
                        direction=m15_ob.direction,
                        timeframes=overlapping_tfs,
                        order_blocks=overlapping_obs,
                        fvgs=overlapping_fvgs,
                        confluence_score=score
                    )

                    confluence_zones.append(confluence_zone)

                    if SMC_DEBUG:
                        print(f"[SMC] Found confluence zone: {confluence_zone.direction.value} "
                              f"TFs: {overlapping_tfs} Score: {score:.1f}")

        return confluence_zones

    def _zones_overlap(self, zone1: Zone, zone2: Zone) -> bool:
        """Check if two zones overlap"""
        return zone1.bottom <= zone2.top and zone1.top >= zone2.bottom

    def _calculate_confluence_score(
        self,
        timeframes: List[str],
        order_blocks: List[OrderBlock],
        fvgs: List[FairValueGap]
    ) -> float:
        """Calculate confluence score based on detected factors"""
        score = 0.0

        # Timeframe weights
        if 'H4' in timeframes:
            score += SMC_CONFLUENCE_WEIGHTS.get('h4_ob', 4)
        if 'H1' in timeframes:
            score += SMC_CONFLUENCE_WEIGHTS.get('h1_ob', 3)
        if 'M15' in timeframes:
            score += SMC_CONFLUENCE_WEIGHTS.get('m15_ob', 2)

        # FVG bonus
        for fvg in fvgs:
            if fvg.timeframe == 'H4':
                score += SMC_CONFLUENCE_WEIGHTS.get('h4_fvg', 2)
            elif fvg.timeframe == 'H1':
                score += SMC_CONFLUENCE_WEIGHTS.get('h1_fvg', 2)
            elif fvg.timeframe == 'M15':
                score += SMC_CONFLUENCE_WEIGHTS.get('m15_fvg', 1)

        # OB strength bonus
        for ob in order_blocks:
            score += min(ob.strength, 2.0) * 0.5  # Max 1 point per OB for strength

        return score

    def _check_all_liquidity_sweeps(self, m15_data: pd.DataFrame):
        """Check for liquidity sweeps across all timeframes"""
        self.recent_sweeps = []

        # Collect all swept liquidity pools
        for pool in self.h4_smc.get_recent_sweeps():
            self.recent_sweeps.append({
                'timeframe': 'H4',
                'level': pool.level,
                'direction': pool.direction.value,
                'sweep_time': pool.sweep_time
            })

        for pool in self.h1_smc.get_recent_sweeps():
            self.recent_sweeps.append({
                'timeframe': 'H1',
                'level': pool.level,
                'direction': pool.direction.value,
                'sweep_time': pool.sweep_time
            })

        for pool in self.m15_smc.get_recent_sweeps():
            self.recent_sweeps.append({
                'timeframe': 'M15',
                'level': pool.level,
                'direction': pool.direction.value,
                'sweep_time': pool.sweep_time
            })

        # Update confluence zones with liquidity sweep status
        for zone in self.confluence_zones:
            zone.liquidity_swept = len(self.recent_sweeps) > 0

    def _check_m15_zone_breaches(self, m15_data: pd.DataFrame):
        """
        Check if price went straight through M15 OB zones

        If price closes beyond M15 OB for consecutive bars, zone is invalidated
        and we enter a cooldown period (stay out of market)
        """
        if len(m15_data) < M15_ZONE_BREACH_BARS + 1:
            return

        current_time = m15_data.iloc[-1]['time'] if 'time' in m15_data.columns else datetime.now()

        # Check cooldown
        if self.m15_breach_cooldown_until and current_time < self.m15_breach_cooldown_until:
            if SMC_DEBUG:
                remaining = (self.m15_breach_cooldown_until - current_time).total_seconds() / 60
                print(f"[SMC] M15 zone breach cooldown active. {remaining:.0f} minutes remaining.")
            # Invalidate all confluence zones during cooldown
            for zone in self.confluence_zones:
                zone.valid = False
            return

        # Check each M15 OB for breach
        for ob in self.m15_smc.order_blocks:
            if ob.mitigated:
                continue

            # Check last N bars for consecutive closes beyond OB
            recent_bars = m15_data.tail(M15_ZONE_BREACH_BARS)
            breach_count = 0

            for _, bar in recent_bars.iterrows():
                if ob.direction == Direction.BULLISH:
                    # Bullish OB breached if price closes below
                    if bar['close'] < ob.bottom:
                        breach_count += 1
                else:
                    # Bearish OB breached if price closes above
                    if bar['close'] > ob.top:
                        breach_count += 1

            # If consecutive breach detected, enter cooldown
            if breach_count >= M15_ZONE_BREACH_BARS:
                cooldown_minutes = M15_ZONE_BREACH_COOLDOWN * 15  # M15 bars to minutes
                self.m15_breach_cooldown_until = current_time + timedelta(minutes=cooldown_minutes)

                if SMC_DEBUG:
                    print(f"[SMC] M15 OB zone breached! Cooldown until {self.m15_breach_cooldown_until}")

                # Invalidate confluence zones that include this OB
                for zone in self.confluence_zones:
                    if ob in zone.order_blocks:
                        zone.valid = False
                        zone.breach_time = current_time

    def get_valid_confluence_zones(self, direction: Optional[Direction] = None) -> List[ConfluenceZone]:
        """Get valid (non-breached) confluence zones"""
        zones = [z for z in self.confluence_zones if z.valid]
        if direction:
            zones = [z for z in zones if z.direction == direction]
        return zones

    def check_entry_conditions(
        self,
        current_price: float,
        m5_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Check if entry conditions are met

        Conditions:
        1. Price is in a valid confluence zone
        2. At least 2 timeframes align (including M15)
        3. Liquidity sweep has occurred
        4. (Optional) M5 shows reversal/ChoCH

        Returns:
            Dict with entry signal info
        """
        result = {
            'entry_valid': False,
            'direction': None,
            'confluence_zone': None,
            'confluence_score': 0,
            'factors': [],
            'reasons': []
        }

        # Check cooldown
        if self.m15_breach_cooldown_until:
            current_time = datetime.now()
            if current_time < self.m15_breach_cooldown_until:
                result['reasons'].append(f"M15 zone breach cooldown active")
                return result

        # Find confluence zone containing current price
        matching_zones = []
        for zone in self.get_valid_confluence_zones():
            if zone.contains_price(current_price, CONFLUENCE_ZONE_TOLERANCE):
                matching_zones.append(zone)

        if not matching_zones:
            result['reasons'].append("Price not in any confluence zone")
            return result

        # Use the zone with highest confluence score
        best_zone = max(matching_zones, key=lambda z: z.confluence_score)
        result['confluence_zone'] = best_zone.to_dict()
        result['confluence_score'] = best_zone.confluence_score
        result['direction'] = best_zone.direction.value

        # Check minimum timeframe confluence
        if len(best_zone.timeframes) < MIN_TF_CONFLUENCE:
            result['reasons'].append(f"Insufficient timeframe confluence: {len(best_zone.timeframes)} < {MIN_TF_CONFLUENCE}")
            return result

        # Check M15 OB requirement
        if M15_OB_REQUIRED and 'M15' not in best_zone.timeframes:
            result['reasons'].append("M15 Order Block required but not present")
            return result

        result['factors'].append(f"Confluence: {', '.join(best_zone.timeframes)}")

        # Check liquidity sweep requirement
        if LIQUIDITY_SWEEP_REQUIRED:
            if not best_zone.liquidity_swept and len(self.recent_sweeps) == 0:
                result['reasons'].append("No liquidity sweep detected")
                return result
            result['factors'].append("Liquidity swept")

        # Check M5 entry timing (if data provided)
        if m5_data is not None and len(m5_data) >= 10:
            m5_entry = self._check_m5_entry_timing(m5_data, best_zone.direction)
            if m5_entry['valid']:
                result['factors'].extend(m5_entry['factors'])
                result['confluence_score'] += m5_entry['score_bonus']
            else:
                result['reasons'].append(f"M5 entry timing not confirmed: {m5_entry['reason']}")
                # Don't return - M5 confirmation is optional but adds score

        # Check minimum confluence score
        if result['confluence_score'] < MIN_SMC_CONFLUENCE_SCORE:
            result['reasons'].append(f"Confluence score {result['confluence_score']:.1f} < {MIN_SMC_CONFLUENCE_SCORE}")
            return result

        # All conditions met
        result['entry_valid'] = True
        return result

    def _check_m5_entry_timing(self, m5_data: pd.DataFrame, expected_direction: Direction) -> Dict:
        """
        Check M5 timeframe for entry timing signals

        Looking for:
        - ChoCH (Change of Character)
        - Reversal candle patterns
        - Momentum slowdown
        """
        result = {
            'valid': False,
            'factors': [],
            'score_bonus': 0,
            'reason': ''
        }

        # Analyze M5 if not already done
        if not self.m5_analysis:
            self.m5_analysis = self.m5_smc.analyze(m5_data)

        # Check for ChoCH on M5
        recent_breaks = [b for b in self.m5_smc.structure_breaks[-3:]]
        for brk in recent_breaks:
            if brk.break_type == 'choch' and brk.direction == expected_direction:
                result['factors'].append("M5 ChoCH confirmed")
                result['score_bonus'] += SMC_CONFLUENCE_WEIGHTS.get('m5_choch', 3)
                result['valid'] = True
                break

        # Check for reversal patterns
        from indicators.smc_indicators import detect_reversal_pattern, detect_momentum_slowdown

        pattern = detect_reversal_pattern(m5_data)
        if pattern['pattern']:
            pattern_direction = Direction.BULLISH if pattern['direction'] == 'bullish' else Direction.BEARISH
            if pattern_direction == expected_direction:
                result['factors'].append(f"M5 {pattern['pattern']} pattern")
                result['score_bonus'] += SMC_CONFLUENCE_WEIGHTS.get('m5_reversal_candle', 2)
                result['valid'] = True

        # Check for momentum slowdown
        momentum = detect_momentum_slowdown(m5_data)
        if momentum['slowdown']:
            result['factors'].append("M5 momentum slowdown")
            result['score_bonus'] += SMC_CONFLUENCE_WEIGHTS.get('m5_momentum_slowdown', 1)

        if not result['valid']:
            result['reason'] = "No ChoCH or reversal pattern on M5"

        return result

    def get_analysis_summary(self, current_price: float) -> Dict:
        """Get complete analysis summary"""
        return {
            'symbol': self.symbol,
            'current_price': current_price,
            'h4_analysis': self.h4_analysis,
            'h1_analysis': self.h1_analysis,
            'm15_analysis': self.m15_analysis,
            'm5_analysis': self.m5_analysis,
            'confluence_zones': [z.to_dict() for z in self.confluence_zones],
            'valid_confluence_zones': [z.to_dict() for z in self.get_valid_confluence_zones()],
            'recent_sweeps': self.recent_sweeps,
            'm15_cooldown_active': self.m15_breach_cooldown_until is not None and datetime.now() < self.m15_breach_cooldown_until,
            'summary': {
                'h4_trend': self.h4_analysis.get('current_trend', 'unknown'),
                'h1_trend': self.h1_analysis.get('current_trend', 'unknown'),
                'm15_trend': self.m15_analysis.get('current_trend', 'unknown'),
                'total_confluence_zones': len(self.confluence_zones),
                'valid_confluence_zones': len(self.get_valid_confluence_zones()),
                'bullish_zones': len([z for z in self.get_valid_confluence_zones() if z.direction == Direction.BULLISH]),
                'bearish_zones': len([z for z in self.get_valid_confluence_zones() if z.direction == Direction.BEARISH]),
                'liquidity_sweeps': len(self.recent_sweeps)
            }
        }

    def _empty_analysis(self) -> Dict:
        """Return empty analysis structure"""
        return {
            'symbol': self.symbol,
            'current_price': 0,
            'h4_analysis': {},
            'h1_analysis': {},
            'm15_analysis': {},
            'm5_analysis': {},
            'confluence_zones': [],
            'valid_confluence_zones': [],
            'recent_sweeps': [],
            'm15_cooldown_active': False,
            'summary': {
                'h4_trend': 'unknown',
                'h1_trend': 'unknown',
                'm15_trend': 'unknown',
                'total_confluence_zones': 0,
                'valid_confluence_zones': 0,
                'bullish_zones': 0,
                'bearish_zones': 0,
                'liquidity_sweeps': 0
            }
        }

    def get_nearest_confluence_zone(
        self,
        current_price: float,
        direction: Optional[Direction] = None
    ) -> Optional[ConfluenceZone]:
        """Get the nearest confluence zone to current price"""
        zones = self.get_valid_confluence_zones(direction)
        if not zones:
            return None

        # Find nearest zone
        nearest = None
        min_distance = float('inf')

        for zone in zones:
            distance = min(
                abs(current_price - zone.top),
                abs(current_price - zone.bottom),
                abs(current_price - zone.midpoint)
            )
            if distance < min_distance:
                min_distance = distance
                nearest = zone

        return nearest

    def print_analysis_summary(self, current_price: float):
        """Print a human-readable analysis summary"""
        print("\n" + "=" * 60)
        print(f"SMC MULTI-TIMEFRAME ANALYSIS - {self.symbol}")
        print("=" * 60)

        print(f"\nCurrent Price: {current_price:.5f}")

        print(f"\n--- TREND ANALYSIS ---")
        print(f"  H4 Trend: {self.h4_analysis.get('current_trend', 'unknown').upper()}")
        print(f"  H1 Trend: {self.h1_analysis.get('current_trend', 'unknown').upper()}")
        print(f"  M15 Trend: {self.m15_analysis.get('current_trend', 'unknown').upper()}")

        print(f"\n--- ORDER BLOCKS ---")
        print(f"  H4 Active OBs: {self.h4_analysis.get('counts', {}).get('active_order_blocks', 0)}")
        print(f"  H1 Active OBs: {self.h1_analysis.get('counts', {}).get('active_order_blocks', 0)}")
        print(f"  M15 Active OBs: {self.m15_analysis.get('counts', {}).get('active_order_blocks', 0)}")

        print(f"\n--- FAIR VALUE GAPS ---")
        print(f"  H4 Active FVGs: {self.h4_analysis.get('counts', {}).get('active_fvgs', 0)}")
        print(f"  H1 Active FVGs: {self.h1_analysis.get('counts', {}).get('active_fvgs', 0)}")
        print(f"  M15 Active FVGs: {self.m15_analysis.get('counts', {}).get('active_fvgs', 0)}")

        print(f"\n--- CONFLUENCE ZONES ---")
        valid_zones = self.get_valid_confluence_zones()
        print(f"  Total: {len(self.confluence_zones)}, Valid: {len(valid_zones)}")

        for i, zone in enumerate(valid_zones[:5], 1):
            print(f"\n  Zone {i}: {zone.direction.value.upper()}")
            print(f"    Range: {zone.bottom:.5f} - {zone.top:.5f}")
            print(f"    Timeframes: {', '.join(zone.timeframes)}")
            print(f"    Score: {zone.confluence_score:.1f}")
            print(f"    Liquidity Swept: {'Yes' if zone.liquidity_swept else 'No'}")

        print(f"\n--- LIQUIDITY SWEEPS ---")
        print(f"  Recent Sweeps: {len(self.recent_sweeps)}")
        for sweep in self.recent_sweeps[:3]:
            print(f"    {sweep['timeframe']}: {sweep['direction']} @ {sweep['level']:.5f}")

        if self.m15_breach_cooldown_until:
            print(f"\n[!] M15 ZONE BREACH COOLDOWN ACTIVE until {self.m15_breach_cooldown_until}")

        print("\n" + "=" * 60)
