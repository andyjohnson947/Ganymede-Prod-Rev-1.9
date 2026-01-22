# Adaptive Confluence Weighting - Integration Guide

## What This Does

The adaptive confluence system **learns from your trades** to:

1. **Rate individual factors** (vwap_band_1, poc, swing_low, etc.) by actual performance
2. **Discover winning patterns** (factor combinations that work together)
3. **Categorize setups** (EXCELLENT → VERY_GOOD → GOOD → MEDIUM → POOR)
4. **Recommend optimal weights** based on what actually wins
5. **Score trades before entry** (0-100 quality score)

## Current Static Weights (strategy_config.py)

```python
CONFLUENCE_WEIGHTS = {
    'vwap_band_1': 1,
    'vwap_band_2': 1,
    'poc': 1,
    'swing_low': 1,
    'swing_high': 1,
    # ... all set to 1 or 2 or 3 manually
}
```

**Problem**: These are guesses. We don't know which factors actually win.

## Adaptive System Output

After 50+ trades, the system will output:

```python
OPTIMAL_WEIGHTS = {
    'daily_hvn': 5,           # 87.5% win rate, $3.45 avg profit → weight 5
    'vwap_band_2': 4,         # 78.2% win rate, $2.10 avg profit → weight 4
    'poc': 4,                 # 76.5% win rate, $2.34 avg profit → weight 4
    'swing_low': 3,           # 68.3% win rate, $1.20 avg profit → weight 3
    'vwap_band_1': 2,         # 55.1% win rate, $0.45 avg profit → weight 2
    'lvn': 1,                 # 48.2% win rate, $-0.30 avg profit → weight 1
}
```

And **winning patterns**:

```python
EXCELLENT_PATTERNS = [
    {
        'factors': ['daily_hvn', 'poc', 'vwap_band_2'],
        'win_rate': 85.7%,
        'avg_profit': $4.20,
        'trades': 14
    },
    {
        'factors': ['weekly_poc', 'daily_poc', 'swing_low'],
        'win_rate': 82.4%,
        'avg_profit': $3.80,
        'trades': 17
    }
]
```

## Integration Steps

### Step 1: Log Confluence Factors (5 minutes)

In `confluence_strategy.py`, when logging a trade, add the factors:

```python
# When signal is generated
signal = {
    'symbol': symbol,
    'confluence_score': 12,
    'confluence_factors': [
        'vwap_band_2',
        'poc',
        'swing_low',
        'daily_hvn',
        'weekly_poc'
    ],
    # ... rest of signal data
}

# Log to enhanced logger
self.ml_logger.log_trade_with_execution({
    'ticket': ticket,
    'confluence_factors': signal['confluence_factors'],  # <- ADD THIS
    'confluence_score': signal['confluence_score'],
    # ... rest of trade data
})
```

### Step 2: Score Setups Before Entry (10 minutes)

Before placing trade, score it:

```python
from ml_system.adaptive_confluence_weighting import AdaptiveConfluenceWeighting

# Initialize once
self.confluence_analyzer = AdaptiveConfluenceWeighting()

# Before placing trade
setup_quality = self.confluence_analyzer.categorize_setup_quality(
    confluence_factors=signal['confluence_factors']
)

print(f"Setup Quality: {setup_quality['quality_tier']}")
print(f"Score: {setup_quality['score']}/100")
print(f"Win Probability: {setup_quality['win_probability']}%")
print(f"Expected Profit: ${setup_quality['expected_profit']}")
print(f"Recommendation: {setup_quality['recommendation']}")

# Filter trades by quality
if setup_quality['quality_tier'] in ['POOR', 'UNKNOWN']:
    print(f"[SKIP] Setup quality {setup_quality['quality_tier']} - skipping trade")
    return

# Adjust position size by quality
if setup_quality['quality_tier'] == 'EXCELLENT':
    volume = BASE_LOT_SIZE * 1.5  # Increase size for excellent setups
elif setup_quality['quality_tier'] == 'MEDIUM':
    volume = BASE_LOT_SIZE * 0.5  # Reduce size for medium setups
else:
    volume = BASE_LOT_SIZE
```

### Step 3: Update Weights Periodically (automated)

Run analysis weekly:

```python
# In a weekly maintenance script or background task
analyzer = AdaptiveConfluenceWeighting()
report = analyzer.generate_report()

# Get optimal weights
optimal_weights = report['optimal_weights']

# Compare with current
from config.strategy_config import CONFLUENCE_WEIGHTS
comparison = analyzer.compare_with_current_weights(CONFLUENCE_WEIGHTS)

# Flag changes needed
for factor, data in comparison.items():
    if data['status'] == 'INCREASE':
        print(f"⬆️  {factor}: {data['current_weight']} → {data['optimal_weight']} "
              f"(importance: {data['importance_score']:.1f})")
    elif data['status'] == 'DECREASE':
        print(f"⬇️  {factor}: {data['current_weight']} → {data['optimal_weight']} "
              f"(importance: {data['importance_score']:.1f})")
```

## Example Output After 100 Trades

