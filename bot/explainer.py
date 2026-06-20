"""Plain-English narrator for bot decisions. Non-critical: never raises into the loop."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from bot.glossary import detect_terms
from bot.reason_derivers import derive_reason

logger = logging.getLogger(__name__)


class Explainer:
    """Writes a human journal (markdown) and a structured feed (jsonl)."""

    def __init__(self, log_dir: str | Path = "logs") -> None:
        self.log_dir = Path(log_dir)
        self.journal_dir = self.log_dir / "journal"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.log_dir / "journal.jsonl"

    def explain_entry(
        self, event: dict, data: pd.DataFrame, strategy_name: str, params: dict
    ) -> tuple[str, list[str]]:
        """Narrate a position entry. Returns (narrative, glossary_terms)."""
        try:
            direction = event.get("direction", "long")
            qty = event.get("qty", 0)
            symbol = event.get("symbol", "?")
            price = float(event.get("price", 0.0))
            notional = qty * price
            reason = derive_reason(strategy_name, data, direction, params)

            if reason["zone"] == "cheap":
                why = f"price ${reason['close']:,.2f} dipped to the {reason['band_name']} (${reason['band']:,.2f}) — an unusually cheap zone"
            elif reason["zone"] == "expensive":
                why = f"price ${reason['close']:,.2f} stretched to the {reason['band_name']} (${reason['band']:,.2f}) — an unusually expensive zone"
            else:
                why = f"the {strategy_name} strategy signalled a {direction} entry"

            verb = "Bought" if direction == "long" else "Shorted"
            narrative = (
                f"{verb} {qty} {symbol} @ ${price:,.2f} (about ${notional:,.0f}); {why}. "
                f"Stop-loss ${event.get('stop_loss', 0):,.2f}, take-profit ${event.get('take_profit', 0):,.2f}. "
                f"This is a mean reversion bet sized by the risk per trade rule."
            )
            return narrative, self._emit("entry", symbol, narrative)
        except Exception:
            logger.exception("Explainer.explain_entry failed; trading continues")
            return "", []

    def _emit(self, kind: str, symbol: str, narrative: str) -> list[str]:
        """Detect glossary terms, append to md + jsonl. Best-effort."""
        terms = detect_terms(narrative)
        try:
            now = datetime.now()
            md_path = self.journal_dir / f"{now.date()}.md"
            with md_path.open("a", encoding="utf-8") as f:
                f.write(f"### {now.strftime('%H:%M:%S')} — {kind} {symbol}\n\n{narrative}\n\n")
            record = {
                "timestamp": now.isoformat(),
                "kind": kind,
                "symbol": symbol,
                "narrative": narrative,
                "terms": terms,
            }
            with self.jsonl_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            logger.exception("Explainer._emit failed to write journal; trading continues")
        return terms
