# forex_backtester_cli/strategies/choch_ha_sma_strategy.py

# Need to import global_config at the top of the file
import config as global_config
from strategy_logic import detect_choch as original_detect_choch
import pandas as pd
from .base_strategy import BaseStrategy

### File: X:\AmalTrading\trading_backtesting\strategies\choch_ha_sma_strategy.py
# ... (imports and __init__ remain the same) ...
class ChochHaSmaStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        self.sma_period = self.params.get("SMA_PERIOD", 9)
        self.sl_fixed_pips = self.params.get("SL_FIXED_PIPS", 10) # Used for initial SL calc, not CHoCH
        self.sl_ha_swing_candles = self.params.get("SL_HA_SWING_CANDLES", 5) # Used for initial SL calc
        self.tp_rr_ratio = self.params.get("TP_RR_RATIO", 1.5) 
        self.htf_break_type = self.params.get("HTF_BREAK_TYPE", global_config.BREAK_TYPE) 
        self.r_levels_to_track = self.params.get("R_LEVELS_TO_TRACK", [1.0, 1.5, 2.0, 2.5, 3.0])

    def prepare_data(self, htf_data_with_swings: pd.DataFrame, ltf_data_ha_with_swings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if 'ha_close' not in ltf_data_ha_with_swings.columns:
            raise ValueError("LTF data must have 'ha_close' for SMA calculation (Heikin Ashi expected).")
        ltf_data_ha_with_swings[f'sma_{self.sma_period}'] = ltf_data_ha_with_swings['ha_close'].rolling(window=self.sma_period).mean()
        return htf_data_with_swings, ltf_data_ha_with_swings

    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
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

    def check_ltf_entry_signal(self, ltf_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        if current_ltf_candle_idx < 1: 
            return None

        signal_candle = ltf_data_prepared.iloc[current_ltf_candle_idx]
        sma_value = signal_candle.get(f'sma_{self.sma_period}')

        if pd.isna(sma_value): 
            return None

        required_direction_from_htf = htf_signal_details["required_ltf_direction"]
        
        ha_open = signal_candle['ha_open']
        ha_close = signal_candle['ha_close']
        
        entry_signal_type = None
        current_ltf_direction = None

        if ha_close > ha_open and ha_open < sma_value and ha_close > sma_value: # Potential bullish HA/SMA cross
            current_ltf_direction = "bullish"
            if required_direction_from_htf == "bullish":
                entry_signal_type = "ltf_bullish_ha_sma_cross"
        
        elif ha_close < ha_open and ha_open > sma_value and ha_close < sma_value: # Potential bearish HA/SMA cross
            current_ltf_direction = "bearish"
            if required_direction_from_htf == "bearish":
                entry_signal_type = "ltf_bearish_ha_sma_cross"

        if entry_signal_type:
            return {
                "type": entry_signal_type,
                "confirmed_time": signal_candle.name, 
                "direction": required_direction_from_htf, # Explicitly pass the confirmed direction
                "signal_candle_details": { 
                    "ha_high": signal_candle['ha_high'],
                    "ha_low": signal_candle['ha_low'],
                }
            }
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_prepared: pd.DataFrame, 
                        ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        
        direction = ltf_signal_details["direction"] # Use direction from LTF signal
        
        sl_fixed_level = None
        if direction == "bullish":
            sl_fixed_level = entry_price - (self.sl_fixed_pips * self.pip_size)
        elif direction == "bearish":
            sl_fixed_level = entry_price + (self.sl_fixed_pips * self.pip_size)

        signal_candle_time = ltf_signal_details['confirmed_time']
        
        sl_ha_swing_level = None # Initialize
        try:
            signal_candle_idx_loc = ltf_data_prepared.index.get_loc(signal_candle_time)
            start_idx_for_ha_swing = max(0, signal_candle_idx_loc - self.sl_ha_swing_candles + 1)
            ha_candles_for_sl = ltf_data_prepared.iloc[start_idx_for_ha_swing : signal_candle_idx_loc + 1]

            if not ha_candles_for_sl.empty:
                if direction == "bullish":
                    lowest_ha_low = ha_candles_for_sl['ha_low'].min()
                    sl_ha_swing_level = lowest_ha_low - self.sl_buffer_price
                elif direction == "bearish":
                    highest_ha_high = ha_candles_for_sl['ha_high'].max()
                    sl_ha_swing_level = highest_ha_high + self.sl_buffer_price
            else: 
                sl_ha_swing_level = sl_fixed_level 
        except KeyError:
            print(f"    Warning (ChochHaSma): Signal candle time {signal_candle_time} not found in LTF data for SL calc. Using fixed SL only.")
            sl_ha_swing_level = sl_fixed_level 
        except Exception as e:
             print(f"    Error (ChochHaSma) calculating HA Swing SL: {e}. Using fixed SL.")
             sl_ha_swing_level = sl_fixed_level


        final_sl_price = None
        if direction == "bullish":
            if sl_fixed_level is not None and sl_ha_swing_level is not None:
                final_sl_price = max(sl_fixed_level, sl_ha_swing_level) # Nearer to entry = smaller risk
            elif sl_fixed_level is not None:
                final_sl_price = sl_fixed_level
            else: 
                final_sl_price = sl_ha_swing_level 
        elif direction == "bearish":
            if sl_fixed_level is not None and sl_ha_swing_level is not None:
                final_sl_price = min(sl_fixed_level, sl_ha_swing_level) # Nearer to entry = smaller risk
            elif sl_fixed_level is not None:
                final_sl_price = sl_fixed_level
            else:
                final_sl_price = sl_ha_swing_level

        if final_sl_price is None:
            print(f"    ERROR (ChochHaSma): Could not determine final SL price for trade at {entry_time}. Skipping.")
            return None, None

        risk_amount_price = abs(entry_price - final_sl_price)
        if risk_amount_price < self.pip_size: 
            print(f"    Warning (ChochHaSma): Risk amount too small ({risk_amount_price:.5f}) for {self.symbol} at {entry_time}. Cannot set valid TP.")
            return final_sl_price, None 

        tp_price = None
        if direction == "bullish":
            tp_price = entry_price + (risk_amount_price * self.tp_rr_ratio)
        elif direction == "bearish":
            tp_price = entry_price - (risk_amount_price * self.tp_rr_ratio)
            
        return final_sl_price, tp_price

    def get_r_levels_to_track(self) -> list:
        return self.r_levels_to_track