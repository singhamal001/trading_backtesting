# forex_backtester_cli/strategies/choch_ha_strategy.py
import config as global_config
from strategy_logic import detect_choch as original_detect_choch, detect_ltf_structure_change as original_detect_ltf_change
import pandas as pd
from .base_strategy import BaseStrategy
# Import necessary functions from your existing strategy_logic or utils
# For this example, we'll assume detect_choch and detect_ltf_structure_change
# are adapted or their core logic is moved into this class's methods.
# We also need get_market_structure_and_recent_swings.
# For simplicity, let's assume these are now methods or called by methods here.

# --- Re-import or redefine necessary helper functions from strategy_logic.py ---
# It's cleaner to have these as part of the class or helper methods if they are specific.
# For now, let's assume they are available (e.g., from a shared utils or strategy_helpers module)
# Or, we can copy/paste and adapt them here.
# For this example, I'll integrate parts of their logic directly.

class ChochHaStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        self.break_type = self.params.get("BREAK_TYPE", global_config.BREAK_TYPE) # Use global if not specified
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 1.5)

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        return htf_data, ltf_data

    def check_htf_condition(self, htf_data_with_swings: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        # This strategy uses the global config.BREAK_TYPE for HTF CHoCH if not specified in params
        # or its own self.break_type if it was set from params.
        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_with_swings,
            current_htf_candle_idx,
            self.break_type 
        )
        if choch_type:
            return {
                "type": choch_type, 
                "level_broken": choch_price_broken,
                "confirmed_time": choch_confirmed_time,
                "required_ltf_direction": "bullish" if "bullish" in choch_type else "bearish"
            }
        return None

    def check_ltf_entry_signal(self, ltf_data_ha_with_swings: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        required_direction = htf_signal_details["required_ltf_direction"]
        
        ltf_signal_type, ltf_signal_price_broken, ltf_signal_confirmed_time = original_detect_ltf_change(
            ltf_data_ha_with_swings,
            current_ltf_candle_idx,
            required_direction,
            self.break_type # Assuming LTF break type is same as HTF for this strategy
        )
        if ltf_signal_type:
            # Ensure the LTF signal's inherent direction matches the required HTF direction
            # (original_detect_ltf_change already does this by taking 'required_direction' as input)
            return {
                "type": ltf_signal_type, 
                "level_broken": ltf_signal_price_broken,
                "confirmed_time": ltf_signal_confirmed_time,
                "direction": required_direction # Add direction explicitly for clarity in backtester
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_ha_with_swings: pd.DataFrame, 
                        ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        sl_price = None
        # direction comes from htf_signal_details or ltf_signal_details, should be consistent
        direction = ltf_signal_details.get("direction", htf_signal_details["required_ltf_direction"])


        relevant_swings_for_sl = ltf_data_ha_with_swings[ltf_data_ha_with_swings.index < entry_time]

        if direction == "bullish":
            last_ha_swing_low_for_sl = relevant_swings_for_sl[relevant_swings_for_sl['swing_low'].notna()]
            if not last_ha_swing_low_for_sl.empty:
                sl_price = last_ha_swing_low_for_sl['swing_low'].iloc[-1] - self.sl_buffer_price
            else: 
                # Fallback SL if no swing found (e.g. 15 pips, should be configurable)
                sl_price = entry_price - (15 * self.pip_size) 
                print(f"    Warning (ChochHa): No prior LTF HA swing low for SL ({self.symbol}). Using default pip SL.")
        
        elif direction == "bearish":
            last_ha_swing_high_for_sl = relevant_swings_for_sl[relevant_swings_for_sl['swing_high'].notna()]
            if not last_ha_swing_high_for_sl.empty:
                sl_price = last_ha_swing_high_for_sl['swing_high'].iloc[-1] + self.sl_buffer_price
            else: 
                sl_price = entry_price + (15 * self.pip_size) 
                print(f"    Warning (ChochHa): No prior LTF HA swing high for SL ({self.symbol}). Using default pip SL.")

        if sl_price is None: return None, None

        risk_amount_price = abs(entry_price - sl_price)
        if risk_amount_price < self.pip_size: 
            print(f"    Warning (ChochHa): Risk amount too small ({risk_amount_price:.5f}) for {self.symbol}. Cannot set valid SL/TP.")
            return None, None 

        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return sl_price, tp_price