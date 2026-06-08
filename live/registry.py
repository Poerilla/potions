from __future__ import annotations

from typing import Dict, Type

from .models import StrategyInstance
from .store import FlatFileStore
from .strategies import (
    AtrSupertrendDcaStrategy,
    HourlyStPmcRetestStrategy,
    MonthlyOrbOverlapStRetestStrategy,
    MonthlyOrbRestrictedScaleout3Strategy,
    StrategyPlugin,
    SupertrendWickRetestStrategy,
    V2BCleanBreakStrategy,
    V2BScaleoutStrategy,
    WeeklyMidMa500BiasStrategy,
    WoGapReversalStrategy,
    YearlyOrbScaleout3Strategy,
)


class StrategyRegistry:
    def __init__(self) -> None:
        self._types: Dict[str, Type[StrategyPlugin]] = {
            AtrSupertrendDcaStrategy.strategy_type: AtrSupertrendDcaStrategy,
            HourlyStPmcRetestStrategy.strategy_type: HourlyStPmcRetestStrategy,
            MonthlyOrbOverlapStRetestStrategy.strategy_type: MonthlyOrbOverlapStRetestStrategy,
            MonthlyOrbRestrictedScaleout3Strategy.strategy_type: MonthlyOrbRestrictedScaleout3Strategy,
            SupertrendWickRetestStrategy.strategy_type: SupertrendWickRetestStrategy,
            V2BCleanBreakStrategy.strategy_type: V2BCleanBreakStrategy,
            V2BScaleoutStrategy.strategy_type: V2BScaleoutStrategy,
            WeeklyMidMa500BiasStrategy.strategy_type: WeeklyMidMa500BiasStrategy,
            WoGapReversalStrategy.strategy_type: WoGapReversalStrategy,
            YearlyOrbScaleout3Strategy.strategy_type: YearlyOrbScaleout3Strategy,
        }

    def create(self, store: FlatFileStore, instance: StrategyInstance) -> StrategyPlugin:
        cls = self._types.get(instance.strategy_type)
        if cls is None:
            raise KeyError("Unknown strategy type: %s" % instance.strategy_type)
        return cls(store, instance)

    def available(self):
        return sorted(self._types.keys())
