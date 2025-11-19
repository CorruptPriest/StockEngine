import datetime as dt
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf

INDEX_TICKERS = {
    "1": ("S&P 500 (USA)", "^GSPC"),
    "2": ("NASDAQ Composite (USA)", "^IXIC"),
    "3": ("Dow Jones (USA)", "^DJI"),
    "4": ("FTSE 100 (UK)", "^FTSE"), # UK
    "5": ("DAX (Germany)", "^GDAXI"), # Germany
    "6": ("CAC 40 (France)", "^FCHI"), # France
    "7": ("NIKKEI 225 (Japan)", "^N225"), # Japan
    "8": ("Hang Seng (Hong Kong)", "^HSI"), # Hong Kong
    "9": ("NIFTY 50 (India)", "^NSEI"), # India
    "10": ("SENSEX (India)", "^BSESN"), # India
    "11": ("S&P/ASX 200 (Australia)", "^AXJO"), # Australia
    "12": ("KOSPI (S. Korea)", "^KS11"), # South Korea
    "13": ("Shanghai Composite (China)", "000001.SS"), # China
}


def get_user_selection():
    """Prints the list of indices and prompts the user for a selection."""
    print("Please select a stock market index for the Monte Carlo simulation:")
    for key, (name, ticker) in INDEX_TICKERS.items():
        print(f"{key}: {name} ({ticker})")

    while True:
        choice = input("Enter the number of your choice: ")
        if choice in INDEX_TICKERS:
            return INDEX_TICKERS[choice][1]
        else:
            print("Invalid selection. Please try again.")


def fetch_data(ticker):
    """Fetches 5 years of historical data for the selected ticker."""
    end_date = dt.datetime.now()
    start_date = end_date - dt.timedelta(days=5 * 365)
    data = yf.download(ticker, start=start_date, end=end_date)
    return data["Close"]


def run_simulation(data):
    """Runs the Monte Carlo simulation using Geometric Brownian Motion."""
    log_returns = np.log(1 + data.pct_change())
    # Drop NaN values that result from pct_change()
    log_returns = log_returns.dropna()
    drift = log_returns.mean()
    volatility = log_returns.std()

    simulations = 10000
    projection_days = 252

    # Vectorized simulation
    daily_returns = np.exp(
        drift + volatility * np.random.standard_normal((projection_days, simulations))
    )

    price_paths = np.zeros_like(daily_returns)
    price_paths[0] = data.iloc[-1]

    for t in range(1, projection_days):
        price_paths[t] = price_paths[t - 1] * daily_returns[t]

    return price_paths


def plot_results(price_paths):
    """Plots the histogram of the simulated future values."""
    plt.figure(figsize=(10, 6))
    plt.hist(price_paths[-1], bins=50, ec="black")
    plt.title("Distribution of Simulated Index Values (1 Year)")
    plt.xlabel("Simulated Index Value")
    plt.ylabel("Frequency")
    plt.show()


def print_summary(price_paths):
    """Prints the summary of the simulation results."""
    final_values = price_paths[-1]
    mean_value = np.mean(final_values)
    quantile_5 = np.percentile(final_values, 5)
    quantile_95 = np.percentile(final_values, 95)

    print("\n--- Simulation Summary ---")
    print(f"Mean Simulated Future Value: {mean_value:.2f}")
    print(f"5% Quantile: {quantile_5:.2f}")
    print(f"95% Quantile: {quantile_95:.2f}")
    print("--------------------------\n")


if __name__ == "__main__":
    selected_ticker = get_user_selection()
    adj_close_data = fetch_data(selected_ticker)

    if adj_close_data.empty:
        print(
            f"Could not download data for ticker {selected_ticker}. Please check the ticker or your internet connection."
        )
    else:
        simulation_paths = run_simulation(adj_close_data)
        print_summary(simulation_paths)
        plot_results(simulation_paths)
