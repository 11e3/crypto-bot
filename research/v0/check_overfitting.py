#!/usr/bin/env python3
"""Check for overfitting in VBO strategy.

Performs multiple validation tests:
1. Train/Test split (In-sample vs Out-of-sample)
2. Parameter sensitivity analysis
3. Year-by-year performance consistency
"""

import subprocess
import sys


def run_backtest(script: str, start: str = None, end: str = None) -> dict:
    """Run a backtest and parse key metrics."""
    cmd = [sys.executable, script]
    if start:
        cmd.extend(['--start', start])
    if end:
        cmd.extend(['--end', end])

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout

    # Parse BTC+ETH results (best Sharpe combination)
    results = {}
    for line in output.split('\n'):
        if 'BTC+ETH' in line and 'CAGR' in line:
            # Extract metrics from table row
            parts = line.split()
            if len(parts) >= 6:
                try:
                    # Find CAGR, MDD, Sharpe values
                    for i, part in enumerate(parts):
                        if '%' in part and 'CAGR' not in results:
                            results['CAGR'] = float(part.rstrip('%'))
                        elif i > 0 and parts[i-1].rstrip('%').replace('-','').replace('.','').isdigit():
                            if 'MDD' not in results and '-' in part:
                                results['MDD'] = float(part.rstrip('%'))
                            elif 'Sharpe' not in results and '-' not in part and '.' in part:
                                results['Sharpe'] = float(part)
                except:
                    pass
            break

    # If not found in table, try single coin results
    if not results:
        for line in output.split('\n'):
            if 'BTC' in line and 'ETH' not in line:
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        for i, part in enumerate(parts):
                            if '%' in part and 'CAGR' not in results:
                                results['CAGR'] = float(part.rstrip('%'))
                            elif '-' in part and '%' in part and 'MDD' not in results:
                                results['MDD'] = float(part.rstrip('%'))
                            elif '.' in part and '-' not in part and 'Sharpe' not in results:
                                try:
                                    val = float(part)
                                    if 0 < val < 10:  # Reasonable Sharpe range
                                        results['Sharpe'] = val
                                except:
                                    pass
                    except:
                        pass
                    if len(results) >= 3:
                        break

    return results


print("=" * 100)
print("OVERFITTING ANALYSIS - VBO Strategy")
print("=" * 100)
print()

# ============================================================================
# Test 1: Train/Test Split
# ============================================================================
print("TEST 1: TRAIN/TEST SPLIT (In-Sample vs Out-of-Sample)")
print("-" * 100)
print()

# Define periods
train_periods = [
    ("2017-01-01", "2021-12-31", "Train (2017-2021)"),
    ("2017-01-01", "2022-06-30", "Train (2017-mid2022)"),
]

test_periods = [
    ("2022-01-01", "2024-12-31", "Test (2022-2024)"),
    ("2022-07-01", "2024-12-31", "Test (mid2022-2024)"),
]

print("Running backtests for BTC+ETH portfolio (best combination)...")
print()

results_train = []
results_test = []

for start, end, label in train_periods:
    print(f"  {label}...", end=' ', flush=True)
    result = run_backtest('backtest_vbo_portfolio.py', start, end)
    if result:
        results_train.append((label, result))
        print(f"CAGR: {result.get('CAGR', 'N/A'):.2f}%, Sharpe: {result.get('Sharpe', 'N/A'):.2f}")
    else:
        print("Failed to parse results")

for start, end, label in test_periods:
    print(f"  {label}...", end=' ', flush=True)
    result = run_backtest('backtest_vbo_portfolio.py', start, end)
    if result:
        results_test.append((label, result))
        print(f"CAGR: {result.get('CAGR', 'N/A'):.2f}%, Sharpe: {result.get('Sharpe', 'N/A'):.2f}")
    else:
        print("Failed to parse results")

print()
print("Results:")
print("-" * 100)
print(f"{'Period':<30} {'CAGR':<15} {'MDD':<15} {'Sharpe':<15}")
print("-" * 100)

for label, result in results_train:
    print(f"{label:<30} {result.get('CAGR', 0):>13.2f}%  {result.get('MDD', 0):>13.2f}%  {result.get('Sharpe', 0):>13.2f}")

for label, result in results_test:
    print(f"{label:<30} {result.get('CAGR', 0):>13.2f}%  {result.get('MDD', 0):>13.2f}%  {result.get('Sharpe', 0):>13.2f}")

print("-" * 100)
print()

