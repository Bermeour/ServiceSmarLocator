from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from bs4 import BeautifulSoup

import lxml.html


@dataclass
class ValidationResult:
    ok: bool
    matches: int
    bonus: int
    note: str


class LocatorValidator:
    """
    Valida unicidad (match count) para CSS y XPath.

    - CSS: soup.select(...)
    - XPath: lxml.html.fromstring(...).xpath(...)

    Regla por defecto:
      matches == 1  -> ok + bonus fuerte
      matches <= 3  -> ok + bonus pequeño (o neutro)
      matches <= 5  -> ok pero penaliza (riesgoso)
      matches > 5   -> descartar (demasiado genérico)
      matches == 0  -> descartar
    """

    def __init__(
        self,
        max_matches: int = 5,#Si tu HTML tiene muchos botones repetidos y estás descartando demasiado: subir o bajar el castigo
        prefer_unique_bonus: int = 20,
        small_multi_bonus: int = 5,
        risky_multi_penalty: int = -10,
    ):
        self.max_matches = max_matches
        self.prefer_unique_bonus = prefer_unique_bonus
        self.small_multi_bonus = small_multi_bonus
        self.risky_multi_penalty = risky_multi_penalty

    def validate(
        self,
        soup: BeautifulSoup,
        raw_html: str,
        locator_type: str,
        locator_value: str
    ) -> ValidationResult:

        locator_type = (locator_type or "").lower().strip()

        try:
            if locator_type == "css":
                matches = self._count_css(soup, locator_value)
            elif locator_type == "xpath":
                matches = self._count_xpath(raw_html, locator_value)
            else:
                return ValidationResult(False, 0, -999, f"tipo desconocido: {locator_type}")

        except Exception as e:
            return ValidationResult(False, 0, -999, f"error validando {locator_type}: {e}")

        # reglas de decisión
        if matches <= 0:
            return ValidationResult(False, matches, -999, "0 matches (descartar)")

        if matches == 1:
            return ValidationResult(True, matches, self.prefer_unique_bonus, "único (match=1) (+20)")

        if matches <= 3:
            return ValidationResult(True, matches, self.small_multi_bonus, f"pocos matches (match={matches}) (+5)")

        if matches <= self.max_matches:
            return ValidationResult(True, matches, self.risky_multi_penalty, f"riesgoso (match={matches}) (-10)")

        return ValidationResult(False, matches, -999, f"demasiados matches (match={matches}) (descartar)")

    def _count_css(self, soup: BeautifulSoup, selector: str) -> int:
        # BeautifulSoup soporta select() para CSS (limitado pero útil)
        return len(soup.select(selector))

    def _count_xpath(self, raw_html: str, xpath_expr: str) -> int:
        # lxml ejecuta XPath real (mejor para validar unicidad)
        doc = lxml.html.fromstring(raw_html)
        res = doc.xpath(xpath_expr)
        return len(res)
