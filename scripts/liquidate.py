#!/usr/bin/env python3
"""Liquidate all coins to KRW across all accounts.

Usage:
    python liquidate.py           # Dry run (show what would be sold)
    python liquidate.py --execute # Actually sell
"""

import os
import sys

try:
    import pyupbit

    from bot import load_env
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

DRY_RUN = "--execute" not in sys.argv


def get_accounts() -> list[tuple[str, pyupbit.Upbit]]:
    """Load all accounts from env."""
    accounts = []
    for i in range(1, 100):
        name = os.getenv(f"ACCOUNT_{i}_NAME")
        key = os.getenv(f"ACCOUNT_{i}_ACCESS_KEY")
        secret = os.getenv(f"ACCOUNT_{i}_SECRET_KEY")
        if not all([name, key, secret]):
            break
        accounts.append((name, pyupbit.Upbit(key, secret)))
    return accounts


def liquidate_account(_name: str, api: pyupbit.Upbit) -> float:
    """Sell all coins in account. Returns total KRW value."""
    total = 0.0
    try:
        balances = api.get_balances()
    except Exception as e:
        print(f"  Error getting balances: {e}")
        return 0.0

    if not isinstance(balances, list):
        print(f"  Invalid response: {balances}")
        return 0.0

    for bal in balances:
        currency = bal["currency"]
        if currency == "KRW":
            continue

        amount = float(bal["balance"])
        if amount <= 0:
            continue

        ticker = f"KRW-{currency}"
        try:
            price = pyupbit.get_current_price(ticker)
        except Exception:
            price = None
        if not price:
            print(f"  {currency}: no KRW market, skip")
            continue

        value = amount * price
        if value < 5000:
            print(f"  {currency}: {value:,.0f} KRW (< 5000, skip)")
            continue

        if DRY_RUN:
            print(f"  {currency}: {amount:.8f} × {price:,.0f} = {value:,.0f} KRW")
            total += value
        else:
            print(f"  {currency}: selling {amount:.8f} @ {price:,.0f}...", end=" ")
            result = api.sell_market_order(ticker, amount)
            if result and "uuid" in result:
                print("OK")
                total += value
            else:
                print(f"FAILED: {result}")

    return total


def main():
    load_env()
    accounts = get_accounts()

    if not accounts:
        print("No accounts configured")
        sys.exit(1)

    mode = "DRY RUN" if DRY_RUN else "EXECUTING"
    print(f"=== {mode} === ({len(accounts)} accounts)\n")

    grand_total = 0.0
    for name, api in accounts:
        print(f"[{name}]")
        total = liquidate_account(name, api)
        if total > 0:
            print(f"  → {total:,.0f} KRW\n")
        else:
            print("  → nothing to sell\n")
        grand_total += total

    print(f"Total: {grand_total:,.0f} KRW")
    if DRY_RUN:
        print("\nRun with --execute to actually sell")


if __name__ == "__main__":
    main()
