"""Job source adapters package."""

from backend.discovery.adapters.arbeitnow import ArbeitnowAdapter
from backend.discovery.adapters.mock_source import MockJobSourceAdapter

__all__ = ["ArbeitnowAdapter", "MockJobSourceAdapter"]
