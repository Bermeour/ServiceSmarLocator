import re
import unicodedata


def normalize_text(s: str) -> str:
    """
    Normaliza texto para comparación:
    - lower
    - trim
    - colapsa espacios
    - elimina acentos
    """
    if not s:
        return ""

    s = s.strip().lower()
    s = " ".join(s.split())  # colapsa espacios

    # elimina acentos (áéíóú -> aeiou)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    return s


def is_generic_text(s: str) -> bool:
    t = normalize_text(s)
    generic = {
        "ok", "si", "sí", "no", "next", "back", "cancel", "close", "x",
        "aceptar", "continuar", "volver", "cerrar"
    }
    return t in generic or len(t) <= 1


def text_contains(haystack: str, needle: str) -> bool:
    h = normalize_text(haystack)
    n = normalize_text(needle)
    if not h or not n:
        return False
    return n in h


def safe_xpath_literal(s: str) -> str:
    """
    Devuelve un literal XPath seguro.
    Maneja comillas simples y dobles.
    """
    if s is None:
        return "''"

    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return f'"{s}"'

    # si tiene ambas, usamos concat()
    parts = s.split("'")
    return "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"
