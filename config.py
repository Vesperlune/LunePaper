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


def get_ocr_engine_config(engine_name: str | None = None) -> dict:
    """
    Get full configuration for an OCR engine.
    If engine_name is None, defaults to models.ocr_default ('unlimited').
    """
    default_engine = get('models', 'ocr_default', default='unlimited')
    engine_id = (engine_name or default_engine).lower().strip()

    engines = get('models', 'ocr_engines', default={})
    cfg = engines.get(engine_id) if isinstance(engines, dict) else None

    # Fallback to legacy single-model config if engine not found in engines dict
    if not cfg:
        if engine_id == 'ovis':
            cfg = {
                'id': 'ovis',
                'name': 'OvisOCR2',
                'model_path': 'OvisOCR2-Q8_0.gguf',
                'mmproj_path': 'mmproj-BF16.gguf',
                'prompt_fmt': "<|im_start|>user\n{marker}Extract all readable content from the image in natural human reading order and output the result as a single Markdown document.<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n",
                'vram_estimate_mb': 1730,
                'reading_order_sorted': False
            }
        else:
            cfg = {
                'id': 'unlimited',
                'name': 'Unlimited-OCR',
                'model_path': get('models', 'ocr', default='Unlimited-OCR-Q8_0.gguf'),
                'mmproj_path': get('models', 'mmproj', default='mmproj-Unlimited-OCR-F16.gguf'),
                'prompt_fmt': '{marker}document parsing.',
                'vram_estimate_mb': 5950,
                'reading_order_sorted': True
            }

    # Resolve relative paths to absolute paths
    res = dict(cfg)
    for p_key in ('model_path', 'mmproj_path'):
        if p_key in res and res[p_key]:
            if not os.path.isabs(res[p_key]):
                res[p_key] = os.path.join(_BASE, res[p_key])

    return res


def list_ocr_models() -> list[dict]:
    """List all registered OCR models with their disk availability."""
    default_engine = get('models', 'ocr_default', default='unlimited')
    engines = get('models', 'ocr_engines', default={})
    if not engines or not isinstance(engines, dict):
        engine_keys = ['unlimited', 'ovis']
    else:
        engine_keys = list(engines.keys())

    models_list = []
    for key in engine_keys:
        cfg = get_ocr_engine_config(key)
        m_path = cfg.get('model_path', '')
        mm_path = cfg.get('mmproj_path', '')
        available = bool(m_path and os.path.isfile(m_path) and mm_path and os.path.isfile(mm_path))
        models_list.append({
            'id': cfg.get('id', key),
            'name': cfg.get('name', key),
            'description': cfg.get('description', ''),
            'vram_estimate_mb': cfg.get('vram_estimate_mb', 0),
            'is_default': (key == default_engine),
            'available': available
        })
    return models_list

