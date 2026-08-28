"""Teste ponta a ponta: Discord -> sanitização -> Groq -> Discord."""

from __future__ import annotations

import asyncio
import datetime
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import discord

import config
from utils.ai import (
    collect_sanitized_context,
    generate_support_suggestion,
    safe_thread_label,
)


_RESULT_FILE = Path(".runtime/discord-ai-smoke-result.json")
_RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _save_result(status: str, **details) -> None:
    _RESULT_FILE.write_text(
        json.dumps(
            {
                "status": status,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                **details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class SmokeClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.started = False

    async def on_ready(self) -> None:
        if self.started:
            return
        self.started = True

        try:
            guild = next(
                (
                    candidate
                    for guild_id in config.SERVIDORES
                    if (candidate := self.get_guild(guild_id)) is not None
                ),
                None,
            )
            if guild is None:
                raise RuntimeError("Nenhum servidor configurado foi encontrado.")

            channel_id = config.SERVIDORES[guild.id].get("canal_unificado")
            channel = guild.get_channel(channel_id) if channel_id else None
            if not isinstance(channel, discord.TextChannel):
                raise RuntimeError("Canal unificado de teste não encontrado.")

            timestamp = datetime.datetime.now().strftime("%H%M%S")
            thread = await channel.create_thread(
                name=f"1 - Teste IA - Codex {timestamp}",
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60,
            )
            try:
                await thread.join()
            except Exception:
                pass

            owner = guild.get_member(guild.owner_id)
            if owner is None:
                try:
                    owner = await guild.fetch_member(guild.owner_id)
                except Exception:
                    owner = None
            if owner:
                try:
                    await thread.add_user(owner)
                except Exception:
                    pass

            await thread.send(
                "🧪 **Teste automático da IA**\n\n"
                "O sistema fictício está lento desde hoje. A página já foi atualizada, "
                "mas o computador ainda não foi reiniciado. Este texto não contém dados reais."
            )

            context = await collect_sanitized_context(thread)
            suggestion = await generate_support_suggestion(
                context,
                safe_thread_label(thread.name),
            )

            embed = discord.Embed(
                title="🤖 Sugestão de diagnóstico — TESTE",
                description=suggestion[:4000],
                color=discord.Color.purple(),
            )
            embed.set_footer(
                text="Teste com dados fictícios — valide a sugestão antes de aplicar."
            )
            response_message = await thread.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
            )

            verified = False
            async for message in thread.history(limit=5):
                if message.id == response_message.id and any(
                    item.title == "🤖 Sugestão de diagnóstico — TESTE"
                    for item in message.embeds
                ):
                    verified = True
                    break

            _save_result(
                "success" if verified else "verification_failed",
                guild_id=guild.id,
                guild_name=guild.name,
                channel_id=channel.id,
                thread_id=thread.id,
                thread_name=thread.name,
                thread_url=f"https://discord.com/channels/{guild.id}/{thread.id}",
                response_message_id=response_message.id,
                response_characters=len(suggestion),
                verified=verified,
            )
        except Exception as exc:
            _save_result(
                "error",
                error_type=type(exc).__name__,
                error=str(exc)[:500],
            )
        finally:
            await self.close()


async def main() -> None:
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN não definido no .env")
    if not config.GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY não definido no .env")

    client = SmokeClient()
    await client.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
