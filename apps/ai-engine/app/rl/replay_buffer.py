"""
Fixed-size circular experience replay buffer, the standard DQN component (Mnih et
al., 2015) that breaks the temporal correlation between consecutive transitions —
without it, training on a strictly sequential price series would violate the i.i.d.
assumption most gradient-descent convergence arguments lean on, and DQN training
becomes unstable (chases the most recent market regime instead of learning general
structure).
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


class ReplayBuffer:
    def __init__(self, capacity: int = 50_000, seed: int | None = None):
        self._buffer: deque[Transition] = deque(maxlen=capacity)
        self._rng = random.Random(seed)

    def push(self, transition: Transition) -> None:
        self._buffer.append(transition)

    def sample(self, batch_size: int) -> list[Transition]:
        if len(self._buffer) < batch_size:
            raise ValueError(
                f"cannot sample {batch_size} transitions from a buffer of size {len(self._buffer)}"
            )
        return self._rng.sample(self._buffer, batch_size)

    def __len__(self) -> int:
        return len(self._buffer)
