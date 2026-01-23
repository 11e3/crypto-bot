#!/usr/bin/env python3
"""Fetch historical OHLCV data from Upbit and save to data/ directory."""

import os
import time
from pathlib import Path

import pandas as pd
import pyupbit


def load_env_file(path: str = ".env") -> None:
    """Load .env file into os.environ."""
    env_path = Path(path)
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_symbols() -> list[str]:
    """Get symbols from environment or use defaults."""
    load_env_file()
    symbols_str = os.getenv("SYMBOLS", "BTC,ETH,XRP,TRX,ADA")
    symbols_str = symbols_str.strip()
    if symbols_str.startswith("["):
        import json
        try:
            return json.loads(symbols_str)
        except json.JSONDecodeError:
            symbols_str = symbols_str.strip("[]")
            return [s.strip().strip('"').strip("'") for s in symbols_str.split(",")]
    return [s.strip() for s in symbols_str.split(",")]


def fetch_all_ohlcv(symbol: str, interval: str = "day") -> pd.DataFrame:
    """Fetch all available OHLCV data for a symbol."""
    ticker = f"KRW-{symbol}"
    all_data = []
    to = None

    print(f"  Fetching {symbol}...", end="", flush=True)

    while True:
        try:
            df = pyupbit.get_ohlcv(ticker, interval=interval, count=200, to=to)
            if df is None or len(df) == 0:
                break

            all_data.append(df)
            to = df.index[0]

            # Rate limiting
            time.sleep(0.1)

            # Check if we got less than requested (reached the beginning)
            if len(df) < 200:
                break

        except Exception as e:
            print(f" Error: {e}")
            break

    if not all_data:
        print(" No data")
        return pd.DataFrame()

    # Combine and sort
    combined = pd.concat(all_data)
    combined = combined[~combined.index.duplicated(keep='first')]
    combined = combined.sort_index()

    print(f" {len(combined)} rows ({combined.index[0].date()} ~ {combined.index[-1].date()})")
    return combined


def main() -> None:
    """Fetch and save OHLCV data for all symbols."""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    symbols = get_symbols()
    print(f"Fetching data for {len(symbols)} symbols: {', '.join(symbols)}\n")

    for symbol in symbols:
        df = fetch_all_ohlcv(symbol)
        if len(df) > 0:
            # Reset index to make datetime a column
            df = df.reset_index()
            df.rename(columns={"index": "datetime"}, inplace=True)

            # Save to CSV
            filepath = data_dir / f"{symbol}.csv"
            df.to_csv(filepath, index=False)

    print(f"\nDone. Data saved to {data_dir}/")


if __name__ == "__main__":
    main()
