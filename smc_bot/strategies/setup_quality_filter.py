"""
Setup Quality Filter & Scoring System
Filters out weak SMC setups and scores setup quality

Quality Grades:
- A+ (90-100): Exceptional - take with full size
- A  (80-89):  Excellent - take with full size
- B  (70-79):  Good - take with reduced size
- C  (60-69):  Marginal - consider skipping
- D  (<60):    Weak - SKIP

Scoring Factors:
1. POI Quality (0-25 points)
2. Sweep Quality (0-20 points)
3. MSS Quality (0-20 points)
4. Entry Quality (0-15 points)
5. Context/Timing (0-20 points)
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SetupGrade(Enum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    SKIP = "SKIP"


@dataclass
class QualityScore:
    """Detailed quality score breakdown"""
    total_score: int
    grade: SetupGrade
    poi_score: int
    sweep_score: int
    mss_score: int
    entry_score: int
    context_score: int
    factors: List[str]
    warnings: List[str]
    recommendation: str

    def to_dict(self) -> Dict:
        return {
            'total_score': self.total_score,
            'grade': self.grade.value,
            'poi_score': self.poi_score,
            'sweep_score': self.sweep_score,
            'mss_score': self.mss_score,
            'entry_score': self.entry_score,
            'context_score': self.context_score,
            'factors': self.factors,
            'warnings': self.warnings,
            'recommendation': self.recommendation
        }


class SetupQualityFilter:
    """
    Scores and filters SMC trade setups

    Uses multiple factors to determine setup quality
    and whether to take the trade.
    """

    def __init__(self, min_score: int = 60, pip_value: float = 0.0001):
        self.min_score = min_score
        self.pip_value = pip_value

        # Configurable weights (out of 100 total)
        self.weights = {
            'poi': 25,
            'sweep': 20,
            'mss': 20,
            'entry': 15,
            'context': 20
        }

    def score_setup(
        self,
        poi_data: Dict,
        sweep_data: Dict,
        mss_data: Dict,
        entry_data: Dict,
        context_data: Dict
    ) -> QualityScore:
        """
        Score a complete trade setup

        Args:
            poi_data: POI quality information
            sweep_data: Liquidity sweep information
            mss_data: Market structure shift information
            entry_data: Entry quality information
            context_data: Market context information

        Returns:
            QualityScore with detailed breakdown
        """
        factors = []
        warnings = []

        # 1. Score POI Quality (0-25 points)
        poi_score, poi_factors, poi_warnings = self._score_poi(poi_data)
        factors.extend(poi_factors)
        warnings.extend(poi_warnings)

        # 2. Score Sweep Quality (0-20 points)
        sweep_score, sweep_factors, sweep_warnings = self._score_sweep(sweep_data)
        factors.extend(sweep_factors)
        warnings.extend(sweep_warnings)

        # 3. Score MSS Quality (0-20 points)
        mss_score, mss_factors, mss_warnings = self._score_mss(mss_data)
        factors.extend(mss_factors)
        warnings.extend(mss_warnings)

        # 4. Score Entry Quality (0-15 points)
        entry_score, entry_factors, entry_warnings = self._score_entry(entry_data)
        factors.extend(entry_factors)
        warnings.extend(entry_warnings)

        # 5. Score Context (0-20 points)
        context_score, context_factors, context_warnings = self._score_context(context_data)
        factors.extend(context_factors)
        warnings.extend(context_warnings)

        # Calculate total
        total_score = poi_score + sweep_score + mss_score + entry_score + context_score

        # Determine grade
        grade = self._get_grade(total_score)

        # Generate recommendation
        recommendation = self._get_recommendation(grade, total_score, warnings)

        return QualityScore(
            total_score=total_score,
            grade=grade,
            poi_score=poi_score,
            sweep_score=sweep_score,
            mss_score=mss_score,
            entry_score=entry_score,
            context_score=context_score,
            factors=factors,
            warnings=warnings,
            recommendation=recommendation
        )

    def _score_poi(self, poi_data: Dict) -> Tuple[int, List[str], List[str]]:
        """
        Score POI Quality (max 25 points)

        Factors:
        - POI type (equal highs/lows > session > swing)
        - POI strength (multiple touches)
        - POI age (recent > old)
        - HTF alignment
        """
        score = 0
        factors = []
        warnings = []

        poi_type = poi_data.get('type', '')
        strength = poi_data.get('strength', 1)
        age_hours = poi_data.get('age_hours', 0)
        htf_aligned = poi_data.get('htf_aligned', False)
        near_session_level = poi_data.get('near_session_level', False)

        # POI Type scoring (0-10)
        if 'equal' in poi_type:
            score += 10
            factors.append("Equal highs/lows (obvious liquidity)")
        elif 'session' in poi_type:
            score += 8
            factors.append("Session high/low")
        elif 'swing' in poi_type:
            score += 5
            factors.append("Swing point")
        else:
            score += 3
            warnings.append("Weak POI type")

        # Strength scoring (0-8)
        if strength >= 3:
            score += 8
            factors.append(f"Strong POI ({strength} touches)")
        elif strength >= 2:
            score += 5
            factors.append(f"POI tested {strength}x")
        else:
            score += 2
            warnings.append("Single-touch POI")

        # Age scoring (0-4) - fresher is better
        if age_hours <= 24:
            score += 4
            factors.append("Fresh POI (<24h)")
        elif age_hours <= 72:
            score += 2
        else:
            warnings.append("Old POI (>72h)")

        # HTF alignment bonus (0-3)
        if htf_aligned:
            score += 3
            factors.append("HTF aligned")

        return min(score, 25), factors, warnings

    def _score_sweep(self, sweep_data: Dict) -> Tuple[int, List[str], List[str]]:
        """
        Score Sweep Quality (max 20 points)

        Factors:
        - Sweep depth (how far beyond level)
        - Sweep rejection (wick vs body)
        - Close back inside (confirmation)
        - Volume on sweep
        """
        score = 0
        factors = []
        warnings = []

        sweep_pips = sweep_data.get('sweep_pips', 0)
        closed_back = sweep_data.get('closed_back', False)
        wick_ratio = sweep_data.get('wick_ratio', 0)  # Wick / total range
        high_volume = sweep_data.get('high_volume', False)

        # Sweep depth (0-6) - not too shallow, not too deep
        if 3 <= sweep_pips <= 15:
            score += 6
            factors.append(f"Clean sweep ({sweep_pips:.1f} pips)")
        elif sweep_pips > 15:
            score += 3
            warnings.append("Deep sweep (may continue)")
        elif sweep_pips > 0:
            score += 2
            warnings.append("Shallow sweep")
        else:
            warnings.append("No clear sweep")

        # Closed back inside (0-6) - critical
        if closed_back:
            score += 6
            factors.append("Closed back inside (trap confirmed)")
        else:
            warnings.append("No close back - sweep not confirmed")

        # Wick rejection (0-5) - long wick = strong rejection
        if wick_ratio >= 0.7:
            score += 5
            factors.append("Strong wick rejection")
        elif wick_ratio >= 0.5:
            score += 3
            factors.append("Good wick rejection")
        elif wick_ratio >= 0.3:
            score += 1
        else:
            warnings.append("Weak rejection (small wick)")

        # Volume confirmation (0-3)
        if high_volume:
            score += 3
            factors.append("High volume on sweep")

        return min(score, 20), factors, warnings

    def _score_mss(self, mss_data: Dict) -> Tuple[int, List[str], List[str]]:
        """
        Score MSS Quality (max 20 points)

        Factors:
        - Break clarity (clean vs marginal)
        - Momentum after break
        - Impulsive candle
        - Created imbalance
        """
        score = 0
        factors = []
        warnings = []

        break_pips = mss_data.get('break_pips', 0)
        impulsive = mss_data.get('impulsive_candle', False)
        created_imbalance = mss_data.get('created_imbalance', False)
        momentum_bars = mss_data.get('momentum_bars', 0)  # Bars continuing after break

        # Break clarity (0-8)
        if break_pips >= 5:
            score += 8
            factors.append(f"Clear MSS break ({break_pips:.1f} pips)")
        elif break_pips >= 3:
            score += 5
            factors.append("Decent MSS break")
        elif break_pips > 0:
            score += 2
            warnings.append("Marginal MSS break")
        else:
            warnings.append("No clear MSS")

        # Impulsive candle (0-5)
        if impulsive:
            score += 5
            factors.append("Impulsive MSS candle")
        else:
            score += 1

        # Created imbalance (0-4) - shows strong move
        if created_imbalance:
            score += 4
            factors.append("MSS created imbalance")

        # Momentum continuation (0-3)
        if momentum_bars >= 2:
            score += 3
            factors.append("MSS momentum confirmed")
        elif momentum_bars >= 1:
            score += 1

        return min(score, 20), factors, warnings

    def _score_entry(self, entry_data: Dict) -> Tuple[int, List[str], List[str]]:
        """
        Score Entry Quality (max 15 points)

        Factors:
        - Entry type (imbalance > OB > fib)
        - Entry precision (edge vs middle)
        - Risk:Reward potential
        - SL tightness
        """
        score = 0
        factors = []
        warnings = []

        entry_type = entry_data.get('entry_type', '')
        at_edge = entry_data.get('at_edge', False)
        risk_reward = entry_data.get('risk_reward', 0)
        sl_pips = entry_data.get('sl_pips', 0)

        # Entry type (0-5)
        if entry_type == 'imbalance':
            score += 5
            factors.append("Entry at imbalance")
        elif entry_type == 'order_block':
            score += 4
            factors.append("Entry at OB")
        elif entry_type == 'fib_50':
            score += 3
            factors.append("Entry at 50% fib")
        else:
            score += 1
            warnings.append("Non-optimal entry zone")

        # Entry precision (0-3)
        if at_edge:
            score += 3
            factors.append("Entry at zone edge (tight)")
        else:
            score += 1

        # Risk:Reward (0-5)
        if risk_reward >= 10:
            score += 5
            factors.append(f"Excellent R:R ({risk_reward:.1f})")
        elif risk_reward >= 5:
            score += 4
            factors.append(f"Great R:R ({risk_reward:.1f})")
        elif risk_reward >= 3:
            score += 3
            factors.append(f"Good R:R ({risk_reward:.1f})")
        else:
            score += 1
            warnings.append(f"Low R:R ({risk_reward:.1f})")

        # SL tightness (0-2) - tighter = better
        if sl_pips <= 10:
            score += 2
            factors.append(f"Tight SL ({sl_pips:.1f} pips)")
        elif sl_pips <= 20:
            score += 1
        else:
            warnings.append(f"Wide SL ({sl_pips:.1f} pips)")

        return min(score, 15), factors, warnings

    def _score_context(self, context_data: Dict) -> Tuple[int, List[str], List[str]]:
        """
        Score Market Context (max 20 points)

        Factors:
        - Session timing (London/NY overlap best)
        - Day of week (Tue-Thu best)
        - News proximity
        - HTF trend alignment
        - Recent volatility
        """
        score = 0
        factors = []
        warnings = []

        session = context_data.get('session', '')
        hour = context_data.get('hour', 12)
        day_of_week = context_data.get('day_of_week', 2)  # 0=Mon, 4=Fri
        near_news = context_data.get('near_news', False)
        htf_trend_aligned = context_data.get('htf_trend_aligned', False)
        volatility = context_data.get('volatility', 'normal')  # low, normal, high

        # Session timing (0-6)
        if 13 <= hour <= 16:  # London/NY overlap
            score += 6
            factors.append("London/NY overlap (best time)")
        elif 8 <= hour <= 16:  # London session
            score += 4
            factors.append("London session")
        elif 13 <= hour <= 21:  # NY session
            score += 4
            factors.append("NY session")
        elif 0 <= hour <= 8:  # Asian
            score += 2
            factors.append("Asian session (lower volatility)")
        else:
            score += 1
            warnings.append("Off-session timing")

        # Day of week (0-4)
        if day_of_week in [1, 2, 3]:  # Tue, Wed, Thu
            score += 4
            factors.append("Mid-week (best days)")
        elif day_of_week == 0:  # Monday
            score += 2
            warnings.append("Monday (watch for gaps)")
        elif day_of_week == 4:  # Friday
            score += 1
            warnings.append("Friday (reduced exposure)")
        else:
            warnings.append("Weekend/holiday")

        # News proximity (0-4)
        if near_news:
            score += 0
            warnings.append("Near high-impact news - CAUTION")
        else:
            score += 4
            factors.append("No nearby news")

        # HTF trend alignment (0-4)
        if htf_trend_aligned:
            score += 4
            factors.append("HTF trend aligned")
        else:
            score += 1
            warnings.append("Counter-trend setup")

        # Volatility (0-2)
        if volatility == 'normal':
            score += 2
        elif volatility == 'high':
            score += 1
            warnings.append("High volatility - wider SL may be needed")
        else:
            score += 0
            warnings.append("Low volatility - may not reach TP")

        return min(score, 20), factors, warnings

    def _get_grade(self, score: int) -> SetupGrade:
        """Convert score to grade"""
        if score >= 90:
            return SetupGrade.A_PLUS
        elif score >= 80:
            return SetupGrade.A
        elif score >= 70:
            return SetupGrade.B
        elif score >= 60:
            return SetupGrade.C
        elif score >= 50:
            return SetupGrade.D
        else:
            return SetupGrade.SKIP

    def _get_recommendation(self, grade: SetupGrade, score: int, warnings: List[str]) -> str:
        """Generate trade recommendation"""
        if grade == SetupGrade.A_PLUS:
            return "TAKE - Exceptional setup, full position size"
        elif grade == SetupGrade.A:
            return "TAKE - Excellent setup, full position size"
        elif grade == SetupGrade.B:
            return "TAKE - Good setup, consider 75% position size"
        elif grade == SetupGrade.C:
            if len(warnings) > 3:
                return "SKIP - Too many warnings despite passing score"
            return "CONSIDER - Marginal setup, 50% position size max"
        elif grade == SetupGrade.D:
            return "SKIP - Weak setup, wait for better opportunity"
        else:
            return "SKIP - Setup does not meet minimum criteria"

    def should_take_trade(self, quality_score: QualityScore) -> Tuple[bool, float]:
        """
        Determine if trade should be taken and position size multiplier

        Returns:
            (should_take, size_multiplier)
        """
        if quality_score.grade == SetupGrade.SKIP:
            return False, 0.0
        elif quality_score.grade == SetupGrade.D:
            return False, 0.0
        elif quality_score.grade == SetupGrade.C:
            # Only take C grades if no critical warnings
            critical_warnings = [w for w in quality_score.warnings if 'CAUTION' in w or 'No clear' in w]
            if critical_warnings:
                return False, 0.0
            return True, 0.5
        elif quality_score.grade == SetupGrade.B:
            return True, 0.75
        else:  # A or A+
            return True, 1.0

    def print_score_card(self, quality_score: QualityScore):
        """Print detailed score card"""
        print("\n" + "=" * 50)
        print(f" SETUP QUALITY SCORE: {quality_score.total_score}/100 ({quality_score.grade.value})")
        print("=" * 50)

        print(f"\nBreakdown:")
        print(f"  POI Quality:    {quality_score.poi_score}/25")
        print(f"  Sweep Quality:  {quality_score.sweep_score}/20")
        print(f"  MSS Quality:    {quality_score.mss_score}/20")
        print(f"  Entry Quality:  {quality_score.entry_score}/15")
        print(f"  Context:        {quality_score.context_score}/20")

        if quality_score.factors:
            print(f"\n[+] Positive Factors:")
            for f in quality_score.factors:
                print(f"    + {f}")

        if quality_score.warnings:
            print(f"\n[!] Warnings:")
            for w in quality_score.warnings:
                print(f"    ! {w}")

        print(f"\nRecommendation: {quality_score.recommendation}")
        print("=" * 50)


def create_poi_data(
    poi_type: str,
    strength: int = 1,
    age_hours: float = 12,
    htf_aligned: bool = False,
    near_session_level: bool = False
) -> Dict:
    """Helper to create POI data dict"""
    return {
        'type': poi_type,
        'strength': strength,
        'age_hours': age_hours,
        'htf_aligned': htf_aligned,
        'near_session_level': near_session_level
    }


def create_sweep_data(
    sweep_pips: float,
    closed_back: bool = True,
    wick_ratio: float = 0.5,
    high_volume: bool = False
) -> Dict:
    """Helper to create sweep data dict"""
    return {
        'sweep_pips': sweep_pips,
        'closed_back': closed_back,
        'wick_ratio': wick_ratio,
        'high_volume': high_volume
    }


def create_mss_data(
    break_pips: float,
    impulsive_candle: bool = False,
    created_imbalance: bool = False,
    momentum_bars: int = 0
) -> Dict:
    """Helper to create MSS data dict"""
    return {
        'break_pips': break_pips,
        'impulsive_candle': impulsive_candle,
        'created_imbalance': created_imbalance,
        'momentum_bars': momentum_bars
    }


def create_entry_data(
    entry_type: str,
    at_edge: bool = True,
    risk_reward: float = 3.0,
    sl_pips: float = 10.0
) -> Dict:
    """Helper to create entry data dict"""
    return {
        'entry_type': entry_type,
        'at_edge': at_edge,
        'risk_reward': risk_reward,
        'sl_pips': sl_pips
    }


def create_context_data(
    hour: int = 14,
    day_of_week: int = 2,
    near_news: bool = False,
    htf_trend_aligned: bool = True,
    volatility: str = 'normal'
) -> Dict:
    """Helper to create context data dict"""
    return {
        'hour': hour,
        'day_of_week': day_of_week,
        'near_news': near_news,
        'htf_trend_aligned': htf_trend_aligned,
        'volatility': volatility
    }
