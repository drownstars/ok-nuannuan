from dataclasses import dataclass, field
from math import isfinite


@dataclass
class AssistGate:
    cooldown: float = 0.6
    pickup_enabled: bool = True
    dialogue_enabled: bool = True
    _previous: str | None = field(default=None, init=False)
    _last_sent: float = field(default=float('-inf'), init=False)

    def __post_init__(self):
        if not isfinite(self.cooldown) or self.cooldown < 0.25:
            raise ValueError('操作间隔不得小于 0.25 秒')

    def reset(self):
        self._previous = None
        self._last_sent = float('-inf')

    def decide(self, main: bool, pickup: bool, dialogue: bool, now: float) -> str | None:
        candidate = None
        if self.dialogue_enabled and dialogue:
            candidate = 'dialogue'
        elif self.pickup_enabled and main and pickup and not dialogue:
            candidate = 'pickup'
        stable = candidate is not None and candidate == self._previous
        self._previous = candidate
        if stable and now - self._last_sent >= self.cooldown:
            self._last_sent = now
            return candidate
        return None
