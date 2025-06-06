# forex_backtester_cli/strategies/choch_ha_strategy.py
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

from strategy_logic import get_market_structure_and_recent_swings, detect_choch as original_detect_choch, detect_ltf_structure_change as original_detect_ltf_change

class ChochHaStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        # Strategy-specific parameters from strategy_params
        self.break_type = self.params.get("BREAK_TYPE", "close")
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 1.5)
        # Swing identification parameters are now part of common_params or assumed to be on data
        # self.htf_swing_len = self.params.get("ZIGZAG_LEN_HTF", 9) # Example
        # self.ltf_swing_len = self.params.get("ZIGZAG_LEN_LTF", 5) # Example

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        For this strategy, swing points and HA are assumed to be pre-calculated
        by the main backtester script before calling strategy methods.
        This method could add strategy-specific indicators if needed.
        """
        # If this strategy needed unique indicators, calculate them here.
        # e.g., htf_data['EMA20'] = htf_data['close'].ewm(span=20, adjust=False).mean()
        return htf_data, ltf_data # Return them as is if no further prep needed by this strategy

    def check_htf_condition(self, htf_data_with_swings: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_with_swings,
            current_htf_candle_idx,
            self.break_type
        )
        if choch_type:
            return {
                "type": choch_type, # e.g., "bullish_choch" or "bearish_choch"
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
            self.break_type
        )
        if ltf_signal_type:
            return {
                "type": ltf_signal_type, # e.g., "ltf_bullish_confirm_bos"
                "level_broken": ltf_signal_price_broken,
                "confirmed_time": ltf_signal_confirmed_time
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_ha_with_swings: pd.DataFrame, # Using HA swings for SL placement
                        ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        sl_price = None
        direction = htf_signal_details["required_ltf_direction"]

        # Find the HA swing point *before* entry_time to base SL on
        relevant_swings_for_sl = ltf_data_ha_with_swings[ltf_data_ha_with_swings.index < entry_time]

        if direction == "bullish":
            last_ha_swing_low_for_sl = relevant_swings_for_sl[relevant_swings_for_sl['swing_low'].notna()]
            if not last_ha_swing_low_for_sl.empty:
                sl_price = last_ha_swing_low_for_sl['swing_low'].iloc[-1] - self.sl_buffer_price
            else: 
                sl_price = entry_price - (15 * self.pip_size) # Default SL
                print(f"    Warning: No prior LTF HA swing low for SL ({self.symbol}). Using default SL.")
        
        elif direction == "bearish":
            last_ha_swing_high_for_sl = relevant_swings_for_sl[relevant_swings_for_sl['swing_high'].notna()]
            if not last_ha_swing_high_for_sl.empty:
                sl_price = last_ha_swing_high_for_sl['swing_high'].iloc[-1] + self.sl_buffer_price
            else: 
                sl_price = entry_price + (15 * self.pip_size) # Default SL
                print(f"    Warning: No prior LTF HA swing high for SL ({self.symbol}). Using default SL.")

        if sl_price is None: return None, None # Should not happen with fallbacks

        risk_amount_price = abs(entry_price - sl_price)
        if risk_amount_price < self.pip_size: # Avoid tiny/zero risk
            print(f"    Warning: Risk amount too small ({risk_amount_price:.5f}) for {self.symbol}. Cannot set valid SL/TP.")
            return None, None # Indicate invalid SL/TP

        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return sl_price, tp_price