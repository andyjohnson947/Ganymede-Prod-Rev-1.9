"""
SMC Entry Strategy with M5 Timing
Implements precise entry timing using M5 timeframe for trade execution

Entry Logic:
1. Wait for price to enter confluence zone (H4/H1/M15 aligned OBs)
2. Liquidity sweep must have occurred
3. Monitor M5 for reversal confirmation (ChoCH, reversal candles, momentum slowdown)
4. Enter on M5 confirmation with SL beyond OB zone
5. Use M15 OB as gauge - if price goes straight through, stay out
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from strategies.smc_analyzer import SMCMultiTimeframeAnalyzer, ConfluenceZone
from indicators.smc_indicators import (
    Direction,
    detect_reversal_pattern,
    detect_momentum_slowdown
)
from config.smc_config import (
    SMC_ENTRY_TIMEFRAME,
    M5_ENTRY_LOOKBACK,
    M5_CHOCH_REQUIRED,
    REVERSAL_PATTERNS,
    PIN_BAR_WICK_RATIO,
    MOMENTUM_SLOWDOWN_BARS,
    MOMENTUM_DECREASE_THRESHOLD,
    SL_BEYOND_OB_PIPS,
    TP_RATIOS,
    PARTIAL_CLOSE_PERCENTS,
    MIN_SMC_CONFLUENCE_SCORE,
    OPTIMAL_SMC_CONFLUENCE_SCORE,
    SMC_DEBUG
)


class EntryState(Enum):
    """Entry state machine states"""
    WAITING_FOR_ZONE = "waiting_for_zone"
    IN_ZONE_WAITING_SWEEP = "in_zone_waiting_sweep"
    WAITING_FOR_M5_CONFIRMATION = "waiting_for_m5_confirmation"
    ENTRY_TRIGGERED = "entry_triggered"
    TRADE_ACTIVE = "trade_active"
    COOLDOWN = "cooldown"


@dataclass
class EntrySignal:
    """SMC Entry Signal"""
    valid: bool
    direction: str  # 'buy' or 'sell'
    entry_price: float
    stop_loss: float
    take_profits: List[float]
    confluence_zone: Dict
    confluence_score: float
    factors: List[str]
    m5_confirmation: Dict
    timestamp: datetime

    def to_dict(self) -> Dict:
        return {
            'valid': self.valid,
            'direction': self.direction,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'confluence_zone': self.confluence_zone,
            'confluence_score': self.confluence_score,
            'factors': self.factors,
            'm5_confirmation': self.m5_confirmation,
            'timestamp': self.timestamp
        }


class SMCEntryStrategy:
    """
    SMC Entry Strategy

    Monitors price action and triggers entries based on:
    - Multi-timeframe Order Block confluence
    - Liquidity sweeps
    - M5 reversal confirmation
    """

    def __init__(
        self,
        symbol: str = "EURUSD",
        pip_value: float = 0.0001,
        lot_size: float = 0.04
    ):
        self.symbol = symbol
        self.pip_value = pip_value
        self.lot_size = lot_size

        # Initialize multi-timeframe analyzer
        self.analyzer = SMCMultiTimeframeAnalyzer(symbol=symbol, pip_value=pip_value)

        # Entry state tracking
        self.entry_state = EntryState.WAITING_FOR_ZONE
        self.current_zone: Optional[ConfluenceZone] = None
        self.zone_entry_time: Optional[datetime] = None
        self.m5_confirmation_bars = 0

        # Active signals and trades
        self.pending_signal: Optional[EntrySignal] = None
        self.active_trades: List[Dict] = []

        # Statistics
        self.signals_generated = 0
        self.trades_entered = 0
        self.trades_won = 0
        self.trades_lost = 0

    def process_tick(
        self,
        h4_data: pd.DataFrame,
        h1_data: pd.DataFrame,
        m15_data: pd.DataFrame,
        m5_data: pd.DataFrame,
        current_price: float
    ) -> Optional[EntrySignal]:
        """
        Process new price data and check for entry signals

        Args:
            h4_data: H4 OHLCV data
            h1_data: H1 OHLCV data
            m15_data: M15 OHLCV data
            m5_data: M5 OHLCV data
            current_price: Current market price

        Returns:
            EntrySignal if conditions are met, None otherwise
        """
        # Step 1: Run multi-timeframe analysis
        analysis = self.analyzer.analyze_all_timeframes(
            h4_data=h4_data,
            h1_data=h1_data,
            m15_data=m15_data,
            m5_data=m5_data
        )

        if SMC_DEBUG:
            print(f"\n[SMC Entry] State: {self.entry_state.value}, Price: {current_price:.5f}")

        # Step 2: State machine processing
        if self.entry_state == EntryState.COOLDOWN:
            # Check if cooldown is over
            if not analysis.get('m15_cooldown_active', False):
                self.entry_state = EntryState.WAITING_FOR_ZONE
                if SMC_DEBUG:
                    print("[SMC Entry] Cooldown ended, resuming...")
            return None

        if self.entry_state == EntryState.WAITING_FOR_ZONE:
            return self._handle_waiting_for_zone(analysis, current_price, m5_data)

        elif self.entry_state == EntryState.IN_ZONE_WAITING_SWEEP:
            return self._handle_waiting_for_sweep(analysis, current_price, m5_data)

        elif self.entry_state == EntryState.WAITING_FOR_M5_CONFIRMATION:
            return self._handle_waiting_for_m5(analysis, current_price, m5_data)

        return None

    def _handle_waiting_for_zone(
        self,
        analysis: Dict,
        current_price: float,
        m5_data: pd.DataFrame
    ) -> Optional[EntrySignal]:
        """Handle WAITING_FOR_ZONE state"""

        # Check if M15 cooldown is active
        if analysis.get('m15_cooldown_active', False):
            self.entry_state = EntryState.COOLDOWN
            if SMC_DEBUG:
                print("[SMC Entry] M15 zone breached - entering cooldown")
            return None

        # Find valid confluence zones
        valid_zones = analysis.get('valid_confluence_zones', [])

        if not valid_zones:
            if SMC_DEBUG:
                print("[SMC Entry] No valid confluence zones")
            return None

        # Check if price is in any confluence zone
        for zone_dict in valid_zones:
            zone_top = zone_dict['top']
            zone_bottom = zone_dict['bottom']

            # Check if price is in zone
            if zone_bottom <= current_price <= zone_top:
                # Reconstruct ConfluenceZone for internal use
                self.current_zone = self._dict_to_confluence_zone(zone_dict)
                self.zone_entry_time = datetime.now()
                self.m5_confirmation_bars = 0

                # Check if liquidity has already been swept
                if zone_dict.get('liquidity_swept', False) or len(analysis.get('recent_sweeps', [])) > 0:
                    self.entry_state = EntryState.WAITING_FOR_M5_CONFIRMATION
                    if SMC_DEBUG:
                        print(f"[SMC Entry] Price in zone with liquidity swept - waiting for M5 confirmation")
                else:
                    self.entry_state = EntryState.IN_ZONE_WAITING_SWEEP
                    if SMC_DEBUG:
                        print(f"[SMC Entry] Price entered zone - waiting for liquidity sweep")

                return None

        return None

    def _handle_waiting_for_sweep(
        self,
        analysis: Dict,
        current_price: float,
        m5_data: pd.DataFrame
    ) -> Optional[EntrySignal]:
        """Handle IN_ZONE_WAITING_SWEEP state"""

        if self.current_zone is None:
            self.entry_state = EntryState.WAITING_FOR_ZONE
            return None

        # Check if still in zone
        if not self.current_zone.contains_price(current_price, tolerance=0.005):
            if SMC_DEBUG:
                print("[SMC Entry] Price left zone without sweep - resetting")
            self.entry_state = EntryState.WAITING_FOR_ZONE
            self.current_zone = None
            return None

        # Check for liquidity sweep
        recent_sweeps = analysis.get('recent_sweeps', [])
        if len(recent_sweeps) > 0:
            if SMC_DEBUG:
                print(f"[SMC Entry] Liquidity sweep detected! Moving to M5 confirmation")
            self.entry_state = EntryState.WAITING_FOR_M5_CONFIRMATION
            self.m5_confirmation_bars = 0

        return None

    def _handle_waiting_for_m5(
        self,
        analysis: Dict,
        current_price: float,
        m5_data: pd.DataFrame
    ) -> Optional[EntrySignal]:
        """Handle WAITING_FOR_M5_CONFIRMATION state"""

        if self.current_zone is None:
            self.entry_state = EntryState.WAITING_FOR_ZONE
            return None

        self.m5_confirmation_bars += 1

        # Max bars to wait for M5 confirmation (30 bars = 2.5 hours)
        MAX_M5_WAIT_BARS = 30

        if self.m5_confirmation_bars > MAX_M5_WAIT_BARS:
            if SMC_DEBUG:
                print("[SMC Entry] M5 confirmation timeout - resetting")
            self.entry_state = EntryState.WAITING_FOR_ZONE
            self.current_zone = None
            return None

        # Check if price went straight through zone (M15 gauge)
        if not self.current_zone.contains_price(current_price, tolerance=0.01):
            # Price left the zone
            zone_direction = Direction.BULLISH if self.current_zone.direction.value == 'bullish' else Direction.BEARISH

            if zone_direction == Direction.BULLISH and current_price < self.current_zone.bottom:
                # Bullish zone but price broke below - zone failed
                if SMC_DEBUG:
                    print("[SMC Entry] Price broke through bullish zone - STAY OUT")
                self.entry_state = EntryState.COOLDOWN
                self.current_zone = None
                return None

            elif zone_direction == Direction.BEARISH and current_price > self.current_zone.top:
                # Bearish zone but price broke above - zone failed
                if SMC_DEBUG:
                    print("[SMC Entry] Price broke through bearish zone - STAY OUT")
                self.entry_state = EntryState.COOLDOWN
                self.current_zone = None
                return None

        # Check for M5 confirmation signals
        m5_confirmation = self._check_m5_confirmation(m5_data, self.current_zone)

        if m5_confirmation['confirmed']:
            # Generate entry signal
            signal = self._generate_entry_signal(
                current_price=current_price,
                zone=self.current_zone,
                m5_confirmation=m5_confirmation
            )

            if signal and signal.valid:
                self.signals_generated += 1
                self.entry_state = EntryState.ENTRY_TRIGGERED
                self.pending_signal = signal

                if SMC_DEBUG:
                    print(f"\n[SMC Entry] ENTRY SIGNAL GENERATED!")
                    print(f"  Direction: {signal.direction.upper()}")
                    print(f"  Entry: {signal.entry_price:.5f}")
                    print(f"  SL: {signal.stop_loss:.5f}")
                    print(f"  TP1: {signal.take_profits[0]:.5f}")
                    print(f"  Confluence: {signal.confluence_score:.1f}")
                    print(f"  Factors: {', '.join(signal.factors)}")

                return signal

        return None

    def _check_m5_confirmation(
        self,
        m5_data: pd.DataFrame,
        zone: ConfluenceZone
    ) -> Dict:
        """
        Check M5 data for entry confirmation

        Looking for:
        1. ChoCH (Change of Character) - most important
        2. Reversal candlestick patterns (pin bar, engulfing, doji)
        3. Momentum slowdown
        """
        result = {
            'confirmed': False,
            'choch': False,
            'reversal_pattern': None,
            'momentum_slowdown': False,
            'factors': [],
            'score': 0
        }

        if len(m5_data) < M5_ENTRY_LOOKBACK:
            return result

        expected_direction = zone.direction

        # 1. Check for ChoCH on M5
        m5_analysis = self.analyzer.m5_smc.analyze(m5_data)
        recent_breaks = m5_analysis.get('structure_breaks', [])[-5:]

        for brk in recent_breaks:
            if brk.get('break_type') == 'choch':
                brk_direction = Direction.BULLISH if brk.get('direction') == 'bullish' else Direction.BEARISH
                if brk_direction == expected_direction:
                    result['choch'] = True
                    result['factors'].append("M5 ChoCH")
                    result['score'] += 3
                    break

        # 2. Check for reversal patterns
        pattern = detect_reversal_pattern(m5_data, lookback=3)
        if pattern['pattern']:
            pattern_direction = Direction.BULLISH if pattern['direction'] == 'bullish' else Direction.BEARISH

            # Check if pattern aligns with expected direction
            if pattern_direction == expected_direction:
                result['reversal_pattern'] = pattern['pattern']
                result['factors'].append(f"M5 {pattern['pattern']}")
                result['score'] += 2

                if pattern['pattern'] == 'engulfing':
                    result['score'] += 1  # Engulfing is stronger

        # 3. Check for momentum slowdown
        momentum = detect_momentum_slowdown(m5_data, lookback=MOMENTUM_SLOWDOWN_BARS)
        if momentum['slowdown']:
            result['momentum_slowdown'] = True
            result['factors'].append("M5 momentum slowdown")
            result['score'] += 1

        # 4. Check for retest of zone
        latest_candle = m5_data.iloc[-1]
        if zone.contains_price(latest_candle['low']) or zone.contains_price(latest_candle['high']):
            result['factors'].append("Zone retest")
            result['score'] += 1

        # Determine if confirmed
        # ChoCH required OR strong reversal pattern with momentum slowdown
        if M5_CHOCH_REQUIRED:
            result['confirmed'] = result['choch']
        else:
            # Alternative confirmation: reversal pattern + momentum slowdown
            if result['reversal_pattern'] and result['momentum_slowdown']:
                result['confirmed'] = True
            elif result['choch']:
                result['confirmed'] = True
            elif result['score'] >= 4:
                result['confirmed'] = True

        return result

    def _generate_entry_signal(
        self,
        current_price: float,
        zone: ConfluenceZone,
        m5_confirmation: Dict
    ) -> Optional[EntrySignal]:
        """Generate entry signal with SL/TP levels"""

        direction_str = 'buy' if zone.direction == Direction.BULLISH else 'sell'

        # Calculate stop loss beyond the OB zone
        sl_buffer_pips = SL_BEYOND_OB_PIPS.get('M15', 10)
        sl_buffer = sl_buffer_pips * self.pip_value

        if direction_str == 'buy':
            stop_loss = zone.bottom - sl_buffer
            sl_distance = current_price - stop_loss
        else:
            stop_loss = zone.top + sl_buffer
            sl_distance = stop_loss - current_price

        # Calculate take profit levels
        take_profits = []
        for ratio in TP_RATIOS:
            if direction_str == 'buy':
                tp = current_price + (sl_distance * ratio)
            else:
                tp = current_price - (sl_distance * ratio)
            take_profits.append(round(tp, 5))

        # Compile factors
        factors = [f"Zone: {', '.join(zone.timeframes)}"]
        factors.extend(m5_confirmation.get('factors', []))

        # Calculate total confluence score
        confluence_score = zone.confluence_score + m5_confirmation.get('score', 0)

        # Validate minimum score
        if confluence_score < MIN_SMC_CONFLUENCE_SCORE:
            return None

        return EntrySignal(
            valid=True,
            direction=direction_str,
            entry_price=round(current_price, 5),
            stop_loss=round(stop_loss, 5),
            take_profits=take_profits,
            confluence_zone=zone.to_dict(),
            confluence_score=confluence_score,
            factors=factors,
            m5_confirmation=m5_confirmation,
            timestamp=datetime.now()
        )

    def _dict_to_confluence_zone(self, zone_dict: Dict) -> ConfluenceZone:
        """Convert zone dictionary back to ConfluenceZone object"""
        direction = Direction.BULLISH if zone_dict['direction'] == 'bullish' else Direction.BEARISH

        return ConfluenceZone(
            top=zone_dict['top'],
            bottom=zone_dict['bottom'],
            direction=direction,
            timeframes=zone_dict['timeframes'],
            order_blocks=[],  # Not reconstructed from dict
            fvgs=[],
            confluence_score=zone_dict['confluence_score'],
            liquidity_swept=zone_dict.get('liquidity_swept', False)
        )

    def reset_state(self):
        """Reset entry state machine"""
        self.entry_state = EntryState.WAITING_FOR_ZONE
        self.current_zone = None
        self.zone_entry_time = None
        self.m5_confirmation_bars = 0
        self.pending_signal = None

    def on_trade_opened(self, trade: Dict):
        """Called when a trade is opened"""
        self.active_trades.append(trade)
        self.trades_entered += 1
        self.entry_state = EntryState.TRADE_ACTIVE
        self.pending_signal = None

    def on_trade_closed(self, trade: Dict, profit: float):
        """Called when a trade is closed"""
        if trade in self.active_trades:
            self.active_trades.remove(trade)

        if profit > 0:
            self.trades_won += 1
        else:
            self.trades_lost += 1

        # Reset to look for new entries
        self.reset_state()

    def get_statistics(self) -> Dict:
        """Get strategy statistics"""
        total_trades = self.trades_won + self.trades_lost
        win_rate = (self.trades_won / total_trades * 100) if total_trades > 0 else 0

        return {
            'signals_generated': self.signals_generated,
            'trades_entered': self.trades_entered,
            'trades_won': self.trades_won,
            'trades_lost': self.trades_lost,
            'win_rate': win_rate,
            'current_state': self.entry_state.value,
            'active_trades': len(self.active_trades)
        }

    def get_signal_quality(self, signal: EntrySignal) -> str:
        """Assess signal quality based on confluence score"""
        if signal.confluence_score >= OPTIMAL_SMC_CONFLUENCE_SCORE:
            return "EXCELLENT"
        elif signal.confluence_score >= MIN_SMC_CONFLUENCE_SCORE + 3:
            return "GOOD"
        elif signal.confluence_score >= MIN_SMC_CONFLUENCE_SCORE:
            return "ACCEPTABLE"
        else:
            return "POOR"

    def print_status(self):
        """Print current strategy status"""
        stats = self.get_statistics()
        print("\n" + "-" * 40)
        print("SMC ENTRY STRATEGY STATUS")
        print("-" * 40)
        print(f"Symbol: {self.symbol}")
        print(f"State: {stats['current_state']}")
        print(f"Active Trades: {stats['active_trades']}")
        print(f"\nStatistics:")
        print(f"  Signals: {stats['signals_generated']}")
        print(f"  Trades: {stats['trades_entered']}")
        print(f"  Won: {stats['trades_won']}")
        print(f"  Lost: {stats['trades_lost']}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")

        if self.current_zone:
            print(f"\nCurrent Zone:")
            print(f"  Direction: {self.current_zone.direction.value}")
            print(f"  Range: {self.current_zone.bottom:.5f} - {self.current_zone.top:.5f}")
            print(f"  TFs: {', '.join(self.current_zone.timeframes)}")

        if self.pending_signal:
            print(f"\nPending Signal:")
            print(f"  {self.pending_signal.direction.upper()} @ {self.pending_signal.entry_price:.5f}")

        print("-" * 40)
