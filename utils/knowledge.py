"""Carregamento e seleção da base local de conhecimento do suporte."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.historical_knowledge import retrieve_historical_solution_context
from utils.system_knowledge import retrieve_structured_system_knowledge


_ROOT = Path(__file__).resolve().parent.parent
_KNOWLEDGE_DIR = _ROOT / "knowledge_base"
_INSTITUTIONAL_FILE = _KNOWLEDGE_DIR / "institutional.json"
_POPS_DIR = _KNOWLEDGE_DIR / "pops"
_SUPPORTED_SUFFIXES = {".md", ".txt", ".json"}
_ERROR_CODE_RE = re.compile(
    r"(?<!\d)(?:erro\s*(?:n[ºo]\.?\s*)?)?(\d{3,6})(?!\d)",
    re.IGNORECASE,
)
_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "essa", "esse", "esta", "este", "eu", "foi", "mais", "me",
    "meu", "minha", "na", "nas", "no", "nos", "o", "os", "ou", "para",
    "por", "que", "se", "sem", "ser", "tem", "um", "uma",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", _normalize(text))
        if token not in _STOPWORDS
    }


def _flatten(value: Any, *, prefix: str = "") -> list[str]:
    """Converte o JSON institucional em linhas compactas e legíveis para a IA."""
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"schema_version", "document_id", "updated_at", "status"}:
                continue
            label = str(key).replace("_", " ").strip().title()
            next_prefix = f"{prefix} > {label}" if prefix else label
            lines.extend(_flatten(item, prefix=next_prefix))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.extend(_flatten(item, prefix=prefix))
            else:
                lines.append(f"- {prefix}: {item}")
    elif value not in (None, ""):
        lines.append(f"- {prefix}: {value}")
    return lines


@lru_cache(maxsize=1)
def load_institutional_knowledge() -> str:
    """Carrega a referência institucional que deve acompanhar toda geração."""
    try:
        data = json.loads(_INSTITUTIONAL_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[IA] Não foi possível carregar a base institucional: {exc}")
        return ""
    return "\n".join(_flatten(data))


def _read_document(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return "\n".join(_flatten(json.loads(raw)))
        return raw.strip()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"[IA] POP ignorado ({path.name}): {exc}")
        return ""


def _split_document(text: str, *, chunk_size: int = 1800) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > chunk_size:
            chunks.append(current)
            current = ""
        if len(paragraph) > chunk_size:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(
                paragraph[index:index + chunk_size]
                for index in range(0, len(paragraph), chunk_size)
            )
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def retrieve_relevant_pops(
    query: str,
    *,
    max_chunks: int = 3,
    character_limit: int = 5000,
) -> str:
    """Seleciona localmente trechos de POP relacionados ao chamado."""
    query_terms = _terms(query)
    if not query_terms or not _POPS_DIR.exists():
        return ""

    candidates: list[tuple[int, str, str]] = []
    for path in sorted(_POPS_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        if path.name.lower() == "readme.md":
            continue
        document = _read_document(path)
        if not document:
            continue
        name_terms = _terms(str(path.relative_to(_POPS_DIR)))
        for chunk in _split_document(document):
            overlap = query_terms & _terms(chunk)
            score = len(overlap) * 3 + len(query_terms & name_terms) * 5
            if score:
                candidates.append(
                    (score, str(path.relative_to(_POPS_DIR)), chunk)
                )

    selected: list[str] = []
    used = 0
    for _, source, chunk in sorted(candidates, key=lambda item: item[0], reverse=True):
        block = f"[POP: {source}]\n{chunk}"
        if selected and used + len(block) + 2 > character_limit:
            continue
        selected.append(block)
        used += len(block) + 2
        if len(selected) >= max_chunks:
            break
    return "\n\n".join(selected)


def has_local_error_guidance(query: str) -> bool:
    """Indica se um código citado possui orientação em algum POP local.

    A verificação é genérica: o código não é mantido em uma lista do código-fonte.
    """
    codes = _ERROR_CODE_RE.findall(str(query or ""))
    if not codes or not _POPS_DIR.exists():
        return False

    for path in _POPS_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        document = _read_document(path)
        if any(re.search(rf"(?<!\d){re.escape(code)}(?!\d)", document) for code in codes):
            return True
    return False


def build_knowledge_context(
    conversation: str,
    thread_label: str,
    *,
    character_limit: int = 12000,
) -> str:
    """Monta a base usada na geração, priorizando regras e POPs relevantes."""
    institutional = load_institutional_knowledge()
    structured = retrieve_structured_system_knowledge(
        f"{thread_label}\n{conversation}"
    )
    pops = retrieve_relevant_pops(f"{thread_label}\n{conversation}")
    historical = retrieve_historical_solution_context(
        f"{thread_label}\n{conversation}"
    )
    sections: list[str] = []
    if institutional:
        sections.append(
            "REFERÊNCIA INSTITUCIONAL (regras permanentes do atendimento):\n"
            f"{institutional}"
        )
    if structured:
        sections.append(structured)
    if pops:
        sections.append(
            "PROCEDIMENTOS RELACIONADOS AO CHAMADO (use somente se aplicáveis):\n"
            f"{pops}"
        )
    if historical:
        sections.append(historical)
    return "\n\n".join(sections)[:character_limit]
