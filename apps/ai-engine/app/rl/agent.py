"""
DQN agent (Mnih et al., 2015 architecture, simplified for a low-dimensional state):
a small MLP Q-network, a separate target network updated periodically for training
stability, epsilon-greedy exploration with decay, and standard Bellman-target
gradient descent via Huber loss (more robust to reward outliers than MSE — relevant
here since a single bad bar's transaction-cost/drawdown-penalty terms can spike).
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from app.rl.replay_buffer import ReplayBuffer, Transition


class QNetwork(nn.Module):
    def __init__(self, observation_dim: int, n_actions: int, hidden_dim: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(observation_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


@dataclass
class DQNConfig:
    hidden_dim: int = 64
    learning_rate: float = 1e-3
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay_steps: int = 5000
    target_update_every: int = 250
    batch_size: int = 64
    replay_capacity: int = 50_000
    min_replay_before_training: int = 500


class DQNAgent:
    def __init__(self, observation_dim: int, n_actions: int, config: DQNConfig | None = None, seed: int = 42):
        self.config = config or DQNConfig()
        self.n_actions = n_actions
        self.observation_dim = observation_dim

        torch.manual_seed(seed)
        self.q_network = QNetwork(observation_dim, n_actions, self.config.hidden_dim)
        self.target_network = copy.deepcopy(self.q_network)
        self.target_network.eval()

        self.optimizer = torch.optim.Adam(self.q_network.parameters(), lr=self.config.learning_rate)
        self.replay_buffer = ReplayBuffer(self.config.replay_capacity, seed=seed)

        self._step_count = 0
        self._rng = random.Random(seed)

    @property
    def epsilon(self) -> float:
        progress = min(self._step_count / self.config.epsilon_decay_steps, 1.0)
        return self.config.epsilon_start + progress * (self.config.epsilon_end - self.config.epsilon_start)

    def select_action(self, observation: np.ndarray, explore: bool = True) -> int:
        if explore and self._rng.random() < self.epsilon:
            return self._rng.randrange(self.n_actions)

        with torch.no_grad():
            obs_tensor = torch.from_numpy(observation).float().unsqueeze(0)
            q_values = self.q_network(obs_tensor)
            return int(torch.argmax(q_values, dim=1).item())

    def q_values(self, observation: np.ndarray) -> np.ndarray:
        """Exposes raw Q-values for a state — used to report suggestion confidence (Q-value spread)."""
        with torch.no_grad():
            obs_tensor = torch.from_numpy(observation).float().unsqueeze(0)
            return self.q_network(obs_tensor).squeeze(0).numpy()

    def store_transition(self, state, action, reward, next_state, done) -> None:
        self.replay_buffer.push(Transition(state, action, reward, next_state, done))

    def train_step(self) -> float | None:
        """Returns the training loss for this step, or None if there isn't enough replay data yet."""
        if len(self.replay_buffer) < max(self.config.batch_size, self.config.min_replay_before_training):
            return None

        batch = self.replay_buffer.sample(self.config.batch_size)
        states = torch.from_numpy(np.stack([t.state for t in batch])).float()
        actions = torch.tensor([t.action for t in batch], dtype=torch.long).unsqueeze(1)
        rewards = torch.tensor([t.reward for t in batch], dtype=torch.float32)
        next_states = torch.from_numpy(np.stack([t.next_state for t in batch])).float()
        dones = torch.tensor([t.done for t in batch], dtype=torch.float32)

        q_values = self.q_network(states).gather(1, actions).squeeze(1)

        with torch.no_grad():
            next_q_values = self.target_network(next_states).max(dim=1).values
            targets = rewards + self.config.gamma * next_q_values * (1 - dones)

        loss = F.smooth_l1_loss(q_values, targets)  # Huber loss

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=10.0)
        self.optimizer.step()

        self._step_count += 1
        if self._step_count % self.config.target_update_every == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())

        return float(loss.item())

    def state_dict(self) -> dict:
        return {"q_network": self.q_network.state_dict(), "step_count": self._step_count}

    def load_state_dict(self, state: dict) -> None:
        self.q_network.load_state_dict(state["q_network"])
        self.target_network.load_state_dict(state["q_network"])
        self._step_count = state.get("step_count", 0)
