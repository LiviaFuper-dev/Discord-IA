"""
_command.py — Comando !sistema e SectorSelectView.

Contém:
  - SectorSelectView      (seleção de setor do colaborador → envia N8N → deleta thread)
  - _remove_non_allowed() (remove membros sem cargo autorizado da thread)
  - setup()               (registra o comando !sistema no bot)
"""

import discord
from discord.ext import commands

import config
from utils.logs import coletar_historico, enviar_log_conversa
from utils.resolution import (
    RESULT_OPTIONS,
    SOLUTION_OPTIONS,
    build_resolution_payload,
    resolution_log_block,
)
from ._engine import (
    PENDING_PAYLOADS,
    _allowed_roles,
    _empresa_clickup,
    _member_has_role,
    _send_to_n8n,
    pop_payload,
)


# ── Encerramento estruturado de Sistemas ─────────────────────────────────────

async def _authorized_interaction(interaction: discord.Interaction) -> bool:
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Servidor não identificado.", ephemeral=True)
        return False
    allowed = _allowed_roles(guild.id)
    member = guild.get_member(interaction.user.id)
    if member is None:
        try:
            member = await guild.fetch_member(interaction.user.id)
        except Exception:
            member = None
    if _member_has_role(member, allowed):
        return True
    await interaction.response.send_message(
        "Apenas membros autorizados podem preencher este formulário.",
        ephemeral=True,
    )
    return False


