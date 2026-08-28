"""
_3cplus.py — Sistema 3c+.

Fluxo:
  Usuário clica "3c+" no ServicesView → thread "1 - 3c+ - {usuario}"
  → inicia conversa com IA; o cargo só é marcado após confirmação do usuário
  → TI digita !sistema → payload enviado ao N8N
"""

import datetime

import discord

import config
from ._engine import _start_ai_support, set_payload

_CARGO_3CPLUS_ID = config.TRESCEPLUS_ROLE_ID


async def _abrir_3cplus(interaction: discord.Interaction) -> None:
    """Cria a thread do 3c+, inicializa o payload e inicia a IA."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    channel = interaction.channel
    user = interaction.user

    if not guild or not channel:
        await interaction.followup.send("Erro ao identificar servidor/canal.", ephemeral=True)
        return

    try:
        thread = await channel.create_thread(
            name=f"1 - 3c+ - {user.display_name}",
            type=discord.ChannelType.private_thread,
            auto_archive_duration=config.THREAD_AUTO_ARCHIVE_MINUTES,
        )
    except Exception as e:
        await interaction.followup.send("Erro ao criar o tópico.", ephemeral=True)
        print(f"[3CPLUS] Erro ao criar thread: {e}")
        return

    try:
        await thread.join()
    except Exception:
        try:
            await thread.add_user(interaction.client.user)
        except Exception:
            pass

    try:
        await thread.add_user(user)
    except Exception:
        pass

    set_payload(thread.id, {
        "event": "topic_created",
        "system": "3c+",
        "user_id": user.id,
        "user_name": user.display_name,
        "user_tag": str(user),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channel_id": channel.id,
        "channel_name": getattr(channel, "name", None),
        "thread_id": thread.id,
        "thread_name": thread.name,
        "thread_url": getattr(thread, "jump_url", None),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "steps": {},
    })
    print(f"[3CPLUS] Payload inicializado: thread {thread.id}")

    await _start_ai_support(
        thread,
        user,
        initial_context=(
            "Sistema: 3c+. O solicitante ainda precisa descrever o problema; "
            "comece perguntando de forma simples o que está acontecendo."
        ),
        handoff_role_id=_CARGO_3CPLUS_ID,
    )

    await interaction.followup.send("Tópico criado! Acesse-o para continuar.", ephemeral=True)
