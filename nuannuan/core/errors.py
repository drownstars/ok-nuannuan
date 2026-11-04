"""Shared automation failure type; kept dependency-free for every layer."""


class AutomationError(RuntimeError):
    """A known game state could not be observed within the allowed time."""
