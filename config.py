"""Load config.yaml, provide dotted-key access with defaults."""
import os, yaml

_CONFIG = None
_BASE = os.path.dirname(os.path.abspath(__file__))


def _load():
    global _CONFIG
    if _CONFIG is None:
        path = os.path.join(_BASE, "config.yaml")
        with open(path, encoding="utf-8") as f:
            _CONFIG = yaml.safe_load(f)
    return _CONFIG


def get(*keys, default=None):
    """Get nested config value: get('ocr', 'max_tokens')"""
    cfg = _load()
    for k in keys:
        if isinstance(cfg, dict):
            cfg = cfg.get(k)
        else:
            return default
    return cfg if cfg is not None else default


def model_path(name: str) -> str:
    """Get absolute path to a model file."""
    rel = get('models', name, default='')
    return os.path.join(_BASE, rel) if rel else ''
