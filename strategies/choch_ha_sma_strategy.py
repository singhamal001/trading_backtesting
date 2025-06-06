# forex_backtester_cli/strategies/choch_ha_sma_strategy.py
import pandas as pd
import numpy as np
from .base_strategy import BaseStrategy
from strategy_logic import detect_choch as original_detect_choch # For HTF CHoCH
# We'll need access to config for some default params if not in strategy_params
import config 

class ChochHaSmaStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        # Strategy-specific parameters
        self.sma_period = self.params.get("SMA_PERIOD", 9)
        self.sl_fixed_pips = self.params.get("SL_FIXED_PIPS", 10)
        self.sl_ha_swing_candles = self.params.get("SL_HA_SWING_CANDLES", 5)
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 1.5) # Default if not in params
        # BREAK_TYPE for HTF CHoCH can also be a param if needed, else use common
        self.htf_break_type = self.params.get("HTF_BREAK_TYPE", config.BREAK_TYPE) 

        # Ensure R-levels are correctly fetched or defaulted
        self.r_levels_to_track = self.params.get("R_LEVELS_TO_TRACK", [1.0, 1.5, 2.0, 2.5, 3.0])


    def prepare_data(self, htf_data_with_swings: pd.DataFrame, ltf_data_ha_with_swings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        HTF data already has swings.
        LTF HA data already has HA candles and swings.
        This strategy needs to add the 9 SMA to the LTF HA data.
        """
        if 'ha_close' not in ltf_data_ha_with_swings.columns:
            raise ValueError("LTF data must have 'ha_close' for SMA calculation (Heikin Ashi expected).")
        
        # Calculate SMA on HA_Close for the LTF data
        ltf_data_ha_with_swings[f'sma_{self.sma_period}'] = ltf_data_ha_with_swings['ha_close'].rolling(window=self.sma_period).mean()
        
        return htf_data_with_swings, ltf_data_ha_with_swings

    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        """
        Uses the existing CHoCH detection logic for the HTF.
        htf_data_prepared is assumed to be htf_data_with_swings.
        """
        choch_type, choch_price_broken, choch_confirmed_time = original_detect_choch(
            htf_data_prepared, # This df already has swings
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

    def check_ltf_entry_signal(self, ltf_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        """
        Checks for the HA candle / SMA crossover signal on LTF.
        ltf_data_prepared is assumed to be ltf_data_ha_with_swings_and_sma.
        """
        if current_ltf_candle_idx < 1: # Need previous candle for SMA
            return None

        signal_candle = ltf_data_prepared.iloc[current_ltf_candle_idx]
        sma_value = signal_candle.get(f'sma_{self.sma_period}')

        if pd.isna(sma_value): # SMA not yet calculated for early bars
            return None

        required_direction = htf_signal_details["required_ltf_direction"]
        
        ha_open = signal_candle['ha_open']
        ha_close = signal_candle['ha_close']
        # ha_high = signal_candle['ha_high'] # Not directly used for entry signal logic
        # ha_low = signal_candle['ha_low']   # Not directly used for entry signal logic

        entry_signal_type = None

        if required_direction == "bullish":
            # HA Green: ha_close > ha_open
            # HA Open below SMA: ha_open < sma_value
            # HA Close above SMA: ha_close > sma_value
            if ha_close > ha_open and ha_open < sma_value and ha_close > sma_value:
                entry_signal_type = "ltf_bullish_ha_sma_cross"
        
        elif required_direction == "bearish":
            # HA Red: ha_close < ha_open
            # HA Open above SMA: ha_open > sma_value
            # HA Close below SMA: ha_close < sma_value
            if ha_close < ha_open and ha_open > sma_value and ha_close < sma_value:
                entry_signal_type = "ltf_bearish_ha_sma_cross"

        if entry_signal_type:
            return {
                "type": entry_signal_type,
                "confirmed_time": signal_candle.name, # Time of the signal HA candle
                "signal_candle_details": { # Store for SL calculation if needed
                    "ha_high": signal_candle['ha_high'],
                    "ha_low": signal_candle['ha_low'],
                }
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_prepared: pd.DataFrame, # This is ltf_data_ha_with_swings_and_sma
                        ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        direction = htf_signal_details["required_ltf_direction"]
        
        # SL Condition 1: Fixed pips
        sl_fixed_level = None
        if direction == "bullish":
            sl_fixed_level = entry_price - (self.sl_fixed_pips * self.pip_size)
        elif direction == "bearish":
            sl_fixed_level = entry_price + (self.sl_fixed_pips * self.pip_size)

        # SL Condition 2: Recent HA Swing (5 candles *before* entry candle)
        # Entry candle is the one *after* the signal candle.
        # Signal candle time is ltf_signal_details['confirmed_time']
        signal_candle_time = ltf_signal_details['confirmed_time']
        
        # Get the 5 HA candles ending at the signal candle
        # (signal candle is index 0, then -1, -2, -3, -4 relative to signal candle)
        try:
            signal_candle_idx_loc = ltf_data_prepared.index.get_loc(signal_candle_time)
        except KeyError:
            print(f"    Warning: Signal candle time {signal_candle_time} not found in LTF data for SL calc. Using fixed SL only.")
            sl_ha_swing_level = sl_fixed_level # Fallback
        else:
            start_idx_for_ha_swing = max(0, signal_candle_idx_loc - self.sl_ha_swing_candles + 1)
            # Ensure we don't go beyond the signal candle itself for this window
            ha_candles_for_sl = ltf_data_prepared.iloc[start_idx_for_ha_swing : signal_candle_idx_loc + 1]

            sl_ha_swing_level = None
            if not ha_candles_for_sl.empty:
                if direction == "bullish":
                    lowest_ha_low = ha_candles_for_sl['ha_low'].min()
                    sl_ha_swing_level = lowest_ha_low - self.sl_buffer_price
                elif direction == "bearish":
                    highest_ha_high = ha_candles_for_sl['ha_high'].max()
                    sl_ha_swing_level = highest_ha_high + self.sl_buffer_price
            else: # Should not happen if signal_candle_idx_loc is valid
                sl_ha_swing_level = sl_fixed_level # Fallback

        # Determine final SL: "whichever is near to Entry"
        # For long: nearer means higher SL value (smaller risk). max()
        # For short: nearer means lower SL value (smaller risk). min()
        final_sl_price = None
        if direction == "bullish":
            if sl_fixed_level is not None and sl_ha_swing_level is not None:
                final_sl_price = max(sl_fixed_level, sl_ha_swing_level)
            elif sl_fixed_level is not None:
                final_sl_price = sl_fixed_level
            else: # Should only be sl_ha_swing_level if sl_fixed_level was None (not possible with current logic)
                final_sl_price = sl_ha_swing_level 
        elif direction == "bearish":
            if sl_fixed_level is not None and sl_ha_swing_level is not None:
                final_sl_price = min(sl_fixed_level, sl_ha_swing_level)
            elif sl_fixed_level is not None:
                final_sl_price = sl_fixed_level
            else:
                final_sl_price = sl_ha_swing_level

        if final_sl_price is None:
            print(f"    ERROR: Could not determine final SL price for trade at {entry_time}. Skipping.")
            return None, None

        # Calculate TP
        risk_amount_price = abs(entry_price - final_sl_price)
        if risk_amount_price < self.pip_size: # Avoid tiny/zero risk
            print(f"    Warning: Risk amount too small ({risk_amount_price:.5f}) for {self.symbol} at {entry_time}. Cannot set valid TP.")
            return final_sl_price, None # Return SL, but no TP

        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return final_sl_price, tp_price

    def get_r_levels_to_track(self) -> list:
        # Ensure R-levels are correctly fetched or defaulted from strategy_params
        return self.params.get("R_LEVELS_TO_TRACK", [1.0, 1.5, 2.0, 2.5, 3.0])