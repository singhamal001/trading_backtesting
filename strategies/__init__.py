# forex_backtester_cli/strategies/__init__.py

from .choch_ha_strategy import ChochHaStrategy

STRATEGY_MAP = {
    "ChochHa": ChochHaStrategy,
}

def get_strategy_class(strategy_name: str):
    return STRATEGY_MAP.get(strategy_name)