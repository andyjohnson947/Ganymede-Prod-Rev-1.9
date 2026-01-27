# Ryuryu's FOREX MT5 EURUSD Bot

**Only Shorts** (Production Mode #6973)

A MetaTrader 5 trading bot for EURUSD that only takes short positions based on SMA (Simple Moving Average) indicators.

## Credits

- (c) 2023 Ryan Hayabusa
- GitHub: https://github.com/ryu878
- Web: https://aadresearch.xyz
- Discord: https://discord.gg/zSw58e9Uvf
- Telegram: https://t.me/aadresearch

## Requirements

- Python 3.8+
- MetaTrader 5 terminal installed and running
- Windows OS (MT5 Python API only works on Windows)

## Installation

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

Or install manually:

```bash
pip install MetaTrader5 pandas ta
```

2. Make sure MetaTrader 5 is installed and running on your system.

3. Configure your account settings in the script:
   - `magic` - Magic number for order identification
   - `account_id` - Your MT5 account ID

## Configuration

Edit the following parameters in `eurusd_short_bot.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `magic` | 12345678 | Magic number for order identification |
| `account_id` | 1234567890 | Your MT5 account ID |
| `symbol` | EURUSD | Trading symbol |
| `lot` | 0.1 | Initial lot size |
| `add_lot` | 0.01 | Additional lot size for averaging |
| `take_profit_short` | 21 | Take profit in points |
| `sl_multiplier` | 13 | Stop loss multiplier (SL = TP * multiplier) |

## Strategy Overview

The bot uses multiple SMA indicators on the M1 timeframe:
- SMA 6 (High)
- SMA 6 (Low)
- SMA 33
- SMA 60
- SMA 120
- SMA 240

### Entry Conditions

**First Entry (Short):**
- No existing position
- Ask price > SMA 6H (price above short-term high SMA)

**Additional Entry:**
- Existing position open
- Ask price > SMA 6H
- SMA 6L > position open price (for averaging down)

## Usage

Run the bot:

```bash
python eurusd_short_bot.py
```

## Risk Warning

Trading forex carries significant risk. This bot is provided for educational purposes. Always test on a demo account first and never risk more than you can afford to lose.
