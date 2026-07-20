"""
Position-sizing environment, gym-style interface (reset()/step()) but hand-rolled
rather than depending on the `gym`/`gymnasium` package — the interface is trivial
enough (5-value step return, array observation, discrete action) that pulling in a
whole framework dependency isn't justified for one environment.

Scope, stated plainly: this environment does NOT learn trade direction. Direction
comes from an external signal (a simple EMA12/EMA26 trend rule by default, but any
precomputed +1/-1 array works — e.g. thresholding DirectionalForecaster's
probability_up). The RL agent's only job is: given the current market/account state,
how much size (0.0 to 1.0, discretized into bins) should be allocated to that
direction this bar. This is a real, if intentionally narrow, position-sizing RL
formulation — not a claim that RL can be handed the whole trading decision safely.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.features.pipeline import build_feature_matrix
from app.indicators.technical import ema
from app.rl.reward import step_reward

# Discrete action space: fraction of max size to allocate this bar.
SIZE_BINS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
N_ACTIONS = len(SIZE_BINS)

# State features pulled from the feature pipeline — kept to a fixed, bounded-range
# subset so the observation vector is small and stable in scale for the Q-network.
STATE_FEATURE_COLUMNS = ["rsi_14", "adx", "atr_pct", "bb_position", "hurst_exponent", "return_entropy"]


@dataclass
class EpisodeResult:
    total_reward: float
    final_equity: float
    max_drawdown: float
    n_steps: int


class PositionSizingEnv:
    def __init__(
        self,
        df: pd.DataFrame,
        cost_rate: float = 0.0002,
        drawdown_penalty_coef: float = 0.5,
        episode_length: int = 200,
    ):
        """
        df: OHLCV bars, ascending timestamp index, enough history for the feature
        pipeline's warmup (60+ bars) plus episode_length.
        """
        self.cost_rate = cost_rate
        self.drawdown_penalty_coef = drawdown_penalty_coef
        self.episode_length = episode_length

        features = build_feature_matrix(df)
        missing = [c for c in STATE_FEATURE_COLUMNS if c not in features.columns]
        if missing:
            raise ValueError(f"feature matrix is missing expected columns: {missing}")

        self._features = features[STATE_FEATURE_COLUMNS].copy()
        # Normalize each feature to roughly unit scale — raw RSI (0-100) and ADX
        # (0-100) on the same vector as bb_position (0-1) would make the network's
        # gradient updates dominated by whichever feature has the largest raw range.
        self._feature_means = self._features.mean()
        self._feature_stds = self._features.std().replace(0, 1)
        self._normalized_features = (self._features - self._feature_means) / self._feature_stds

        close = df["close"].reindex(features.index)
        self._returns = close.pct_change().shift(-1)  # next-bar return, the reward signal for this bar's action

        ema_fast, ema_slow = ema(close, 12), ema(close, 26)
        self._direction = np.where(ema_fast > ema_slow, 1, -1)
        self._direction = pd.Series(self._direction, index=features.index)

        valid = self._returns.notna()
        self._normalized_features = self._normalized_features[valid]
        self._returns = self._returns[valid]
        self._direction = self._direction[valid]

        if len(self._normalized_features) < episode_length + 1:
            raise ValueError(
                f"only {len(self._normalized_features)} usable bars after feature warmup — "
                f"need at least {episode_length + 1} for one episode"
            )

        self._episode_start_idx = 0
        self._t = 0
        self._prev_size = 0.0
        self._equity = 1.0
        self._peak_equity = 1.0
        self._max_drawdown = 0.0

    @property
    def observation_dim(self) -> int:
        # market features + [prev_size, direction, unrealized-equity-vs-peak]
        return len(STATE_FEATURE_COLUMNS) + 3

    @property
    def n_usable_bars(self) -> int:
        return len(self._normalized_features)

    def _get_observation(self, idx: int) -> np.ndarray:
        market = self._normalized_features.iloc[idx].values.astype(np.float32)
        account = np.array(
            [
                self._prev_size,
                float(self._direction.iloc[idx]),
                (self._equity - self._peak_equity) / self._peak_equity if self._peak_equity > 0 else 0.0,
            ],
            dtype=np.float32,
        )
        return np.concatenate([market, account])

    def reset(self, start_idx: int | None = None, rng: np.random.Generator | None = None) -> np.ndarray:
        max_start = len(self._normalized_features) - self.episode_length - 1
        if start_idx is not None:
            self._episode_start_idx = min(start_idx, max_start)
        elif rng is not None:
            self._episode_start_idx = int(rng.integers(0, max_start + 1))
        else:
            self._episode_start_idx = 0

        self._t = self._episode_start_idx
        self._prev_size = 0.0
        self._equity = 1.0
        self._peak_equity = 1.0
        self._max_drawdown = 0.0

        return self._get_observation(self._t)

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        if not (0 <= action < N_ACTIONS):
            raise ValueError(f"action must be in [0, {N_ACTIONS}), got {action}")

        size = float(SIZE_BINS[action])
        direction = int(self._direction.iloc[self._t])
        next_return = float(self._returns.iloc[self._t])

        result = step_reward(
            size=size,
            prev_size=self._prev_size,
            direction=direction,
            next_bar_return=next_return,
            equity_before=self._equity,
            peak_equity_before=self._peak_equity,
            cost_rate=self.cost_rate,
            drawdown_penalty_coef=self.drawdown_penalty_coef,
        )

        self._equity = result["equity_after"]
        self._peak_equity = result["peak_equity_after"]
        self._prev_size = size
        self._max_drawdown = min(
            self._max_drawdown, (self._equity - self._peak_equity) / self._peak_equity if self._peak_equity > 0 else 0.0
        )

        self._t += 1
        steps_taken = self._t - self._episode_start_idx
        done = steps_taken >= self.episode_length

        next_obs = self._get_observation(self._t) if not done else np.zeros(self.observation_dim, dtype=np.float32)

        info = {
            "size": size,
            "direction": direction,
            "equity": self._equity,
            "pnl_return": result["pnl_return"],
            "transaction_cost": result["transaction_cost"],
            "drawdown_penalty": result["drawdown_penalty"],
        }
        return next_obs, result["reward"], done, info

    def episode_summary(self, total_reward: float, n_steps: int) -> EpisodeResult:
        return EpisodeResult(
            total_reward=total_reward,
            final_equity=self._equity,
            max_drawdown=self._max_drawdown,
            n_steps=n_steps,
        )
