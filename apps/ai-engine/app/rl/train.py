"""
Trains a DQNAgent against PositionSizingEnv over historical bars, and provides the
inference-side helper (`suggest_size`) that turns a trained agent + current market
state into a servable position-size suggestion with a simple confidence proxy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.rl.agent import DQNAgent, DQNConfig
from app.rl.environment import N_ACTIONS, SIZE_BINS, PositionSizingEnv


@dataclass
class TrainingCurve:
    episode_rewards: list[float] = field(default_factory=list)
    episode_final_equity: list[float] = field(default_factory=list)
    episode_max_drawdown: list[float] = field(default_factory=list)
    losses: list[float] = field(default_factory=list)

    def summary(self) -> dict:
        recent = self.episode_rewards[-20:] if self.episode_rewards else []
        return {
            "n_episodes": len(self.episode_rewards),
            "mean_reward_all_episodes": float(np.mean(self.episode_rewards)) if self.episode_rewards else 0.0,
            "mean_reward_last_20": float(np.mean(recent)) if recent else 0.0,
            "mean_final_equity_last_20": (
                float(np.mean(self.episode_final_equity[-20:])) if self.episode_final_equity else 1.0
            ),
            "worst_drawdown_overall": float(min(self.episode_max_drawdown)) if self.episode_max_drawdown else 0.0,
            "mean_training_loss_last_100_steps": (
                float(np.mean(self.losses[-100:])) if self.losses else None
            ),
        }


def train_position_sizing_agent(
    df: pd.DataFrame,
    n_episodes: int = 150,
    episode_length: int = 200,
    config: DQNConfig | None = None,
    seed: int = 42,
) -> tuple[DQNAgent, TrainingCurve]:
    env = PositionSizingEnv(df, episode_length=episode_length)
    agent = DQNAgent(env.observation_dim, N_ACTIONS, config=config, seed=seed)
    curve = TrainingCurve()
    rng = np.random.default_rng(seed)

    for _episode in range(n_episodes):
        obs = env.reset(rng=rng)
        total_reward = 0.0
        steps = 0
        done = False

        while not done:
            action = agent.select_action(obs, explore=True)
            next_obs, reward, done, _info = env.step(action)
            agent.store_transition(obs, action, reward, next_obs, done)

            loss = agent.train_step()
            if loss is not None:
                curve.losses.append(loss)

            obs = next_obs
            total_reward += reward
            steps += 1

        result = env.episode_summary(total_reward, steps)
        curve.episode_rewards.append(result.total_reward)
        curve.episode_final_equity.append(result.final_equity)
        curve.episode_max_drawdown.append(result.max_drawdown)

    return agent, curve


def suggest_size(agent: DQNAgent, env: PositionSizingEnv, observation: np.ndarray) -> dict:
    """
    Inference-time helper: given a trained agent and the current observation, returns
    the suggested size fraction plus a confidence proxy derived from how peaked the
    Q-value distribution is (a large gap between the best and second-best action's
    Q-value means the agent is confident; a near-tie means it's not).
    """
    q_values = agent.q_values(observation)
    best_action = int(np.argmax(q_values))
    sorted_q = np.sort(q_values)[::-1]
    q_gap = float(sorted_q[0] - sorted_q[1]) if len(sorted_q) > 1 else 0.0

    # Normalize the gap into a rough [0, 1] confidence score via a saturating function
    # — this is a heuristic, not a calibrated probability (DQN Q-values aren't
    # probabilities), presented as such rather than overstating its meaning.
    confidence = float(np.tanh(abs(q_gap) * 5))

    return {
        "suggested_size": float(SIZE_BINS[best_action]),
        "action_index": best_action,
        "q_values": {f"size_{s:.2f}": float(q) for s, q in zip(SIZE_BINS, q_values)},
        "confidence": confidence,
    }
