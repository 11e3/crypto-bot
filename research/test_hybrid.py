#!/usr/bin/env python3
"""Test Hybrid VBO + Funding strategy."""

from strategies import VBOStrategy, FundingStrategy, HybridVBOFundingStrategy


def test_hybrid():
    """Test hybrid strategy against standalone VBO and Funding."""
    print("\n" + "="*100)
    print("HYBRID STRATEGY TEST: VBO (Bull) + Funding (Bear)")
    print("="*100)

    symbols = ['BTC', 'ETH']
    period_start = '2022-01-01'
    period_end = '2024-12-31'

    print(f"\nTest Period: {period_start} ~ {period_end}")
    print("\nStrategy:")
    print("  - Bull Market (BTC > MA20): VBO long strategy")
    print("  - Bear Market (BTC < MA20): Funding arbitrage")
    print("  - Benefits: VBO returns in bull + Funding stability in bear")
    print()

    results = []

    # Test each symbol
    for symbol in symbols:
        print(f"\n{'='*100}")
        print(f"{symbol} - Comparing Strategies")
        print(f"{'='*100}")

        # VBO only
        vbo = VBOStrategy()
        vbo_metrics, _ = vbo.backtest(symbol, start=period_start, end=period_end)
        results.append(('VBO', symbol, vbo_metrics))

        print(f"\nVBO (Bull only):")
        print(f"  CAGR: {vbo_metrics['cagr']:.2f}%")
        print(f"  MDD: {vbo_metrics['mdd']:.2f}%")
        print(f"  Sharpe: {vbo_metrics['sharpe']:.2f}")
        print(f"  Trades: {vbo_metrics['total_trades']}")

        # Funding only
        funding = FundingStrategy()
        funding_metrics, _ = funding.backtest(symbol, start=period_start, end=period_end)
        results.append(('Funding', symbol, funding_metrics))

        print(f"\nFunding (Always on):")
        print(f"  CAGR: {funding_metrics['cagr']:.2f}%")
        print(f"  MDD: {funding_metrics['mdd']:.2f}%")
        print(f"  Sharpe: {funding_metrics['sharpe']:.2f}")
        print(f"  Funding Profit: ${funding_metrics['total_funding']:,.0f}")
        print(f"  ⚠️  Liquidation Risk: {funding_metrics['liquidation_risk']}")

        # Hybrid
        hybrid = HybridVBOFundingStrategy()
        hybrid_metrics, equity_df = hybrid.backtest(symbol, start=period_start, end=period_end)
        results.append(('Hybrid', symbol, hybrid_metrics))

        print(f"\nHybrid (VBO + Funding):")
        print(f"  CAGR: {hybrid_metrics['cagr']:.2f}%")
        print(f"  MDD: {hybrid_metrics['mdd']:.2f}%")
        print(f"  Sharpe: {hybrid_metrics['sharpe']:.2f}")
        print(f"  Total Trades: {hybrid_metrics['total_trades']}")
        print(f"  VBO Days: {hybrid_metrics['vbo_days']} ({hybrid_metrics['vbo_pct']:.1f}%)")
        print(f"  Funding Days: {hybrid_metrics['funding_days']} ({hybrid_metrics['funding_pct']:.1f}%)")
        print(f"  Total Funding: ${hybrid_metrics['total_funding']:,.0f}")

        # Compare
        print(f"\n{symbol} Comparison:")
        print(f"  Hybrid vs VBO:")
        print(f"    CAGR diff: {hybrid_metrics['cagr'] - vbo_metrics['cagr']:+.2f}%p")
        print(f"    MDD diff: {hybrid_metrics['mdd'] - vbo_metrics['mdd']:+.2f}%p")
        print(f"    Sharpe diff: {hybrid_metrics['sharpe'] - vbo_metrics['sharpe']:+.2f}")

    # Summary table
    print("\n" + "="*100)
    print("SUMMARY")
    print("="*100)
    print(f"\n{'Strategy':<15} {'Symbol':<10} {'CAGR':<12} {'MDD':<12} {'Sharpe':<12}")
    print("-" * 100)

    for strategy_name, symbol, metrics in results:
        print(f"{strategy_name:<15} {symbol:<10} {metrics['cagr']:>10.2f}%  "
              f"{metrics['mdd']:>10.2f}%  {metrics['sharpe']:>10.2f}")

    print("-" * 100)

    # Analysis
    print("\n" + "="*100)
    print("ANALYSIS")
    print("="*100)

    vbo_results = [r for r in results if r[0] == 'VBO']
    hybrid_results = [r for r in results if r[0] == 'Hybrid']

    print("\nVBO vs Hybrid:")
    for vbo_r, hybrid_r in zip(vbo_results, hybrid_results):
        symbol = vbo_r[1]
        vbo_m = vbo_r[2]
        hybrid_m = hybrid_r[2]

        print(f"\n{symbol}:")
        print(f"  CAGR: {vbo_m['cagr']:.2f}% → {hybrid_m['cagr']:.2f}% "
              f"({hybrid_m['cagr'] - vbo_m['cagr']:+.2f}%p)")
        print(f"  MDD: {vbo_m['mdd']:.2f}% → {hybrid_m['mdd']:.2f}% "
              f"({hybrid_m['mdd'] - vbo_m['mdd']:+.2f}%p)")
        print(f"  Sharpe: {vbo_m['sharpe']:.2f} → {hybrid_m['sharpe']:.2f} "
              f"({hybrid_m['sharpe'] - vbo_m['sharpe']:+.2f})")

        if hybrid_m['sharpe'] > vbo_m['sharpe']:
            print(f"  ✓ Hybrid improves risk-adjusted returns")
        else:
            print(f"  ✗ VBO has better risk-adjusted returns")

    print("\n" + "="*100)
    print("RECOMMENDATION")
    print("="*100)

    avg_hybrid_sharpe = sum(r[2]['sharpe'] for r in hybrid_results) / len(hybrid_results)
    avg_vbo_sharpe = sum(r[2]['sharpe'] for r in vbo_results) / len(vbo_results)

    print(f"\nAverage Sharpe:")
    print(f"  VBO: {avg_vbo_sharpe:.2f}")
    print(f"  Hybrid: {avg_hybrid_sharpe:.2f}")

    if avg_hybrid_sharpe > avg_vbo_sharpe:
        print(f"\n✓ HYBRID is BETTER (Sharpe +{avg_hybrid_sharpe - avg_vbo_sharpe:.2f})")
        print("  Reason: Funding provides stable returns in bear markets")
    else:
        print(f"\n✗ VBO is BETTER (Sharpe +{avg_vbo_sharpe - avg_hybrid_sharpe:.2f})")
        print("  Reason: Switching overhead or funding returns too low")

    print()


if __name__ == "__main__":
    test_hybrid()
