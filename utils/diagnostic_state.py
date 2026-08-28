"""Ficha interna, sem campos visíveis, de um atendimento com IA."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_ERROR_CODE_RE = re.compile(r"(?<!\d)(\d{3,6})(?!\d)")


def _norm(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").lower())
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.split())


def _context_value(context: str, label: str) -> str:
    match = re.search(
        rf"(?<![\w]){re.escape(label)}\s*:\s*([^\.\n]+)",
        str(context or ""),
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def initial_diagnostic_state(initial_context: str) -> dict[str, Any]:
    """Cria os campos iniciais, todos internos, a partir da abertura."""
    context = str(initial_context or "")
    return {
        "sistema": (
            _context_value(context, "Sistema")
            or _context_value(context, "Área")
            or "não informado"
        ),
        "tipo_problema": _context_value(context, "Tipo de problema selecionado"),
        "subsistema": _context_value(context, "Subsistema"),
        "acao_afetada": "",
        "codigo_erro": "",
        "abrangencia": "",
        "inicio": "",
        "tentativas": {},
        "evidencia": "",
        "situacao": "em diagnóstico",
    }


def _attempt_key_from_question(question: str) -> str:
    normalized = _norm(question)
    if "cache" in normalized:
        return "cache"
    if "ctrl" in normalized or "atualizar" in normalized or "reiniciar a pagina" in normalized:
        return "atualizacao_pagina"
    if "5 minutos" in normalized or "cinco minutos" in normalized or "aguardar" in normalized:
        return "aguardar"
    if "outro navegador" in normalized:
        return "outro_navegador"
    if "reiniciar o computador" in normalized or "reinicie o computador" in normalized:
        return "reinicio_computador"
    return ""


def _status_from_reply(reply: str) -> str:
    normalized = _norm(reply)
    if any(term in normalized for term in ("nao resolveu", "nao funcionou", "continua", "nao deu certo")):
        return "tentado_sem_resolver"
    if any(term in normalized for term in ("resolveu", "funcionou", "deu certo")):
        return "resolveu"
    if any(term in normalized for term in ("ja tentei", "tentei", "fiz", "limpei", "atualizei", "reiniciei")):
        return "tentado"
    if "nao tentei" in normalized or "ainda nao" in normalized:
        return "não tentado"
    return ""


def _detect_action(normalized: str) -> str:
    action_signals = (
        ("enviar mensagem", ("enviar", "mensagem")),
        ("acessar ou entrar", ("acessar", "entrar", "login")),
        ("baixar", ("baixar", "download")),
        ("enviar mídia", ("imagem", "midia", "arquivo", "video")),
        ("abrir ou carregar", ("abrir", "carregar", "pagina")),
        ("usar automação", ("robo", "automacao", "planilha")),
    )
    for action, signals in action_signals:
        if any(signal in normalized for signal in signals):
            return action
    return ""


def update_diagnostic_state(
    state: dict[str, Any],
    message_text: str,
    *,
    attachment_count: int = 0,
    previous_question: str = "",
) -> dict[str, Any]:
    """Atualiza somente classificações seguras; não armazena texto livre do usuário."""
    normalized = _norm(message_text)
    updated = dict(state or {})
    updated.setdefault("tentativas", {})
    updated.setdefault("situacao", "em diagnóstico")

    code = _ERROR_CODE_RE.search(str(message_text or ""))
    code_was_requested = "codigo" in _norm(previous_question)
    if code and (
        "erro" in normalized
        or "codigo" in normalized
        or "#" in str(message_text or "")
        or code_was_requested
    ):
        updated["codigo_erro"] = code.group(1)

    action = _detect_action(normalized)
    if action:
        updated["acao_afetada"] = action

    if any(term in normalized for term in ("todos os clientes", "todo mundo", "todos estao")):
        updated["abrangencia"] = "todos"
    elif any(term in normalized for term in ("varios", "alguns clientes", "mais de um")):
        updated["abrangencia"] = "vários"
    elif any(term in normalized for term in ("apenas esse", "um cliente", "so esse")):
        updated["abrangencia"] = "um caso"

    if "desde ontem" in normalized:
        updated["inicio"] = "desde ontem"
    elif "hoje" in normalized:
        updated["inicio"] = "hoje"
    elif any(term in normalized for term in ("agora", "acabou de", "neste momento")):
        updated["inicio"] = "agora"

    if attachment_count:
        updated["evidencia"] = "anexo ou print enviado"
    elif any(term in normalized for term in ("enviei o print", "mandei o print", "print enviado")):
        updated["evidencia"] = "print informado"

    attempt_key = _attempt_key_from_question(previous_question)
    attempt_status = _status_from_reply(message_text)
    if attempt_key and attempt_status:
        updated["tentativas"][attempt_key] = attempt_status
    else:
        direct_attempts = {
            "cache": ("cache", "cachê"),
            "atualizacao_pagina": ("ctrl f5", "atualizei a pagina", "recarreguei"),
            "aguardar": ("esperei", "aguardei", "5 minutos", "cinco minutos"),
            "reinicio_computador": ("reiniciei o computador", "reiniciei o pc"),
            "outro_navegador": ("outro navegador", "chrome", "edge", "firefox"),
        }
        for key, signals in direct_attempts.items():
            if any(signal in normalized for signal in signals):
                updated["tentativas"][key] = attempt_status or "informado"

    return updated


def format_diagnostic_state(state: dict[str, Any] | None) -> str:
    """Produz contexto compacto para a IA e para o resumo, nunca exibido diretamente."""
    if not state:
        return ""
    labels = (
        ("sistema", "Sistema"),
        ("tipo_problema", "Tipo"),
        ("subsistema", "Subsistema"),
        ("acao_afetada", "Ação afetada"),
        ("codigo_erro", "Código"),
        ("abrangencia", "Abrangência"),
        ("inicio", "Início"),
        ("evidencia", "Evidência"),
        ("situacao", "Situação"),
    )
    lines = [
        f"- {label}: {state[key]}"
        for key, label in labels
        if state.get(key)
    ]
    attempts = state.get("tentativas") or {}
    if attempts:
        rendered = ", ".join(f"{key}: {value}" for key, value in attempts.items())
        lines.append(f"- Tentativas: {rendered}")
    if not lines:
        return ""
    return "FICHA INTERNA DO CHAMADO (não mostre ao usuário):\n" + "\n".join(lines)
