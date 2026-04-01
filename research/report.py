"""HTML report generation for research pipeline results."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from research.pipeline import CandidateResult, ResearchResult

logger = logging.getLogger(__name__)


def generate_report(result: ResearchResult, output_path: str | Path) -> Path:
    """Generate an HTML report summarizing the research pipeline results."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html = _build_html(result)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Research report saved to %s", output_path)
    return output_path


def _build_html(result: ResearchResult) -> str:
    """Build the complete HTML report string."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Funnel data
    funnel_rows = f"""
    <tr><td>Generated</td><td>{result.total_generated}</td><td>—</td></tr>
    <tr><td>Passed Quick Screen</td><td>{result.total_screened}</td><td>{_pct(result.total_screened, result.total_generated)}</td></tr>
    <tr><td>Full Backtested</td><td>{result.total_backtested}</td><td>{_pct(result.total_backtested, result.total_generated)}</td></tr>
    <tr><td>Passed Filters</td><td>{result.total_filtered}</td><td>{_pct(result.total_filtered, result.total_generated)}</td></tr>
    <tr><td>Robustness Checked</td><td>{result.total_robust}</td><td>{_pct(result.total_robust, result.total_generated)}</td></tr>
    """

    # Winner details
    winner_rows = ""
    for i, w in enumerate(result.winners, 1):
        m = w.metrics
        winner_rows += f"""
        <tr>
            <td>{i}</td>
            <td>{w.strategy.name}</td>
            <td>{m.get('sharpe_ratio', 0):.3f}</td>
            <td>{m.get('total_return', 0):.2%}</td>
            <td>{m.get('win_rate', 0):.1%}</td>
            <td>{m.get('profit_factor', 0):.2f}</td>
            <td>{m.get('max_drawdown', 0):.2%}</td>
            <td>{m.get('total_trades', 0):.0f}</td>
            <td>{w.robustness_score:.1f}</td>
        </tr>
        """

    # Strategy descriptions
    desc_blocks = ""
    for i, w in enumerate(result.winners[:10], 1):
        desc_blocks += f"""
        <div class="strategy-card">
            <h3>#{i} — {w.strategy.name}</h3>
            <pre>{w.strategy.describe()}</pre>
            <p><strong>Robustness Score:</strong> {w.robustness_score:.1f} / 100</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Strategy Research Report — {timestamp}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #16213e; padding-bottom: 10px; }}
        h2 {{ color: #16213e; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; background: white;
                 box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin: 15px 0; }}
        th {{ background: #16213e; color: white; padding: 12px 15px; text-align: left; }}
        td {{ padding: 10px 15px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f0f4ff; }}
        .strategy-card {{ background: white; padding: 20px; margin: 15px 0; border-radius: 8px;
                          box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .strategy-card pre {{ background: #f8f9fa; padding: 15px; border-radius: 4px;
                              font-size: 13px; overflow-x: auto; }}
        .summary {{ display: flex; gap: 20px; flex-wrap: wrap; margin: 20px 0; }}
        .stat-box {{ background: white; padding: 20px; border-radius: 8px; flex: 1; min-width: 150px;
                     box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; }}
        .stat-box .value {{ font-size: 28px; font-weight: bold; color: #16213e; }}
        .stat-box .label {{ color: #666; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>Strategy Research Report</h1>
    <p>Generated: {timestamp} | Elapsed: {result.elapsed_seconds:.1f}s</p>

    <div class="summary">
        <div class="stat-box"><div class="value">{result.total_generated}</div><div class="label">Generated</div></div>
        <div class="stat-box"><div class="value">{result.total_screened}</div><div class="label">Screened</div></div>
        <div class="stat-box"><div class="value">{result.total_filtered}</div><div class="label">Passed Filters</div></div>
        <div class="stat-box"><div class="value">{result.total_robust}</div><div class="label">Robust Winners</div></div>
    </div>

    <h2>Survival Funnel</h2>
    <table>
        <tr><th>Phase</th><th>Count</th><th>% of Total</th></tr>
        {funnel_rows}
    </table>

    <h2>Top Strategies</h2>
    <table>
        <tr>
            <th>#</th><th>Name</th><th>Sharpe</th><th>Return</th>
            <th>Win Rate</th><th>Profit Factor</th><th>Max DD</th>
            <th>Trades</th><th>Robustness</th>
        </tr>
        {winner_rows}
    </table>

    <h2>Strategy Details</h2>
    {desc_blocks}

    <hr>
    <p style="color: #999; font-size: 12px;">
        Automated Strategy Research Pipeline — Quant Trading System
    </p>
</body>
</html>"""


def _pct(part: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{part / total:.1%}"
