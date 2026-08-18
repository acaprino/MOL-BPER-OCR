"""Pure page-stability state machine for BPER capture (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StabilityConfig:
    """Thresholds for declaring a page stable."""

    min_matches: int = 2      # concordant observations required on the candidate
    min_seconds: float = 2.0  # minimum candidate presence (anti mid-scroll)
    miss_tolerance: int = 1   # consecutive discordant/null observations tolerated


class StabilityTracker:
    """Decides when a recognized page is stable enough to capture.

    observe() takes the resolved page name (or None when unrecognized) plus a
    timestamp and returns the page name once the candidate has both
    min_matches concordant observations and min_seconds of presence. Up to
    miss_tolerance discordant/null observations do not reset the candidate;
    two consecutive concordant observations of a different page switch the
    candidate immediately (anchored at the first of the two).
    """

    def __init__(self, config: Optional[StabilityConfig] = None) -> None:
        self.config = config or StabilityConfig()
        self.candidate: Optional[str] = None
        self._first_seen: float = 0.0
        self._matches: int = 0
        self._misses: int = 0
        self._pending: Optional[str] = None
        self._pending_since: float = 0.0

    def reset(self) -> None:
        self.candidate = None
        self._first_seen = 0.0
        self._matches = 0
        self._misses = 0
        self._pending = None
        self._pending_since = 0.0

    def observe(self, page: Optional[str], now: float) -> Optional[str]:
        if page is None:
            self._register_miss()
            return None
        if self.candidate is None:
            self._adopt(page, now)
            return None
        if page == self.candidate:
            self._matches += 1
            self._misses = 0
            self._pending = None
            if (
                self._matches >= self.config.min_matches
                and (now - self._first_seen) >= self.config.min_seconds
            ):
                return self.candidate
            return None
        if self._pending == page:
            # Second consecutive concordant observation of a new page: switch.
            first_seen = self._pending_since
            self.reset()
            self.candidate = page
            self._first_seen = first_seen
            self._matches = 2
            return None
        self._pending = page
        self._pending_since = now
        self._register_miss()
        return None

    def confirm(self, now: float) -> Optional[str]:
        """Count an unchanged frame as another observation of the current candidate.

        A duplicate frame is direct evidence that the page on screen has not
        changed, which is what the second concordant observation was standing in
        for. It matters because the page router costs one VLM call per answer:
        demanding two answers means demanding that the operator hold a screen
        still for two routing round-trips, which with the LLM router is 10-24
        seconds rather than the 2 seconds the thresholds were written for.

        The trade is deliberate and worth stating: confirmation is *stronger*
        evidence that the screen is stable, and *weaker* evidence that the label
        is right, because only one router answer backs it. `min_seconds` still
        applies, so this never shortcuts the anti-mid-scroll delay.

        Returns the candidate when it becomes stable, else None. A no-op when
        there is no candidate: an unchanged frame says nothing about a page
        nobody has identified yet.
        """
        if self.candidate is None:
            return None
        return self.observe(self.candidate, now)

    def _adopt(self, page: str, now: float) -> None:
        self.reset()
        self.candidate = page
        self._first_seen = now
        self._matches = 1

    def _register_miss(self) -> None:
        if self.candidate is None:
            return
        self._misses += 1
        if self._misses > self.config.miss_tolerance:
            pending, pending_since = self._pending, self._pending_since
            self.reset()
            if pending is not None:
                self.candidate = pending
                self._first_seen = pending_since
                self._matches = 1
