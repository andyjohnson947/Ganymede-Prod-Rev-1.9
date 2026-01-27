#!/usr/bin/env python3
"""
Enhanced Trade Logger - Phase 1 Implementation

Immediate improvements:
1. Execution quality tracking (slippage, spread, fill time)
2. Market conditions at entry (ADX, ATR, session, spread status)
3. Continuous logging with enhanced metadata

Usage:
    python3 ml_system/enhanced_trade_logger.py &
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class EnhancedTradeLogger:
    """Enhanced continuous logger with execution quality and market condition tracking"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.output_dir = self.project_root / "ml_system" / "outputs"
        self.output_dir.mkdir(exist_ok=True)

        self.log_file = self.output_dir / "enhanced_trade_log.jsonl"
        self.execution_log = self.output_dir / "execution_quality.jsonl"
        self.market_conditions_log = self.output_dir / "market_conditions.jsonl"

        print(f"[ENHANCED LOGGER] Starting...")
        print(f"  Trade log: {self.log_file}")
        print(f"  Execution log: {self.execution_log}")
        print(f"  Market conditions log: {self.market_conditions_log}")

    def log_trade_with_execution(self, trade_data: Dict):
        """
        Log trade with enhanced execution quality data

        Enhanced fields:
        - slippage (expected vs actual entry)
        - spread_at_entry
        - fill_time_ms
        - execution_quality_score (0-100)
        """
        # Add execution quality metrics
        execution_quality = {
            'timestamp': datetime.now().isoformat(),
            'ticket': trade_data.get('ticket'),
            'symbol': trade_data.get('symbol'),

            # Execution quality
            'expected_price': trade_data.get('expected_price'),
            'actual_price': trade_data.get('entry_price'),
            'slippage_pips': self._calculate_slippage(
                trade_data.get('expected_price'),
                trade_data.get('entry_price'),
                trade_data.get('symbol')
            ),
            'spread_at_entry_pips': trade_data.get('spread_at_entry_pips', 0),
            'fill_time_ms': trade_data.get('fill_time_ms', 0),
            'requotes': trade_data.get('requotes', 0),

            # Quality score (0-100)
            'execution_quality_score': self._calculate_execution_quality(trade_data)
        }

        # Log to execution quality file
        with open(self.execution_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(execution_quality, ensure_ascii=False) + '\n')

        # Add to main trade data
        trade_data['execution_quality'] = execution_quality

        # Log to main trade log
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(trade_data, ensure_ascii=False) + '\n')

    def log_market_conditions(self, symbol: str, conditions: Dict):
        """
        Log market conditions at signal detection time

        Conditions to track:
        - ADX (trend strength)
        - ATR (volatility)
        - Spread status (normal/widened)
        - Session (Tokyo/London/NY/Sydney)
        - Distance to nearest level
        - Volume profile position
        """
        market_data = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,

            # Trend and volatility
            'adx': conditions.get('adx'),
            'adx_classification': self._classify_adx(conditions.get('adx', 0)),
            'atr_pips': conditions.get('atr_pips'),
            'volatility_regime': self._classify_volatility(conditions.get('atr_pips', 0)),

            # Spread
            'spread_pips': conditions.get('spread_pips'),
            'spread_status': 'WIDENED' if conditions.get('spread_pips', 0) > 2 else 'NORMAL',

            # Time context
            'hour': conditions.get('hour'),
            'session': self._get_session(conditions.get('hour', 0)),
            'is_spread_hour': conditions.get('hour', 0) in [0, 9, 13, 20, 21],

            # Technical context
            'distance_to_level_pips': conditions.get('distance_to_level_pips'),
            'at_hvn': conditions.get('at_hvn', False),
            'at_lvn': conditions.get('at_lvn', False),
            'at_poc': conditions.get('at_poc', False),

            # Signal quality
            'confluence_score': conditions.get('confluence_score'),
            'signal_strength': self._classify_signal_strength(conditions.get('confluence_score', 0))
        }

        # Log to market conditions file
        with open(self.market_conditions_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(market_data, ensure_ascii=False) + '\n')

        return market_data

    def log_recovery_decision(self, decision_data: Dict):
        """
        Log recovery trigger decision with context

        Captures WHY recovery was triggered and surrounding conditions
        """
        recovery_log = self.output_dir / "recovery_decisions.jsonl"

        decision_record = {
            'timestamp': datetime.now().isoformat(),
            'ticket': decision_data.get('ticket'),
            'recovery_type': decision_data.get('type'),  # DCA/Hedge/Grid

            # Trigger conditions
            'price_at_trigger': decision_data.get('price_at_trigger'),
            'pips_underwater': decision_data.get('pips_underwater'),
            'unrealized_pnl': decision_data.get('unrealized_pnl'),
            'time_underwater_minutes': decision_data.get('time_underwater_minutes'),

            # Market conditions at trigger
            'adx_at_entry': decision_data.get('adx_at_entry'),
            'adx_at_trigger': decision_data.get('adx_at_trigger'),
            'spread_at_trigger': decision_data.get('spread_at_trigger'),
            'hour_at_trigger': decision_data.get('hour_at_trigger'),

            # Decision outcome
            'was_blocked': decision_data.get('was_blocked', False),
            'block_reason': decision_data.get('block_reason'),
            'recovery_placed': decision_data.get('recovery_placed', False)
        }

        with open(recovery_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(decision_record, ensure_ascii=False) + '\n')

    def log_near_miss_signal(self, signal_data: Dict):
        """
        Log signals that were blocked/skipped

        Tracks what we DIDN'T trade and validates blocking rules
        """
        near_miss_log = self.output_dir / "near_miss_signals.jsonl"

        near_miss = {
            'timestamp': datetime.now().isoformat(),
            'symbol': signal_data.get('symbol'),
            'confluence_score': signal_data.get('confluence_score'),
            'direction': signal_data.get('direction'),

            # Why was it blocked?
            'block_reason': signal_data.get('block_reason'),
            'adx': signal_data.get('adx'),
            'hour': signal_data.get('hour'),
            'spread_pips': signal_data.get('spread_pips'),

            # What happened after? (to be filled in later via update_near_miss_outcomes)
            'price_at_signal': signal_data.get('price'),
            'price_1h_later': None,
            'price_4h_later': None,
            'dodged_bullet': None  # True if price went against signal
        }

        with open(near_miss_log, 'a', encoding='utf-8') as f:
            f.write(json.dumps(near_miss, ensure_ascii=False) + '\n')

    def update_near_miss_outcomes(self, current_prices: Dict[str, float]) -> Dict[str, int]:
        """
        Update near-miss signals with price outcomes after 1h and 4h.

        This method reads the near_miss_signals.jsonl file, checks for entries
        that are old enough (1h or 4h), and updates them with:
        - price_1h_later: Price 1 hour after signal
        - price_4h_later: Price 4 hours after signal
        - dodged_bullet: True if price went against the signal direction

        Args:
            current_prices: Dict mapping symbol to current price (e.g., {'EURUSD': 1.10500})

        Returns:
            Dict with counts: {'updated_1h': N, 'updated_4h': N, 'dodged_bullets': N}
        """
        near_miss_log = self.output_dir / "near_miss_signals.jsonl"

        if not near_miss_log.exists():
            return {'updated_1h': 0, 'updated_4h': 0, 'dodged_bullets': 0}

        # Read all entries
        entries = []
        with open(near_miss_log, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        if not entries:
            return {'updated_1h': 0, 'updated_4h': 0, 'dodged_bullets': 0}

        now = datetime.now()
        updated_1h = 0
        updated_4h = 0
        dodged_bullets = 0

        for entry in entries:
            signal_time = datetime.fromisoformat(entry['timestamp'])
            hours_elapsed = (now - signal_time).total_seconds() / 3600
            symbol = entry.get('symbol')
            current_price = current_prices.get(symbol)

            if current_price is None:
                continue

            # Update 1h price if elapsed time is >= 1h and not yet set
            if hours_elapsed >= 1 and entry.get('price_1h_later') is None:
                entry['price_1h_later'] = current_price
                updated_1h += 1

            # Update 4h price if elapsed time is >= 4h and not yet set
            if hours_elapsed >= 4 and entry.get('price_4h_later') is None:
                entry['price_4h_later'] = current_price
                updated_4h += 1

                # Calculate dodged_bullet when we have 4h data
                entry['dodged_bullet'] = self._calculate_dodged_bullet(entry)
                if entry['dodged_bullet']:
                    dodged_bullets += 1

        # Rewrite the file with updated entries
        with open(near_miss_log, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

        return {
            'updated_1h': updated_1h,
            'updated_4h': updated_4h,
            'dodged_bullets': dodged_bullets
        }

    def _calculate_dodged_bullet(self, entry: Dict) -> Optional[bool]:
        """
        Determine if blocking this signal was correct (dodged a bullet).

        A "dodged bullet" means:
        - For BUY signals: price went DOWN after the signal (would have lost)
        - For SELL signals: price went UP after the signal (would have lost)

        Uses 4h price for the calculation if available, otherwise 1h price.

        Args:
            entry: Near-miss signal entry with price data

        Returns:
            True if blocking was correct (avoided loss), False if blocking missed a profit,
            None if insufficient data to determine
        """
        price_at_signal = entry.get('price_at_signal')
        price_later = entry.get('price_4h_later') or entry.get('price_1h_later')
        direction = entry.get('direction', '').lower()

        if price_at_signal is None or price_later is None:
            return None

        if direction not in ('buy', 'sell'):
            return None

        price_change = price_later - price_at_signal

        if direction == 'buy':
            # For buy signal, dodged bullet if price went down
            return price_change < 0
        else:
            # For sell signal, dodged bullet if price went up
            return price_change > 0

    def get_near_miss_statistics(self) -> Dict:
        """
        Get statistics on near-miss signals to evaluate blocking rules.

        Returns:
            Dict with statistics on blocked signals and their outcomes
        """
        near_miss_log = self.output_dir / "near_miss_signals.jsonl"

        if not near_miss_log.exists():
            return {'total': 0, 'with_outcomes': 0, 'dodged_bullets': 0, 'missed_opportunities': 0}

        total = 0
        with_outcomes = 0
        dodged_bullets = 0
        missed_opportunities = 0
        by_block_reason = {}

        with open(near_miss_log, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                total += 1

                # Track by block reason
                reason = entry.get('block_reason', 'UNKNOWN')
                if reason not in by_block_reason:
                    by_block_reason[reason] = {'total': 0, 'dodged': 0, 'missed': 0}
                by_block_reason[reason]['total'] += 1

                if entry.get('dodged_bullet') is not None:
                    with_outcomes += 1
                    if entry['dodged_bullet']:
                        dodged_bullets += 1
                        by_block_reason[reason]['dodged'] += 1
                    else:
                        missed_opportunities += 1
                        by_block_reason[reason]['missed'] += 1

        accuracy = (dodged_bullets / with_outcomes * 100) if with_outcomes > 0 else 0

        return {
            'total': total,
            'with_outcomes': with_outcomes,
            'dodged_bullets': dodged_bullets,
            'missed_opportunities': missed_opportunities,
            'blocking_accuracy_pct': round(accuracy, 1),
            'by_block_reason': by_block_reason
        }

    # Helper methods

    def _calculate_slippage(self, expected: Optional[float], actual: Optional[float], symbol: str) -> float:
        """Calculate slippage in pips"""
        if not expected or not actual:
            return 0.0

        # Assuming 4/5 digit pricing
        point = 0.0001 if 'JPY' not in symbol else 0.01
        pip_diff = abs(actual - expected) / point
        return round(pip_diff, 2)

    def _calculate_execution_quality(self, trade_data: Dict) -> int:
        """Calculate execution quality score (0-100)"""
        score = 100

        # Penalize slippage
        slippage = abs(trade_data.get('slippage_pips', 0))
        if slippage > 2:
            score -= min(30, slippage * 5)

        # Penalize wide spreads
        spread = trade_data.get('spread_at_entry_pips', 0)
        if spread > 2:
            score -= min(20, (spread - 2) * 10)

        # Penalize slow fills
        fill_time = trade_data.get('fill_time_ms', 0)
        if fill_time > 1000:  # > 1 second
            score -= 20

        # Penalize requotes
        requotes = trade_data.get('requotes', 0)
        score -= requotes * 10

        return max(0, score)

    def _classify_adx(self, adx: float) -> str:
        """Classify ADX value"""
        if adx < 20:
            return 'WEAK_NO_TREND'
        elif adx < 25:
            return 'DEVELOPING_TREND'
        elif adx < 30:
            return 'MODERATE_TREND'
        elif adx < 40:
            return 'STRONG_TREND'
        else:
            return 'VERY_STRONG_TREND'

    def _classify_volatility(self, atr_pips: float) -> str:
        """Classify volatility regime"""
        if atr_pips < 50:
            return 'LOW'
        elif atr_pips < 100:
            return 'MEDIUM'
        else:
            return 'HIGH'

    def _get_session(self, hour: int) -> str:
        """Determine trading session"""
        if 0 <= hour < 8:
            return 'Tokyo'
        elif 8 <= hour < 13:
            return 'London'
        elif 13 <= hour < 21:
            return 'NY'
        else:
            return 'Sydney'

    def _classify_signal_strength(self, confluence: int) -> str:
        """Classify signal strength"""
        if confluence < 9:
            return 'WEAK'
        elif confluence < 13:
            return 'MODERATE'
        elif confluence < 17:
            return 'STRONG'
        else:
            return 'VERY_STRONG'


# Example usage demonstrating the enhanced logger
def example_usage():
    """Show how to use the enhanced logger"""
    logger = EnhancedTradeLogger()

    # Example 1: Log a trade with execution quality
    trade = {
        'ticket': 12345678,
        'symbol': 'EURUSD',
        'direction': 'buy',
        'expected_price': 1.10500,
        'entry_price': 1.10508,  # 0.8 pip slippage
        'volume': 0.04,
        'spread_at_entry_pips': 1.2,
        'fill_time_ms': 450,
        'requotes': 0,
        'confluence_score': 12
    }
    logger.log_trade_with_execution(trade)
    print("[EXAMPLE] Logged trade with execution quality")

    # Example 2: Log market conditions at signal time
    conditions = {
        'adx': 28.5,
        'atr_pips': 85.3,
        'spread_pips': 1.5,
        'hour': 12,
        'distance_to_level_pips': 5.2,
        'at_poc': True,
        'confluence_score': 12
    }
    logger.log_market_conditions('EURUSD', conditions)
    print("[EXAMPLE] Logged market conditions")

    # Example 3: Log a recovery decision
    recovery_decision = {
        'ticket': 12345678,
        'type': 'DCA',
        'price_at_trigger': 1.10400,
        'pips_underwater': 35,
        'unrealized_pnl': -14.00,
        'time_underwater_minutes': 45,
        'adx_at_entry': 28.5,
        'adx_at_trigger': 32.1,
        'spread_at_trigger': 2.5,
        'hour_at_trigger': 13,
        'was_blocked': True,
        'block_reason': 'ADX_HARD_STOPS_ENABLED'
    }
    logger.log_recovery_decision(recovery_decision)
    print("[EXAMPLE] Logged recovery decision")

    # Example 4: Log a near-miss signal
    near_miss = {
        'symbol': 'GBPUSD',
        'confluence_score': 11,
        'direction': 'sell',
        'block_reason': 'SPREAD_HOUR',
        'adx': 22.3,
        'hour': 0,
        'spread_pips': 3.8,
        'price': 1.27500
    }
    logger.log_near_miss_signal(near_miss)
    print("[EXAMPLE] Logged near-miss signal")

    # Example 5: Update near-miss outcomes with current prices
    # In production, this would be called periodically (e.g., every hour)
    # to update signals with their price outcomes
    current_prices = {
        'EURUSD': 1.10520,
        'GBPUSD': 1.27350  # Price went down from 1.27500 - dodged bullet for sell signal
    }
    results = logger.update_near_miss_outcomes(current_prices)
    print(f"[EXAMPLE] Updated near-miss outcomes: {results}")

    # Example 6: Get statistics on blocking effectiveness
    stats = logger.get_near_miss_statistics()
    print(f"[EXAMPLE] Near-miss statistics: {stats}")

    print()
    print("=" * 80)
    print("Enhanced logger examples complete!")
    print("Check ml_system/outputs/ for generated files:")
    print("  - enhanced_trade_log.jsonl")
    print("  - execution_quality.jsonl")
    print("  - market_conditions.jsonl")
    print("  - recovery_decisions.jsonl")
    print("  - near_miss_signals.jsonl")
    print("=" * 80)


if __name__ == '__main__':
    # Run example to demonstrate functionality
    example_usage()
