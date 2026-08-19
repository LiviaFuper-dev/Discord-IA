"""
Executa somente o comando !ia para testes seguros no Discord.

Não publica menus, não inicia monitores e não altera chamados automaticamente.
"""

import datetime
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import discord
from discord.ext import commands

import config
from modules import ia as ia_module


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
ia_module.setup(bot)
_STATUS_FILE = Path(".runtime/ai-only-status.json")
_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _write_status(status: str, **details) -> None:
    payload = {
        "status": status,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        **details,
    }
    _STATUS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@bot.event
async def on_ready() -> None:
    guild_names = ", ".join(guild.name for guild in bot.guilds) or "nenhum servidor"
    _write_status(
        "ready",
        bot_user=str(bot.user),
        bot_user_id=bot.user.id,
        guilds=[{"id": guild.id, "name": guild.name} for guild in bot.guilds],
    )
    print(
        f"[IA-ONLY] Conectado como {bot.user} (ID: {bot.user.id}) | "
        f"Servidores: {guild_names}",
        flush=True,
    )


@bot.event
async def on_command_completion(ctx: commands.Context) -> None:
    _write_status(
        "command_completed",
        command=ctx.command.qualified_name if ctx.command else None,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel.id,
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    _write_status(
        "command_error",
        command=ctx.command.qualified_name if ctx.command else None,
        guild_id=ctx.guild.id if ctx.guild else None,
        channel_id=ctx.channel.id,
        error_type=type(error).__name__,
        error=str(error)[:500],
    )
    print(f"[IA-ONLY] Erro no comando '{ctx.message.content}': {error}", flush=True)


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN não definido no .env")
    if not config.GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY não definido no .env")
    _write_status("starting")
    try:
        bot.run(config.DISCORD_TOKEN, log_handler=None)
    except Exception as exc:
        _write_status(
            "startup_error",
            error_type=type(exc).__name__,
            error=str(exc)[:500],
        )
        raise
