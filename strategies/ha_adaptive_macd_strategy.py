### File: X:\AmalTrading\trading_backtesting\strategies\ha_adaptive_macd_strategy.py

import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from indicators import calculate_adaptive_macd
from heikin_ashi import calculate_heikin_ashi
import config as global_config
from strategy_logic import detect_choch as original_detect_choch

class HAAdaptiveMACDStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 2.0)
        
        self.macd_r2_period = self.params.get("ADAPTIVE_MACD_R2_PERIOD", 20)
        self.macd_fast = self.params.get("ADAPTIVE_MACD_FAST", 12)
        self.macd_slow = self.params.get("ADAPTIVE_MACD_SLOW", 26)
        self.macd_signal = self.params.get("ADAPTIVE_MACD_SIGNAL", 9)
        
        self.sl_ha_signal_candle_buffer_pips = self.params.get("SL_HA_SIGNAL_CANDLE_BUFFER_PIPS", 2)
        self.htf_break_type = self.params.get("HTF_BREAK_TYPE", global_config.BREAK_TYPE)

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        # htf_data is M15 with swings (passed from backtester, used for CHoCH)
        # ltf_data is M5 OHLC (passed from backtester)
        
        # LTF Data (M5) Preparation
        chart_data = ltf_data.copy() 
        
        # 1. Calculate Heikin Ashi
        ha_candles = calculate_heikin_ashi(chart_data)
        chart_data = pd.concat([chart_data, ha_candles], axis=1)
        # Add boolean columns for HA candle color for easier checking
        chart_data['ha_is_green'] = chart_data['ha_close'] > chart_data['ha_open']
        chart_data['ha_is_red'] = chart_data['ha_close'] < chart_data['ha_open']

        # 2. Calculate Adaptive MACD (using 'close' of original OHLC for MACD)
        chart_data['macd_line'], chart_data['macd_signal_line'], chart_data['macd_hist'] = \
            calculate_adaptive_macd(chart_data['close'], self.macd_r2_period,
                                    self.macd_fast, self.macd_slow, self.macd_signal)
        
        return htf_data, chart_data # Return original htf_data and prepared chart_data (LTF)

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
            "type": f"htf_{required_direction}_choch_for_ha_adaptive_macd", 
            "level_broken": choch_price_broken,
            "confirmed_time": choch_confirmed_time,
            "required_ltf_direction": required_direction
        }

    def check_ltf_entry_signal(self, chart_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        required_direction_from_htf = htf_signal_details["required_ltf_direction"]
        
        # Need at least one previous candle for MACD calculation to be stable, and current candle data
        if current_ltf_candle_idx < 1: # Or a larger lookback if MACD needs more history
            return None

        signal_candle = chart_data_prepared.iloc[current_ltf_candle_idx]
        
        # Check for NaN in critical indicators
        if pd.isna(signal_candle.get('macd_hist')) or \
           pd.isna(signal_candle.get('ha_is_green')) or \
           pd.isna(signal_candle.get('ha_is_red')):
            return None

        macd_is_bullish = signal_candle['macd_hist'] > 0
        macd_is_bearish = signal_candle['macd_hist'] < 0
        ha_is_bullish = signal_candle['ha_is_green']
        ha_is_bearish = signal_candle['ha_is_red']

        entry_signal_type = None
        trade_direction = None

        if required_direction_from_htf == "bullish":
            if macd_is_bullish and ha_is_bullish:
                entry_signal_type = "ha_adaptive_macd_bullish_entry"
                trade_direction = "bullish"
        
        elif required_direction_from_htf == "bearish":
            if macd_is_bearish and ha_is_bearish:
                entry_signal_type = "ha_adaptive_macd_bearish_entry"
                trade_direction = "bearish"

        if entry_signal_type and trade_direction:
            return {
                "type": entry_signal_type,
                "confirmed_time": signal_candle.name, # Time of the signal candle
                "direction": trade_direction,
                "signal_candle_ha_low": signal_candle['ha_low'], # For SL calculation
                "signal_candle_ha_high": signal_candle['ha_high'] # For SL calculation
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        chart_data_prepared: pd.DataFrame, # This is the prepared LTF data
                        ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        direction = ltf_signal_details["direction"]
        signal_candle_ha_low = ltf_signal_details["signal_candle_ha_low"]
        signal_candle_ha_high = ltf_signal_details["signal_candle_ha_high"]
        
        sl_buffer_actual = self.sl_ha_signal_candle_buffer_pips * self.pip_size
        sl_price = None

        if direction == "bullish":
            sl_price = signal_candle_ha_low - sl_buffer_actual
        elif direction == "bearish":
            sl_price = signal_candle_ha_high + sl_buffer_actual

        if sl_price is None:
            # This should ideally not happen if signal_candle_ha_low/high are always present
            print(f"    ERROR (HAAdaptiveMACD): SL price could not be determined for trade at {entry_time}.")
            return None, None

        risk_amount_price = abs(entry_price - sl_price)
        
        # Ensure minimum risk (e.g., 1 pip, or more depending on typical volatility)
        min_risk_threshold = self.pip_size 
        if risk_amount_price < min_risk_threshold: 
            # print(f"    Warning (HAAdaptiveMACD): Risk amount {risk_amount_price:.5f} too small for {self.symbol} at {entry_time}. SL: {sl_price:.5f}, Entry: {entry_price:.5f}. Adjusting SL.")
            # Adjust SL to meet minimum risk, or skip trade
            if direction == "bullish":
                sl_price = entry_price - min_risk_threshold
            else: # Bearish
                sl_price = entry_price + min_risk_threshold
            risk_amount_price = abs(entry_price - sl_price) # Recalculate risk
            if risk_amount_price < min_risk_threshold / 2 : # Still too small, skip
                 print(f"    Skipping (HAAdaptiveMACD): Risk still too small after adjustment for {self.symbol} at {entry_time}.")
                 return None, None


        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return sl_price, tp_price