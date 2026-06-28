"""ActionRegistry — maps step type names to async handler functions."""
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ActionDef:
    name:        str
    handler:     Callable
    description: str      = ""
    contract:    Optional[object] = field(default=None, compare=False)


class ActionRegistry:
    def __init__(self):
        self._actions: dict[str, ActionDef] = {}

    def register(self, name: str, handler: Callable,
                 description: str = "", contract=None) -> None:
        self._actions[name] = ActionDef(
            name=name, handler=handler, description=description,
            contract=contract,
        )

    def apply_contracts(self, contracts: dict) -> None:
        """Bulk-apply a {name: BlockContract} mapping after all actions are registered."""
        for name, contract in contracts.items():
            if name in self._actions:
                self._actions[name].contract = contract

    def get(self, name: str) -> ActionDef:
        if name not in self._actions:
            raise KeyError(
                f"Unknown action type: {name!r}. "
                f"Registered: {sorted(self._actions)}"
            )
        return self._actions[name]

    def list(self) -> list[str]:
        return sorted(self._actions)

    def is_registered(self, name: str) -> bool:
        return name in self._actions


# Shared default registry — populated by action modules at import time.
registry = ActionRegistry()
