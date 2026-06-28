"""BlockRegistry — loads reusable block definitions from sources/blocks/*.yaml."""
from pathlib import Path
from typing import Optional

import yaml

from engine.v3_models import BlockDef, StepDef


class BlockRegistry:
    def __init__(self, blocks_dir: Path = None):
        if blocks_dir is None:
            blocks_dir = Path(__file__).parent.parent / "sources" / "blocks"
        self._blocks: dict[str, BlockDef] = {}
        if blocks_dir.exists():
            self._load_all(blocks_dir)

    def _load_all(self, blocks_dir: Path) -> None:
        for yaml_path in sorted(blocks_dir.glob("*.yaml")):
            try:
                self._load_one(yaml_path)
            except Exception as exc:
                import sys
                print(f"[warn] block load failed {yaml_path.name}: {exc}", file=sys.stderr)

    def _load_one(self, path: Path) -> None:
        raw   = yaml.safe_load(path.read_text(encoding="utf-8"))
        steps = [
            StepDef(
                step_id=             s["step_id"],
                type=                s["type"],
                params=              s.get("params", {}),
                mode=                s.get("mode", "dom"),
                max_retries=         s.get("max_retries", 0),
                retry_delay_seconds= s.get("retry_delay_seconds", 1.0),
                idempotent=          s.get("idempotent", True),
                on_choice=           s.get("on_choice", {}),
                on_timeout=          s.get("on_timeout"),
                on_error=            s.get("on_error"),
                on_error_mode=       s.get("on_error_mode", "blocking"),
                enabled=             s.get("enabled", True),
                block_ref=           s.get("block"),
            )
            for s in raw.get("steps", [])
        ]
        block = BlockDef(
            id=            raw["id"],
            name=          raw.get("name", raw["id"]),
            version=       raw.get("version", 1),
            steps=         steps,
            params=        raw.get("params", {}),
            input_schema=  raw.get("input_schema", []),
            output_schema= raw.get("output_schema", []),
            on_error=      raw.get("on_error"),
        )
        self._blocks[block.id] = block

    def get(self, block_id: str) -> Optional[BlockDef]:
        return self._blocks.get(block_id)

    def list(self) -> list[str]:
        return list(self._blocks.keys())
