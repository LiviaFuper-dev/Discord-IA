"""
_falepaco.py — Sistema Falepaco.

Fluxo:
  Usuário clica "Falepaco" → ephemeral FalepacoView (some após escolha)

  → "Baixar Falepaco"   → thread "1 - Falepaco - {usuario}" + pinga cargo TI
                           payload inicializado → enviado via !sistema

  → "Dúvidas com senha" → ephemeral orientando a chamar o gestor (some em 15s)
                           payload enviado imediatamente ao N8N (sem thread)

  → "Outros"            → thread "1 - Falepaco - {usuario}" + pinga cargo TI
                           payload inicializado → enviado via !sistema
"""

import asyncio
import datetime

import discord

import config
from ._engine import PENDING_PAYLOADS, _start_ai_support, _update_step, set_payload
from utils import n8n as n8n_utils

_CARGO_FALEPACO_ID = 1415390806541598831


class FalepacoView(discord.ui.View):
    """Ephemeral com as três opções do Falepaco."""

    def __init__(self, menu_interaction: discord.Interaction = None):
        super().__init__(timeout=None)
        self.menu_interaction = menu_interaction

    async def _fechar_este_ephemeral(self) -> None:
        """Apaga o FalepacoView ephemeral após 3s."""
        if self.menu_interaction:
            await asyncio.sleep(3)
            try:
                await self.menu_interaction.delete_original_response()
            except Exception:
                pass

    async def _criar_thread(
        self, interaction: discord.Interaction, opcao: str
    ) -> discord.Thread | None:
        """Cria a thread, inicializa o payload e retorna a thread."""
        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user

        if not guild or not channel:
            await interaction.followup.send("Erro ao identificar servidor/canal.", ephemeral=True)
            return None

        try:
            thread = await channel.create_thread(
                name=f"1 - Falepaco - {user.display_name}",
                type=discord.ChannelType.private_thread,
                auto_archive_duration=config.THREAD_AUTO_ARCHIVE_MINUTES,
            )
        except Exception as e:
            await interaction.followup.send("Erro ao criar o tópico.", ephemeral=True)
            print(f"[FALEPACO] Erro ao criar thread ({opcao}): {e}")
            return None

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
            "system": "Falepaco",
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
            "steps": {
                "opcao": opcao,
            },
        })
        print(f"[FALEPACO] Payload inicializado ({opcao}): thread {thread.id}")
        return thread

    # ── Baixar Falepaco ───────────────────────────────────────────────────────

    @discord.ui.button(label="Baixar Falepaco 📥", style=discord.ButtonStyle.primary)
    async def baixar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        thread = await self._criar_thread(interaction, "download")
        if not thread:
            return

        await _start_ai_support(
            thread,
            interaction.user,
            initial_context=(
                "Sistema: Falepaco. Solicitação: baixar ou instalar o Falepaco. "
                "Não peça acesso remoto nem dados do AnyDesk. Como a instalação "
                "precisa da equipe, ofereça intervenção humana e aguarde confirmação."
            ),
            handoff_role_id=_CARGO_FALEPACO_ID,
        )

        await interaction.followup.send("Tópico criado! Acesse-o para continuar.", ephemeral=True)
        await self._fechar_este_ephemeral()

    # ── Dúvidas com senha ─────────────────────────────────────────────────────

    @discord.ui.button(label="Dúvidas com senha 🔑", style=discord.ButtonStyle.secondary)
    async def esqueci_senha(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Oi, tudo bem? 😊 Que pena que você está com dúvidas sobre sua senha!\n\n"
            "🔑 Para ter acesso ou recuperar a senha do **Falepaco** você precisa falar "
            "diretamente com o seu **gestor**, tá bem? Ele é o responsável por fazer esse ajuste pra você.\n\n"
            "📌 Qualquer outra dúvida, pode me chamar aqui que eu apareço! 🚀",
            ephemeral=True,
        )

        guild = interaction.guild
        channel = interaction.channel
        user = interaction.user

        if guild and config.N8N_WEBHOOK_SISTEMAS:
            payload = {
                "event": "falepaco_duvida_senha",
                "system": "Falepaco",
                "opcao": "duvida_senha",
                "user_id": user.id,
                "user_name": user.display_name,
                "user_tag": str(user),
                "guild_id": guild.id,
                "guild_name": guild.name,
                "channel_id": getattr(channel, "id", None),
                "channel_name": getattr(channel, "name", None),
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }
            await n8n_utils.send(config.N8N_WEBHOOK_SISTEMAS, payload)
            print(f"[FALEPACO] Payload 'duvida_senha' enviado para N8N.")

        await self._fechar_este_ephemeral()

        await asyncio.sleep(15)
        try:
            await interaction.delete_original_response()
        except Exception:
            pass

    # ── Outros ────────────────────────────────────────────────────────────────

    @discord.ui.button(label="Outros ❓", style=discord.ButtonStyle.danger)
    async def outros(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        thread = await self._criar_thread(interaction, "outros")
        if not thread:
            return

        await _start_ai_support(
            thread,
            interaction.user,
            initial_context=(
                "Sistema: Falepaco. Opção selecionada: outro problema. "
                "Comece perguntando de forma simples o que está acontecendo."
            ),
            handoff_role_id=_CARGO_FALEPACO_ID,
        )

        await interaction.followup.send("Tópico criado! Acesse-o para continuar.", ephemeral=True)
        await self._fechar_este_ephemeral()


async def _abrir_falepaco_menu(interaction: discord.Interaction) -> None:
    """Envia o ephemeral com FalepacoView."""
    await interaction.response.send_message(
        "Selecione uma opção do **Falepaco**:",
        view=FalepacoView(menu_interaction=interaction),
        ephemeral=True,
    )
