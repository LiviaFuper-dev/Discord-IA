"""Consulta pública e sanitizada para códigos ausentes da base interna."""

from __future__ import annotations

import asyncio
import html
import re
import time
from html.parser import HTMLParser
from urllib.parse import quote_plus

import aiohttp

import config


_ERROR_CODE_RE = re.compile(r"(?<!\d)(?:erro\s*(?:n[ºo]\.?\s*)?)?(\d{3,6})(?!\d)", re.I)
_SYSTEM_BY_LABEL = {
    "chatguru": "ChatGuru",
    "clickup": "ClickUp",
    "whom": "Whom",
    "falepaco": "Falepaco",
    "google drive": "Google Drive",
    "e-mail": "e-mail",
    "email": "e-mail",
}
_CACHE_TTL_SECONDS = 60 * 60
_CACHE: dict[str, tuple[float, str]] = {}


class _SearchResultsParser(HTMLParser):
    """Extrai somente título, URL e trecho dos primeiros resultados públicos."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = dict(attrs)
        classes = data.get("class", "")
        if tag == "a" and "result__a" in classes and len(self.results) < 3:
            self._current = {"title": "", "url": data.get("href", ""), "snippet": ""}
            self._capture = "title"
        elif tag in {"a", "div"} and "result__snippet" in classes and self._current:
            self._capture = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture == "title":
            self._capture = None
        elif tag in {"a", "div"} and self._capture == "snippet":
            if self._current and self._current["title"]:
                self.results.append(self._current)
                self._current = None
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._current and self._capture:
            self._current[self._capture] += data


def extract_error_code(text: str) -> str | None:
    """Obtém o último código numérico citado, sem depender de uma lista fixa."""
    matches = _ERROR_CODE_RE.findall(str(text or ""))
    return matches[-1] if matches else None


def _system_from_label(thread_label: str, conversation: str) -> str:
    text = f"{thread_label}\n{conversation}".lower()
    for keyword, system in _SYSTEM_BY_LABEL.items():
        if keyword in text:
            return system
    return "sistema"


def _format_results(code: str, system: str, results: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for result in results:
        title = " ".join(html.unescape(result["title"]).split())[:160]
        snippet = " ".join(html.unescape(result["snippet"]).split())[:500]
        url = result["url"].strip()
        if title or snippet:
            blocks.append(f"- {title}\n  {snippet}\n  Fonte: {url}")
    if not blocks:
        return ""
    return (
        "PESQUISA EXTERNA PARA CÓDIGO DESCONHECIDO (dados públicos não verificados):\n"
        f"Sistema: {system}. Código informado: {code}.\n"
        + "\n".join(blocks)
    )[:2400]


async def search_unknown_error_code(
    conversation: str,
    thread_label: str,
    *,
    has_local_guidance: bool,
) -> str:
    """Busca somente código + sistema quando não há orientação interna correspondente."""
    if not config.ERROR_WEB_SEARCH_ENABLED or has_local_guidance:
        return ""
    code = extract_error_code(conversation)
    if not code:
        return ""

    system = _system_from_label(thread_label, conversation)
    query = f"{system} erro {code}"
    cached = _CACHE.get(query)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Discord-IA/1.0)"}
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if not 200 <= response.status < 300:
                    return ""
                page = await response.text(errors="ignore")
    except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError):
        return ""

    parser = _SearchResultsParser()
    parser.feed(page)
    result = _format_results(code, system, parser.results)
    _CACHE[query] = (time.monotonic(), result)
    return result
