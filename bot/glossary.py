"""Beginner-friendly glossary of trading terms used in the journal."""
from __future__ import annotations

import re

GLOSSARY: dict[str, str] = {
    "Bollinger band": "A price envelope a set number of standard deviations above and below a moving average. Touching the lower band is often read as 'unusually cheap', the upper band as 'unusually expensive'.",
    "moving average": "The average closing price over the last N bars, used to smooth out noise and show the trend.",
    "standard deviation": "A measure of how spread out prices are. Bigger standard deviation means more volatile.",
    "Sharpe ratio": "Return earned per unit of risk. Higher is better; below 1 is weak, above 1 is decent for a simple strategy.",
    "drawdown": "How far the account has fallen from its previous peak. Max drawdown is the worst such drop.",
    "stop-loss": "A pre-set exit price that caps the loss on a trade if it moves against you.",
    "take-profit": "A pre-set exit price that locks in profit once a trade moves in your favour.",
    "trailing stop": "A stop-loss that ratchets up as the trade gains, protecting profit without capping upside.",
    "bracket order": "An order that ships with both a stop-loss and a take-profit attached, so the exit is automatic.",
    "position sizing": "Deciding how many shares to buy so a single trade only risks a small slice of the account.",
    "risk per trade": "The fraction of the account you allow yourself to lose on one trade (here, 2%).",
    "kill switch": "A hard stop that halts all trading, e.g. when the daily loss limit is breached.",
    "mean reversion": "The idea that price tends to snap back toward its average after stretching too far.",
    "slippage": "The difference between the price you expected and the price you actually got.",
    "commission": "The broker's fee per trade.",
    "paper trading": "Trading with fake money against live prices, to validate a strategy before risking real capital.",
    "equity curve": "A line chart of account value over time.",
    "long": "A bet that price will rise (you buy first, sell later).",
    "short": "A bet that price will fall (you sell first, buy back later).",
}


def detect_terms(text: str) -> list[str]:
    """Return canonical glossary terms appearing in ``text``.

    Matching is case-insensitive and whole-word. Terms are deduplicated and
    returned in order of first appearance.
    """
    found: list[tuple[int, str]] = []
    lowered = text.lower()
    for term in GLOSSARY:
        pattern = r"\b" + re.escape(term.lower()) + r"\b"
        match = re.search(pattern, lowered)
        if match:
            found.append((match.start(), term))
    found.sort(key=lambda pair: pair[0])
    return [term for _, term in found]
