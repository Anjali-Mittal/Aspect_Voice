"""Loads config.yaml, resolves ${target.x} refs against the yaml tree itself,
and ${ENV_VAR} refs (all-caps, no dots) against the process environment.
Ports, hosts, CORS origins, DB URL, and all secrets live in .env — nothing
runtime-environment-specific is hardcoded here or in config.yaml.
"""
import os
import re
import yaml
from pathlib import Path
from functools import lru_cache

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
REF_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_.]+)\}")


def _resolve_refs(node, root):
    if isinstance(node, dict):
        return {k: _resolve_refs(v, root) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(v, root) for v in node]
    if isinstance(node, str):
        def repl(m):
            ref = m.group(1)
            if "." not in ref and ref.isupper():
                # ${DATABASE_URL} style -> environment variable
                val = os.getenv(ref)
                if val is None:
                    raise RuntimeError(f"Missing env var {ref}. Set it in .env (see .env.example)")
                return val
            # ${target.product_name} style -> lookup inside the yaml tree itself
            path = ref.split(".")
            val = root
            for p in path:
                val = val[p]
            return str(val)
        return REF_PATTERN.sub(repl, node)
    return node


@lru_cache
def get_config() -> dict:
    with open(CONFIG_PATH) as f:
        raw = yaml.safe_load(f)
    resolved = _resolve_refs(raw, raw)
    return resolved


def get_secret(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing env var {name}. Set it in .env (see .env.example)")
    return val


def get_server_settings() -> dict:
    """Host/port/CORS — read directly from env, not config.yaml, so a vendor's
    injected PORT env var (Render, Railway, etc.) is always respected."""
    origins = os.getenv("CORS_ORIGINS", "")
    return {
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": int(os.getenv("PORT", "8000")),
        "cors_origins": [o.strip() for o in origins.split(",") if o.strip()],
    }
