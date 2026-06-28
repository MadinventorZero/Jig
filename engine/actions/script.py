"""Script action — python_run with per-script venv isolation."""
import asyncio
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

from engine.context import RunContext

_VENV_BASE       = Path(".venv-scripts")
_OUTPUT_CAP      = 8000
_DEFAULT_TIMEOUT = 240.0


def _parse_requires(code: str) -> list[str]:
    pkgs = []
    for line in code.splitlines():
        m = re.match(r"#\s*requires:\s*(.+)", line.strip())
        if m:
            pkgs.extend(p.strip() for p in m.group(1).split(",") if p.strip())
    return pkgs


def _venv_key(requires: list[str]) -> str:
    h = hashlib.sha256("|".join(sorted(requires)).encode()).hexdigest()[:12]
    return f"auto_{h}"


def _ensure_venv(venv_path: Path, packages: list[str]) -> None:
    python_bin = venv_path / "bin" / "python"
    if not python_bin.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True, capture_output=True,
        )
    if packages:
        pip = venv_path / "bin" / "pip"
        subprocess.run(
            [str(pip), "install", "--quiet", *packages],
            check=True, capture_output=True,
        )


async def handle_python_run(ctx: RunContext, params: dict) -> dict:
    code      = params["code"]
    venv_nm   = params.get("venv")
    extra_env = params.get("env", {})
    timeout   = float(params.get("timeout_seconds", _DEFAULT_TIMEOUT))

    requires = _parse_requires(code)
    if venv_nm is None:
        venv_nm = _venv_key(requires) if requires else "default"

    venv_path = _VENV_BASE / venv_nm
    await asyncio.to_thread(_ensure_venv, venv_path, requires)

    python = venv_path / "bin" / "python"
    env    = {**os.environ, **{str(k): str(v) for k, v in extra_env.items()}}

    proc = await asyncio.create_subprocess_exec(
        str(python), "-c", code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"python_run timed out after {timeout}s")

    out = stdout.decode(errors="replace")[:_OUTPUT_CAP]
    err = stderr.decode(errors="replace")[:_OUTPUT_CAP]
    ok  = proc.returncode == 0

    return {
        "exit_code": proc.returncode,
        "stdout":    out,
        "stderr":    err,
        "ok":        ok,
        "choice":    "ok" if ok else "error",
    }


def register(registry) -> None:
    registry.register("python_run", handle_python_run,
                       "Run Python code in an isolated venv (# requires: pkg)")
