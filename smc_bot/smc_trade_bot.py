"""
SMC Trade Bot - Paul's Methodology
Based on TradeForexwithPaul's approach

Entry Flow:
1. Mark HTF POIs (previous highs/lows, session levels)
2. Wait for price to raid liquidity INTO the POI
3. Look for MSS (Market Structure Shift) on LTF
4. Enter on pullback to LTF imbalance
5. SL just beyond sweep (tight!)
6. TP at opposite-side liquidity

Usage:
    python smc_trade_bot.py [--test] [--debug] [--symbols EURUSD GBPUSD]
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Add trading_bot directory to path (for mt5_manager's config imports)
trading_bot_path = project_root / 'trading_bot'
sys.path.insert(0, str(trading_bot_path))

import argparse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('SMCTradeBot')


class SMCTradeBot:
    """
    SMC Trade Bot - Paul's Methodology

    Simple, high R:R trading based on:
    - HTF POI identification
    - Liquidity sweeps
    - LTF Market Structure Shifts
    - Tight entries on pullbacks
    """

    def __init__(
        self,
        symbols: List[str] = None,
        test_mode: bool = False,
        debug: bool = False,
        lot_size: float = 0.04,
        htf: str = 'H1',
        ltf: str = 'M5',
        login: int = None,
        password: str = None,
        server: str = None
    ):
        self.symbols = symbols or ['EURUSD', 'GBPUSD']
        self.test_mode = test_mode
        self.debug = debug
        self.lot_size = lot_size
        self.htf = htf
        self.ltf = ltf

        # MT5 credentials
        self.login = login
        self.password = password
        self.server = server

        # MT5 connection
        self.mt5 = None

        # Strategy instances per symbol
        self.strategies: Dict = {}

        # Bot state
        self.running = False
        self.last_analysis_time: Dict[str, datetime] = {}

        # Analysis interval
        self.analysis_interval = 60  # seconds

        # Statistics
        self.stats = {
            'start_time': None,
            'setups_found': 0,
            'trades_taken': 0,
            'trades_won': 0,
            'trades_lost': 0,
            'total_rr': 0.0
        }

        # Risk management
        from smc_bot.config.smc_config import (
            RISK_PER_TRADE_PERCENT,
            MAX_DAILY_LOSS_PERCENT,
            MAX_TRADES_PER_DAY
        )
        self.risk_per_trade = RISK_PER_TRADE_PERCENT
        self.max_daily_loss = MAX_DAILY_LOSS_PERCENT
        self.max_trades_per_day = MAX_TRADES_PER_DAY
        self.daily_trades = 0
        self.daily_loss = 0.0

        logger.info(f"SMC Trade Bot (Paul's Method) initialized")
        logger.info(f"Symbols: {', '.join(self.symbols)}")
        logger.info(f"HTF: {htf}, LTF: {ltf}")
        logger.info(f"Risk per trade: {self.risk_per_trade}%")

    def connect(self) -> bool:
        """Connect to MT5"""
        try:
            from trading_bot.core.mt5_manager import MT5Manager
            logger.info("Connecting to MT5...")
            self.mt5 = MT5Manager(
                login=self.login,
                password=self.password,
                server=self.server
            )

            if not self.mt5.connect():
                logger.error("Failed to connect to MT5")
                return False

            account_info = self.mt5.get_account_info()
            if account_info:
                logger.info(f"Connected - Balance: ${account_info['balance']:.2f}")
                self.account_balance = account_info['balance']
            return True

        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False

    def initialize_strategies(self):
        """Initialize strategy for each symbol"""
        from smc_bot.strategies.paul_smc_strategy import PaulSMCStrategy

        for symbol in self.symbols:
            pip_value = 0.0001 if 'JPY' not in symbol else 0.01
            self.strategies[symbol] = PaulSMCStrategy(
                symbol=symbol,
                pip_value=pip_value,
                htf=self.htf,
                ltf=self.ltf
            )
            logger.info(f"Strategy initialized for {symbol}")

    def fetch_data(self, symbol: str) -> Optional[Dict]:
        """Fetch HTF and LTF data"""
        try:
            from smc_bot.config.smc_config import MIN_BARS_REQUIRED

            htf_bars = MIN_BARS_REQUIRED.get(self.htf, 200)
            ltf_bars = MIN_BARS_REQUIRED.get(self.ltf, 500)

            htf_data = self.mt5.get_data(symbol, self.htf, bars=htf_bars)
            ltf_data = self.mt5.get_data(symbol, self.ltf, bars=ltf_bars)

            if htf_data is None or ltf_data is None:
                return None

            if len(htf_data) < 50 or len(ltf_data) < 100:
                return None

            return {
                'htf': htf_data,
                'ltf': ltf_data
            }

        except Exception as e:
            logger.error(f"Data fetch error for {symbol}: {e}")
            return None

    def process_symbol(self, symbol: str) -> Optional[Dict]:
        """Process a symbol for trade setups"""
        strategy = self.strategies.get(symbol)
        if not strategy:
            return None

        data = self.fetch_data(symbol)
        if not data:
            return None

        # Run analysis
        setup = strategy.analyze(
            htf_data=data['htf'],
            ltf_data=data['ltf']
        )

        if setup:
            self.stats['setups_found'] += 1
            return {
                'symbol': symbol,
                'setup': setup,
                'data': data
            }

        return None

    def execute_trade(self, symbol: str, setup) -> bool:
        """Execute a trade based on setup"""
        if self.test_mode:
            logger.info(f"[TEST] Would execute: {symbol} {setup.direction.value.upper()}")
            logger.info(f"[TEST]   Entry: {setup.entry_price:.5f}")
            logger.info(f"[TEST]   SL: {setup.stop_loss:.5f}")
            logger.info(f"[TEST]   TP1: {setup.take_profits[0]:.5f}")
            logger.info(f"[TEST]   R:R: {setup.risk_reward}")
            return True

        # Check daily limits
        if self.daily_trades >= self.max_trades_per_day:
            logger.warning("Max daily trades reached")
            return False

        if self.daily_loss >= self.max_daily_loss:
            logger.warning("Max daily loss reached")
            return False

        # Calculate position size based on risk
        account_info = self.mt5.get_account_info()
        if not account_info:
            return False

        balance = account_info['balance']
        risk_amount = balance * (self.risk_per_trade / 100)

        # SL distance in pips
        pip_value = 0.0001 if 'JPY' not in symbol else 0.01
        sl_pips = abs(setup.entry_price - setup.stop_loss) / pip_value

        # Calculate lot size (assuming $10/pip for 1 lot)
        pip_value_per_lot = 10.0
        lot_size = risk_amount / (sl_pips * pip_value_per_lot)
        lot_size = round(max(0.01, min(lot_size, 1.0)), 2)

        # Place order
        order_type = 'buy' if setup.direction.value == 'long' else 'sell'

        result = self.mt5.open_position(
            symbol=symbol,
            order_type=order_type,
            lot_size=lot_size,
            sl=setup.stop_loss,
            tp=setup.take_profits[0],
            magic=987655,  # SMC bot magic number
            comment=f"SMC_RR{setup.risk_reward:.0f}"
        )

        if result:
            self.stats['trades_taken'] += 1
            self.daily_trades += 1
            logger.info(f"Trade opened: {symbol} {order_type.upper()} {lot_size} lots")
            logger.info(f"  Entry: {setup.entry_price:.5f}")
            logger.info(f"  SL: {setup.stop_loss:.5f}")
            logger.info(f"  TP: {setup.take_profits[0]:.5f}")
            logger.info(f"  R:R: {setup.risk_reward}")
            return True

        logger.error(f"Failed to open trade for {symbol}")
        return False

    def check_re_sweep(self, symbol: str, setup) -> bool:
        """
        Check if price re-swept the level (invalidates trade)

        If price goes back beyond the sweep level, exit immediately
        """
        from smc_bot.config.smc_config import RESWEEP_INVALIDATES_TRADE

        if not RESWEEP_INVALIDATES_TRADE:
            return False

        # Get current price
        data = self.fetch_data(symbol)
        if not data:
            return False

        current = data['ltf'].iloc[-1]

        # Check re-sweep
        if setup.direction.value == 'long':
            # For longs, re-sweep = price goes below sweep level again
            if current['low'] < setup.sweep_level:
                logger.warning(f"[{symbol}] RE-SWEEP detected - trade invalid!")
                return True
        else:
            # For shorts, re-sweep = price goes above sweep level again
            if current['high'] > setup.sweep_level:
                logger.warning(f"[{symbol}] RE-SWEEP detected - trade invalid!")
                return True

        return False

    def run(self):
        """Main bot loop"""
        print("\n" + "=" * 60)
        print(" SMC TRADE BOT - PAUL'S METHODOLOGY")
        print("=" * 60)
        print(f"\nKey Rules:")
        print(f"  - Wait for liquidity sweep INTO POI")
        print(f"  - MSS on LTF confirms direction")
        print(f"  - Enter on pullback (tight entry)")
        print(f"  - SL beyond sweep, TP at opposite liquidity")
        print(f"  - High R:R (3R minimum, 10R+ potential)")
        print(f"\nSettings:")
        print(f"  Symbols: {', '.join(self.symbols)}")
        print(f"  HTF: {self.htf}, LTF: {self.ltf}")
        print(f"  Risk: {self.risk_per_trade}% per trade")
        print(f"  Max trades/day: {self.max_trades_per_day}")
        print("=" * 60 + "\n")

        if not self.test_mode:
            if not self.connect():
                logger.error("Failed to connect to MT5")
                return

        self.initialize_strategies()

        self.running = True
        self.stats['start_time'] = datetime.now()

        try:
            while self.running:
                for symbol in self.symbols:
                    try:
                        # Rate limit
                        last = self.last_analysis_time.get(symbol)
                        now = datetime.now()
                        if last and (now - last).total_seconds() < self.analysis_interval:
                            continue

                        self.last_analysis_time[symbol] = now

                        # Analyze
                        result = self.process_symbol(symbol)

                        if result and result['setup']:
                            setup = result['setup']
                            quality = "EXCELLENT" if setup.risk_reward >= 5 else "GOOD" if setup.risk_reward >= 3 else "OK"

                            print(f"\n{'='*50}")
                            print(f"SETUP FOUND: {symbol}")
                            print(f"{'='*50}")
                            print(f"Direction: {setup.direction.value.upper()}")
                            print(f"Quality: {quality} ({setup.risk_reward}R)")
                            print(f"Entry: {setup.entry_price:.5f}")
                            print(f"SL: {setup.stop_loss:.5f}")
                            print(f"TPs: {[f'{tp:.5f}' for tp in setup.take_profits]}")
                            print(f"POI: {setup.poi.poi_type} @ {setup.poi.level:.5f}")
                            print(f"{'='*50}\n")

                            # Execute if not test mode
                            self.execute_trade(symbol, setup)

                            # Reset strategy for next setup
                            self.strategies[symbol].reset()

                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                        if self.debug:
                            import traceback
                            traceback.print_exc()

                # Print status periodically
                if self.stats['setups_found'] > 0 and self.stats['setups_found'] % 5 == 0:
                    self.print_status()

                time.sleep(5)

        except KeyboardInterrupt:
            logger.info("\nShutdown requested...")

        finally:
            self.shutdown()

    def print_status(self):
        """Print bot status"""
        runtime = datetime.now() - self.stats['start_time'] if self.stats['start_time'] else timedelta(0)

        print(f"\n[STATUS] Runtime: {runtime}")
        print(f"  Setups found: {self.stats['setups_found']}")
        print(f"  Trades taken: {self.stats['trades_taken']}")
        print(f"  Daily trades: {self.daily_trades}/{self.max_trades_per_day}")

        for symbol, strategy in self.strategies.items():
            status = strategy.get_status()
            print(f"  {symbol}: {status['state']} | POIs: {status['htf_pois']}")

    def shutdown(self):
        """Shutdown bot"""
        logger.info("Shutting down SMC Trade Bot...")
        self.running = False

        print("\n" + "=" * 60)
        print(" FINAL STATISTICS")
        print("=" * 60)
        print(f"Setups Found: {self.stats['setups_found']}")
        print(f"Trades Taken: {self.stats['trades_taken']}")
        print(f"Trades Won: {self.stats['trades_won']}")
        print(f"Trades Lost: {self.stats['trades_lost']}")

        if self.stats['trades_won'] + self.stats['trades_lost'] > 0:
            wr = self.stats['trades_won'] / (self.stats['trades_won'] + self.stats['trades_lost']) * 100
            print(f"Win Rate: {wr:.1f}%")

        print("=" * 60)

        if self.mt5:
            self.mt5.disconnect()


def main():
    parser = argparse.ArgumentParser(description="SMC Trade Bot - Paul's Methodology")
    parser.add_argument('--test', action='store_true', help='Test mode (no real trades)')
    parser.add_argument('--debug', action='store_true', help='Debug output')
    parser.add_argument('--symbols', nargs='+', default=['EURUSD', 'GBPUSD'], help='Symbols')
    parser.add_argument('--htf', default='H1', help='Higher timeframe (H4, H1)')
    parser.add_argument('--ltf', default='M5', help='Lower timeframe (M5, M1)')
    parser.add_argument('--lot-size', type=float, default=0.04, help='Lot size')
    parser.add_argument('--login', type=int, required=True, help='MT5 account login')
    parser.add_argument('--password', type=str, required=True, help='MT5 account password')
    parser.add_argument('--server', type=str, required=True, help='MT5 server name')

    args = parser.parse_args()

    bot = SMCTradeBot(
        symbols=args.symbols,
        test_mode=args.test,
        debug=args.debug,
        lot_size=args.lot_size,
        htf=args.htf,
        ltf=args.ltf,
        login=args.login,
        password=args.password,
        server=args.server
    )

    bot.run()


if __name__ == '__main__':
    main()
