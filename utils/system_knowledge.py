"""Consulta da base estruturada de regras específicas por sistema."""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


_FILE = Path(__file__).resolve().parent.parent / "knowledge_base" / "systems.json"


@lru_cache(maxsize=1)
def load_system_catalog() -> dict[str, Any]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8")).get("systems", {})
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[IA] Base estruturada de sistemas indisponível: {exc}")
        return {}


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents).strip()


def _pick_system(query: str) -> tuple[str, dict[str, Any]] | None:
    normalized = _norm(query)
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    for name, data in load_system_catalog().items():
        aliases = [name, *data.get("aliases", [])]
        score = max((len(alias) for alias in aliases if _norm(alias) in normalized), default=0)
        if score:
            candidates.append((score, name, data))
    if not candidates:
        return None
    _, name, data = max(candidates, key=lambda item: item[0])
    return name, data


def retrieve_structured_system_knowledge(
    query: str,
    *,
    character_limit: int = 6500,
) -> str:
    """Retorna somente as regras do sistema identificado no chamado."""
    selected = _pick_system(query)
    if not selected:
        return ""
    name, data = selected
    normalized = _norm(query)
    problem_types = data.get("problem_types", {})
    selected_type = "default"
    type_aliases = {
        "permissao_cadastro": ("permissao", "cadastro"),
        "mensagem_de_erro": ("mensagem de erro",),
        "mensagem_de_aviso": ("mensagem de aviso",),
        "pagina_nao_carrega": ("pagina nao carrega",),
        "lentidao_travamento": ("lentidao", "travamento"),
    }
    for problem_type in problem_types:
        permission_match = problem_type == "permissao_cadastro" and any(
            term in normalized for term in ("permiss", "cadastro", "acesso")
        )
        if problem_type != "default" and (
            _norm(problem_type) in normalized
            or _norm(problem_type.replace("_", " ")) in normalized
            or all(term in normalized for term in type_aliases.get(problem_type, ()))
            or permission_match
        ):
            selected_type = problem_type
            break
    rules = problem_types.get(selected_type) or problem_types.get("default", {})

    lines = [
        f"Sistema estruturado: {name}",
        f"Responsável: {data.get('responsible', 'equipe responsável')}",
        f"Perguntas obrigatórias (coletar sem listar para o usuário): {', '.join(rules.get('required_questions', []))}",
        f"Testes/ações seguros: {', '.join(rules.get('safe_actions', [])) or 'nenhum teste genérico'}",
        f"Ações proibidas: {', '.join(rules.get('avoid', []))}",
        f"Escalonar quando: {', '.join(rules.get('escalate_when', []))}",
    ]
    solutions = data.get("error_solutions", {})
    if solutions:
        relevant = []
        for code, solution in solutions.items():
            if re.search(rf"(?<!\d){re.escape(code)}(?!\d)", query or ""):
                relevant.append(f"{code}: {solution}")
        if relevant:
            lines.append("Soluções aprovadas para códigos citados: " + " | ".join(relevant))
        else:
            lines.append("Soluções por código disponíveis somente quando o usuário informar o código exato.")
    return "BASE ESTRUTURADA DO SISTEMA (priorize regras e POPs):\n" + "\n".join(lines)
