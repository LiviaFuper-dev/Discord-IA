"""Estrutura padronizada para registrar o encerramento de chamados."""

from __future__ import annotations

import datetime


SOLUTION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Permissão/cadastro ajustado", "permissao_cadastro"),
    ("Cache ou navegador", "cache_navegador"),
    ("Serviço ou robô reiniciado", "servico_robo_reiniciado"),
    ("Configuração corrigida", "configuracao_corrigida"),
    ("Programa instalado/reinstalado", "programa_instalado"),
    ("Encaminhado ao fornecedor", "encaminhado_fornecedor"),
    ("Não foi possível reproduzir", "nao_reproduzido"),
    ("Outro", "outro"),
)

RESULT_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Resolvido", "resolvido"),
    ("Solução temporária", "solucao_temporaria"),
    ("Encaminhado / pendente", "encaminhado_pendente"),
    ("Não resolvido", "nao_resolvido"),
)

_SOLUTION_LABELS = {value: label for label, value in SOLUTION_OPTIONS}
_RESULT_LABELS = {value: label for label, value in RESULT_OPTIONS}


def build_resolution_payload(
    *,
    category: str,
    result: str,
    description: str,
    resolver: str,
) -> dict[str, str]:
    """Cria nomes técnicos e legíveis para Discord, n8n e ClickUp."""
    category_label = _SOLUTION_LABELS.get(category, category)
    result_label = _RESULT_LABELS.get(result, result)
    description = str(description or "").strip()
    resolver = str(resolver or "").strip()
    resolved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "solucao_final_categoria": category,
        "solucao_final_categoria_label": category_label,
        "solucao_final": description,
        "resultado_final": result,
        "resultado_final_label": result_label,
        "resolvido_por": resolver,
        "resolvido_em": resolved_at,
        "Solução final": f"{category_label}: {description}",
        "Resultado final": result_label,
    }


def resolution_log_block(payload: dict) -> str:
    """Formata o encerramento para permanecer no histórico enviado ao ClickUp."""
    return (
        "\n\n=== Encerramento do atendimento ===\n"
        f"Categoria: {payload.get('solucao_final_categoria_label') or '-'}\n"
        f"Solução aplicada: {payload.get('solucao_final') or '-'}\n"
        f"Resultado: {payload.get('resultado_final_label') or '-'}\n"
        f"Registrado por: {payload.get('resolvido_por') or '-'}\n"
        f"Registrado em: {payload.get('resolvido_em') or '-'}"
    )
