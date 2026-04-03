"""Ornstein-Uhlenbeck Mean Reversion strategy (Leung & Li).

Models log-price as an OU process, estimates parameters via rolling OLS,
and trades when the price deviates beyond the equilibrium z-score.

Reference: Leung & Li, "Optimal Mean Reversion Trading: Mathematical
           Analysis and Practical Applications".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class OUMeanReversionStrategy(BaseStrategy):
    """Trade mean reversion using a rolling Ornstein-Uhlenbeck fit.

    Parameters
    ----------
    ou_window:
        Rolling window (days) for estimating OU parameters.
    entry_z:
        Z-score threshold to open a position (|z| > entry_z).
    exit_z:
        Z-score threshold to close a position (|z| < exit_z).
    stop_z:
        Hard stop: close at loss if |z| exceeds this (divergence, not convergence).
    min_halflife:
        Reject fits where the implied half-life is shorter than this (days).
    max_halflife:
        Reject fits where the implied half-life is longer than this (days).
    """

    strategy_name = "ou_mean_reversion"

    def __init__(
        self,
        ou_window: int = 120,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        stop_z: float = 4.0,
        min_halflife: float = 5.0,
        max_halflife: float = 200.0,
    ) -> None:
        if exit_z >= entry_z:
            raise ValueError("exit_z must be smaller than entry_z.")
        self.ou_window = ou_window
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z
        self.min_halflife = min_halflife
        self.max_halflife = max_halflife

    @classmethod
    def get_param_ranges(cls) -> dict[str, list]:
        return {
            "ou_window": [60, 90, 120, 180],
            "entry_z": [1.5, 2.0, 2.5],
            "exit_z": [0.0, 0.25, 0.5],
            "stop_z": [3.0, 4.0, 5.0],
        }

    # ------------------------------------------------------------------
    # OU parameter estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _fit_ou(log_prices: np.ndarray) -> tuple[float, float, float]:
        """Estimate OU params (theta, mu, sigma) via OLS on discrete increments.

        Returns (theta, mu, sigma) or (nan, nan, nan) on failure.
        theta = long-run mean
        mu    = speed of mean reversion  (annualised)
        sigma = diffusion volatility
        """
        if len(log_prices) < 10:
            return np.nan, np.nan, np.nan

        x = log_prices[:-1]
        dx = np.diff(log_prices)

        # OLS: dx = a + b*x + eps
        n = len(x)
        sx = x.sum()
        sdx = dx.sum()
        sxx = (x * x).sum()
        sxdx = (x * dx).sum()

        denom = n * sxx - sx * sx
        if abs(denom) < 1e-12:
            return np.nan, np.nan, np.nan

        b = (n * sxdx - sx * sdx) / denom
        a = (sdx - b * sx) / n

        if b >= 0:  # not mean-reverting
            return np.nan, np.nan, np.nan

        mu = -b          # speed of reversion (dt=1 day)
        theta = -a / b   # long-run mean
        residuals = dx - (a + b * x)
        sigma = residuals.std(ddof=2)

        # Annualise mu
        mu_annualised = mu * 252
        return theta, mu_annualised, sigma

    def _rolling_zscore(self, log_prices: pd.Series) -> pd.Series:
        """Compute rolling OU z-score series."""
        n = len(log_prices)
        zscores = np.full(n, np.nan)
        lp = log_prices.to_numpy()

        for i in range(self.ou_window, n):
            window = lp[i - self.ou_window: i]
            theta, mu_ann, sigma = self._fit_ou(window)

            if np.isnan(mu_ann) or mu_ann <= 0:
                continue

            halflife = np.log(2) / (mu_ann / 252)  # back to daily
            if halflife < self.min_halflife or halflife > self.max_halflife:
                continue

            # Equilibrium std of OU process
            mu_daily = mu_ann / 252
            sigma_eq = sigma / np.sqrt(2 * mu_daily) if mu_daily > 0 else np.nan
            if np.isnan(sigma_eq) or sigma_eq < 1e-10:
                continue

            zscores[i] = (lp[i] - theta) / sigma_eq

        return pd.Series(zscores, index=log_prices.index)

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        prepared = self.prepare_data(data)
        self.require_columns(prepared, "Close")

        log_prices = np.log(prepared["Close"].replace(0.0, np.nan))
        zscore = self._rolling_zscore(log_prices)

        long_entry = zscore < -self.entry_z
        long_exit = (zscore > -self.exit_z) | (zscore < -self.stop_z)
        short_entry = zscore > self.entry_z
        short_exit = (zscore < self.exit_z) | (zscore > self.stop_z)

        signals = self.build_signals(
            prepared,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )
        return self.finalize_signals(prepared, signals)
