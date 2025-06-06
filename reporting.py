# forex_backtester_cli/reporting.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from config import INITIAL_CAPITAL

# forex_backtester_cli/reporting.py
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
# from config import INITIAL_CAPITAL, TP_RR_RATIO # TP_RR_RATIO will come from strategy_params_used
from config import INITIAL_CAPITAL # Keep INITIAL_CAPITAL if used for other calcs, though R-focus reduces its direct use here

def calculate_performance_metrics(trades_log: list, 
                                  initial_capital: float, 
                                  symbol: str, 
                                  pip_size: float,
                                  strategy_params_used: dict, 
                                  session_results_path: str):
    """
    Calculates and prints key performance metrics from a list of trades for a single symbol.
    Saves the equity curve plot to the specified session path.
    Returns the report as a string.
    """
    if not trades_log:
        report_text = f"No trades to report for {symbol}.\n"
        print(report_text)
        return report_text 

    df_trades = pd.DataFrame(trades_log)

    # Ensure numeric types and handle potential NaNs
    df_trades['pnl_pips'] = pd.to_numeric(df_trades['pnl_pips'], errors='coerce')
    df_trades['pnl_R'] = pd.to_numeric(df_trades['pnl_R'], errors='coerce').fillna(0) 
    df_trades['max_R_achieved_for_analysis'] = pd.to_numeric(df_trades.get('max_R_achieved_for_analysis'), errors='coerce').fillna(0)
    
    total_trades = len(df_trades)
    
    # Categorize trades
    winning_trades = df_trades[df_trades['pnl_R'] > 0.01] # Wins if R > 0.01 (to exclude tiny positives from BE)
    losing_trades_strict = df_trades[df_trades['pnl_R'] < -0.01] # Losses if R < -0.01
    
    # Breakeven trades: status is 'closed_sl_be' AND pnl_R is close to 0
    # Or any trade where pnl_R is very close to 0, regardless of status (e.g. EOD close at entry)
    breakeven_trades = df_trades[
        ((df_trades['status'] == 'closed_sl_be') & (abs(df_trades['pnl_R']) <= 0.01)) |
        ((df_trades['status'] != 'closed_sl_be') & (abs(df_trades['pnl_R']) <= 0.01))
    ]
    # Ensure trades counted as BE are not also counted as strict wins/losses
    winning_trades = winning_trades[~winning_trades.index.isin(breakeven_trades.index)]
    losing_trades_strict = losing_trades_strict[~losing_trades_strict.index.isin(breakeven_trades.index)]

    num_wins = len(winning_trades)
    num_losses = len(losing_trades_strict) # Use strict losses for loss count
    num_be = len(breakeven_trades)
    num_sl_be_hits = len(df_trades[df_trades['status'] == 'closed_sl_be']) # Count all BE SL hits

    win_rate = (num_wins / total_trades) * 100 if total_trades > 0 else 0
    loss_rate = (num_losses / total_trades) * 100 if total_trades > 0 else 0 # Based on strict losses

    avg_win_r = winning_trades['pnl_R'].mean() if num_wins > 0 else 0
    avg_loss_r = losing_trades_strict['pnl_R'].mean() if num_losses > 0 else 0 # Use strict losses for avg loss

    expectancy_r = 0
    if total_trades > 0:
        # Expectancy considers all outcomes, including breakevens (which have pnl_R ~ 0)
        # So, use win_rate (for wins) and loss_rate (for strict losses). BE trades contribute ~0 to expectancy.
        expectancy_r = ( (win_rate / 100) * avg_win_r ) + \
                       ( (loss_rate / 100) * avg_loss_r ) 
    
    total_r_won = winning_trades['pnl_R'].sum()
    total_r_lost = abs(losing_trades_strict['pnl_R'].sum()) # Sum of strict losses
    profit_factor = total_r_won / total_r_lost if total_r_lost > 0 else np.inf if total_r_won > 0 else 1.0

    df_trades['cumulative_R'] = df_trades['pnl_R'].cumsum()
    
    peak_r = df_trades['cumulative_R'].expanding(min_periods=1).max()
    drawdown_r_series = peak_r - df_trades['cumulative_R']
    max_drawdown_r = drawdown_r_series.max() if not drawdown_r_series.empty else 0.0
    
    avg_max_r_analysis = df_trades['max_R_achieved_for_analysis'].mean() if not df_trades['max_R_achieved_for_analysis'].empty else 0.0
    median_max_r_analysis = df_trades['max_R_achieved_for_analysis'].median() if not df_trades['max_R_achieved_for_analysis'].empty else 0.0

    tp_rr_ratio_for_report = strategy_params_used.get("TP_RR_RATIO", "N/A (Not in params)")
    df_trades['entry_time'] = pd.to_datetime(df_trades['entry_time'])
    # Ensure exit_time exists and handle NaT for trades that might not have exited (though all should have a status)
    df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'], errors='coerce') 
    
    period_start_str = df_trades['entry_time'].min().strftime('%Y-%m-%d %H:%M') if not df_trades.empty and df_trades['entry_time'].notna().any() else "N/A"
    period_end_str = df_trades['exit_time'].max().strftime('%Y-%m-%d %H:%M') if not df_trades.empty and df_trades['exit_time'].notna().any() else "N/A"

    report_lines = [
        f"--------------------------------------------------",
        f"Backtest Performance Report for: {symbol}",
        f"Period: {period_start_str} to {period_end_str}",
        f"Target R:R Ratio (TP): 1:{tp_rr_ratio_for_report}",
        f"--------------------------------------------------",
        f"Total Trades:              {total_trades}",
        f"Winning Trades (>0.01R):   {num_wins} ({win_rate:.2f}%)",
        f"Losing Trades (<-0.01R):   {num_losses} ({loss_rate:.2f}%)",
        f"Breakeven Trades (at BE SL): {num_sl_be_hits}",
        f"Other Breakeven (~0R):   {num_be - num_sl_be_hits if num_be >= num_sl_be_hits else num_be}", # BE not from SL_BE status
        f"--------------------------------------------------",
        f"Average Win (R):           {avg_win_r:.2f} R",
        f"Average Loss (R):          {avg_loss_r:.2f} R ",
        f"Expectancy (R):            {expectancy_r:.2f} R per trade",
        f"Profit Factor:             {profit_factor:.2f}",
        f"--------------------------------------------------",
        f"Total R Won:               {total_r_won:.2f} R",
        f"Total R Lost:              {total_r_lost:.2f} R",
        f"Net Profit (R):            {df_trades['cumulative_R'].iloc[-1] if not df_trades.empty else 0.0:.2f} R",
        f"--------------------------------------------------",
        f"Max Drawdown (R):          {max_drawdown_r:.2f} R",
        f"Avg Max R Achieved (Analysis):   {avg_max_r_analysis:.2f} R (capped at 5R)",
        f"Median Max R Achieved (Analysis):{median_max_r_analysis:.2f} R (capped at 5R)",
        f"--------------------------------------------------",
        f"R-Level Achievement Counts (Analysis up to 5R):"
    ]
    
    r_levels_to_report_analysis = strategy_params_used.get("R_LEVELS_TO_TRACK", []) + [3.5, 4.0, 4.5, 5.0]
    all_r_levels_for_report = sorted(list(set(r_levels_to_report_analysis)))

    for r_val in all_r_levels_for_report:
        if r_val > 5.0: continue 
        col_name = f'{r_val:.1f}R_achieved' # Ensure consistent naming with .1f for float keys
        count = df_trades[col_name].sum() if col_name in df_trades.columns else 0
        percentage = (count / total_trades) * 100 if total_trades > 0 else 0
        report_lines.append(f"    {r_val:.1f}R Achieved:            {count} trades ({percentage:.2f}%)")
    report_lines.append(f"--------------------------------------------------")
    
    report_text = "\n".join(report_lines)
    print(report_text) 
    
    if not df_trades.empty:
        plot_dir = os.path.join(session_results_path, "EquityCurves") 
        os.makedirs(plot_dir, exist_ok=True)
        equity_curve_path = os.path.join(plot_dir, f"{symbol}_equity_curve_R.png")
        
        plt.figure(figsize=(12, 6))
        plt.plot(df_trades.index, df_trades['cumulative_R'], label=f'Equity Curve (R) for {symbol}')
        plt.title(f'Cumulative R Profit Over Trades - {symbol}')
        plt.xlabel('Trade Number'); plt.ylabel('Cumulative R')
        plt.legend(); plt.grid(True)
        try:
            plt.savefig(equity_curve_path)
            print(f"Equity curve saved to {equity_curve_path}")
        except Exception as e: print(f"Error saving equity curve plot for {symbol}: {e}")
        plt.close()

    return report_text

