# forex_backtester_cli/plotting_utils.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

def plot_ohlc_with_swings(
    df_ohlc: pd.DataFrame, 
    df_swings: pd.DataFrame, # DataFrame that includes swing_high and swing_low columns
    symbol: str, 
    timeframe_str: str, 
    plot_title: str = "OHLC with Swing Points",
    ha_mode: bool = False, # If true, use ha_open, ha_high etc.
    choch_points: list = None, # List of tuples: [(time, price, 'type'), ...]
    ltf_signals: list = None,  # List of tuples: [(time, price, 'type'), ...]
    save_path: str = None
    ):
    """
    Plots OHLC data with identified swing points, and optionally CHoCH/LTF signals.
    Saves the plot if save_path is provided.
    """
    fig, ax = plt.subplots(figsize=(15, 7))

    ohlc_cols = ['open', 'high', 'low', 'close']
    if ha_mode:
        ohlc_cols = ['ha_open', 'ha_high', 'ha_low', 'ha_close']
        if not all(col in df_ohlc.columns for col in ohlc_cols):
            print("Error: Heikin Ashi columns not found in DataFrame for HA plot.")
            return

    # Candlestick plot (simplified)
    for index, row in df_ohlc.iterrows():
        color = 'green' if row[ohlc_cols[3]] >= row[ohlc_cols[0]] else 'red'
        # Plot body
        ax.plot([index, index], [row[ohlc_cols[0]], row[ohlc_cols[3]]], color=color, linewidth=2)
        # Plot wicks
        ax.plot([index, index], [row[ohlc_cols[2]], row[ohlc_cols[1]]], color=color, linewidth=0.5)

    # Plot Swing Highs
    swing_highs_to_plot = df_swings[df_swings['swing_high'].notna()]
    ax.scatter(swing_highs_to_plot.index, swing_highs_to_plot['swing_high'] + (df_ohlc[ohlc_cols[1]].std() * 0.1), 
               color='red', marker='v', s=50, label='Swing High', zorder=5)

    # Plot Swing Lows
    swing_lows_to_plot = df_swings[df_swings['swing_low'].notna()]
    ax.scatter(swing_lows_to_plot.index, swing_lows_to_plot['swing_low'] - (df_ohlc[ohlc_cols[1]].std() * 0.1), 
               color='lime', marker='^', s=50, label='Swing Low', zorder=5)

    # Plot CHoCH points
    if choch_points:
        for ch_time, ch_price, ch_type in choch_points:
            color = 'magenta' if 'bullish' in ch_type else 'cyan'
            marker = 'P' # Plus sign
            ax.scatter(ch_time, ch_price, color=color, marker=marker, s=150, label=f"{ch_type.split('_')[0].upper()} CHoCH Line", zorder=6, edgecolor='black')
            ax.axhline(y=ch_price, color=color, linestyle='--', linewidth=1.5, alpha=0.7, xmin=0.05, xmax=0.95) # Line for CHoCH level
            # Annotate the CHoCH point
            ax.annotate(f"{ch_type.split('_')[0][:1]}CH@{'%.5f'%ch_price}", (ch_time, ch_price), textcoords="offset points", xytext=(0,10), ha='center', fontsize=9, color=color)


    # Plot LTF entry signals
    if ltf_signals:
        for sig_time, sig_price, sig_type in ltf_signals:
            color = 'blue' if 'bullish' in sig_type else 'orange'
            marker = '*'
            ax.scatter(sig_time, sig_price, color=color, marker=marker, s=150, label=f"LTF Signal ({sig_type.split('_')[1]})", zorder=7, edgecolor='black')
            ax.annotate(f"LTF {sig_type.split('_')[1][:1].upper()}S", (sig_time, sig_price), textcoords="offset points", xytext=(0,-15), ha='center', fontsize=9, color=color)


    ax.set_title(f"{plot_title} - {symbol} {timeframe_str}")
    ax.set_ylabel("Price")
    ax.legend()
    ax.grid(True, linestyle='--', alpha=0.7)

    # Format x-axis dates
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()

    if save_path:
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            plt.savefig(save_path)
            print(f"Plot saved to {save_path}")
        except Exception as e:
            print(f"Error saving plot: {e}")
    else:
        plt.show()
    plt.close(fig) # Close the figure to free memory

if __name__ == '__main__':
    # Create dummy data for testing the plotting function
    from datetime import datetime, timedelta
    idx = pd.to_datetime([datetime(2023,1,1, H, M) for H in range(1,3) for M in range(0, 60, 5)])
    data = {
        'open': np.random.rand(len(idx)) * 10 + 100,
        'close': np.random.rand(len(idx)) * 10 + 100,
        'high': np.random.rand(len(idx)) * 5 + 105,
        'low': 100 - np.random.rand(len(idx)) * 5,
    }
    # Ensure high is highest and low is lowest
    for i in range(len(idx)):
        data['high'][i] = max(data['open'][i], data['close'][i], data['high'][i])
        data['low'][i] = min(data['open'][i], data['close'][i], data['low'][i])

    dummy_df = pd.DataFrame(data, index=idx)
    dummy_df['swing_high'] = np.nan
    dummy_df['swing_low'] = np.nan
    dummy_df.loc[dummy_df.index[5], 'swing_high'] = dummy_df.loc[dummy_df.index[5], 'high']
    dummy_df.loc[dummy_df.index[10], 'swing_low'] = dummy_df.loc[dummy_df.index[10], 'low']
    dummy_df.loc[dummy_df.index[15], 'swing_high'] = dummy_df.loc[dummy_df.index[15], 'high']

    choch_test_points = [(dummy_df.index[8], dummy_df.loc[dummy_df.index[10], 'low'], 'bearish_choch_test')]
    ltf_test_signals = [(dummy_df.index[12], dummy_df.loc[dummy_df.index[12], 'close'], 'ltf_bullish_confirm_test')]

    plot_ohlc_with_swings(dummy_df, dummy_df, "DUMMY", "M5", "Test Plot", 
                          choch_points=choch_test_points, 
                          ltf_signals=ltf_test_signals,
                          save_path="plots/dummy_plot.png")
    print("Plotting test finished. Check for plots/dummy_plot.png")