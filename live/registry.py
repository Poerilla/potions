from __future__ import annotations

from typing import Dict, Type

from .models import StrategyInstance
from .store import FlatFileStore
from .strategies import (
    AtrSupertrendDcaStrategy,
    HourlyStDaybiasDcaStrategy,
    HourlyStPmcBreakPrevTrailStrategy,
    HourlyStPmcCausalRevivalStrategy,
    HourlyStPmcRetestStrategy,
    IntradayStDcaStrategy,
    IntradayStFadeDcaStrategy,
    MondayOrBreakoutStrategy,
    MonthlyOpenAtrExtensionBandStrategy,
    MonthlyOpenLiqRunFadeStrategy,
    MonthlyOpenLiqRunFade2cHalfOpenStrategy,
    MonthlyOpenLiqRangeBreakoutStrategy,
    MonthlyOrbOverlapStRetestStrategy,
    MonthlyOrbRestrictedScaleout3Strategy,
    MonthlyOrbV2bOcoStrategy,
    Or2RFadeStrategy,
    NyLiquidityGrabStrategy,
    PeriodicDcaStrategy,
    FirstHourFollowStrategy,
    FailureFadeStrategy,
    PhantomExitFadeStrategy,
    Q1FakeoutReversalStrategy,
    QuarterlyAtr4FadeStrategy,
    QuarterlyAtr4FadeLadderStrategy,
    QuarterlyRangeBreakoutStrategy,
    StrategyPlugin,

    SupertrendWickRetestStrategy,
    TrendMomentumStrategy,
    StructureProgramStStrategy,
    V2BCleanBreakStrategy,
    V2BNqLeadNas100Strategy,
    V2BOrCloseSwingStrategy,
    V2BScaleoutStrategy,
    V2DFadeStrategy,
    WeeklyMidMa500BiasStrategy,
    WeeklyOpenDayBreakoutStrategy,
    WoGapReversalStrategy,
    YearlyAtr4FadeStrategy,
    YearlyOrbScaleout3Strategy,
)


class StrategyRegistry:
    def __init__(self) -> None:
        self._types: Dict[str, Type[StrategyPlugin]] = {
            AtrSupertrendDcaStrategy.strategy_type: AtrSupertrendDcaStrategy,
            HourlyStDaybiasDcaStrategy.strategy_type: HourlyStDaybiasDcaStrategy,
            HourlyStPmcBreakPrevTrailStrategy.strategy_type: HourlyStPmcBreakPrevTrailStrategy,
            HourlyStPmcCausalRevivalStrategy.strategy_type: HourlyStPmcCausalRevivalStrategy,
            HourlyStPmcRetestStrategy.strategy_type: HourlyStPmcRetestStrategy,
            IntradayStDcaStrategy.strategy_type: IntradayStDcaStrategy,
            IntradayStFadeDcaStrategy.strategy_type: IntradayStFadeDcaStrategy,
            MondayOrBreakoutStrategy.strategy_type: MondayOrBreakoutStrategy,
            MonthlyOpenAtrExtensionBandStrategy.strategy_type: MonthlyOpenAtrExtensionBandStrategy,
            MonthlyOpenLiqRunFadeStrategy.strategy_type: MonthlyOpenLiqRunFadeStrategy,
            MonthlyOpenLiqRunFade2cHalfOpenStrategy.strategy_type: MonthlyOpenLiqRunFade2cHalfOpenStrategy,
            MonthlyOpenLiqRangeBreakoutStrategy.strategy_type: MonthlyOpenLiqRangeBreakoutStrategy,
            MonthlyOrbOverlapStRetestStrategy.strategy_type: MonthlyOrbOverlapStRetestStrategy,
            MonthlyOrbRestrictedScaleout3Strategy.strategy_type: MonthlyOrbRestrictedScaleout3Strategy,
            MonthlyOrbV2bOcoStrategy.strategy_type: MonthlyOrbV2bOcoStrategy,
            Or2RFadeStrategy.strategy_type: Or2RFadeStrategy,
            NyLiquidityGrabStrategy.strategy_type: NyLiquidityGrabStrategy,
            PeriodicDcaStrategy.strategy_type: PeriodicDcaStrategy,
            FirstHourFollowStrategy.strategy_type: FirstHourFollowStrategy,
            FailureFadeStrategy.strategy_type: FailureFadeStrategy,
            Q1FakeoutReversalStrategy.strategy_type: Q1FakeoutReversalStrategy,
            QuarterlyAtr4FadeStrategy.strategy_type: QuarterlyAtr4FadeStrategy,
            QuarterlyAtr4FadeLadderStrategy.strategy_type: QuarterlyAtr4FadeLadderStrategy,
            QuarterlyRangeBreakoutStrategy.strategy_type: QuarterlyRangeBreakoutStrategy,
            PhantomExitFadeStrategy.strategy_type: PhantomExitFadeStrategy,
            SupertrendWickRetestStrategy.strategy_type: SupertrendWickRetestStrategy,
            TrendMomentumStrategy.strategy_type: TrendMomentumStrategy,
            StructureProgramStStrategy.strategy_type: StructureProgramStStrategy,
            V2BCleanBreakStrategy.strategy_type: V2BCleanBreakStrategy,
            V2BNqLeadNas100Strategy.strategy_type: V2BNqLeadNas100Strategy,
            V2BOrCloseSwingStrategy.strategy_type: V2BOrCloseSwingStrategy,
            V2BScaleoutStrategy.strategy_type: V2BScaleoutStrategy,
            V2DFadeStrategy.strategy_type: V2DFadeStrategy,
            WeeklyMidMa500BiasStrategy.strategy_type: WeeklyMidMa500BiasStrategy,
            WeeklyOpenDayBreakoutStrategy.strategy_type: WeeklyOpenDayBreakoutStrategy,
            WoGapReversalStrategy.strategy_type: WoGapReversalStrategy,
            YearlyAtr4FadeStrategy.strategy_type: YearlyAtr4FadeStrategy,
            YearlyOrbScaleout3Strategy.strategy_type: YearlyOrbScaleout3Strategy,
        }

    def create(self, store: FlatFileStore, instance: StrategyInstance) -> StrategyPlugin:
        cls = self._types.get(instance.strategy_type)
        if cls is None:
            raise KeyError("Unknown strategy type: %s" % instance.strategy_type)
        return cls(store, instance)

    def available(self):
        return sorted(self._types.keys())
