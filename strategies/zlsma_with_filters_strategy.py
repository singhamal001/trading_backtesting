### File: X:\AmalTrading\trading_backtesting\strategies\zlsma_with_filters_strategy.py

import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from indicators import ( 
    calculate_zlsma, 
    calculate_range_filter_bands, 
    calculate_adaptive_macd,
    calculate_atr 
)
from strategy_logic import detect_choch as original_detect_choch # For HTF CHoCH
import config as global_config # To access global BREAK_TYPE if needed

class ZLSMAWithFiltersStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        self.zlsma_length = self.params.get("ZLSMA_LENGTH", 32)
        self.zlsma_source_col = self.params.get("ZLSMA_SOURCE", 'close')
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 2.0)
        self.sl_atr_period = self.params.get("SL_ATR_PERIOD", 14)
        self.sl_atr_multiplier = self.params.get("SL_ATR_MULTIPLIER", 1.5)

        self.use_range_filter = self.params.get("USE_RANGE_FILTER_HTF", False)
        self.range_len = self.params.get("RANGE_FILTER_LENGTH", 20)
        self.range_mult = self.params.get("RANGE_FILTER_MULT", 1.0)
        self.range_atr_len = self.params.get("RANGE_FILTER_ATR_LEN", 100)

        self.use_macd_filter = self.params.get("USE_ADAPTIVE_MACD_FILTER", False)
        self.macd_r2_period = self.params.get("ADAPTIVE_MACD_R2_PERIOD", 20)
        self.macd_fast = self.params.get("ADAPTIVE_MACD_FAST", 10)
        self.macd_slow = self.params.get("ADAPTIVE_MACD_SLOW", 12) 
        self.macd_signal = self.params.get("ADAPTIVE_MACD_SIGNAL", 9)
        
        # HTF CHoCH break type (can be a param or use global)
        self.htf_break_type = self.params.get("HTF_BREAK_TYPE_ZLSMA", global_config.BREAK_TYPE)


    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        # HTF Data Preparation (Range Filter is applied in check_htf_condition after CHoCH)
        # Swings on HTF are assumed to be pre-calculated by the backtester main script
        # and passed in htf_data (which becomes htf_data_with_swings)
        
        # LTF Data Preparation
        if self.zlsma_source_col not in ltf_data.columns:
            raise ValueError(f"Source column '{self.zlsma_source_col}' not in LTF data for ZLSMA.")
        ltf_data['zlsma'] = calculate_zlsma(ltf_data[self.zlsma_source_col], self.zlsma_length)

        if self.use_macd_filter:
            ltf_data['macd_line'], ltf_data['macd_signal_line'], ltf_data['macd_hist'] = \
                calculate_adaptive_macd(ltf_data['close'], self.macd_r2_period,
                                        self.macd_fast, self.macd_slow, self.macd_signal)
        ltf_data['atr_sl'] = calculate_atr(ltf_data['high'], ltf_data['low'], ltf_data['close'], self.sl_atr_period)
        
        # Prepare HTF for range filter if used (indicators only, actual check in HTF condition)
        if self.use_range_filter:
            # Calculate range filter components but don't filter yet
            # The htf_data passed here is htf_data_with_swings from backtester
            htf_data['in_range_temp'], htf_data['range_top_temp'], htf_data['range_bottom_temp'] = \
                calculate_range_filter_bands(htf_data['close'], self.range_len, 
                                             self.range_atr_len, self.range_mult,
                                             htf_data['high'], htf_data['low'])
                                             
        return htf_data, ltf_data

    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        # 1. Detect HTF CHoCH
        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_prepared, # This is htf_data_with_swings, and potentially range indicators
            current_htf_candle_idx,
            self.htf_break_type 
        )

        if not choch_type:
            return None # No CHoCH, no directional bias, no trade

        required_direction = "bullish" if "bullish" in choch_type else "bearish"
        htf_signal_type = f"htf_{required_direction}_choch_for_zlsma"

        # 2. Apply Range Filter (if enabled) AFTER CHoCH confirmation
        if self.use_range_filter:
            current_htf_candle = htf_data_prepared.iloc[current_htf_candle_idx]
            if 'in_range_temp' not in current_htf_candle.index:
                print(f"  WARNING ({self.symbol} HTF ZLSMA): 'in_range_temp' column missing for range filter check at {current_htf_candle.name}")
            elif pd.notna(current_htf_candle.get('in_range_temp')) and current_htf_candle.get('in_range_temp'):
                return None # CHoCH occurred, but HTF is in range, so filter out

        return {
            "type": htf_signal_type, 
            "level_broken": choch_price_broken, # CHoCH break level
            "confirmed_time": choch_confirmed_time, # CHoCH confirmation time
            "required_ltf_direction": required_direction
        }

    def check_ltf_entry_signal(self, ltf_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        if current_ltf_candle_idx < 1 or 'zlsma' not in ltf_data_prepared.columns:
            return None

        required_direction_from_htf = htf_signal_details["required_ltf_direction"]
        current_candle = ltf_data_prepared.iloc[current_ltf_candle_idx]
        prev_candle = ltf_data_prepared.iloc[current_ltf_candle_idx - 1]

        if pd.isna(current_candle['zlsma']) or pd.isna(prev_candle['zlsma']) or \
           pd.isna(current_candle[self.zlsma_source_col]) or pd.isna(prev_candle[self.zlsma_source_col]):
            return None 

        is_bullish_zlsma_cross = prev_candle[self.zlsma_source_col] < prev_candle['zlsma'] and \
                                 current_candle[self.zlsma_source_col] > current_candle['zlsma']
        is_bearish_zlsma_cross = prev_candle[self.zlsma_source_col] > prev_candle['zlsma'] and \
                                 current_candle[self.zlsma_source_col] < current_candle['zlsma']
        
        signal_to_return = None
        
        if required_direction_from_htf == "bullish" and is_bullish_zlsma_cross:
            if self.use_macd_filter:
                if 'macd_hist' not in current_candle.index or pd.isna(current_candle.get('macd_hist')):
                    return None 
                if current_candle.get('macd_hist') > 0: # MACD confirms bullish
                    signal_to_return = {"type": "zlsma_bullish_cross_macd_confirm", "confirmed_time": current_candle.name, "direction": "bullish"}
            else: 
                signal_to_return = {"type": "zlsma_bullish_cross", "confirmed_time": current_candle.name, "direction": "bullish"}
        
        elif required_direction_from_htf == "bearish" and is_bearish_zlsma_cross:
            if self.use_macd_filter:
                if 'macd_hist' not in current_candle.index or pd.isna(current_candle.get('macd_hist')):
                    return None 
                if current_candle.get('macd_hist') < 0: # MACD confirms bearish
                    signal_to_return = {"type": "zlsma_bearish_cross_macd_confirm", "confirmed_time": current_candle.name, "direction": "bearish"}
            else: 
                signal_to_return = {"type": "zlsma_bearish_cross", "confirmed_time": current_candle.name, "direction": "bearish"}
        
        return signal_to_return

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_prepared: pd.DataFrame, ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        direction = ltf_signal_details["direction"] # This should align with htf_signal_details["required_ltf_direction"]
        atr_at_entry_candle_prev = np.nan
        try:
            # SL is based on ATR of the candle *before* the entry candle (which is the signal candle + 1)
            # So, if entry_time is for candle K+1, signal was on K. ATR is from candle K.
            # Find index of signal candle:
            signal_candle_time = ltf_signal_details['confirmed_time']
            signal_candle_idx = ltf_data_prepared.index.get_loc(signal_candle_time)

            if signal_candle_idx >= 0 and 'atr_sl' in ltf_data_prepared.columns:
                 atr_at_entry_candle_prev = ltf_data_prepared['atr_sl'].iloc[signal_candle_idx]
            else: # Should not happen if signal_candle_idx is valid
                raise IndexError("ATR not found for signal candle or atr_sl column missing")

            if pd.isna(atr_at_entry_candle_prev):
                print(f"    Warning (ZLSMA): ATR is NaN at {ltf_data_prepared.index[signal_candle_idx]} for SL calc. Using default pip SL.")
                atr_at_entry_candle_prev = self.pip_size * 20 # Default ATR value in pips
        except (IndexError, KeyError) as e:
             print(f"    Warning (ZLSMA): Error getting ATR for SL/TP at {entry_time} (signal time {ltf_signal_details.get('confirmed_time')}): {e}. Using default pip SL.")
             atr_at_entry_candle_prev = self.pip_size * 20 

        sl_distance = atr_at_entry_candle_prev * self.sl_atr_multiplier
        sl_price, tp_price = None, None

        if direction == "bullish":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + (sl_distance * self.tp_rr_ratio)
        elif direction == "bearish":
            sl_price = entry_price + sl_distance
            tp_price = entry_price - (sl_distance * self.tp_rr_ratio)
            
        if sl_price is None or tp_price is None or sl_distance < self.pip_size / 2 : 
            print(f"    Warning (ZLSMA): Invalid SL/TP ({sl_price}, {tp_price}) or too small SL distance ({sl_distance}) for {self.symbol} at {entry_time}.")
            return None, None 
            
        return sl_price, tp_price