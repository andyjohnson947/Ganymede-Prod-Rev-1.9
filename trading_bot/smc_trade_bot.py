"""
SMC (Smart Money Concepts) Trade Bot
Multi-Timeframe Order Block Analysis with Liquidity Sweeps

This bot implements institutional trading concepts:
- H4/H1/M15 Order Block confluence detection
- Liquidity sweeps and swing hi/lo identification
- M5 entry timing with ChoCH and reversal patterns
- M15 OB zone as market gauge (stay out if breached)

Entry Logic:
1. Detect Order Blocks on H4, H1, M15 (as zones with top/bottom)
2. Find confluence where 2+ timeframe OBs align (M15 required)
3. Wait for liquidity sweep
4. Enter on M5 when price retests zone with reversal confirmation
5. If price goes straight through M15 OB, stay out

Usage:
    python smc_trade_bot.py [--test] [--debug] [--symbols EURUSD GBPUSD]
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Import trading components
from trading_bot.core.mt5_manager import MT5Manager
from trading_bot.strategies.smc_analyzer import SMCMultiTimeframeAnalyzer
from trading_bot.strategies.smc_entry_strategy import SMCEntryStrategy, EntrySignal
from trading_bot.utils.risk_calculator import RiskCalculator
from trading_bot.config.smc_config import (
    SMC_HTF_TIMEFRAMES,
    SMC_LTF_TIMEFRAME,
    SMC_ENTRY_TIMEFRAME,
    SMC_DEBUG,
    MIN_BARS_REQUIRED
)
from trading_bot.config.strategy_config import (
    SYMBOLS,
    BASE_LOT_SIZE,
    MAX_OPEN_POSITIONS,
    MT5_MAGIC_NUMBER
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SMCTradeBot')


class SMCTradeBot:
    """
    SMC (Smart Money Concepts) Trade Bot

    Implements multi-timeframe order block analysis with
    liquidity sweeps and M5 entry timing.
    """

    def __init__(
        self,
        symbols: List[str] = None,
        test_mode: bool = False,
        debug: bool = False,
        lot_size: float = BASE_LOT_SIZE
    ):
        """
        Initialize SMC Trade Bot

        Args:
            symbols: List of symbols to trade (default: from config)
            test_mode: If True, bypass time filters and paper trade
            debug: Enable verbose debug output
            lot_size: Position size for trades
        """
        self.symbols = symbols or SYMBOLS
        self.test_mode = test_mode
        self.debug = debug or SMC_DEBUG
        self.lot_size = lot_size

        # MT5 connection
        self.mt5: Optional[MT5Manager] = None

        # Strategy components per symbol
        self.strategies: Dict[str, SMCEntryStrategy] = {}

        # Risk calculator
        self.risk_calculator = RiskCalculator()

        # Bot state
        self.running = False
        self.last_analysis_time: Dict[str, datetime] = {}
        self.market_data_cache: Dict[str, Dict] = {}

        # Statistics
        self.stats = {
            'start_time': None,
            'analyses_performed': 0,
            'signals_generated': 0,
            'trades_opened': 0,
            'trades_closed': 0,
            'total_profit': 0.0
        }

        # Analysis interval (seconds)
        self.analysis_interval = 60  # Run analysis every minute

        logger.info(f"SMC Trade Bot initialized for symbols: {', '.join(self.symbols)}")

    def connect(self) -> bool:
        """Connect to MT5"""
        logger.info("Connecting to MT5...")
        self.mt5 = MT5Manager()

        if not self.mt5.connect():
            logger.error("Failed to connect to MT5")
            return False

        # Get account info
        account_info = self.mt5.get_account_info()
        if account_info:
            logger.info(f"Connected to MT5 - Balance: ${account_info['balance']:.2f}")
            self.risk_calculator.set_initial_balance(account_info['balance'])
        else:
            logger.warning("Connected but couldn't get account info")

        return True

    def initialize_strategies(self):
        """Initialize SMC strategy for each symbol"""
        for symbol in self.symbols:
            pip_value = 0.0001 if 'JPY' not in symbol else 0.01
            self.strategies[symbol] = SMCEntryStrategy(
                symbol=symbol,
                pip_value=pip_value,
                lot_size=self.lot_size
            )
            logger.info(f"Initialized SMC strategy for {symbol}")

    def fetch_market_data(self, symbol: str) -> Dict[str, any]:
        """
        Fetch market data for all required timeframes

        Returns:
            Dict with H4, H1, M15, M5 DataFrames
        """
        data = {}

        timeframes = {
            'H4': ('H4', MIN_BARS_REQUIRED.get('H4', 100) + 50),
            'H1': ('H1', MIN_BARS_REQUIRED.get('H1', 200) + 50),
            'M15': ('M15', MIN_BARS_REQUIRED.get('M15', 500) + 50),
            'M5': ('M5', MIN_BARS_REQUIRED.get('M5', 1000) + 50)
        }

        for tf_name, (tf_code, bars) in timeframes.items():
            df = self.mt5.get_data(symbol, tf_code, bars=bars)
            if df is not None and len(df) > 0:
                data[tf_name] = df
                if self.debug:
                    logger.debug(f"Fetched {len(df)} {tf_name} bars for {symbol}")
            else:
                logger.warning(f"Failed to fetch {tf_name} data for {symbol}")
                return None

        return data

    def process_symbol(self, symbol: str) -> Optional[EntrySignal]:
        """
        Process a symbol for potential entry signals

        Args:
            symbol: Trading symbol

        Returns:
            EntrySignal if conditions met, None otherwise
        """
        strategy = self.strategies.get(symbol)
        if not strategy:
            return None

        # Fetch market data
        data = self.fetch_market_data(symbol)
        if not data:
            return None

        # Get current price
        current_price = data['M5'].iloc[-1]['close']

        # Process tick through strategy
        signal = strategy.process_tick(
            h4_data=data['H4'],
            h1_data=data['H1'],
            m15_data=data['M15'],
            m5_data=data['M5'],
            current_price=current_price
        )

        self.stats['analyses_performed'] += 1

        if signal and signal.valid:
            self.stats['signals_generated'] += 1
            return signal

        return None

    def execute_signal(self, signal: EntrySignal) -> bool:
        """
        Execute a trade based on entry signal

        Args:
            signal: EntrySignal object

        Returns:
            True if trade opened successfully
        """
        if self.test_mode:
            logger.info(f"[TEST MODE] Would execute: {signal.direction.upper()} "
                       f"@ {signal.entry_price:.5f}, SL: {signal.stop_loss:.5f}")
            return True

        # Check position limits
        positions = self.mt5.get_positions()
        if len(positions) >= MAX_OPEN_POSITIONS:
            logger.warning("Max positions reached, skipping signal")
            return False

        # Open the trade
        symbol = signal.confluence_zone.get('timeframe', 'EURUSD')  # Get from zone
        if 'order_blocks' in signal.confluence_zone and signal.confluence_zone['order_blocks']:
            symbol = signal.confluence_zone['order_blocks'][0].get('timeframe', symbol)

        # Determine order type
        order_type = 'buy' if signal.direction == 'buy' else 'sell'

        # Place the order
        result = self.mt5.open_position(
            symbol=symbol,
            order_type=order_type,
            lot_size=self.lot_size,
            sl=signal.stop_loss,
            tp=signal.take_profits[0] if signal.take_profits else None,
            magic=MT5_MAGIC_NUMBER,
            comment=f"SMC_{signal.confluence_score:.0f}"
        )

        if result:
            self.stats['trades_opened'] += 1
            logger.info(f"Trade opened: {order_type.upper()} @ {signal.entry_price:.5f}")

            # Notify strategy
            self.strategies[symbol].on_trade_opened({
                'symbol': symbol,
                'type': order_type,
                'price': signal.entry_price,
                'sl': signal.stop_loss,
                'tp': signal.take_profits[0] if signal.take_profits else None
            })

            return True

        logger.error("Failed to open trade")
        return False

    def print_analysis_summary(self, symbol: str, data: Dict):
        """Print analysis summary for a symbol"""
        strategy = self.strategies.get(symbol)
        if not strategy:
            return

        analyzer = strategy.analyzer
        current_price = data['M5'].iloc[-1]['close']

        print("\n" + "=" * 60)
        print(f" SMC ANALYSIS: {symbol} @ {current_price:.5f}")
        print("=" * 60)

        summary = analyzer.get_analysis_summary(current_price)

        print(f"\n[TRENDS]")
        print(f"  H4: {summary['summary']['h4_trend'].upper()}")
        print(f"  H1: {summary['summary']['h1_trend'].upper()}")
        print(f"  M15: {summary['summary']['m15_trend'].upper()}")

        print(f"\n[ORDER BLOCKS]")
        h4_obs = summary['h4_analysis'].get('counts', {}).get('active_order_blocks', 0)
        h1_obs = summary['h1_analysis'].get('counts', {}).get('active_order_blocks', 0)
        m15_obs = summary['m15_analysis'].get('counts', {}).get('active_order_blocks', 0)
        print(f"  H4: {h4_obs}, H1: {h1_obs}, M15: {m15_obs}")

        print(f"\n[CONFLUENCE ZONES]")
        print(f"  Total: {summary['summary']['total_confluence_zones']}")
        print(f"  Valid: {summary['summary']['valid_confluence_zones']}")
        print(f"  Bullish: {summary['summary']['bullish_zones']}")
        print(f"  Bearish: {summary['summary']['bearish_zones']}")

        # Print zone details
        for i, zone in enumerate(summary.get('valid_confluence_zones', [])[:3], 1):
            print(f"\n  Zone {i}: {zone['direction'].upper()}")
            print(f"    Range: {zone['bottom']:.5f} - {zone['top']:.5f}")
            print(f"    TFs: {', '.join(zone['timeframes'])}")
            print(f"    Score: {zone['confluence_score']:.1f}")

        print(f"\n[LIQUIDITY]")
        print(f"  Sweeps: {summary['summary']['liquidity_sweeps']}")

        if summary.get('m15_cooldown_active'):
            print(f"\n[!] M15 ZONE BREACH - COOLDOWN ACTIVE")

        print("\n" + "=" * 60)

    def run(self):
        """Main bot loop"""
        logger.info("=" * 60)
        logger.info(" SMC TRADE BOT STARTING")
        logger.info("=" * 60)

        if not self.connect():
            logger.error("Failed to connect to MT5, exiting")
            return

        self.initialize_strategies()

        self.running = True
        self.stats['start_time'] = datetime.now()

        logger.info(f"Bot running - Analyzing: {', '.join(self.symbols)}")
        logger.info(f"Test Mode: {self.test_mode}")
        logger.info(f"Debug Mode: {self.debug}")
        logger.info("")

        try:
            while self.running:
                for symbol in self.symbols:
                    try:
                        # Check if it's time to analyze
                        last_time = self.last_analysis_time.get(symbol)
                        now = datetime.now()

                        if last_time and (now - last_time).total_seconds() < self.analysis_interval:
                            continue

                        self.last_analysis_time[symbol] = now

                        # Fetch and analyze
                        data = self.fetch_market_data(symbol)
                        if not data:
                            continue

                        # Store in cache
                        self.market_data_cache[symbol] = data

                        # Run analysis
                        current_price = data['M5'].iloc[-1]['close']
                        strategy = self.strategies[symbol]

                        # Full analysis
                        analysis = strategy.analyzer.analyze_all_timeframes(
                            h4_data=data['H4'],
                            h1_data=data['H1'],
                            m15_data=data['M15'],
                            m5_data=data['M5']
                        )

                        # Print summary if debug
                        if self.debug:
                            self.print_analysis_summary(symbol, data)

                        # Check for entry signal
                        signal = strategy.process_tick(
                            h4_data=data['H4'],
                            h1_data=data['H1'],
                            m15_data=data['M15'],
                            m5_data=data['M5'],
                            current_price=current_price
                        )

                        self.stats['analyses_performed'] += 1

                        if signal and signal.valid:
                            self.stats['signals_generated'] += 1
                            quality = strategy.get_signal_quality(signal)

                            logger.info(f"\n{'='*50}")
                            logger.info(f"ENTRY SIGNAL: {symbol} {signal.direction.upper()}")
                            logger.info(f"Quality: {quality}")
                            logger.info(f"Entry: {signal.entry_price:.5f}")
                            logger.info(f"SL: {signal.stop_loss:.5f}")
                            logger.info(f"TP1: {signal.take_profits[0]:.5f}")
                            logger.info(f"Score: {signal.confluence_score:.1f}")
                            logger.info(f"Factors: {', '.join(signal.factors)}")
                            logger.info(f"{'='*50}\n")

                            # Execute if not in test mode
                            if not self.test_mode:
                                self.execute_signal(signal)

                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                        if self.debug:
                            import traceback
                            traceback.print_exc()

                # Print status periodically
                if self.stats['analyses_performed'] % 10 == 0:
                    self.print_status()

                # Sleep between iterations
                time.sleep(5)

        except KeyboardInterrupt:
            logger.info("\nShutdown requested...")

        finally:
            self.shutdown()

    def print_status(self):
        """Print bot status"""
        runtime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else timedelta(0)

        print(f"\n[STATUS] Runtime: {runtime} | "
              f"Analyses: {self.stats['analyses_performed']} | "
              f"Signals: {self.stats['signals_generated']} | "
              f"Trades: {self.stats['trades_opened']}")

        for symbol, strategy in self.strategies.items():
            stats = strategy.get_statistics()
            print(f"  {symbol}: State={stats['current_state']}, "
                  f"Win Rate={stats['win_rate']:.1f}%")

    def shutdown(self):
        """Shutdown the bot"""
        logger.info("Shutting down SMC Trade Bot...")
        self.running = False

        # Print final statistics
        self.print_final_stats()

        # Disconnect MT5
        if self.mt5:
            self.mt5.disconnect()

    def print_final_stats(self):
        """Print final statistics"""
        runtime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else timedelta(0)

        print("\n" + "=" * 60)
        print(" SMC TRADE BOT - FINAL STATISTICS")
        print("=" * 60)
        print(f"Runtime: {runtime}")
        print(f"Analyses Performed: {self.stats['analyses_performed']}")
        print(f"Signals Generated: {self.stats['signals_generated']}")
        print(f"Trades Opened: {self.stats['trades_opened']}")
        print(f"Trades Closed: {self.stats['trades_closed']}")
        print(f"Total Profit: ${self.stats['total_profit']:.2f}")

        print("\nPer-Symbol Statistics:")
        for symbol, strategy in self.strategies.items():
            stats = strategy.get_statistics()
            print(f"\n  {symbol}:")
            print(f"    Signals: {stats['signals_generated']}")
            print(f"    Trades: {stats['trades_entered']}")
            print(f"    Won: {stats['trades_won']}")
            print(f"    Lost: {stats['trades_lost']}")
            print(f"    Win Rate: {stats['win_rate']:.1f}%")

        print("\n" + "=" * 60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='SMC Trade Bot')
    parser.add_argument('--test', action='store_true', help='Run in test mode (no real trades)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--symbols', nargs='+', default=SYMBOLS, help='Symbols to trade')
    parser.add_argument('--lot-size', type=float, default=BASE_LOT_SIZE, help='Lot size for trades')

    args = parser.parse_args()

    bot = SMCTradeBot(
        symbols=args.symbols,
        test_mode=args.test,
        debug=args.debug,
        lot_size=args.lot_size
    )

    bot.run()


if __name__ == '__main__':
    main()
