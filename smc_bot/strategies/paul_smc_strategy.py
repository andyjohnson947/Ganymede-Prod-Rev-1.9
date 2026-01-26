"""
Paul's SMC Strategy Implementation
Based on TradeForexwithPaul's methodology

Entry Flow:
1. Mark HTF POIs (previous highs/lows, session levels, imbalances)
2. Wait for price to raid liquidity INTO the POI
3. Look for MSS (Market Structure Shift) on LTF
4. Enter on pullback to LTF imbalance/OB
5. SL just beyond sweep (tight!)
6. TP at opposite-side liquidity

Key Rules:
- NO chasing - wait for price to come to POI
- Bias only valid AFTER liquidity taken
- If price re-sweeps = trade invalid, exit immediately
- High R:R (10R-50R potential), low win rate is OK
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class TradeDirection(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SetupState(Enum):
    """State machine for trade setup"""
    WAITING_FOR_POI = "waiting_for_poi"
    AT_POI_WAITING_SWEEP = "at_poi_waiting_sweep"
    SWEEP_OCCURRED_WAITING_MSS = "sweep_occurred_waiting_mss"
    MSS_CONFIRMED_WAITING_PULLBACK = "mss_confirmed_waiting_pullback"
    ENTRY_TRIGGERED = "entry_triggered"
    IN_TRADE = "in_trade"


@dataclass
class POI:
    """Point of Interest - where we look for trades"""
    level: float
    poi_type: str  # 'swing_high', 'swing_low', 'session_high', 'session_low', 'equal_highs', 'equal_lows', 'imbalance'
    direction: TradeDirection  # LONG if it's a low (buy zone), SHORT if it's a high (sell zone)
    created_time: datetime
    timeframe: str
    strength: int = 1  # How many times level was tested
    swept: bool = False
    sweep_time: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            'level': self.level,
            'type': self.poi_type,
            'direction': self.direction.value,
            'created_time': str(self.created_time),
            'timeframe': self.timeframe,
            'strength': self.strength,
            'swept': self.swept
        }


@dataclass
class Imbalance:
    """Fair Value Gap / Imbalance zone"""
    top: float
    bottom: float
    direction: TradeDirection  # LONG if bullish imbalance, SHORT if bearish
    created_time: datetime
    timeframe: str
    filled: bool = False

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2

    def contains_price(self, price: float) -> bool:
        return self.bottom <= price <= self.top


@dataclass
class TradeSetup:
    """Complete trade setup"""
    direction: TradeDirection
    entry_price: float
    stop_loss: float
    take_profits: List[float]
    poi: POI
    sweep_level: float
    mss_level: float
    entry_imbalance: Optional[Imbalance]
    risk_reward: float
    setup_time: datetime
    quality_score: Optional[int] = None
    quality_grade: Optional[str] = None
    size_multiplier: float = 1.0

    def to_dict(self) -> Dict:
        return {
            'direction': self.direction.value,
            'entry': self.entry_price,
            'sl': self.stop_loss,
            'tps': self.take_profits,
            'poi': self.poi.to_dict(),
            'sweep_level': self.sweep_level,
            'mss_level': self.mss_level,
            'rr': self.risk_reward,
            'quality_score': self.quality_score,
            'quality_grade': self.quality_grade,
            'size_multiplier': self.size_multiplier
        }


class PaulSMCStrategy:
    """
    Paul's SMC Strategy

    Simple, clean, high R:R trading based on:
    - HTF POI identification
    - Liquidity sweeps
    - LTF Market Structure Shifts
    - Tight entries on pullbacks
    """

    def __init__(
        self,
        symbol: str = "EURUSD",
        pip_value: float = 0.0001,
        htf: str = "H1",
        ltf: str = "M5",
        min_quality_score: int = 60,
        use_quality_filter: bool = True
    ):
        self.symbol = symbol
        self.pip_value = pip_value
        self.htf = htf
        self.ltf = ltf
        self.min_quality_score = min_quality_score
        self.use_quality_filter = use_quality_filter

        # Initialize quality filter
        from smc_bot.strategies.setup_quality_filter import SetupQualityFilter
        self.quality_filter = SetupQualityFilter(min_score=min_quality_score, pip_value=pip_value)

        # POIs storage
        self.htf_pois: List[POI] = []
        self.session_levels: Dict[str, Dict] = {}

        # Imbalances
        self.htf_imbalances: List[Imbalance] = []
        self.ltf_imbalances: List[Imbalance] = []

        # State
        self.state = SetupState.WAITING_FOR_POI
        self.current_poi: Optional[POI] = None
        self.sweep_level: Optional[float] = None
        self.mss_level: Optional[float] = None
        self.pending_setup: Optional[TradeSetup] = None

        # Swing tracking for MSS
        self.ltf_swing_highs: List[Tuple[float, datetime, int]] = []
        self.ltf_swing_lows: List[Tuple[float, datetime, int]] = []

        # Statistics
        self.setups_found = 0
        self.trades_taken = 0

    # =========================================================================
    # POI DETECTION
    # =========================================================================

    def identify_htf_pois(self, htf_data: pd.DataFrame) -> List[POI]:
        """
        Identify Points of Interest on HTF

        POIs include:
        - Previous swing highs/lows
        - Equal highs/lows (obvious liquidity)
        - Imbalance zones
        """
        pois = []

        if len(htf_data) < 20:
            return pois

        # Get time column
        time_col = 'time' if 'time' in htf_data.columns else htf_data.index

        # 1. Find Swing Highs (sell zones - liquidity above)
        swing_highs = self._find_swings(htf_data, 'high', lookback=7)
        for price, time, idx in swing_highs:
            pois.append(POI(
                level=price,
                poi_type='swing_high',
                direction=TradeDirection.SHORT,  # We look to sell at highs
                created_time=time,
                timeframe=self.htf
            ))

        # 2. Find Swing Lows (buy zones - liquidity below)
        swing_lows = self._find_swings(htf_data, 'low', lookback=7)
        for price, time, idx in swing_lows:
            pois.append(POI(
                level=price,
                poi_type='swing_low',
                direction=TradeDirection.LONG,  # We look to buy at lows
                created_time=time,
                timeframe=self.htf
            ))

        # 3. Find Equal Highs (obvious liquidity targets)
        equal_highs = self._find_equal_levels(swing_highs, tolerance=0.0003)
        for level, count in equal_highs:
            pois.append(POI(
                level=level,
                poi_type='equal_highs',
                direction=TradeDirection.SHORT,
                created_time=datetime.now(),
                timeframe=self.htf,
                strength=count
            ))

        # 4. Find Equal Lows (obvious liquidity targets)
        equal_lows = self._find_equal_levels(swing_lows, tolerance=0.0003)
        for level, count in equal_lows:
            pois.append(POI(
                level=level,
                poi_type='equal_lows',
                direction=TradeDirection.LONG,
                created_time=datetime.now(),
                timeframe=self.htf,
                strength=count
            ))

        self.htf_pois = pois
        return pois

    def identify_session_levels(self, data: pd.DataFrame, session: str = 'london') -> Dict:
        """
        Identify session high/low levels

        These are key POIs for intraday trading
        """
        from smc_bot.config.smc_config import SESSIONS

        session_config = SESSIONS.get(session, {})
        if not session_config.get('enabled', False):
            return {}

        start_hour = session_config['start']
        end_hour = session_config['end']

        # Filter data for session
        if 'time' in data.columns:
            session_data = data[
                (data['time'].dt.hour >= start_hour) &
                (data['time'].dt.hour < end_hour)
            ]
        else:
            return {}

        if len(session_data) == 0:
            return {}

        session_high = session_data['high'].max()
        session_low = session_data['low'].min()

        self.session_levels[session] = {
            'high': session_high,
            'low': session_low,
            'range': session_high - session_low
        }

        # Add as POIs
        self.htf_pois.append(POI(
            level=session_high,
            poi_type=f'{session}_session_high',
            direction=TradeDirection.SHORT,
            created_time=datetime.now(),
            timeframe=self.htf
        ))

        self.htf_pois.append(POI(
            level=session_low,
            poi_type=f'{session}_session_low',
            direction=TradeDirection.LONG,
            created_time=datetime.now(),
            timeframe=self.htf
        ))

        return self.session_levels[session]

    def identify_imbalances(self, data: pd.DataFrame, timeframe: str) -> List[Imbalance]:
        """
        Find Fair Value Gaps / Imbalances

        Bullish: Candle 1 high < Candle 3 low
        Bearish: Candle 1 low > Candle 3 high
        """
        imbalances = []

        for i in range(2, len(data)):
            c1 = data.iloc[i - 2]
            c3 = data.iloc[i]

            time_val = data.iloc[i - 1]['time'] if 'time' in data.columns else datetime.now()

            # Bullish imbalance (gap up)
            if c1['high'] < c3['low']:
                imbalances.append(Imbalance(
                    top=c3['low'],
                    bottom=c1['high'],
                    direction=TradeDirection.LONG,
                    created_time=time_val,
                    timeframe=timeframe
                ))

            # Bearish imbalance (gap down)
            elif c1['low'] > c3['high']:
                imbalances.append(Imbalance(
                    top=c1['low'],
                    bottom=c3['high'],
                    direction=TradeDirection.SHORT,
                    created_time=time_val,
                    timeframe=timeframe
                ))

        if timeframe == self.htf:
            self.htf_imbalances = imbalances[-10:]  # Keep last 10
        else:
            self.ltf_imbalances = imbalances[-20:]  # Keep last 20

        return imbalances

    # =========================================================================
    # LIQUIDITY SWEEP DETECTION
    # =========================================================================

    def check_liquidity_sweep(self, current_candle: pd.Series, previous_candle: pd.Series) -> Optional[Dict]:
        """
        Check if liquidity was swept

        Sweep = price runs beyond a POI level then closes back

        For SHORTS: Price sweeps ABOVE high, then closes below
        For LONGS: Price sweeps BELOW low, then closes above
        """
        from smc_bot.config.smc_config import SWEEP_MIN_PENETRATION_PIPS, SWEEP_MUST_CLOSE_BACK

        sweep_min = SWEEP_MIN_PENETRATION_PIPS * self.pip_value

        for poi in self.htf_pois:
            if poi.swept:
                continue

            # Check for sweep of highs (bearish setup)
            if poi.direction == TradeDirection.SHORT:
                # Price went above the high
                if current_candle['high'] > poi.level + sweep_min:
                    # And closed back below (trap!)
                    if not SWEEP_MUST_CLOSE_BACK or current_candle['close'] < poi.level:
                        poi.swept = True
                        poi.sweep_time = current_candle['time'] if 'time' in current_candle else datetime.now()

                        return {
                            'poi': poi,
                            'sweep_high': current_candle['high'],
                            'direction': TradeDirection.SHORT,
                            'message': f"Liquidity swept above {poi.poi_type} @ {poi.level:.5f}"
                        }

            # Check for sweep of lows (bullish setup)
            elif poi.direction == TradeDirection.LONG:
                # Price went below the low
                if current_candle['low'] < poi.level - sweep_min:
                    # And closed back above (trap!)
                    if not SWEEP_MUST_CLOSE_BACK or current_candle['close'] > poi.level:
                        poi.swept = True
                        poi.sweep_time = current_candle['time'] if 'time' in current_candle else datetime.now()

                        return {
                            'poi': poi,
                            'sweep_low': current_candle['low'],
                            'direction': TradeDirection.LONG,
                            'message': f"Liquidity swept below {poi.poi_type} @ {poi.level:.5f}"
                        }

        return None

    # =========================================================================
    # MARKET STRUCTURE SHIFT (MSS) DETECTION
    # =========================================================================

    def update_ltf_swings(self, ltf_data: pd.DataFrame):
        """Update LTF swing highs and lows for MSS detection"""
        self.ltf_swing_highs = self._find_swings(ltf_data, 'high', lookback=5)
        self.ltf_swing_lows = self._find_swings(ltf_data, 'low', lookback=5)

    def check_mss(self, ltf_data: pd.DataFrame, expected_direction: TradeDirection) -> Optional[Dict]:
        """
        Check for Market Structure Shift on LTF

        MSS = Break of internal structure in OPPOSITE direction to the sweep

        For SHORTS (after sweep of highs):
            MSS = Price breaks below recent LTF swing low

        For LONGS (after sweep of lows):
            MSS = Price breaks above recent LTF swing high
        """
        from smc_bot.config.smc_config import MSS_CLOSE_CONFIRMATION

        if len(ltf_data) < 5:
            return None

        current = ltf_data.iloc[-1]
        self.update_ltf_swings(ltf_data.iloc[:-1])  # Update swings excluding current bar

        if expected_direction == TradeDirection.SHORT:
            # Looking for break of swing low (bearish MSS)
            if not self.ltf_swing_lows:
                return None

            # Get most recent swing low
            recent_low = min(self.ltf_swing_lows[-3:], key=lambda x: x[0]) if len(self.ltf_swing_lows) >= 3 else self.ltf_swing_lows[-1]
            swing_low_price = recent_low[0]

            # Check if current candle breaks below
            if MSS_CLOSE_CONFIRMATION:
                if current['close'] < swing_low_price:
                    return {
                        'mss_type': 'bearish',
                        'break_level': swing_low_price,
                        'direction': TradeDirection.SHORT,
                        'message': f"Bearish MSS - broke below {swing_low_price:.5f}"
                    }
            else:
                if current['low'] < swing_low_price:
                    return {
                        'mss_type': 'bearish',
                        'break_level': swing_low_price,
                        'direction': TradeDirection.SHORT,
                        'message': f"Bearish MSS - broke below {swing_low_price:.5f}"
                    }

        elif expected_direction == TradeDirection.LONG:
            # Looking for break of swing high (bullish MSS)
            if not self.ltf_swing_highs:
                return None

            # Get most recent swing high
            recent_high = max(self.ltf_swing_highs[-3:], key=lambda x: x[0]) if len(self.ltf_swing_highs) >= 3 else self.ltf_swing_highs[-1]
            swing_high_price = recent_high[0]

            # Check if current candle breaks above
            if MSS_CLOSE_CONFIRMATION:
                if current['close'] > swing_high_price:
                    return {
                        'mss_type': 'bullish',
                        'break_level': swing_high_price,
                        'direction': TradeDirection.LONG,
                        'message': f"Bullish MSS - broke above {swing_high_price:.5f}"
                    }
            else:
                if current['high'] > swing_high_price:
                    return {
                        'mss_type': 'bullish',
                        'break_level': swing_high_price,
                        'direction': TradeDirection.LONG,
                        'message': f"Bullish MSS - broke above {swing_high_price:.5f}"
                    }

        return None

    # =========================================================================
    # ENTRY LOGIC
    # =========================================================================

    def check_pullback_entry(
        self,
        ltf_data: pd.DataFrame,
        direction: TradeDirection,
        mss_level: float
    ) -> Optional[Dict]:
        """
        Check for pullback entry after MSS

        Entry is on pullback to:
        - LTF imbalance created by the MSS move
        - Or 50% of the MSS move
        """
        if len(ltf_data) < 3:
            return None

        current = ltf_data.iloc[-1]
        current_price = current['close']

        # Find imbalance created after MSS
        self.identify_imbalances(ltf_data.tail(10), self.ltf)

        # Look for imbalance in the right direction
        for imb in self.ltf_imbalances:
            if imb.direction == direction and not imb.filled:
                # Check if price pulled back into imbalance
                if imb.contains_price(current_price):
                    return {
                        'entry_type': 'imbalance',
                        'entry_price': current_price,
                        'imbalance': imb,
                        'message': f"Pullback entry at imbalance {imb.bottom:.5f}-{imb.top:.5f}"
                    }

        # Alternative: Check for pullback to 50% of MSS move
        if direction == TradeDirection.LONG:
            # For longs, we want price to pull back down toward MSS level
            fib_50 = mss_level + (current_price - mss_level) * 0.5
            if current['low'] <= fib_50 <= current['high']:
                return {
                    'entry_type': 'fib_50',
                    'entry_price': fib_50,
                    'imbalance': None,
                    'message': f"Pullback entry at 50% retracement {fib_50:.5f}"
                }

        elif direction == TradeDirection.SHORT:
            # For shorts, we want price to pull back up toward MSS level
            fib_50 = mss_level - (mss_level - current_price) * 0.5
            if current['low'] <= fib_50 <= current['high']:
                return {
                    'entry_type': 'fib_50',
                    'entry_price': fib_50,
                    'imbalance': None,
                    'message': f"Pullback entry at 50% retracement {fib_50:.5f}"
                }

        return None

    # =========================================================================
    # TRADE SETUP GENERATION
    # =========================================================================

    def generate_trade_setup(
        self,
        direction: TradeDirection,
        entry_price: float,
        sweep_level: float,
        poi: POI,
        mss_level: float,
        imbalance: Optional[Imbalance] = None,
        sweep_data: Optional[Dict] = None,
        mss_data: Optional[Dict] = None,
        context_data: Optional[Dict] = None
    ) -> Optional[TradeSetup]:
        """
        Generate complete trade setup with SL and TPs

        SL: Just beyond the sweep level (tight!)
        TP: Opposite-side liquidity
        """
        from smc_bot.config.smc_config import (
            SL_BEYOND_SWEEP_PIPS,
            MIN_RISK_REWARD,
            PARTIAL_TP_LEVELS
        )

        sl_buffer = SL_BEYOND_SWEEP_PIPS * self.pip_value

        # Calculate SL
        if direction == TradeDirection.LONG:
            stop_loss = sweep_level - sl_buffer
            sl_distance = entry_price - stop_loss
        else:  # SHORT
            stop_loss = sweep_level + sl_buffer
            sl_distance = stop_loss - entry_price

        if sl_distance <= 0:
            return None

        # Find opposite-side liquidity for TP
        take_profits = []
        opposite_pois = [p for p in self.htf_pois if p.direction != direction and not p.swept]

        if direction == TradeDirection.LONG:
            # Look for highs above current price
            targets = sorted([p.level for p in opposite_pois if p.level > entry_price])
        else:
            # Look for lows below current price
            targets = sorted([p.level for p in opposite_pois if p.level < entry_price], reverse=True)

        # Calculate R:R for each target
        for target in targets[:3]:  # Max 3 targets
            if direction == TradeDirection.LONG:
                tp_distance = target - entry_price
            else:
                tp_distance = entry_price - target

            rr = tp_distance / sl_distance
            if rr >= MIN_RISK_REWARD:
                take_profits.append(target)

        # If no opposite liquidity, use R:R based targets
        if not take_profits:
            for r in [3.0, 5.0, 10.0]:
                if direction == TradeDirection.LONG:
                    take_profits.append(entry_price + (sl_distance * r))
                else:
                    take_profits.append(entry_price - (sl_distance * r))

        # Calculate overall R:R
        if take_profits:
            if direction == TradeDirection.LONG:
                best_tp_distance = take_profits[-1] - entry_price
            else:
                best_tp_distance = entry_price - take_profits[-1]
            risk_reward = best_tp_distance / sl_distance
        else:
            risk_reward = 0

        if risk_reward < MIN_RISK_REWARD:
            return None

        # Calculate SL in pips
        sl_pips = sl_distance / self.pip_value

        # =====================================================================
        # QUALITY SCORING - Filter weak setups
        # =====================================================================
        quality_score = None
        quality_grade = None
        size_multiplier = 1.0

        if self.use_quality_filter:
            from smc_bot.strategies.setup_quality_filter import (
                create_poi_data, create_sweep_data, create_mss_data,
                create_entry_data, create_context_data
            )

            # Calculate POI age
            poi_age_hours = (datetime.now() - poi.created_time).total_seconds() / 3600 if poi.created_time else 24

            # Build scoring data
            poi_score_data = create_poi_data(
                poi_type=poi.poi_type,
                strength=poi.strength,
                age_hours=poi_age_hours,
                htf_aligned=True,  # We're already using HTF POIs
                near_session_level='session' in poi.poi_type
            )

            sweep_score_data = sweep_data or create_sweep_data(
                sweep_pips=abs(sweep_level - poi.level) / self.pip_value,
                closed_back=True,
                wick_ratio=0.5,
                high_volume=False
            )

            mss_score_data = mss_data or create_mss_data(
                break_pips=abs(mss_level - entry_price) / self.pip_value if mss_level else 5,
                impulsive_candle=False,
                created_imbalance=imbalance is not None,
                momentum_bars=1
            )

            entry_score_data = create_entry_data(
                entry_type='imbalance' if imbalance else 'fib_50',
                at_edge=imbalance is not None,
                risk_reward=risk_reward,
                sl_pips=sl_pips
            )

            ctx_data = context_data or create_context_data(
                hour=datetime.now().hour,
                day_of_week=datetime.now().weekday(),
                near_news=False,
                htf_trend_aligned=True,
                volatility='normal'
            )

            # Score the setup
            score_result = self.quality_filter.score_setup(
                poi_data=poi_score_data,
                sweep_data=sweep_score_data,
                mss_data=mss_score_data,
                entry_data=entry_score_data,
                context_data=ctx_data
            )

            quality_score = score_result.total_score
            quality_grade = score_result.grade.value

            # Check if we should take the trade
            should_take, size_multiplier = self.quality_filter.should_take_trade(score_result)

            # Print score card
            self.quality_filter.print_score_card(score_result)

            if not should_take:
                print(f"[FILTER] Setup REJECTED - Score: {quality_score}, Grade: {quality_grade}")
                return None

            print(f"[FILTER] Setup ACCEPTED - Score: {quality_score}, Grade: {quality_grade}, Size: {size_multiplier*100:.0f}%")

        setup = TradeSetup(
            direction=direction,
            entry_price=round(entry_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profits=[round(tp, 5) for tp in take_profits],
            poi=poi,
            sweep_level=sweep_level,
            mss_level=mss_level,
            entry_imbalance=imbalance,
            risk_reward=round(risk_reward, 1),
            setup_time=datetime.now(),
            quality_score=quality_score,
            quality_grade=quality_grade,
            size_multiplier=size_multiplier
        )

        self.setups_found += 1
        return setup

    # =========================================================================
    # MAIN ANALYSIS LOOP
    # =========================================================================

    def analyze(
        self,
        htf_data: pd.DataFrame,
        ltf_data: pd.DataFrame
    ) -> Optional[TradeSetup]:
        """
        Main analysis function - run on each new bar

        Returns TradeSetup if valid entry conditions are met
        """
        # Step 1: Identify HTF POIs (if not done or stale)
        if not self.htf_pois or len(self.htf_pois) < 3:
            self.identify_htf_pois(htf_data)
            self.identify_imbalances(htf_data, self.htf)

        # Step 2: Check current state and progress
        current_htf = htf_data.iloc[-1]
        current_ltf = ltf_data.iloc[-1]
        prev_ltf = ltf_data.iloc[-2] if len(ltf_data) > 1 else current_ltf

        # State: WAITING_FOR_POI
        if self.state == SetupState.WAITING_FOR_POI:
            # Check if price is near any POI
            current_price = current_ltf['close']
            for poi in self.htf_pois:
                if poi.swept:
                    continue

                distance = abs(current_price - poi.level)
                tolerance = 20 * self.pip_value  # Within 20 pips

                if distance <= tolerance:
                    self.current_poi = poi
                    self.state = SetupState.AT_POI_WAITING_SWEEP
                    print(f"[SMC] Price near POI: {poi.poi_type} @ {poi.level:.5f}")
                    break

        # State: AT_POI_WAITING_SWEEP
        elif self.state == SetupState.AT_POI_WAITING_SWEEP:
            sweep = self.check_liquidity_sweep(current_ltf, prev_ltf)
            if sweep:
                self.sweep_level = sweep.get('sweep_high') or sweep.get('sweep_low')
                self.state = SetupState.SWEEP_OCCURRED_WAITING_MSS
                print(f"[SMC] {sweep['message']}")

        # State: SWEEP_OCCURRED_WAITING_MSS
        elif self.state == SetupState.SWEEP_OCCURRED_WAITING_MSS:
            if self.current_poi:
                mss = self.check_mss(ltf_data, self.current_poi.direction)
                if mss:
                    self.mss_level = mss['break_level']
                    self.state = SetupState.MSS_CONFIRMED_WAITING_PULLBACK
                    print(f"[SMC] {mss['message']}")

        # State: MSS_CONFIRMED_WAITING_PULLBACK
        elif self.state == SetupState.MSS_CONFIRMED_WAITING_PULLBACK:
            if self.current_poi and self.mss_level:
                pullback = self.check_pullback_entry(
                    ltf_data,
                    self.current_poi.direction,
                    self.mss_level
                )
                if pullback:
                    setup = self.generate_trade_setup(
                        direction=self.current_poi.direction,
                        entry_price=pullback['entry_price'],
                        sweep_level=self.sweep_level,
                        poi=self.current_poi,
                        mss_level=self.mss_level,
                        imbalance=pullback.get('imbalance')
                    )
                    if setup:
                        self.state = SetupState.ENTRY_TRIGGERED
                        self.pending_setup = setup
                        print(f"[SMC] {pullback['message']}")
                        print(f"[SMC] TRADE SETUP: {setup.direction.value.upper()} @ {setup.entry_price:.5f}")
                        print(f"[SMC]   SL: {setup.stop_loss:.5f}")
                        print(f"[SMC]   TPs: {[f'{tp:.5f}' for tp in setup.take_profits]}")
                        print(f"[SMC]   R:R: {setup.risk_reward}")
                        return setup

        return None

    def reset(self):
        """Reset state for new setup"""
        self.state = SetupState.WAITING_FOR_POI
        self.current_poi = None
        self.sweep_level = None
        self.mss_level = None
        self.pending_setup = None

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================

    def _find_swings(
        self,
        data: pd.DataFrame,
        price_type: str,  # 'high' or 'low'
        lookback: int = 5
    ) -> List[Tuple[float, datetime, int]]:
        """Find swing highs or lows"""
        swings = []

        for i in range(lookback, len(data) - lookback):
            current = data.iloc[i][price_type]
            is_swing = True

            for j in range(i - lookback, i + lookback + 1):
                if j == i:
                    continue
                compare = data.iloc[j][price_type]

                if price_type == 'high' and compare >= current:
                    is_swing = False
                    break
                elif price_type == 'low' and compare <= current:
                    is_swing = False
                    break

            if is_swing:
                time_val = data.iloc[i]['time'] if 'time' in data.columns else datetime.now()
                swings.append((current, time_val, i))

        return swings

    def _find_equal_levels(
        self,
        swings: List[Tuple[float, datetime, int]],
        tolerance: float = 0.0003
    ) -> List[Tuple[float, int]]:
        """Find equal highs/lows (clustered levels)"""
        if len(swings) < 2:
            return []

        levels = [s[0] for s in swings]
        equal_levels = []

        # Cluster nearby levels
        used = set()
        for i, level in enumerate(levels):
            if i in used:
                continue

            cluster = [level]
            for j, other in enumerate(levels):
                if j != i and j not in used:
                    if abs(level - other) / level <= tolerance:
                        cluster.append(other)
                        used.add(j)

            if len(cluster) >= 2:
                avg_level = sum(cluster) / len(cluster)
                equal_levels.append((avg_level, len(cluster)))
                used.add(i)

        return equal_levels

    def get_status(self) -> Dict:
        """Get current strategy status"""
        return {
            'state': self.state.value,
            'htf_pois': len(self.htf_pois),
            'current_poi': self.current_poi.to_dict() if self.current_poi else None,
            'sweep_level': self.sweep_level,
            'mss_level': self.mss_level,
            'pending_setup': self.pending_setup.to_dict() if self.pending_setup else None,
            'setups_found': self.setups_found,
            'trades_taken': self.trades_taken
        }

    def print_pois(self):
        """Print current POIs"""
        print(f"\n{'='*50}")
        print(f"POINTS OF INTEREST - {self.symbol}")
        print(f"{'='*50}")

        shorts = [p for p in self.htf_pois if p.direction == TradeDirection.SHORT and not p.swept]
        longs = [p for p in self.htf_pois if p.direction == TradeDirection.LONG and not p.swept]

        print(f"\nSELL ZONES (liquidity above):")
        for poi in sorted(shorts, key=lambda x: x.level, reverse=True)[:5]:
            print(f"  {poi.level:.5f} - {poi.poi_type} (strength: {poi.strength})")

        print(f"\nBUY ZONES (liquidity below):")
        for poi in sorted(longs, key=lambda x: x.level)[:5]:
            print(f"  {poi.level:.5f} - {poi.poi_type} (strength: {poi.strength})")

        print(f"{'='*50}\n")
