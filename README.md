# Forex Backtester CLI

A command-line interface (CLI) application for backtesting rule-based Forex trading strategies using historical data from MetaTrader 5. This tool allows users to define strategies, test them across multiple currency pairs and timeframes, and analyze their performance with detailed reports and visualizations.

## Features

*   **MetaTrader 5 Integration:** Fetches historical OHLCV data directly from a running MetaTrader 5 terminal.
*   **Multi-Timeframe Analysis:** Supports strategies that use signals from a Higher Timeframe (HTF) and entry confirmations on a Lower Timeframe (LTF).
*   **Heikin Ashi Candles:** Option to use Heikin Ashi candles for LTF analysis.
*   **Pluggable Strategy Architecture:**
    *   Define custom trading strategies as Python classes.
    *   Easily switch between strategies for backtesting.
    *   Currently includes a "ChochHa" (Change of Character + Heikin Ashi confirmation) strategy.
*   **Swing Point Identification:**
    *   Simple N-bar left/right method.
    *   ZigZag-based method for more dynamic swing detection.
*   **Detailed Backtesting:**
    *   Simulates trade entries, stop losses, and take profits.
    *   Manages one trade at a time per symbol.
    *   Time-based filter to restrict trading to specific UTC hours.
*   **Performance Reporting:**
    *   Generates reports for individual symbols and a combined portfolio.
    *   Metrics include: Win Rate, Avg Win/Loss (R), Expectancy (R), Profit Factor, Net Profit (R), Max Drawdown (R).
    *   Tracks R-level achievements (e.g., how many trades reached 1R, 1.5R, up to 5R for analysis).
*   **Visualizations (Plotly):**
    *   Saves interactive HTML charts for each trade, showing entry, SL, TP, and exit on multiple timeframes (H4, H1, M30, M15, M5).
    *   Generates equity curve plots (R-multiples) for individual symbols and the portfolio.
*   **Structured Results:** Saves all backtest reports and charts in a unique, timestamped session directory.

## Project Structure

```
forex_backtester_cli/
├── strategies/
│ ├── init.py # Makes 'strategies' a package, maps strategy names to classes
│ ├── base_strategy.py # Abstract base class for all strategies
│ └── choch_ha_strategy.py # Example: Change of Character + Heikin Ashi strategy
├── Backtesting_Results/ # Default root directory for all backtest session outputs
│ └── Strategy_Symbols_Timestamp/ # Each session gets a unique folder
│ ├── ConsolidatedReport.txt # Combined text report for all symbols and portfolio
│ ├── EquityCurves/ # Equity curve plots (.png)
│ │ ├── SYMBOL1_equity_curve_R.png
│ │ └── portfolio_equity_curve_R.png
│ └── Win/ # Trade charts for winning trades
│ ├── Longs/
│ │ └── Trade_ID_SYMBOL/
│ │ └── Trade_ID_SYMBOL_TF.html
│ └── Shorts/
│ └── ...
│ └── Loss/ # Trade charts for losing trades
│ ├── Longs/
│ └── Shorts/
│ └── Other/ # Trades closed EOD or other non-SL/TP exits
├── main.py # Main CLI entry point
├── config.py # Global configurations and default parameters
├── data_handler.py # Fetches and manages market data (MT5)
├── heikin_ashi.py # Calculates Heikin Ashi candles
├── utils.py # Utility functions (e.g., swing point identification)
├── backtester.py # Core backtesting engine and trade simulation logic
├── reporting.py # Generates performance reports and metrics
├── plotly_plotting.py # Generates interactive HTML charts for trades using Plotly
└── README.md # This file
```


## Prerequisites

*   **Python:** Version 3.9 or higher recommended.
*   **MetaTrader 5 Terminal:** Must be installed and running, with an active account logged in.
    *   In MT5: `Tools -> Options -> Expert Advisors -> Allow algorithmic trading` must be checked.
*   **Historical Data:** Ensure your MT5 terminal has sufficient historical data downloaded for the symbols and timeframes you intend to backtest. The script will attempt to fetch data, but it relies on what's available from your broker via the terminal.

## Installation

1.  **Clone the repository (if applicable) or download the files into a directory.**
    ```bash
    # git clone <repository_url>
    # cd forex_backtester_cli
    ```

2.  **Create a Python virtual environment (recommended):**
    ```bash
    python -m venv trading_env
    source trading_env/bin/activate  # On Linux/macOS
    # trading_env\Scripts\activate   # On Windows
    ```

