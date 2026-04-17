"""
config.py — Carga la configuración desde app-config.yml.

Todos los valores tienen fallback a defaults seguros, por lo que
el servicio funciona aunque el archivo no exista o falte una clave.

Uso:
    from app.config import cfg
    db_path = cfg("learning.db_path", "learning.db")
"""

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Valores por defecto si app-config.yml no existe o le falta una clave
_DEFAULTS: dict = {
    "learning.enabled": True,
    "learning.db_path": "learning.db",
    "learning.adaptive_weights.enabled": True,
    "learning.adaptive_weights.min_feedbacks": 20,
    "learning.adaptive_weights.precision_scale": 20,
    "learning.ml_model.enabled": True,
    "learning.ml_model.min_samples": 100,
    "learning.ml_model.retrain_every": 50,
    "learning.ml_model.blend_factor": 0.7,
}

_config: dict = {}
_loaded: bool = False


def _load(path: str = "app-config.yml") -> None:
    global _config, _loaded
    if _loaded:
        return
    try:
        import yaml
        p = Path(path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
            log.info("Configuración cargada desde %s", path)
        else:
            log.warning("app-config.yml no encontrado en '%s', usando defaults", path)
    except ImportError:
        log.warning("PyYAML no instalado — usando defaults de configuración")
    except Exception as e:
        log.error("Error cargando app-config.yml: %s", e)
    finally:
        _loaded = True


def cfg(key: str, default: Any = None) -> Any:
    """
    Lee un valor de configuración usando notación de punto.
    Ejemplo: cfg("learning.db_path", "learning.db")

    Orden de resolución:
      1. app-config.yml (si existe la clave)
      2. _DEFAULTS (tabla de defaults internos)
      3. parámetro `default` del caller
    """
    _load()
    parts = key.split(".")
    node = _config
    for part in parts:
        if not isinstance(node, dict):
            node = None
            break
        node = node.get(part)
        if node is None:
            break

    if node is not None:
        return node

    # Fallback a defaults internos
    return _DEFAULTS.get(key, default)
