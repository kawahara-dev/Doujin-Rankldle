from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RankingProvider(ABC):
    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        """Return normalized ranking items."""