3.  **Install required Python packages:**
    ```bash
    pip install pandas MetaTrader5 plotly kaleido pytz matplotlib
    ```
    *   `pandas`: For data manipulation.
    *   `MetaTrader5`: For MT5 integration.
    *   `plotly`: For interactive charts.
    *   `kaleido`: For saving Plotly charts as static images (though we primarily save as HTML, it's good to have if `write_image` is ever used for PNGs).
    *   `pytz`: For timezone handling.
    *   `matplotlib`: For equity curve plots.

## Configuration (`config.py`)

The `config.py` file holds all default settings and parameters. Key sections to review and modify:

*   **MT5 Connection:** `MT5_PATH`, `ACCOUNT_LOGIN`, `ACCOUNT_PASSWORD`, `ACCOUNT_SERVER`.
*   **Default Backtest Parameters:**
    *   `SYMBOLS`: List of default symbols if none are provided via CLI.
    *   `HTF_TIMEFRAME_STR`, `LTF_TIMEFRAME_STR`: Default higher and lower timeframes.
    *   `START_DATE_STR`, `END_DATE_STR`: Default backtesting period.
*   **Swing Identification:**
    *   `SWING_IDENTIFICATION_METHOD`: Choose between `"simple"` or `"zigzag"`.
    *   Parameters for each method (`N_BARS_LEFT_RIGHT...`, `ZIGZAG_LEN...`).
*   **Trade Parameters:**
    *   `SL_BUFFER_PIPS`, `TP_RR_RATIO` (default, can be overridden by strategy).
*   **Time Filter:**
    *   `ENABLE_TIME_FILTER`: `True` or `False`.
    *   `ALLOWED_TRADING_UTC_START_HOUR`, `ALLOWED_TRADING_UTC_START_MINUTE`, `ALLOWED_TRADING_UTC_END_HOUR`, `ALLOWED_TRADING_UTC_END_MINUTE`: Define the UTC time window during which trades are permitted.
*   **Strategy Selection:**
    *   `ACTIVE_STRATEGY_NAME`: The key name of the strategy to run by default (must match a key in `STRATEGY_MAP` in `strategies/__init__.py`).
    *   `STRATEGY_SPECIFIC_PARAMS`: A dictionary where each key is a strategy name and the value is another dictionary of its parameters.

## Usage (`main.py`)

The backtester is run from the command line using `main.py`.

**General Syntax:**
```bash
python main.py --mode <mode> --symbols <SYM1> <SYM2> ... --start <YYYY-MM-DD> --end <YYYY-MM-DD> --strategy <StrategyName>
```
**Arguments:**
- --symbols SYM1 SYM2 ...: (Optional) List of symbols to backtest. If not provided, uses SYMBOLS from config.py.
    - Example: --symbols EURUSD GBPUSD
- --start YYYY-MM-DD: (Optional) Start date for the backtest. Defaults to START_DATE_STR from config.py.
- --end YYYY-MM-DD: (Optional) End date for the backtest. Defaults to END_DATE_STR from config.py.
- --mode <mode>: (Optional) Operation mode.
    - backtest (default): Runs the full backtesting process and generates reports and charts.
    - debug_plot: Runs a debugging session for a single symbol over a shorter, often hardcoded period in main.py, generating plots to visualize strategy logic steps. (Note: This mode may need refactoring to fully utilize the strategy object model for accurate signal plotting if strategy logic is heavily encapsulated).
- --strategy <StrategyName>: (Optional) The name of the strategy to run (must be a key in STRATEGY_MAP in strategies/__init__.py and have parameters in config.STRATEGY_SPECIFIC_PARAMS). Defaults to ACTIVE_STRATEGY_NAME from config.py.

**Examples:**
- Run backtest for default symbols and strategy in config.py for the default period:
```python
python main.py
```

- Run backtest for EURUSD for a specific period with the default strategy:
```python
python main.py --symbol EURUSD --start 2024-01-01 --end 2024-06-30
```

- Run backtest for multiple symbols (EURUSD, USDJPY) for a specific period:
```python
python main.py --symbols EURUSD USDJPY --start 2023-01-01 --end 2023-12-31
```

- Run backtest using a specific strategy (assuming "MyCoolStrategy" is defined):
```python
python main.py --strategy MyCoolStrategy --symbols EURUSD --start 2024-01-01 --end 2024-03-31
```

## Output

After a backtest run, results are saved in the Backtesting_Results/ directory. A new sub-directory is created for each session, named like:
STRATEGYNAME_SYMBOL1_SYMBOL2_YYYYMMDD_HHMMSS

Inside this session directory:
- **ConsolidatedReport.txt:** Contains the text-based performance reports for each individual symbol and the combined portfolio report.
- **EquityCurves/:**
    - **SYMBOL_equity_curve_R.png:** Equity curve (in R-multiples) for each symbol.
    - **portfolio_equity_curve_R.png:** Combined portfolio equity curve.
- **Win/, Loss/, Other/:** These directories categorize trades by outcome.
    - Inside these, Longs/ and Shorts/ further categorize by trade direction.
    - **Trade_OVERALLID_SYMBOL/:** Each trade gets its own folder, named with a globally chronological ID.
    - **Trade_OVERALLID_SYMBOL_TFSUFFIX.html:** Interactive Plotly charts for different timeframes (H4, H1, M30, M15, M5) showing the trade context, entry, SL, TP, and exit.

## Adding a New Strategy
- Create a new Python file in the strategies/ directory (e.g., my_new_strategy.py).
- Define your strategy class in this file, ensuring it inherits from BaseStrategy (from strategies.base_strategy).

```python
# strategies/my_new_strategy.py
from .base_strategy import BaseStrategy
import pandas as pd

class MyNewStrategy(BaseStrategy):
    def __init__(self, strategy_params: dict, common_params: dict):
        super().__init__(strategy_params, common_params)
        # Initialize strategy-specific attributes from self.params
        self.my_param = self.params.get("my_custom_param", 10) 

    def prepare_data(self, htf_data: pd.DataFrame, ltf_data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        # Add any indicators or data transformations your strategy needs
        # Example: htf_data['SMA'] = htf_data['close'].rolling(window=self.my_param).mean()
        return htf_data, ltf_data

    def check_htf_condition(self, htf_data_prepared: pd.DataFrame, current_htf_candle_idx: int) -> dict | None:
        # Implement your HTF signal logic
        # Return a dictionary with signal details or None
        # Example:
        # if htf_data_prepared['close'].iloc[current_htf_candle_idx] > htf_data_prepared['SMA'].iloc[current_htf_candle_idx]:
        #     return {"type": "bullish_ma_cross", "confirmed_time": htf_data_prepared.index[current_htf_candle_idx], "required_ltf_direction": "bullish"}
        return None

    def check_ltf_entry_signal(self, ltf_data_prepared: pd.DataFrame, current_ltf_candle_idx: int, htf_signal_details: dict) -> dict | None:
        # Implement your LTF entry confirmation logic
        # Return a dictionary with entry details or None
        return None

    def calculate_sl_tp(self, entry_price: float, entry_time: pd.Timestamp, 
                        ltf_data_prepared: pd.DataFrame, ltf_signal_details: dict, 
                        htf_signal_details: dict) -> tuple[float | None, float | None]:
        # Implement your SL and TP calculation logic
        # Example:
        # risk_pips = self.params.get("fixed_sl_pips", 20) * self.pip_size
        # tp_rr = self.params.get("TP_RR_RATIO", 2.0)
        # if htf_signal_details["required_ltf_direction"] == "bullish":
        #     sl = entry_price - risk_pips
        #     tp = entry_price + risk_pips * tp_rr
        # else:
        #     sl = entry_price + risk_pips
        #     tp = entry_price - risk_pips * tp_rr
        # return sl, tp
        return None, None # Placeholder
```
- Register the strategy in strategies/__init__.py:
```python
# strategies/__init__.py
from .choch_ha_strategy import ChochHaStrategy
from .my_new_strategy import MyNewStrategy # Import your new strategy

STRATEGY_MAP = {
    "ChochHa": ChochHaStrategy,
    "MyNewStrategy": MyNewStrategy, # Add its mapping
}

def get_strategy_class(strategy_name: str):
    return STRATEGY_MAP.get(strategy_name)
```

- Add parameters for the new strategy in config.py:
```python
# config.py
# ...
STRATEGY_SPECIFIC_PARAMS = {
    "ChochHa": {
        # ... ChochHa params ...
    },
    "MyNewStrategy": {
        "my_custom_param": 15,
        "TP_RR_RATIO": 2.5,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5]
        # ... other params for MyNewStrategy ...
    }
}
# ...
```

- Now you can run your new strategy using the --strategy MyNewStrategy command-line argument.

## Future Enhancements / To-Do
- **More Sophisticated Position Sizing:** Implement fixed fractional, Kelly criterion, or other position sizing models.
- **Portfolio-Level Risk Management:** Max concurrent trades, max exposure per symbol/sector.
- **True Event-Driven Backtester:** For more accurate simulation of concurrent trades and margin.
- **Indicator Library:** Integrate a library like TA-Lib or build more common indicators.
- **Parameter Optimization:** Add functionality to test ranges of strategy parameters.
- Walk-Forward Optimization.
- **GUI:** Develop a web-based or desktop GUI for easier use.
- **Database Integration:** Use a proper database (e.g., PostgreSQL via Supabase, InfluxDB) for storing historical data and backtest results instead of just files.
- **Real-Time Alerting Module:** Extend to generate live alerts.
- **More Detailed Reporting:** Sharpe ratio, Sortino ratio, trade duration stats, etc.
- **Refactor** `debug_plot_mode`: Update it to fully utilize the strategy object model for plotting signals accurately.

## Troubleshooting
- **ImportError:** cannot import name '...' from 'config': Ensure the variable is defined at the global scope in config.py.
- **TypeError:** function() missing X required positional arguments: Check that the function call matches its definition (number and order of arguments). This often happens after refactoring.
- **KeyError:** 'column_name' in Pandas: Usually means a required column is missing from a DataFrame. Check data loading and preparation steps.
- **Plotly HTML charts not saving or empty:**
    - Ensure plotly and plotly.offline are correctly used.
    - Verify that the data slices being passed to go.Candlestick are not empty.
    - Check console for any warnings from plotly_plotting.py about data fetching or slicing.
- **Low number of trades:**
    - Review swing identification parameters (ZIGZAG_LEN_..., N_BARS_...).
    - Check the strictness of your strategy's HTF and LTF conditions.
    - Use debug_plot mode with verbose prints in strategy logic to trace decision-making.
    - Ensure the time filter in config.py is not overly restrictive.
