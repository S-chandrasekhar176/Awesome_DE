import importlib
from typing import Dict, List, Optional, Tuple, Any, Type

from .base import BaseStrategy


class StrategyRegistry:
    """Central registry for all trading strategies."""

    def __init__(self):
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy_class: Type[BaseStrategy], params: Dict[str, Any] = None) -> None:
        """Instantiate and register a strategy class."""
        instance = strategy_class(params=params)
        self._strategies[instance.name] = instance

    def get(self, name: str) -> Optional[BaseStrategy]:
        """Get a strategy instance by name."""
        return self._strategies.get(name)

    def get_all(self) -> Dict[str, BaseStrategy]:
        """Return all registered strategies."""
        return dict(self._strategies)

    def get_active_for_regime(
        self,
        regime: str,
        activation_map: Dict[str, Dict[str, List[str]]],
    ) -> List[Tuple[str, BaseStrategy, str]]:
        """Get strategies with their activation status for a given regime.

        Returns list of (name, instance, status) where status is:
          - "active": strategy is in the active list for this regime
          - "reduced_size": strategy is in the reduced_size list
          - "paused": strategy is not listed (implicitly paused)
        """
        results: List[Tuple[str, BaseStrategy, str]] = []
        regime_config = activation_map.get(regime, {})
        active_names = set(regime_config.get("active", []))
        reduced_names = set(regime_config.get("reduced_size", []))

        for name, instance in self._strategies.items():
            if not instance.enabled:
                status = "paused"
            elif name in active_names:
                status = "active"
            elif name in reduced_names:
                status = "reduced_size"
            else:
                status = "paused"
            results.append((name, instance, status))

        return results

    def discover(self) -> None:
        """Import and register all V2 strategies."""
        v2_modules = [
            ".v2.orb",
            ".v2.mb",
            ".v2.ptc",
            ".v2.vc",
            ".v2.sic",
            ".v2.mrf",
            ".v2.trs",
        ]

        pkg = __package__ or "strategies"
        for module_path in v2_modules:
            try:
                mod = importlib.import_module(module_path, package=pkg)
                # Find strategy classes in the module
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseStrategy)
                        and attr is not BaseStrategy
                        and attr.__name__ != "BaseStrategy"
                    ):
                        if attr.name not in self._strategies:
                            self.register(attr)
            except Exception as e:
                continue

