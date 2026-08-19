"""Cliente somente de leitura para o histórico de chamados no ClickUp."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

import config


class ClickUpError(RuntimeError):
    """Erro seguro ao consultar o ClickUp, sem expor token ou dados."""


@dataclass(frozen=True)
class ClickUpListCheck:
    """Resultado sem conteúdo de chamado usado para confirmar uma conexão."""

    list_id: str
    tasks_on_first_page: int
    last_page: bool


def _ensure_configuration() -> None:
    if not config.CLICKUP_API_TOKEN:
        raise ClickUpError("CLICKUP_API_TOKEN não está configurado no .env.")
    if not config.CLICKUP_SUPPORT_LIST_IDS:
        raise ClickUpError("CLICKUP_SUPPORT_LIST_IDS não está configurado no .env.")


def _error_for_status(status: int) -> ClickUpError:
    if status == 401:
        return ClickUpError("O token do ClickUp foi recusado.")
    if status == 403:
        return ClickUpError("A conta do ClickUp não tem acesso a esta lista.")
    if status == 404:
        return ClickUpError("A lista configurada não foi encontrada no ClickUp.")
    if status == 429:
        return ClickUpError("O limite de consultas do ClickUp foi atingido. Tente novamente mais tarde.")
    return ClickUpError(f"O ClickUp não respondeu como esperado (HTTP {status}).")


async def _get_list_page(
    session: aiohttp.ClientSession,
    list_id: str,
    *,
    page: int,
) -> dict[str, Any]:
    url = f"{config.CLICKUP_API_BASE_URL}/list/{list_id}/task"
    params = {
        "page": page,
        "include_closed": "true",
        "subtasks": "true",
    }
    headers = {"Authorization": config.CLICKUP_API_TOKEN}
    try:
        async with session.get(url, params=params, headers=headers) as response:
            if not 200 <= response.status < 300:
                await response.read()
                raise _error_for_status(response.status)
            data = await response.json()
    except ClickUpError:
        raise
    except TimeoutError as exc:
        raise ClickUpError("O ClickUp demorou demais para responder.") from exc
    except aiohttp.ClientError as exc:
        raise ClickUpError("Não foi possível conectar ao ClickUp.") from exc

    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise ClickUpError("O ClickUp retornou uma resposta inesperada.")
    return data


async def check_read_access() -> list[ClickUpListCheck]:
    """Confirma acesso sem registrar títulos, descrições ou comentários."""
    _ensure_configuration()
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        checks: list[ClickUpListCheck] = []
        for list_id in config.CLICKUP_SUPPORT_LIST_IDS:
            page = await _get_list_page(session, list_id, page=0)
            checks.append(
                ClickUpListCheck(
                    list_id=list_id,
                    tasks_on_first_page=len(page["tasks"]),
                    last_page=bool(page.get("last_page")),
                )
            )
    return checks


async def fetch_historical_tasks(*, max_pages_per_list: int = 1000) -> list[dict[str, Any]]:
    """Lê tarefas abertas e fechadas em memória, sem alterar ou persistir nada.

    O retorno pode conter dados de chamados. Ele deve ser usado somente para a
    análise autorizada e não pode ser enviado a serviços externos sem a etapa de
    sanitização apropriada.
    """
    _ensure_configuration()
    timeout = aiohttp.ClientTimeout(total=30)
    tasks: list[dict[str, Any]] = []
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for list_id in config.CLICKUP_SUPPORT_LIST_IDS:
            for page_number in range(max_pages_per_list):
                page = await _get_list_page(session, list_id, page=page_number)
                tasks.extend(page["tasks"])
                if page.get("last_page") is True:
                    break
            else:
                raise ClickUpError(
                    "A leitura foi interrompida por segurança: a lista excedeu o limite de páginas."
                )
    return tasks
