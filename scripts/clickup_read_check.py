"""Verifica acesso de leitura ao ClickUp sem mostrar conteúdo de chamados."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from utils.clickup import ClickUpError, check_read_access


async def main() -> None:
    try:
        checks = await check_read_access()
    except ClickUpError as exc:
        raise SystemExit(f"Falha ao verificar o ClickUp: {exc}") from exc

    for check in checks:
        print(
            "ClickUp: leitura autorizada "
            f"(lista {check.list_id}, {check.tasks_on_first_page} tarefa(s) na primeira página, "
            f"última página: {'sim' if check.last_page else 'não'})."
        )


if __name__ == "__main__":
    asyncio.run(main())
