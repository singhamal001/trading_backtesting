# forex_backtester_cli/strategies/base_strategy.py
from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    def __init__(self, strategy_params: dict, common_params: dict):
        """
        Args:
            strategy_params (dict): Parameters specific to this strategy instance.
            common_params (dict): Common parameters like symbol, pip_size, etc.
        """
        self.params = strategy_params
        self.common_params = common_params
        self.symbol = common_params.get("symbol", "UNKNOWN")
        self.pip_size = common_params.get("pip_size", 0.0001) # Default, should be set
        self.sl_buffer_price = common_params.get("sl_buffer_price", 0.0)

        # R-levels to track, can be overridden by strategy_params
        self.r_levels_to_track = strategy_params.get("r_levels_to_track", [1.0, 1.5, 2.0, 2.5, 3.0])


    @abstractmethod
    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Prepare HTF and LTF data specific to the strategy's needs.
        This might involve calculating indicators, identifying specific swing types, etc.
        It should return the prepared HTF and LTF DataFrames.
        The input dataframes are raw OHLC.
        Swing points and HA might be calculated here or passed in already prepared.
        For simplicity, let's assume swing points and HA are pre-calculated and passed
        to check_entry_signal. This method can add strategy-specific indicators.

        Returns:
            tuple: (prepared_htf_df, prepared_ltf_df)
        """
        pass

    @abstractmethod
    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        """
        Checks if the Higher Timeframe condition for a potential setup is met.

        Args:
            htf_data_prepared (pd.DataFrame): HTF data, potentially with strategy-specific indicators and swings.
            current_htf_candle_idx (int): Index of the current HTF candle being evaluated.

        Returns:
            dict | None: A dictionary with HTF signal details (e.g., {'type': 'bullish_choch', 'level': 1.2345, 'time': timestamp}) 
                         if condition met, else None.
        """
        pass

    @abstractmethod
    def check_ltf_entry_signal(self, ltf_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        """
        Checks for the Lower Timeframe entry confirmation signal, given an HTF condition.

        Args:
            ltf_data_prepared (pd.DataFrame): LTF data (e.g., Heikin Ashi with swings).
            current_ltf_candle_idx (int): Index of the current LTF candle.
            htf_signal_details (dict): Information from the HTF signal.

        Returns:
            dict | None: A dictionary with LTF entry signal details (e.g., {'type': 'ltf_bullish_bos', 'break_level': 1.1223, 'confirmed_time': timestamp})
                         if entry signal met, else None.
        """
        pass

    @abstractmethod
    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_prepared: pd.DataFrame, ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float, float]:
        """
        Calculates Stop Loss and Take Profit levels for a trade.

        Args:
            entry_price (float): The entry price of the trade.
            entry_time (pd.Timestamp): The entry time of the trade.
            ltf_data_prepared (pd.DataFrame): LTF data around the entry.
            ltf_signal_details (dict): Details from the LTF entry signal.
            htf_signal_details (dict): Details from the HTF condition.


        Returns:
            tuple: (sl_price, tp_price)
        """
        pass
    
    def get_r_levels_to_track(self) -> list:
        """Returns the R-levels this strategy wants to track."""
        return self.r_levels_to_track

    # Optional: Method for custom trade management logic during an open trade
    # def manage_open_trade(self, trade_info: dict, current_ltf_candle: pd.Series) -> dict | None:
    #     """
    #     Allows for custom trade management (e.g., trailing stops, partial closes).
    #     Args:
    #         trade_info (dict): The current active trade's dictionary.
    #         current_ltf_candle (pd.Series): The current LTF OHLC candle.
    #     Returns:
    #         dict | None: Updated trade_info if action taken (e.g., new SL), or None.
    #                      Or a signal to close the trade: {'action': 'close', 'price': ...}
    #     """
    #     return None