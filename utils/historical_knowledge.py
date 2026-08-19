"""Padrões sanitizados de soluções históricas do ClickUp.

O módulo não envia conteúdo do ClickUp a serviços externos e não altera tarefas.
Ele usa campos de classificação/solução e linhas explicitamente rotuladas de
encerramento, gera contagens agregadas e deixa as soluções históricas como
referência — nunca como POP aprovado automaticamente.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
from utils.clickup import ClickUpError, fetch_historical_tasks


_ROOT = Path(__file__).resolve().parent.parent
_PATTERNS_FILE = _ROOT / "data" / "clickup_solution_patterns.json"
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?55[\s.-]*)?(?:\(?\d{2}\)?[\s.-]*)?(?:9?\d{4})[\s.-]?\d{4}(?!\d)")
_SECRET_RE = re.compile(r"\b(?:gsk_|sk-)[A-Za-z0-9_-]{16,}\b")
_FIELD_HINTS = {
    "sistema": ("sistema", "plataforma", "setor"),
    "problema": ("problema", "tipo", "categoria", "motivo", "erro"),
    "solucao": ("solucao", "solução", "resolucao", "resolução", "acao", "ação"),
    "resultado": ("resultado", "status final", "desfecho"),
}
_DESCRIPTION_LABELS = {
    "sistema": ("sistema", "plataforma", "setor"),
    "problema": ("problema", "motivo", "categoria"),
    "solucao": ("solução aplicada", "solucao aplicada", "solução", "solucao"),
    "resultado": ("resultado final", "resultado", "desfecho"),
}
_ACTION_FIELD_HINTS = (
    "cache", "f5", "atualiz", "espera", "reinici", "reinstal", "navegador",
)
_SUCCESS_OPTION_HINTS = ("resolveu", "sucesso", "concluido", "concluído")


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def _clean_text(value: Any, *, limit: int = 280) -> str:
    text = str(value or "").strip()
    text = _SECRET_RE.sub("[CHAVE REMOVIDA]", text)
    text = _EMAIL_RE.sub("[E-MAIL REMOVIDO]", text)
    text = _CPF_RE.sub("[CPF REMOVIDO]", text)
    text = _PHONE_RE.sub("[TELEFONE REMOVIDO]", text)
    text = " ".join(text.split())
    return text[:limit]


def _field_value(field: dict[str, Any]) -> str:
    value = field.get("value")
    if value in (None, ""):
        return ""
    config_options = (field.get("type_config") or {}).get("options") or []
    value_text = str(value)
    for option in config_options:
        if str(option.get("id")) == value_text or str(option.get("orderindex")) == value_text:
            return _clean_text(option.get("name"))
    if isinstance(value, (dict, list)):
        return ""
    return _clean_text(value)


def _task_fields(task: dict[str, Any]) -> dict[str, str]:
    extracted = {name: "" for name in _FIELD_HINTS}
    for field in task.get("custom_fields") or []:
        field_name = _normalize(field.get("name", ""))
        value = _field_value(field)
        if not value:
            continue
        for destination, hints in _FIELD_HINTS.items():
            if not extracted[destination] and any(hint in field_name for hint in hints):
                extracted[destination] = value
                break

    # Alguns fluxos registram o encerramento como linhas identificadas na
    # descrição. O texto livre e o restante do histórico continuam ignorados.
    description = str(task.get("description") or "")
    for line in description.splitlines():
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        normalized_label = _normalize(label)
        clean_value = _clean_text(value)
        if not clean_value:
            continue
        for destination, labels in _DESCRIPTION_LABELS.items():
            if not extracted[destination] and normalized_label in labels:
                extracted[destination] = clean_value
                break
    return extracted


def _is_successful(fields: dict[str, str]) -> bool:
    result = _normalize(fields.get("resultado", ""))
    return not result or any(term in result for term in ("resolvido", "concluido", "sucesso", "feito"))


def _resolved_action_fields(task: dict[str, Any]) -> list[str]:
    """Extrai ações marcadas como resolvidas em campos de checklist do ClickUp."""
    actions: list[str] = []
    for field in task.get("custom_fields") or []:
        name = _clean_text(field.get("name"))
        choice = _normalize(_field_value(field))
        if (
            name
            and any(hint in _normalize(name) for hint in _ACTION_FIELD_HINTS)
            and any(hint in choice for hint in _SUCCESS_OPTION_HINTS)
        ):
            actions.append(name)
    return actions


def build_solution_patterns(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa campos estruturados e linhas de encerramento, ignorando texto livre."""
    counts: Counter[tuple[str, str, str]] = Counter()
    for task in tasks:
        fields = _task_fields(task)
        solutions = [fields["solucao"]] if fields["solucao"] else _resolved_action_fields(task)
        if not solutions or not _is_successful(fields):
            continue
        system = fields["sistema"] or "Sistema não informado"
        problem = fields["problema"] or "Problema não informado"
        for solution in solutions:
            counts[(system, problem, solution)] += 1

    return [
        {
            "sistema": system,
            "problema": problem,
            "solucao": solution,
            "ocorrencias": count,
        }
        for (system, problem, solution), count in counts.most_common(100)
    ]


def _save_patterns(patterns: list[dict[str, Any]], *, tasks_read: int) -> None:
    _PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tasks_read": tasks_read,
        "patterns": patterns,
    }
    temporary = _PATTERNS_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(_PATTERNS_FILE)


async def refresh_clickup_knowledge() -> dict[str, int]:
    """Atualiza a base histórica em memória/disco, sem modificar o ClickUp."""
    if not config.CLICKUP_KNOWLEDGE_ENABLED:
        return {"tasks_read": 0, "patterns": 0}
    try:
        tasks = await fetch_historical_tasks(
            max_pages_per_list=config.CLICKUP_KNOWLEDGE_MAX_PAGES
        )
    except ClickUpError:
        raise
    patterns = build_solution_patterns(tasks)
    _save_patterns(patterns, tasks_read=len(tasks))
    return {"tasks_read": len(tasks), "patterns": len(patterns)}


def retrieve_historical_solution_context(query: str, *, character_limit: int = 3000) -> str:
    """Seleciona padrões relevantes já agregados, sem expor chamados brutos."""
    if not _PATTERNS_FILE.exists():
        return ""
    try:
        payload = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    query_terms = {
        term for term in re.findall(r"[a-z0-9]{3,}", _normalize(query))
        if term not in {"com", "para", "erro", "sistema", "problema"}
    }
    if not query_terms:
        return ""
    selected: list[str] = []
    used = 0
    ranked = []
    for pattern in payload.get("patterns") or []:
        text = " ".join(str(pattern.get(key, "")) for key in ("sistema", "problema", "solucao"))
        score = len(query_terms & set(re.findall(r"[a-z0-9]{3,}", _normalize(text))))
        if score:
            ranked.append((score, int(pattern.get("ocorrencias", 0)), pattern))
    for _, _, pattern in sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True):
        block = (
            f"- Sistema: {pattern['sistema']}; problema: {pattern['problema']}; "
            f"solução registrada: {pattern['solucao']} "
            f"({pattern['ocorrencias']} ocorrência(s))."
        )
        if selected and used + len(block) + 1 > character_limit:
            continue
        selected.append(block)
        used += len(block) + 1
        if len(selected) >= 5:
            break
    if not selected:
        return ""
    return (
        "PADRÕES HISTÓRICOS DO CLICKUP (referência agregada; valide antes de aplicar):\n"
        + "\n".join(selected)
    )
