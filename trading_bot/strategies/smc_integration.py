"""
SMC Integration Module
Bridges SMC (Smart Money Concepts) analysis with existing confluence strategy

This module allows the existing confluence strategy to optionally use
SMC Order Block analysis for enhanced signal quality filtering.

Usage:
    # In confluence_strategy.py
    from strategies.smc_integration import SMCIntegration

    smc = SMCIntegration(symbol='EURUSD')
    smc_signal = smc.check_smc_confluence(h4_data, h1_data, m15_data, m5_data, price)

    if smc_signal['smc_confirmed']:
        # Signal is confirmed by SMC analysis
        signal['confluence_score'] += smc_signal['smc_score']
"""

import pandas as pd
from typing import Dict, Optional, List
from datetime import datetime

from strategies.smc_analyzer import SMCMultiTimeframeAnalyzer, Direction
from strategies.smc_entry_strategy import SMCEntryStrategy
from indicators.smc_indicators import SMCIndicators
from config.smc_config import (
    MIN_SMC_CONFLUENCE_SCORE,
    SMC_CONFLUENCE_WEIGHTS,
    M15_OB_REQUIRED,
    LIQUIDITY_SWEEP_REQUIRED,
    SMC_DEBUG
)


class SMCIntegration:
    """
    SMC Integration for existing confluence strategy

    Provides methods to:
    1. Check if current price is in an SMC confluence zone
    2. Add SMC factors to existing confluence scoring
    3. Filter signals based on SMC analysis
    """

    def __init__(self, symbol: str = "EURUSD", pip_value: float = 0.0001):
        """
        Initialize SMC Integration

        Args:
            symbol: Trading symbol
            pip_value: Pip value for the symbol
        """
        self.symbol = symbol
        self.pip_value = pip_value

        # Initialize analyzers
        self.analyzer = SMCMultiTimeframeAnalyzer(symbol=symbol, pip_value=pip_value)
        self.entry_strategy = SMCEntryStrategy(symbol=symbol, pip_value=pip_value)

        # Cache last analysis
        self.last_analysis: Dict = {}
        self.last_analysis_time: Optional[datetime] = None

        # Cache TTL in seconds
        self.cache_ttl = 60

    def check_smc_confluence(
        self,
        h4_data: pd.DataFrame,
        h1_data: pd.DataFrame,
        m15_data: pd.DataFrame,
        m5_data: Optional[pd.DataFrame],
        current_price: float,
        intended_direction: Optional[str] = None
    ) -> Dict:
        """
        Check SMC confluence for current price

        Args:
            h4_data: H4 OHLCV data
            h1_data: H1 OHLCV data
            m15_data: M15 OHLCV data
            m5_data: M5 OHLCV data (optional)
            current_price: Current market price
            intended_direction: 'buy' or 'sell' (to check alignment)

        Returns:
            Dict with SMC analysis results and score
        """
        result = {
            'smc_confirmed': False,
            'smc_score': 0,
            'smc_factors': [],
            'confluence_zone': None,
            'market_structure': {},
            'liquidity_swept': False,
            'm15_zone_valid': True,
            'direction_aligned': True,
            'reasons': []
        }

        # Check cache
        now = datetime.now()
        if (self.last_analysis_time and
            (now - self.last_analysis_time).total_seconds() < self.cache_ttl):
            return self._process_cached_analysis(current_price, intended_direction)

        # Run full analysis
        try:
            analysis = self.analyzer.analyze_all_timeframes(
                h4_data=h4_data,
                h1_data=h1_data,
                m15_data=m15_data,
                m5_data=m5_data
            )
            self.last_analysis = analysis
            self.last_analysis_time = now
        except Exception as e:
            if SMC_DEBUG:
                print(f"[SMC Integration] Analysis error: {e}")
            result['reasons'].append(f"Analysis error: {str(e)}")
            return result

        return self._process_analysis(analysis, current_price, intended_direction)

    def _process_analysis(
        self,
        analysis: Dict,
        current_price: float,
        intended_direction: Optional[str]
    ) -> Dict:
        """Process analysis results"""
        result = {
            'smc_confirmed': False,
            'smc_score': 0,
            'smc_factors': [],
            'confluence_zone': None,
            'market_structure': {},
            'liquidity_swept': False,
            'm15_zone_valid': True,
            'direction_aligned': True,
            'reasons': []
        }

        # Extract market structure
        result['market_structure'] = {
            'h4_trend': analysis.get('h4_analysis', {}).get('current_trend', 'unknown'),
            'h1_trend': analysis.get('h1_analysis', {}).get('current_trend', 'unknown'),
            'm15_trend': analysis.get('m15_analysis', {}).get('current_trend', 'unknown')
        }

        # Check M15 zone validity
        if analysis.get('m15_cooldown_active', False):
            result['m15_zone_valid'] = False
            result['reasons'].append("M15 zone breached - cooldown active")
            return result

        # Check if price is in a confluence zone
        valid_zones = analysis.get('valid_confluence_zones', [])

        matching_zone = None
        for zone in valid_zones:
            if zone['bottom'] <= current_price <= zone['top']:
                matching_zone = zone
                break

        if not matching_zone:
            result['reasons'].append("Price not in confluence zone")
            return result

        result['confluence_zone'] = matching_zone

        # Check direction alignment
        zone_direction = matching_zone['direction']
        if intended_direction:
            direction_map = {'buy': 'bullish', 'sell': 'bearish'}
            if direction_map.get(intended_direction) != zone_direction:
                result['direction_aligned'] = False
                result['reasons'].append(f"Direction mismatch: signal={intended_direction}, zone={zone_direction}")

        # Check liquidity sweep
        result['liquidity_swept'] = matching_zone.get('liquidity_swept', False) or len(analysis.get('recent_sweeps', [])) > 0

        if LIQUIDITY_SWEEP_REQUIRED and not result['liquidity_swept']:
            result['reasons'].append("No liquidity sweep detected")

        # Calculate SMC score
        smc_score = 0

        # Timeframe confluence
        timeframes = matching_zone.get('timeframes', [])
        if 'H4' in timeframes:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('h4_ob', 4)
            result['smc_factors'].append('H4 Order Block')
        if 'H1' in timeframes:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('h1_ob', 3)
            result['smc_factors'].append('H1 Order Block')
        if 'M15' in timeframes:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('m15_ob', 2)
            result['smc_factors'].append('M15 Order Block')

        # M15 required check
        if M15_OB_REQUIRED and 'M15' not in timeframes:
            result['reasons'].append("M15 OB required but not present")

        # Liquidity sweep bonus
        if result['liquidity_swept']:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('liquidity_sweep', 4)
            result['smc_factors'].append('Liquidity Swept')

        # BOS/ChoCH bonuses
        h4_breaks = analysis.get('h4_analysis', {}).get('counts', {}).get('structure_breaks', 0)
        h1_breaks = analysis.get('h1_analysis', {}).get('counts', {}).get('structure_breaks', 0)
        m15_breaks = analysis.get('m15_analysis', {}).get('counts', {}).get('structure_breaks', 0)

        if h4_breaks > 0:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('h4_bos', 3)
            result['smc_factors'].append('H4 BOS')
        if h1_breaks > 0:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('h1_bos', 2)
            result['smc_factors'].append('H1 BOS')
        if m15_breaks > 0:
            smc_score += SMC_CONFLUENCE_WEIGHTS.get('m15_bos', 2)
            result['smc_factors'].append('M15 BOS')

        result['smc_score'] = smc_score

        # Determine if SMC confirmed
        min_conditions = [
            len(timeframes) >= 2,  # At least 2 timeframe confluence
            result['m15_zone_valid'],  # M15 zone not breached
            result['direction_aligned'],  # Direction matches
        ]

        if LIQUIDITY_SWEEP_REQUIRED:
            min_conditions.append(result['liquidity_swept'])

        if M15_OB_REQUIRED:
            min_conditions.append('M15' in timeframes)

        result['smc_confirmed'] = all(min_conditions) and smc_score >= MIN_SMC_CONFLUENCE_SCORE

        return result

    def _process_cached_analysis(
        self,
        current_price: float,
        intended_direction: Optional[str]
    ) -> Dict:
        """Process cached analysis with new price"""
        if not self.last_analysis:
            return {
                'smc_confirmed': False,
                'smc_score': 0,
                'smc_factors': [],
                'confluence_zone': None,
                'market_structure': {},
                'liquidity_swept': False,
                'm15_zone_valid': True,
                'direction_aligned': True,
                'reasons': ['No cached analysis available']
            }

        return self._process_analysis(self.last_analysis, current_price, intended_direction)

    def get_smc_levels(self, h4_data: pd.DataFrame, h1_data: pd.DataFrame, m15_data: pd.DataFrame) -> Dict:
        """
        Get SMC levels (Order Blocks, FVGs, Liquidity) for charting/display

        Returns:
            Dict with all SMC levels organized by type and timeframe
        """
        levels = {
            'order_blocks': {
                'H4': [],
                'H1': [],
                'M15': []
            },
            'fair_value_gaps': {
                'H4': [],
                'H1': [],
                'M15': []
            },
            'liquidity_pools': {
                'H4': [],
                'H1': [],
                'M15': []
            },
            'swing_levels': {
                'H4': {'highs': [], 'lows': []},
                'H1': {'highs': [], 'lows': []},
                'M15': {'highs': [], 'lows': []}
            }
        }

        # Analyze each timeframe
        h4_smc = SMCIndicators(timeframe='H4', pip_value=self.pip_value)
        h1_smc = SMCIndicators(timeframe='H1', pip_value=self.pip_value)
        m15_smc = SMCIndicators(timeframe='M15', pip_value=self.pip_value)

        # H4 Analysis
        h4_analysis = h4_smc.analyze(h4_data)
        levels['order_blocks']['H4'] = [
            {'top': ob['top'], 'bottom': ob['bottom'], 'direction': ob['direction'], 'mitigated': ob['mitigated']}
            for ob in h4_analysis.get('order_blocks', [])
        ]
        levels['fair_value_gaps']['H4'] = [
            {'top': fvg['top'], 'bottom': fvg['bottom'], 'direction': fvg['direction']}
            for fvg in h4_analysis.get('active_fvgs', [])
        ]
        levels['swing_levels']['H4']['highs'] = [sh['price'] for sh in h4_analysis.get('swing_highs', [])]
        levels['swing_levels']['H4']['lows'] = [sl['price'] for sl in h4_analysis.get('swing_lows', [])]

        # H1 Analysis
        h1_analysis = h1_smc.analyze(h1_data)
        levels['order_blocks']['H1'] = [
            {'top': ob['top'], 'bottom': ob['bottom'], 'direction': ob['direction'], 'mitigated': ob['mitigated']}
            for ob in h1_analysis.get('order_blocks', [])
        ]
        levels['fair_value_gaps']['H1'] = [
            {'top': fvg['top'], 'bottom': fvg['bottom'], 'direction': fvg['direction']}
            for fvg in h1_analysis.get('active_fvgs', [])
        ]
        levels['swing_levels']['H1']['highs'] = [sh['price'] for sh in h1_analysis.get('swing_highs', [])]
        levels['swing_levels']['H1']['lows'] = [sl['price'] for sl in h1_analysis.get('swing_lows', [])]

        # M15 Analysis
        m15_analysis = m15_smc.analyze(m15_data)
        levels['order_blocks']['M15'] = [
            {'top': ob['top'], 'bottom': ob['bottom'], 'direction': ob['direction'], 'mitigated': ob['mitigated']}
            for ob in m15_analysis.get('order_blocks', [])
        ]
        levels['fair_value_gaps']['M15'] = [
            {'top': fvg['top'], 'bottom': fvg['bottom'], 'direction': fvg['direction']}
            for fvg in m15_analysis.get('active_fvgs', [])
        ]
        levels['swing_levels']['M15']['highs'] = [sh['price'] for sh in m15_analysis.get('swing_highs', [])]
        levels['swing_levels']['M15']['lows'] = [sl['price'] for sl in m15_analysis.get('swing_lows', [])]

        return levels

    def filter_signal_by_smc(
        self,
        signal: Dict,
        h4_data: pd.DataFrame,
        h1_data: pd.DataFrame,
        m15_data: pd.DataFrame,
        m5_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Filter an existing signal using SMC analysis

        Args:
            signal: Original signal dict from SignalDetector
            h4_data, h1_data, m15_data, m5_data: OHLCV data

        Returns:
            Modified signal dict with SMC filtering applied
        """
        if not signal or not signal.get('should_trade'):
            return signal

        price = signal['price']
        direction = signal['direction']

        # Get SMC confirmation
        smc_result = self.check_smc_confluence(
            h4_data=h4_data,
            h1_data=h1_data,
            m15_data=m15_data,
            m5_data=m5_data,
            current_price=price,
            intended_direction=direction
        )

        # Add SMC info to signal
        signal['smc_analysis'] = smc_result

        # If SMC confirmed, boost confluence score
        if smc_result['smc_confirmed']:
            signal['confluence_score'] += smc_result['smc_score']
            signal['factors'].extend(smc_result['smc_factors'])

        # If M15 zone breached, reject signal
        elif not smc_result['m15_zone_valid']:
            signal['should_trade'] = False
            signal['reject_reason'] = "M15 zone breached - SMC cooldown"

        # If direction misaligned with SMC zone, add warning
        elif not smc_result['direction_aligned']:
            signal['warnings'] = signal.get('warnings', [])
            signal['warnings'].append("Signal direction conflicts with SMC zone")

        return signal

    def get_analysis_summary(self) -> str:
        """Get human-readable analysis summary"""
        if not self.last_analysis:
            return "No analysis performed yet"

        summary = self.last_analysis.get('summary', {})

        lines = [
            f"SMC Analysis for {self.symbol}",
            "-" * 40,
            f"H4 Trend: {summary.get('h4_trend', 'unknown').upper()}",
            f"H1 Trend: {summary.get('h1_trend', 'unknown').upper()}",
            f"M15 Trend: {summary.get('m15_trend', 'unknown').upper()}",
            "",
            f"Confluence Zones: {summary.get('valid_confluence_zones', 0)}",
            f"  Bullish: {summary.get('bullish_zones', 0)}",
            f"  Bearish: {summary.get('bearish_zones', 0)}",
            "",
            f"Liquidity Sweeps: {summary.get('liquidity_sweeps', 0)}"
        ]

        return "\n".join(lines)
