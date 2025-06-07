### File: X:\AmalTrading\trading_backtesting\strategies\__init__.py

# forex_backtester_cli/strategies/__init__.py

from .choch_ha_strategy import ChochHaStrategy
from .choch_ha_sma_strategy import ChochHaSmaStrategy
from .zlsma_with_filters_strategy import ZLSMAWithFiltersStrategy
from .ha_alligator_macd_strategy import HAAlligatorMACDStrategy
from .ha_adaptive_macd_strategy import HAAdaptiveMACDStrategy # New import

STRATEGY_MAP = {
    "ChochHa": ChochHaStrategy,
    "ChochHaSma": ChochHaSmaStrategy,
    "ZLSMAWithFilters": ZLSMAWithFiltersStrategy,
    "HAAlligatorMACD": HAAlligatorMACDStrategy, 
    "HAAdaptiveMACD": HAAdaptiveMACDStrategy, # New strategy
}

def get_strategy_class(strategy_name: str):
    strategy_class = STRATEGY_MAP.get(strategy_name)
    if strategy_class is None:
        raise ValueError(f"Strategy '{strategy_name}' not found in STRATEGY_MAP.")
    return strategy_class