def calculate_portfolio_performance_metrics(all_symbols_trades_logs: dict, 
                                            initial_capital: float, 
                                            strategy_params_used: dict,
                                            session_results_path: str):
    if not all_symbols_trades_logs:
        report_text = "No trade logs provided for portfolio reporting.\n" # Define report_text
        print(report_text)
        return report_text # Return the defined message

    combined_trades_list = []
    for symbol, trades_log in all_symbols_trades_logs.items():
        if trades_log: 
            for trade in trades_log:
                if trade.get('exit_time') is not None and trade.get('pnl_R') is not None:
                    trade['symbol_id'] = symbol 
                    combined_trades_list.append(trade)
                elif trade.get('status') == 'open' and trade.get('pnl_R') is not None: 
                    trade['symbol_id'] = symbol
                    combined_trades_list.append(trade)

    if not combined_trades_list:
        report_text = "No valid closed/completed trades found across all symbols for portfolio report.\n" # Define report_text
        print(report_text)
        return report_text # Return the defined message
        
    df_portfolio_trades = pd.DataFrame(combined_trades_list)
    # ... (rest of the function as in the previous correct version) ...
    df_portfolio_trades['exit_time'] = pd.to_datetime(df_portfolio_trades['exit_time'])
    df_portfolio_trades['entry_time'] = pd.to_datetime(df_portfolio_trades['entry_time'])
    df_portfolio_trades['pnl_R'] = pd.to_numeric(df_portfolio_trades['pnl_R'], errors='coerce').fillna(0)
    df_portfolio_trades.sort_values(by=['exit_time', 'entry_time', 'id'], inplace=True)
    df_portfolio_trades.reset_index(drop=True, inplace=True) 

    df_portfolio_trades['portfolio_cumulative_R'] = df_portfolio_trades['pnl_R'].cumsum()
    peak_portfolio_r = df_portfolio_trades['portfolio_cumulative_R'].expanding(min_periods=1).max()
    drawdown_portfolio_r_series = peak_portfolio_r - df_portfolio_trades['portfolio_cumulative_R']
    max_drawdown_portfolio_r = drawdown_portfolio_r_series.max() if not drawdown_portfolio_r_series.empty else 0.0
    
    total_portfolio_trades = len(df_portfolio_trades)
    num_wins_portfolio = len(df_portfolio_trades[df_portfolio_trades['pnl_R'] > 0])
    num_losses_portfolio = len(df_portfolio_trades[df_portfolio_trades['pnl_R'] < 0])
    num_be_portfolio = len(df_portfolio_trades[df_portfolio_trades['pnl_R'] == 0])
    win_rate_portfolio = (num_wins_portfolio / total_portfolio_trades) * 100 if total_portfolio_trades > 0 else 0
    
    avg_win_r_portfolio = df_portfolio_trades[df_portfolio_trades['pnl_R'] > 0]['pnl_R'].mean() if num_wins_portfolio > 0 else 0
    avg_loss_r_portfolio = df_portfolio_trades[df_portfolio_trades['pnl_R'] < 0]['pnl_R'].mean() if num_losses_portfolio > 0 else 0 
    
    expectancy_r_portfolio = 0
    if total_portfolio_trades > 0:
        loss_rate_portfolio = num_losses_portfolio / total_portfolio_trades
        expectancy_r_portfolio = ( (win_rate_portfolio / 100) * avg_win_r_portfolio ) + \
                                 ( loss_rate_portfolio * avg_loss_r_portfolio )

    total_r_won_portfolio = df_portfolio_trades[df_portfolio_trades['pnl_R'] > 0]['pnl_R'].sum()
    total_r_lost_portfolio = abs(df_portfolio_trades[df_portfolio_trades['pnl_R'] < 0]['pnl_R'].sum())
    profit_factor_portfolio = total_r_won_portfolio / total_r_lost_portfolio if total_r_lost_portfolio > 0 else np.inf if total_r_won_portfolio > 0 else 1.0

    tp_rr_ratio_for_report = strategy_params_used.get("TP_RR_RATIO", "N/A")
    
    report_lines = [
        "\n\n--- Portfolio Performance Report ---",
        f"Symbols: {', '.join(all_symbols_trades_logs.keys())}",
        f"Strategy Target R:R Ratio (TP): 1:{tp_rr_ratio_for_report}"
    ]
    if not df_portfolio_trades.empty:
        report_lines.append(f"Period: {df_portfolio_trades['entry_time'].min().strftime('%Y-%m-%d')} to {df_portfolio_trades['exit_time'].max().strftime('%Y-%m-%d')}")
    report_lines.extend([
        "------------------------------------",
        f"Total Trades in Portfolio: {total_portfolio_trades}",
        f"Winning Trades:            {num_wins_portfolio} ({win_rate_portfolio:.2f}%)",
        f"Losing Trades:             {num_losses_portfolio}",
        f"Breakeven Trades:          {num_be_portfolio}",
        f"Average Win (R):           {avg_win_r_portfolio:.2f} R",
        f"Average Loss (R):          {avg_loss_r_portfolio:.2f} R",
        f"Expectancy (R):            {expectancy_r_portfolio:.2f} R per trade",
        f"Profit Factor:             {profit_factor_portfolio:.2f}"
    ])
    if not df_portfolio_trades.empty:
        report_lines.append(f"Net Portfolio Profit (R):  {df_portfolio_trades['portfolio_cumulative_R'].iloc[-1]:.2f} R")
    else:
        report_lines.append(f"Net Portfolio Profit (R):  0.00 R")
    report_lines.extend([
        f"Max Portfolio Drawdown (R):{max_drawdown_portfolio_r:.2f} R",
        "------------------------------------"
    ])
    report_text = "\n".join(report_lines) # Define report_text here before printing
    print(report_text)

    if not df_portfolio_trades.empty:
        plot_dir = os.path.join(session_results_path, "EquityCurves") 
        os.makedirs(plot_dir, exist_ok=True)
        equity_curve_path = os.path.join(plot_dir, "portfolio_equity_curve_R.png")
        
        plt.figure(figsize=(12, 6))
        plt.plot(df_portfolio_trades.index, df_portfolio_trades['portfolio_cumulative_R'], label='Portfolio Equity Curve (R)')
        plt.title('Portfolio Cumulative R Profit Over Trades (Sorted by Exit Time)')
        plt.xlabel('Trade Number (Chronological by Exit)')
        plt.ylabel('Cumulative R')
        plt.legend(); plt.grid(True)
        try:
            plt.savefig(equity_curve_path)
            print(f"Portfolio equity curve saved to {equity_curve_path}")
        except Exception as e: print(f"Error saving portfolio equity curve plot: {e}")
        plt.close()
        
    return report_text # Now report_text is always defined before return
