### File: X:\AmalTrading\trading_backtesting\strategies\ha_alligator_macd_strategy.py

import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from indicators import calculate_alligator, calculate_adaptive_macd 
from heikin_ashi import calculate_heikin_ashi
import config as global_config 
from strategy_logic import detect_choch as original_detect_choch # For HTF CHoCH

class HAAlligatorMACDStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 2.0)
        
        self.jaw_period = self.params.get("ALLIGATOR_JAW_PERIOD", global_config.ALLIGATOR_JAW_PERIOD)
        self.jaw_shift = self.params.get("ALLIGATOR_JAW_SHIFT", global_config.ALLIGATOR_JAW_SHIFT)
        self.teeth_period = self.params.get("ALLIGATOR_TEETH_PERIOD", global_config.ALLIGATOR_TEETH_PERIOD)
        self.teeth_shift = self.params.get("ALLIGATOR_TEETH_SHIFT", global_config.ALLIGATOR_TEETH_SHIFT)
        self.lips_period = self.params.get("ALLIGATOR_LIPS_PERIOD", global_config.ALLIGATOR_LIPS_PERIOD)
        self.lips_shift = self.params.get("ALLIGATOR_LIPS_SHIFT", global_config.ALLIGATOR_LIPS_SHIFT)
        self.alligator_source_col = self.params.get("ALLIGATOR_SMMA_SOURCE", global_config.ALLIGATOR_SMMA_SOURCE)
        self.alligator_trend_confirm_bars = self.params.get("ALLIGATOR_TREND_CONFIRM_BARS", 3)

        self.macd_r2_period = self.params.get("ADAPTIVE_MACD_R2_PERIOD", 20)
        self.macd_fast = self.params.get("ADAPTIVE_MACD_FAST", 10)
        self.macd_slow = self.params.get("ADAPTIVE_MACD_SLOW", 20)
        self.macd_signal = self.params.get("ADAPTIVE_MACD_SIGNAL", 9)

        self.ha_structural_lookback = self.params.get("HA_STRUCTURAL_LOOKBACK", 50)
        self.sl_buffer_pips_strat = global_config.SL_BUFFER_PIPS 
        
        # HTF CHoCH break type
        self.htf_break_type = self.params.get("HTF_BREAK_TYPE_HA_ALLIGATOR", global_config.BREAK_TYPE)

        self._reset_strategy_state()

    def _reset_strategy_state(self):
        self.last_defined_ha_high = None
        self.last_defined_ha_high_time = None
        self.last_defined_ha_low = None
        self.last_defined_ha_low_time = None
        self.setup_phase = "SCANNING" 
        self.current_structural_low_for_long = None 
        self.current_structural_high_for_short = None 
        self.breakout_level_price = None 

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        # htf_data is M15 with swings (passed from backtester)
        # ltf_data is M5 OHLC (passed from backtester)
        
        # LTF Data (M5) Preparation
        chart_data = ltf_data.copy() 
        ha_candles = calculate_heikin_ashi(chart_data)
        chart_data = pd.concat([chart_data, ha_candles], axis=1)
        chart_data['ha_median'] = (chart_data['ha_high'] + chart_data['ha_low']) / 2
        chart_data['ha_green'] = chart_data['ha_close'] > chart_data['ha_open']
        chart_data['ha_red'] = chart_data['ha_close'] < chart_data['ha_open']

        source_for_alligator = chart_data[self.alligator_source_col] if self.alligator_source_col in chart_data else chart_data['close']
        chart_data['alligator_jaw_raw'], chart_data['alligator_teeth_raw'], chart_data['alligator_lips_raw'] = \
            calculate_alligator(source_for_alligator,
                                self.jaw_period, self.jaw_shift,
                                self.teeth_period, self.teeth_shift,
                                self.lips_period, self.lips_shift)

        chart_data['macd_line'], chart_data['macd_signal_line'], chart_data['macd_hist'] = \
            calculate_adaptive_macd(chart_data['close'], self.macd_r2_period,
                                    self.macd_fast, self.macd_slow, self.macd_signal)
        
        self._reset_strategy_state() 
        return htf_data, chart_data # Return original htf_data and prepared chart_data (LTF)


    def _get_alligator_values_at_idx(self, df: pd.DataFrame, idx: int):
        jaw = df['alligator_jaw_raw'].iloc[idx - self.jaw_shift] if idx >= self.jaw_shift and idx - self.jaw_shift < len(df) else np.nan
        teeth = df['alligator_teeth_raw'].iloc[idx - self.teeth_shift] if idx >= self.teeth_shift and idx - self.teeth_shift < len(df) else np.nan
        lips = df['alligator_lips_raw'].iloc[idx - self.lips_shift] if idx >= self.lips_shift and idx - self.lips_shift < len(df) else np.nan
        return lips, teeth, jaw

    def _is_alligator_trending_bullish(self, df: pd.DataFrame, current_idx: int) -> bool:
        min_hist_needed = max(self.jaw_shift, self.teeth_shift, self.lips_shift) + self.alligator_trend_confirm_bars
        if current_idx < min_hist_needed:
            return False
        
        for i in range(self.alligator_trend_confirm_bars):
            idx_to_check = current_idx - i
            if idx_to_check < 0 : return False # Should be caught by min_hist_needed
            lips, teeth, jaw = self._get_alligator_values_at_idx(df, idx_to_check)
            if not (pd.notna(lips) and pd.notna(teeth) and pd.notna(jaw) and lips > teeth and teeth > jaw): # Strict fanning
                return False
        return True

    def _is_alligator_trending_bearish(self, df: pd.DataFrame, current_idx: int) -> bool:
        min_hist_needed = max(self.jaw_shift, self.teeth_shift, self.lips_shift) + self.alligator_trend_confirm_bars
        if current_idx < min_hist_needed:
            return False

        for i in range(self.alligator_trend_confirm_bars):
            idx_to_check = current_idx - i
            if idx_to_check < 0 : return False
            lips, teeth, jaw = self._get_alligator_values_at_idx(df, idx_to_check)
            if not (pd.notna(lips) and pd.notna(teeth) and pd.notna(jaw) and lips < teeth and teeth < jaw): # Strict fanning
                return False
        return True
        
    def _identify_recent_ha_structural_points(self, df: pd.DataFrame, current_idx: int):
        if current_idx < 3: return 

        start_scan_idx = max(0, current_idx - self.ha_structural_lookback -1) 
        end_scan_idx = current_idx -1 
        
        temp_high = None; temp_high_time = None
        temp_low = None; temp_low_time = None

        for k_offset in range(end_scan_idx - 2, start_scan_idx -1, -1): 
            if k_offset < 0 : break 
            idx_g = k_offset; idx_r1 = k_offset + 1; idx_r2 = k_offset + 2
            if idx_r2 > end_scan_idx : continue 
            if df.iloc[idx_g]['ha_green'] and df.iloc[idx_r1]['ha_red'] and df.iloc[idx_r2]['ha_red']:
                temp_high = df.iloc[idx_g]['ha_high']
                temp_high_time = df.index[idx_g]
                break 
        
        for k_offset in range(end_scan_idx - 2, start_scan_idx -1, -1): 
            if k_offset < 0 : break
            idx_r = k_offset; idx_g1 = k_offset + 1; idx_g2 = k_offset + 2
            if idx_g2 > end_scan_idx : continue
            if df.iloc[idx_r]['ha_red'] and df.iloc[idx_g1]['ha_green'] and df.iloc[idx_g2]['ha_green']:
                temp_low = df.iloc[idx_r]['ha_low']
                temp_low_time = df.index[idx_r]
                break 

        if temp_high is not None:
            if self.last_defined_ha_high is None or temp_high_time > self.last_defined_ha_high_time:
                self.last_defined_ha_high = temp_high
                self.last_defined_ha_high_time = temp_high_time
        
        if temp_low is not None:
            if self.last_defined_ha_low is None or temp_low_time > self.last_defined_ha_low_time:
                self.last_defined_ha_low = temp_low
                self.last_defined_ha_low_time = temp_low_time

    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        # htf_data_prepared is M15 data with swings
        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_prepared,
            current_htf_candle_idx,
            self.htf_break_type 
        )

        if not choch_type:
            return None 

        required_direction = "bullish" if "bullish" in choch_type else "bearish"
        return {
            "type": f"htf_{required_direction}_choch_for_ha_alligator", 
            "level_broken": choch_price_broken,
            "confirmed_time": choch_confirmed_time,
            "required_ltf_direction": required_direction
        }

    def check_ltf_entry_signal(self, chart_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        required_direction_from_htf = htf_signal_details["required_ltf_direction"]

        min_hist_needed_ltf = max(self.jaw_shift, self.teeth_shift, self.lips_shift, self.ha_structural_lookback, 3, self.alligator_trend_confirm_bars)
        if current_ltf_candle_idx < min_hist_needed_ltf:
            return None

        current_candle = chart_data_prepared.iloc[current_ltf_candle_idx]
        current_time = current_candle.name
        
        self._identify_recent_ha_structural_points(chart_data_prepared, current_ltf_candle_idx)

        alligator_bullish_now = self._is_alligator_trending_bullish(chart_data_prepared, current_ltf_candle_idx)
        alligator_bearish_now = self._is_alligator_trending_bearish(chart_data_prepared, current_ltf_candle_idx)

        # --- State Machine Logic ---
        if self.setup_phase == "SCANNING":
            if self.last_defined_ha_high is not None and self.last_defined_ha_low is not None:
                if required_direction_from_htf == "bullish" and alligator_bullish_now and \
                   current_candle['ha_close'] > self.last_defined_ha_high:
                    self.setup_phase = "HIGH_BROKEN_AWAIT_RETRACE"
                    self.breakout_level_price = self.last_defined_ha_high
                    self.current_structural_low_for_long = self.last_defined_ha_low
                    return None 

                elif required_direction_from_htf == "bearish" and alligator_bearish_now and \
                     current_candle['ha_close'] < self.last_defined_ha_low:
                    self.setup_phase = "LOW_BROKEN_AWAIT_RETRACE"
                    self.breakout_level_price = self.last_defined_ha_low
                    self.current_structural_high_for_short = self.last_defined_ha_high
                    return None 
            return None

        elif self.setup_phase == "HIGH_BROKEN_AWAIT_RETRACE":
            if required_direction_from_htf != "bullish" or not alligator_bullish_now:
                self._reset_strategy_state(); return None
            
            if current_candle['ha_low'] < self.current_structural_low_for_long:
                self._reset_strategy_state(); return None
            
            if current_candle['ha_green']: 
                if pd.notna(current_candle['macd_hist']) and current_candle['macd_hist'] > 0:
                    entry_signal = {"type": "ha_alligator_macd_long", "confirmed_time": current_time, "direction": "bullish",
                                    "sl_level": self.current_structural_low_for_long}
                    self._reset_strategy_state() 
                    return entry_signal
            return None

        elif self.setup_phase == "LOW_BROKEN_AWAIT_RETRACE":
            if required_direction_from_htf != "bearish" or not alligator_bearish_now:
                self._reset_strategy_state(); return None

            if current_candle['ha_high'] > self.current_structural_high_for_short:
                self._reset_strategy_state(); return None
            
            if current_candle['ha_red']: 
                if pd.notna(current_candle['macd_hist']) and current_candle['macd_hist'] < 0:
                    entry_signal = {"type": "ha_alligator_macd_short", "confirmed_time": current_time, "direction": "bearish",
                                    "sl_level": self.current_structural_high_for_short}
                    self._reset_strategy_state() 
                    return entry_signal
            return None
        
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        chart_data_prepared: pd.DataFrame, ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        direction = ltf_signal_details["direction"]
        sl_level_from_signal = ltf_signal_details["sl_level"]
        sl_price = None

        if direction == "bullish":
            sl_price = sl_level_from_signal - (self.sl_buffer_pips_strat * self.pip_size)
        elif direction == "bearish":
            sl_price = sl_level_from_signal + (self.sl_buffer_pips_strat * self.pip_size)

        if sl_price is None: return None, None

        risk_amount_price = abs(entry_price - sl_price)
        min_risk_pips = 2 # Example: minimum 2 pips risk
        if risk_amount_price < (self.pip_size * min_risk_pips): 
            # print(f"    Warning (HAAlligator): Risk amount too small ({risk_amount_price:.5f}) for {self.symbol} at {entry_time}. SL: {sl_price:.5f}. Entry: {entry_price:.5f}")
            return None, None 

        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return sl_price, tp_price