class SystemResolutionDescriptionModal(
    discord.ui.Modal,
    title="Descreva a solução aplicada",
):
    def __init__(self, target_view: "SystemResolutionView"):
        super().__init__()
        self.target_view = target_view
        self.description = discord.ui.TextInput(
            label="O que foi feito?",
            style=discord.TextStyle.long,
            placeholder="Descreva brevemente a ação realizada pela equipe.",
            required=True,
            min_length=5,
            max_length=1000,
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.target_view.solution_description = self.description.value.strip()
        await interaction.response.send_message(
            "✅ Descrição da solução registrada.",
            ephemeral=True,
        )


async def _finalize_system_resolution(
    interaction: discord.Interaction,
    *,
    guild_id: int,
    thread_id: int,
    sector: str,
    resolution: dict,
) -> bool:
    payload = PENDING_PAYLOADS.get(thread_id)
    if payload is None:
        await interaction.followup.send(
            "Payload não encontrado (já enviado?).",
            ephemeral=True,
        )
        return False

    payload = dict(payload)
    steps = payload.get("steps", {})
    if payload.get("system") in {"E-mail", "Google Drive"}:
        email_selecionado = steps.get("email_selecionado") or steps.get("dominio_detectado")
        payload["email_selecionado"] = email_selecionado
        payload["email_usuario"] = steps.get("email_usuario")
        payload["problema_relatado"] = steps.get("problema")

    empresa_value, empresa_label = _empresa_clickup(guild_id)
    if empresa_value:
        payload["empresa"] = empresa_value
        payload["Empresa"] = empresa_label
        payload["empresa_label"] = empresa_label

    payload["setor"] = sector
    payload.update(resolution)
    payload["conversa"] = await coletar_historico(interaction.channel)
    if payload.get("system") in {"E-mail", "Google Drive"}:
        payload["conversa"] += (
            "\n\n=== Dados do E-mail ===\n"
            f"E-mail selecionado: {payload.get('email_selecionado') or '-'}\n"
            f"E-mail informado: {payload.get('email_usuario') or '-'}\n"
            f"Problema relatado: {payload.get('problema_relatado') or '-'}"
        )
    payload["conversa"] += resolution_log_block(resolution)

    if not await _send_to_n8n(payload):
        await interaction.followup.send(
            "Erro ao enviar para o N8N. Verifique os logs.",
            ephemeral=True,
        )
        return False

    pop_payload(thread_id)
    thread = interaction.channel
    await thread.send(
        f"✅ Atendimento encerrado. Resultado: **{resolution['resultado_final_label']}**."
    )
    await interaction.followup.send("Encaminhado com sucesso.", ephemeral=True)

    canal_logs_id = config.SERVIDORES.get(guild_id, {}).get("canal_logs")
    if canal_logs_id:
        await enviar_log_conversa(
            thread,
            interaction.guild,
            canal_logs_id,
            prefixo_log="⚙️",
            header_extra=(
                f"=== Sistemas ===\nSetor: {sector}\n"
                f"Solução: {resolution['Solução final']}\n"
                f"Resultado: {resolution['Resultado final']}"
            ),
        )

    try:
        await thread.delete()
        print(f"[SISTEMAS] Thread {thread_id} deletada após envio.")
    except Exception as exc:
        print(f"[SISTEMAS] Não foi possível deletar thread {thread_id}: {exc}")
    return True


class SystemResolutionView(discord.ui.View):
    def __init__(self, guild_id: int, thread_id: int, sector: str):
        super().__init__(timeout=180.0)
        self.guild_id = guild_id
        self.thread_id = thread_id
        self.sector = sector
        self.selected_solution: str | None = None
        self.selected_result: str | None = None
        self.solution_description: str | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _authorized_interaction(interaction)

    @discord.ui.select(
        placeholder="Categoria da solução aplicada",
        min_values=1,
        max_values=1,
        row=0,
        options=[
            discord.SelectOption(label=label, value=value)
            for label, value in SOLUTION_OPTIONS
        ],
    )
    async def solution_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.selected_solution = select.values[0]
        await interaction.response.send_message("✅ Categoria selecionada.", ephemeral=True)

    @discord.ui.select(
        placeholder="Resultado final do chamado",
        min_values=1,
        max_values=1,
        row=1,
        options=[
            discord.SelectOption(label=label, value=value)
            for label, value in RESULT_OPTIONS
        ],
    )
    async def result_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.selected_result = select.values[0]
        await interaction.response.send_message("✅ Resultado selecionado.", ephemeral=True)

    @discord.ui.button(label="📝 Descrever solução", style=discord.ButtonStyle.secondary, row=2)
    async def describe_solution(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(SystemResolutionDescriptionModal(self))

    @discord.ui.button(label="✅ Confirmar encerramento", style=discord.ButtonStyle.danger, row=2)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.selected_solution or not self.selected_result or not self.solution_description:
            await interaction.response.send_message(
                "Selecione a solução e o resultado e descreva o que foi feito.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        resolution = build_resolution_payload(
            category=self.selected_solution,
            result=self.selected_result,
            description=self.solution_description,
            resolver=interaction.user.display_name,
        )
        if await _finalize_system_resolution(
            interaction,
            guild_id=self.guild_id,
            thread_id=self.thread_id,
            sector=self.sector,
            resolution=resolution,
        ):
            self.stop()


class SectorSelectView(discord.ui.View):
    def __init__(self, guild_id: int, thread_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.thread_id = thread_id
        options = [
            discord.SelectOption(label=sector, value=sector)
            for sector in ["Comercial", "Administrativo", "Jurídico", "Financeiro", "RH", "Marketing", "TI", "Todos"]
        ]
        self._select = discord.ui.Select(
            placeholder="Selecione o setor do colaborador",
            options=options,
            custom_id=f"sistemas_sector_{thread_id}",
            min_values=1,
            max_values=1,
        )
        self._select.callback = self._on_select
        self.add_item(self._select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await _authorized_interaction(interaction)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        selected = self._select.values[0]
        self._select.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            "Agora registre a solução e o resultado final do atendimento.",
            view=SystemResolutionView(self.guild_id, self.thread_id, selected),
            ephemeral=True,
        )
        self.stop()


# ── Helpers do comando ────────────────────────────────────────────────────────

async def _remove_non_allowed(
    thread: discord.Thread, guild: discord.Guild, allowed: set[int]
) -> tuple[list, list]:
    removed, failed = [], []
    try:
        await thread.fetch_members()
    except Exception:
        pass
    for tm in thread.members:
        try:
            member = guild.get_member(tm.id)
            if member is None:
                member = await guild.fetch_member(tm.id)
            if member.bot:
                continue
            if not _member_has_role(member, allowed):
                await thread.remove_user(member)
                removed.append(member.id)
        except Exception as e:
            failed.append(tm.id)
            print(f"[SISTEMAS] Erro ao remover {tm.id}: {e}")
    return removed, failed


# ── setup ─────────────────────────────────────────────────────────────────────

def setup(bot: commands.Bot) -> None:
    @bot.command(name="sistema")
    async def sistema_cmd(ctx: commands.Context):
        guild = ctx.guild
        channel = ctx.channel

        if not guild or not isinstance(channel, discord.Thread):
            await ctx.reply(
                "Este comando só pode ser usado dentro de um tópico.", mention_author=False
            )
            return

        if not channel.name.startswith("1 -"):
            await ctx.reply(
                "Este comando só funciona em tópicos de sistemas (prefixo '1 -').",
                mention_author=False,
            )
            return

        allowed = _allowed_roles(guild.id)
        member = ctx.author if isinstance(ctx.author, discord.Member) else None
        if member is None:
            try:
                member = await guild.fetch_member(ctx.author.id)
            except Exception:
                member = None

        if not _member_has_role(member, allowed):
            await ctx.reply(
                "Apenas membros autorizados (TI/ChatGuru/Whom/ClickUp) podem executar este comando.",
                mention_author=False,
            )
            return

        removed, failed = await _remove_non_allowed(channel, guild, allowed)
        summary = f"Removidos: {len(removed)}."
        if failed:
            summary += f" Falhas: {len(failed)} (veja logs)."
        await ctx.reply(summary, mention_author=False)

        if channel.id in PENDING_PAYLOADS:
            view = SectorSelectView(guild_id=guild.id, thread_id=channel.id)
            await channel.send(
                "Selecione o **Setor do colaborador**. Depois registre a solução "
                "e o resultado final para concluir o atendimento:",
                view=view,
            )
        else:
            await ctx.reply(
                "Nenhum payload pendente para este tópico (já enviado?).",
                mention_author=False,
            )
