"""
Generates a shareable, self-contained HTML report from a real BacktestResult (plus
optional walk-forward and Monte Carlo robustness results). No external JS/CSS
dependency — the equity curve is rendered as an inline SVG built from the actual
equity_curve series, so the report opens correctly even offline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.backtest.replay import BacktestResult
from app.backtest.walkforward import WalkForwardReport
from app.risk.metrics import summarize_performance


def _equity_curve_svg(equity_curve, width: int = 760, height: int = 220) -> str:
    if len(equity_curve) < 2:
        return "<p>Not enough data points for an equity curve.</p>"

    values = equity_curve.values
    min_v, max_v = float(values.min()), float(values.max())
    span = max_v - min_v or 1.0

    points = []
    for i, v in enumerate(values):
        x = (i / (len(values) - 1)) * (width - 40) + 20
        y = height - 20 - ((float(v) - min_v) / span) * (height - 40)
        points.append(f"{x:.1f},{y:.1f}")

    polyline = " ".join(points)
    color = "#22c55e" if values[-1] >= values[0] else "#ef4444"

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width}" height="{height}" fill="#11151f" />'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2" />'
        f'<text x="20" y="18" fill="#9ca3af" font-size="11" font-family="monospace">{max_v:,.2f}</text>'
        f'<text x="20" y="{height - 6}" fill="#9ca3af" font-size="11" font-family="monospace">{min_v:,.2f}</text>'
        f'</svg>'
    )


def _stat_row(label: str, value: str) -> str:
    return f"<tr><td class='label'>{label}</td><td class='value'>{value}</td></tr>"


def generate_html_report(
    result: BacktestResult,
    strategy_name: str = "Strategy",
    symbol: str = "",
    walk_forward: WalkForwardReport | None = None,
    robustness: dict | None = None,
) -> str:
    summary = result.summary()
    risk_metrics = summarize_performance(result.trade_returns) if len(result.trade_returns) >= 5 else None

    equity_svg = _equity_curve_svg(result.equity_curve) if len(result.equity_curve) else "<p>No equity data.</p>"

    trade_rows = "".join(
        f"<tr><td>{t.side}</td><td>{t.entry_price:.5f}</td><td>{t.exit_price:.5f}</td>"
        f"<td>{t.volume}</td><td class='{'pos' if t.pnl >= 0 else 'neg'}'>{t.pnl:+.2f}</td>"
        f"<td>{t.exit_reason}</td></tr>"
        for t in result.trades[-100:]
    )

    risk_rows = ""
    if risk_metrics:
        risk_rows = "".join(
            _stat_row(k.replace("_", " ").title(), f"{v:.4f}") for k, v in risk_metrics.items()
        )

    wf_section = ""
    if walk_forward is not None:
        wf_summary = walk_forward.summary()
        wf_win_rate = (
            f"{wf_summary.get('oos_win_rate', 0):.2%}" if wf_summary.get("total_oos_trades") else "n/a"
        )
        wf_section = (
            "<h2>Walk-Forward Out-of-Sample Results</h2><table class='stats'>"
            + _stat_row("Windows", str(wf_summary.get("total_windows", 0)))
            + _stat_row("Out-of-sample trades", str(wf_summary.get("total_oos_trades", 0)))
            + _stat_row("Out-of-sample win rate", wf_win_rate)
            + _stat_row("Out-of-sample total PnL", f"{wf_summary.get('oos_total_pnl', 0):.2f}")
            + "</table><p class='note'>Only out-of-sample segments are counted — this is what the "
              "strategy would have actually earned running the walk-forward process live, not a "
              "fitted in-sample number.</p>"
        )

    robustness_section = ""
    if robustness is not None:
        robustness_section = (
            "<h2>Monte Carlo Robustness (Bootstrap Resampling)</h2><table class='stats'>"
            + _stat_row("Final return (5th pct)", f"{robustness.get('final_return_p5', 0):.2%}")
            + _stat_row("Final return (median)", f"{robustness.get('final_return_median', 0):.2%}")
            + _stat_row("Final return (95th pct)", f"{robustness.get('final_return_p95', 0):.2%}")
            + _stat_row("Max drawdown (median)", f"{robustness.get('max_drawdown_median', 0):.2%}")
            + _stat_row("Probability of loss", f"{robustness.get('probability_of_loss', 0):.2%}")
            + "</table><p class='note'>Distribution of outcomes from resampling this backtest's "
              "actual trade sequence thousands of times — a wide spread here means the single "
              "backtest result above could easily have gone very differently on trade-order luck alone.</p>"
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    win_rate_display = f"{summary.get('win_rate', 0):.2%}" if summary.get("total_trades") else "n/a"
    final_equity_display = f"{summary.get('final_equity', 0):,.2f}" if summary.get("final_equity") else "n/a"

    style = (
        "body{background:#0b0e14;color:#e5e7eb;font-family:-apple-system,Segoe UI,sans-serif;"
        "padding:32px;max-width:900px;margin:0 auto;}"
        "h1{font-size:22px;margin-bottom:4px;}"
        "h2{font-size:16px;margin-top:32px;border-bottom:1px solid #1f2531;padding-bottom:8px;}"
        ".subtitle{color:#6b7280;font-size:13px;margin-bottom:24px;}"
        "table{width:100%;border-collapse:collapse;font-size:13px;}"
        "table.stats td{padding:6px 12px;border-bottom:1px solid #1f2531;}"
        "table.stats td.label{color:#9ca3af;} table.stats td.value{text-align:right;font-family:monospace;}"
        "table.trades th,table.trades td{padding:6px 10px;text-align:left;border-bottom:1px solid #1f2531;}"
        "table.trades th{color:#6b7280;font-weight:normal;}"
        ".pos{color:#22c55e;} .neg{color:#ef4444;} .note{color:#6b7280;font-size:12px;}"
        ".disclaimer{margin-top:40px;padding:16px;border:1px solid #1f2531;border-radius:8px;"
        "font-size:12px;color:#6b7280;}"
    )

    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8' />"
        f"<title>{strategy_name} — Backtest Report</title><style>{style}</style></head><body>"
        f"<h1>{strategy_name}{f' — {symbol}' if symbol else ''}</h1>"
        f"<div class='subtitle'>Generated {generated_at} · THEMARKET AI Quant Forex backtest engine</div>"
        "<h2>Equity Curve</h2>" + equity_svg +
        "<h2>Trade Summary</h2><table class='stats'>"
        + _stat_row("Total trades", str(summary.get("total_trades", 0)))
        + _stat_row("Win rate", win_rate_display)
        + _stat_row("Avg win", f"{summary.get('avg_win_pct', 0):.2%}")
        + _stat_row("Avg loss", f"{summary.get('avg_loss_pct', 0):.2%}")
        + _stat_row("Total PnL", f"{summary.get('total_pnl', 0):.2f}")
        + _stat_row("Final equity", final_equity_display)
        + "</table>"
        + "<h2>Risk Metrics (from per-trade returns)</h2><table class='stats'>"
        + (risk_rows or "<tr><td colspan='2'>Not enough trades for risk metrics (need 5+).</td></tr>")
        + "</table>"
        + wf_section + robustness_section
        + f"<h2>Recent Trades{'' if len(result.trades) <= 100 else f' (last 100 of {len(result.trades)})'}</h2>"
        + "<table class='trades'><tr><th>Side</th><th>Entry</th><th>Exit</th><th>Volume</th>"
          "<th>PnL</th><th>Reason</th></tr>"
        + (trade_rows or "<tr><td colspan='6'>No trades.</td></tr>")
        + "</table>"
        + "<div class='disclaimer'>Backtested performance does not guarantee future results. "
          "This report reflects a specific historical period, cost assumptions (spread/slippage), "
          "and parameter choices — see the walk-forward and Monte Carlo sections above for how "
          "sensitive the result is to those choices.</div>"
        + "</body></html>"
    )
