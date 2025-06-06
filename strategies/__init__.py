# forex_backtester_cli/strategies/__init__.py

from .choch_ha_strategy import ChochHaStrategy
from .choch_ha_sma_strategy import ChochHaSmaStrategy

STRATEGY_MAP = {
    "ChochHa": ChochHaStrategy,
    "ChochHaSma": ChochHaSmaStrategy, # Add to map
}

def get_strategy_class(strategy_name: str):
    strategy_class = STRATEGY_MAP.get(strategy_name)
    if strategy_class is None:
        raise ValueError(f"Strategy '{strategy_name}' not found in STRATEGY_MAP.")
    return strategy_class