```
====================================================================================================
ADAPTIVE CONFLUENCE WEIGHTING ANALYSIS
====================================================================================================

Trades analyzed: 100
Factors analyzed: 18
Patterns identified: 45

====================================================================================================
TOP 10 INDIVIDUAL CONFLUENCE FACTORS (By Importance)
====================================================================================================
Factor                          Trades    Win%     Avg$   Score  Weight
----------------------------------------------------------------------------------------------------
daily_hvn                           23    87.0     3.45    90.2       5
weekly_poc                          18    84.2     3.10    87.8       5
poc                                 42    78.5     2.34    82.1       4
vwap_band_2                         38    76.3     2.10    79.9       4
daily_poc                           31    74.2     1.95    77.6       4
swing_low                           45    68.3     1.20    70.4       3
vwap_band_1                         52    62.5     0.85    64.8       3
swing_high                          41    58.5     0.45    59.1       3
lvn                                 28    52.1     0.15    52.4       2
above_vah                           19    48.2    -0.30    46.9       2

====================================================================================================
TOP 10 CONFLUENCE PATTERNS (By Pattern Strength)
====================================================================================================

1. EXCELLENT (Score: 92.5)
   Factors: daily_hvn + poc + vwap_band_2
   Performance: 14 trades, 85.7% WR, $4.20 avg
   Recommendation: TAKE_FULL_SIZE

2. EXCELLENT (Score: 90.1)
   Factors: weekly_poc + daily_poc + swing_low
   Performance: 17 trades, 82.4% WR, $3.80 avg
   Recommendation: TAKE_FULL_SIZE

3. VERY_GOOD (Score: 85.3)
   Factors: poc + vwap_band_2 + swing_low + daily_hvn
   Performance: 12 trades, 80.0% WR, $3.20 avg
   Recommendation: TAKE_FULL_SIZE

4. VERY_GOOD (Score: 82.7)
   Factors: daily_poc + weekly_hvn + poc
   Performance: 9 trades, 77.8% WR, $2.90 avg
   Recommendation: TAKE_FULL_SIZE

5. GOOD (Score: 75.4)
   Factors: vwap_band_2 + poc + swing_low
   Performance: 23 trades, 69.6% WR, $1.80 avg
   Recommendation: TAKE_NORMAL_SIZE

====================================================================================================
PATTERN QUALITY DISTRIBUTION
====================================================================================================
EXCELLENT     8 patterns | Avg: 83.5% WR, $3.85 profit
VERY_GOOD    12 patterns | Avg: 75.2% WR, $2.40 profit
GOOD         18 patterns | Avg: 65.8% WR, $1.20 profit
POOR          7 patterns | Avg: 45.3% WR, $-0.80 profit
```

## Key Insights From Adaptive System

### 1. Individual Factor Performance

**Strong Performers** (High importance score):
- HTF levels (daily_hvn, weekly_poc) outperform
- These should get weight 4-5

**Weak Performers** (Low importance score):
- Some M15 levels underperform
- These should get weight 1-2

### 2. Winning Combinations

**Pattern Discovery**:
- HTF + HTF + M15 = Excellent (multiple timeframe alignment)
- POC + VWAP Band = Strong reversal signals
- Single factor signals = Poor quality

**Pattern Avoidance**:
- LVN alone = Poor outcomes
- VWAP Band 1 without confluence = Weak

### 3. Setup Quality Categorization

**EXCELLENT** (85%+ WR, $3+ avg):
- Take full size (1.5x if aggressive)
- Highest confidence
- Multiple HTF factors aligned

**VERY_GOOD** (75%+ WR, $2+ avg):
- Take full size
- High confidence
- Good HTF alignment

**GOOD** (60-75% WR, $1+ avg):
- Take normal size
- Moderate confidence
- Decent setup

**MEDIUM** (50-60% WR, $0-1 avg):
- Take reduced size (0.5x)
- Low confidence
- Marginal setup

**POOR** (<50% WR, negative avg):
- **SKIP**
- Historical data says this pattern loses

## Benefits

### Short Term (After 50 trades)

✅ **Filter bad setups** - Skip patterns that historically lose
✅ **Identify best patterns** - Focus on what works
✅ **Size positions appropriately** - More on good setups, less on marginal

### Medium Term (After 100 trades)

✅ **Optimize weights** - Replace manual guesses with data
✅ **Discover non-obvious patterns** - ML finds combinations you'd miss
✅ **Adapt to changing markets** - Weights update as market behavior shifts

### Long Term (After 200+ trades)

✅ **Full autonomy** - System recommends all parameter changes
✅ **Self-optimization** - Continuously improves based on outcomes
✅ **Market regime adaptation** - Different weights for different conditions

## Implementation Timeline

**Week 1**: Integrate logging of confluence_factors (5 min)
**Week 2-4**: Collect 50+ trades with factor data
**Week 5**: Run first analysis, get initial insights
**Week 6-8**: Collect 100 trades
**Week 9**: Implement weight adjustments based on data
**Week 10+**: Automated continuous optimization

## Advanced: Dynamic Weighting

Once you have 100+ trades, implement dynamic weight selection:

```python
def get_confluence_weights(self, current_adx, current_hour):
    """
    Get optimal weights based on current market conditions

    Different weights for:
    - Trending vs ranging (ADX-based)
    - Session (Tokyo vs London vs NY)
    - Time of day
    """
    if current_adx > 30:
        # Trending market - use trend-following factors
        return self.trending_weights
    else:
        # Ranging market - use mean reversion factors
        return self.ranging_weights
```

This allows **context-aware confluence scoring** where the same factors are weighted differently based on market regime.

## Summary

Your idea of **adaptive confluence weighting** transforms the system from:

**Before**: Manual weights → Static scoring → Same for all conditions
**After**: ML-learned weights → Dynamic scoring → Adapts to conditions

The system will tell you:
- ✅ Which individual factors actually work
- ✅ Which combinations win consistently
- ✅ What quality each setup is BEFORE you trade
- ✅ How to adjust weights based on evidence

This is **Phase 3** of the ML enhancement plan and will dramatically improve setup selection once you have 50-100 trades logged with confluence_factors data.