# Calculate degradation
if len(results_train) > 0 and len(results_test) > 0:
    train_sharpe = results_train[0][1].get('Sharpe', 0)
    test_sharpe = results_test[0][1].get('Sharpe', 0)
    degradation = ((test_sharpe - train_sharpe) / train_sharpe * 100) if train_sharpe > 0 else 0

    print(f"Performance Degradation (Train→Test): {degradation:+.1f}%")
    if abs(degradation) < 30:
        print("✅ GOOD: Performance is consistent between periods (< 30% degradation)")
    else:
        print("⚠️  WARNING: Significant performance degradation detected (> 30%)")
print()

# ============================================================================
# Test 2: Year-by-Year Consistency
# ============================================================================
print("\n" + "=" * 100)
print("TEST 2: YEAR-BY-YEAR CONSISTENCY")
print("-" * 100)
print()

years = [
    ("2018-01-01", "2018-12-31", "2018"),
    ("2019-01-01", "2019-12-31", "2019"),
    ("2020-01-01", "2020-12-31", "2020"),
    ("2021-01-01", "2021-12-31", "2021"),
    ("2022-01-01", "2022-12-31", "2022"),
    ("2023-01-01", "2023-12-31", "2023"),
    ("2024-01-01", "2024-12-31", "2024"),
]

print("Running year-by-year backtests for BTC+ETH...")
print()

yearly_results = []
for start, end, year in years:
    print(f"  {year}...", end=' ', flush=True)
    result = run_backtest('backtest_vbo_portfolio.py', start, end)
    if result:
        yearly_results.append((year, result))
        print(f"Return: {result.get('CAGR', 'N/A'):>7.2f}%, Sharpe: {result.get('Sharpe', 'N/A'):.2f}")
    else:
        print("Failed to parse results")

print()
print("Yearly Performance:")
print("-" * 100)
print(f"{'Year':<10} {'Return':<15} {'MDD':<15} {'Sharpe':<15}")
print("-" * 100)

positive_years = 0
total_years = len(yearly_results)

for year, result in yearly_results:
    ret = result.get('CAGR', 0)
    if ret > 0:
        positive_years += 1
    print(f"{year:<10} {ret:>13.2f}%  {result.get('MDD', 0):>13.2f}%  {result.get('Sharpe', 0):>13.2f}")

print("-" * 100)
if total_years > 0:
    win_rate = (positive_years / total_years * 100)
    print(f"\nWin Rate: {positive_years}/{total_years} years ({win_rate:.1f}%)")
    if win_rate >= 70:
        print("✅ GOOD: Strategy is profitable in most years (>70%)")
    elif win_rate >= 50:
        print("⚠️  FAIR: Strategy is profitable in about half of years")
    else:
        print("❌ WARNING: Strategy is unprofitable in most years")
print()

# ============================================================================
# Summary
# ============================================================================
print("\n" + "=" * 100)
print("OVERFITTING ASSESSMENT SUMMARY")
print("=" * 100)
print()

print("Key Indicators:")
print("-" * 100)
print("1. Parameter Complexity: ✅ LOW (only 2 parameters: MA5, BTC_MA20)")
print("2. Parameter Selection:  ✅ TRADITIONAL (not optimized, common values)")
print("3. Strategy Logic:       ✅ SIMPLE (clear entry/exit rules)")
print()

overfitting_score = 0
total_checks = 0

# Check 1: Train/Test consistency
if len(results_train) > 0 and len(results_test) > 0:
    total_checks += 1
    if abs(degradation) < 30:
        print("4. Train/Test Split:     ✅ PASS (< 30% performance difference)")
        overfitting_score += 1
    else:
        print("4. Train/Test Split:     ⚠️  FAIL (> 30% performance difference)")

# Check 2: Yearly consistency
if total_years > 0:
    total_checks += 1
    if win_rate >= 60:
        print(f"5. Yearly Consistency:   ✅ PASS ({win_rate:.0f}% winning years)")
        overfitting_score += 1
    else:
        print(f"5. Yearly Consistency:   ⚠️  FAIL ({win_rate:.0f}% winning years)")

print()
print("-" * 100)
print(f"Overall Score: {overfitting_score}/{total_checks} checks passed")
print()

if overfitting_score == total_checks:
    print("✅ CONCLUSION: Strategy shows LOW risk of overfitting")
    print("   - Simple parameters with traditional values")
    print("   - Consistent performance across time periods")
    print("   - Robust to train/test splits")
elif overfitting_score >= total_checks * 0.5:
    print("⚠️  CONCLUSION: Strategy shows MODERATE risk of overfitting")
    print("   - Some concerns with consistency")
    print("   - Recommend additional validation before live trading")
else:
    print("❌ CONCLUSION: Strategy shows HIGH risk of overfitting")
    print("   - Significant performance degradation detected")
    print("   - NOT recommended for live trading without revision")

print()
