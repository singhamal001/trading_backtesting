### File: X:\AmalTrading\trading_backtesting\strategies\ha_adaptive_macd_strategy.py

import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from indicators import calculate_adaptive_macd 
from heikin_ashi import calculate_heikin_ashi
import config as global_config 

from strategy_logic import detect_choch as original_detect_choch
from utils import identify_swing_points_zigzag, identify_swing_points_simple # Ensure both are imported if used

class HAAdaptiveMACDStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 2.0) 
        
        self.macd_r2_period = self.params.get("ADAPTIVE_MACD_R2_PERIOD", global_config.STRATEGY_SPECIFIC_PARAMS.get("ZLSMAWithFilters", {}).get("ADAPTIVE_MACD_R2_PERIOD", 20))
        self.macd_fast = self.params.get("ADAPTIVE_MACD_FAST", global_config.STRATEGY_SPECIFIC_PARAMS.get("ZLSMAWithFilters", {}).get("ADAPTIVE_MACD_FAST", 10))
        self.macd_slow = self.params.get("ADAPTIVE_MACD_SLOW", global_config.STRATEGY_SPECIFIC_PARAMS.get("ZLSMAWithFilters", {}).get("ADAPTIVE_MACD_SLOW", 12)) # Defaulted to 12 from ZLSMA, adjust if needed
        self.macd_signal = self.params.get("ADAPTIVE_MACD_SIGNAL", global_config.STRATEGY_SPECIFIC_PARAMS.get("ZLSMAWithFilters", {}).get("ADAPTIVE_MACD_SIGNAL", 9))

        self.htf_break_type = self.params.get("HTF_BREAK_TYPE", global_config.BREAK_TYPE) 
        self.ltf_confirmation_candles = self.params.get("LTF_CONFIRMATION_CANDLES", 1) 
        self.sl_buffer_pips_strat = global_config.SL_BUFFER_PIPS 
        self._reset_strategy_state()

    def _reset_strategy_state(self):
        pass

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        prepared_htf_data = htf_data.copy()
        if not prepared_htf_data.empty:
            if global_config.SWING_IDENTIFICATION_METHOD == "zigzag":
                prepared_htf_data = identify_swing_points_zigzag(
                    prepared_htf_data, 
                    zigzag_len=global_config.ZIGZAG_LEN_HTF # CORRECTED KEYWORD ARGUMENT
                )
            else: 
                 prepared_htf_data = identify_swing_points_simple(
                    prepared_htf_data, 
                    n_left=global_config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF,
                    n_right=global_config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF
                )
        
        chart_data_ltf = ltf_data.copy() 
        if not chart_data_ltf.empty:
            ha_candles = calculate_heikin_ashi(chart_data_ltf)
            chart_data_ltf = pd.concat([chart_data_ltf, ha_candles], axis=1)
            chart_data_ltf['ha_green'] = chart_data_ltf['ha_close'] > chart_data_ltf['ha_open']
            chart_data_ltf['ha_red'] = chart_data_ltf['ha_close'] < chart_data_ltf['ha_open']

            chart_data_ltf['macd_line'], chart_data_ltf['macd_signal_line'], chart_data_ltf['macd_hist'] = \
                calculate_adaptive_macd(chart_data_ltf['close'], self.macd_r2_period,
                                        self.macd_fast, self.macd_slow, self.macd_signal)
        
        self._reset_strategy_state() 
        return prepared_htf_data, chart_data_ltf


    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        if htf_data_prepared.empty or \
           'swing_high' not in htf_data_prepared.columns or \
           'swing_low' not in htf_data_prepared.columns:
            return None 
        
        min_idx_for_choch = (global_config.ZIGZAG_LEN_HTF if global_config.SWING_IDENTIFICATION_METHOD == "zigzag" else global_config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF) + 2 
        if current_htf_candle_idx < min_idx_for_choch :
            return None

        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_prepared, 
            current_htf_candle_idx,
            self.htf_break_type 
        )
        if choch_type:
            return {
                "type": choch_type, 
                "level_broken": choch_price_broken,
                "confirmed_time": choch_confirmed_time,
                "required_ltf_direction": "bullish" if "bullish" in choch_type else "bearish"
            }
        return None

    def check_ltf_entry_signal(self, chart_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        if current_ltf_candle_idx < 1: 
            return None
        
        current_candle = chart_data_prepared.iloc[current_ltf_candle_idx]
        required_direction = htf_signal_details["required_ltf_direction"]

        if not all(col in current_candle for col in ['ha_green', 'ha_red', 'macd_hist']):
            return None
        if pd.isna(current_candle['macd_hist']): 
            return None 

        entry_signal_type = None
        if required_direction == "bullish":
            if current_candle['ha_green'] and current_candle['macd_hist'] > 0:
                entry_signal_type = "ha_macd_bullish_confirm"
        
        elif required_direction == "bearish":
            if current_candle['ha_red'] and current_candle['macd_hist'] < 0:
                entry_signal_type = "ha_macd_bearish_confirm"

        if entry_signal_type:
            return {
                "type": entry_signal_type,
                "confirmed_time": current_candle.name,
                "direction": required_direction, 
                "signal_candle_ha_low": current_candle['ha_low'],
                "signal_candle_ha_high": current_candle['ha_high'],
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        chart_data_prepared: pd.DataFrame, ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        print(f"    DEBUG SL/TP Calc for {self.symbol} at {entry_time}:")
        print(f"      Entry Price: {entry_price:.5f}")
        print(f"      LTF Signal Details: {ltf_signal_details}")

        direction = ltf_signal_details.get("direction")
        if not direction:
            print(f"      ERROR: Direction missing in ltf_signal_details.")
            return None, None
        
        print(f"      Direction: {direction}")

        sl_price = None
        tp_price = None
        sl_buffer_actual = self.sl_buffer_pips_strat * self.pip_size
        print(f"      SL Buffer Actual: {sl_buffer_actual:.5f} (Pips: {self.sl_buffer_pips_strat}, PipSize: {self.pip_size})")
        
        signal_candle_low = ltf_signal_details.get("signal_candle_ha_low")
        signal_candle_high = ltf_signal_details.get("signal_candle_ha_high")

        if direction == "bullish":
            if signal_candle_low is None:
                print(f"      ERROR: Missing signal_candle_ha_low for SL calc.")
                return None, None
            print(f"      Signal Candle HA Low: {signal_candle_low:.5f}")
            sl_price = signal_candle_low - sl_buffer_actual
            print(f"      Calculated Bullish SL (pre-validation): {sl_price:.5f}")
        elif direction == "bearish":
            if signal_candle_high is None:
                print(f"      ERROR: Missing signal_candle_ha_high for SL calc.")
                return None, None
            print(f"      Signal Candle HA High: {signal_candle_high:.5f}")
            sl_price = signal_candle_high + sl_buffer_actual
            print(f"      Calculated Bearish SL (pre-validation): {sl_price:.5f}")
        else: 
            print(f"      ERROR: Invalid direction '{direction}' for SL/TP calc.")
            return None, None

        # Validate SL
        min_sl_distance_from_entry = self.pip_size * 1 # Min 1 pip distance
        if direction == "bullish":
            if sl_price >= entry_price - min_sl_distance_from_entry:
                print(f"      VALIDATION FAIL: Bullish SL {sl_price:.5f} too close or above entry threshold {entry_price - min_sl_distance_from_entry:.5f}.")
                return None, None 
        elif direction == "bearish":
            if sl_price <= entry_price + min_sl_distance_from_entry:
                print(f"      VALIDATION FAIL: Bearish SL {sl_price:.5f} too close or below entry threshold {entry_price + min_sl_distance_from_entry:.5f}.")
                return None, None

        risk_amount_price = abs(entry_price - sl_price)
        print(f"      Risk Amount Price: {risk_amount_price:.5f}")
        min_risk_required = self.pip_size * 2
        if risk_amount_price < min_risk_required: 
            print(f"      VALIDATION FAIL: Risk amount {risk_amount_price:.5f} too small (min required: {min_risk_required:.5f}).")
            return None, None 

        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
        
        #print(f"      Final SL: {sl_price:.5f}, Final TP: {tp_price:.5f if tp_price else 'N/A'}")
        return sl_price, tp_price
