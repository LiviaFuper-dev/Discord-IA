"""
Atendimento com IA para tópicos de Sistemas e Equipamentos.

Fluxo:
  Equipamentos — a conversa guiada começa automaticamente ao abrir o chamado
  Sistemas     — a conversa começa após o solicitante classificar o problema
  !ajuda       — alternativa manual para iniciar uma conversa guiada com a IA
  !resumo      — atendente gera resumo/diagnóstico para passagem do chamado
  !encerrar_ia — solicitante ou atendente encerra a conversa e gera o resumo
  !ia          — atendente gera uma análise pontual sem iniciar conversa

Chamados de Recuperar Contato nunca são enviados à IA.
"""

from __future__ import annotations

import datetime
import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands

import config
from utils.ai import (
    AIServiceError,
    collect_sanitized_context,
    generate_case_summary,
    generate_conversation_reply,
    generate_support_suggestion,
    safe_thread_label,
    sanitize_text,
    split_discord_text,
)
from utils.conversation_guides import build_conversation_guide
from utils.diagnostic_state import (
    format_diagnostic_state,
    initial_diagnostic_state,
    update_diagnostic_state,
)


_SESSIONS_FILE = Path("data/ai_sessions.json")
_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
_BUSY_THREADS: set[int] = set()
_MAX_CONVERSATION_TURNS = 8


def _load_sessions() -> dict[int, dict[str, Any]]:
    if not _SESSIONS_FILE.exists():
        return {}
    try:
        raw = json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
        return {int(key): value for key, value in raw.items()}
    except Exception as exc:
        print(f"[IA] Não foi possível carregar sessões: {exc}")
        return {}


_SESSIONS: dict[int, dict[str, Any]] = _load_sessions()


def _save_sessions() -> None:
    try:
        _SESSIONS_FILE.write_text(
            json.dumps(_SESSIONS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[IA] Não foi possível salvar sessões: {exc}")


def _support_role_ids(guild_id: int) -> set[int]:
    server = config.SERVIDORES.get(guild_id, {})
    ti_cfg = server.get("ti", {})
    sistemas_cfg = server.get("sistemas", {})

    role_ids = {
        config.CHATGURU_ROLE_ID,
        config.WHOM_ROLE_ID,
        config.CLICKUP_SUPPORT_ROLE_ID,
        config.EMAIL_MLR_ROLE_ID,
        config.EMAIL_GMAIL_ROLE_ID,
        config.TRESCEPLUS_ROLE_ID,
        config.ADMIN_EXTRA_ROLE_ID,
    }
    for value in (
        ti_cfg.get("cargo_ti"),
        ti_cfg.get("cargo_equipamentos"),
        sistemas_cfg.get("cargo_ti"),
    ):
        if value:
            role_ids.add(int(value))
    return role_ids


def _is_authorized(member: discord.Member, guild_id: int) -> bool:
    if member.guild_permissions.administrator:
        return True
    allowed = _support_role_ids(guild_id)
    return any(role.id in allowed for role in member.roles)


def _is_supported_thread(channel: discord.abc.Messageable) -> bool:
    return isinstance(channel, discord.Thread) and (
        channel.name.startswith("1 -") or channel.name.startswith("2 -")
    )


def _human_support_role_id(guild_id: int, thread_name: str) -> int | None:
    """Retorna o cargo responsável por assumir o chamado aberto pela IA."""
    server = config.SERVIDORES.get(guild_id, {})
    name = str(thread_name or "")
    if name.startswith("2 -"):
        ti_cfg = server.get("ti", {})
        role_id = ti_cfg.get("cargo_equipamentos") or ti_cfg.get("cargo_ti")
    elif name.startswith("1 -"):
        sistemas_cfg = server.get("sistemas", {})
        ti_cfg = server.get("ti", {})
        role_id = sistemas_cfg.get("cargo_ti") or ti_cfg.get("cargo_ti")
    else:
        role_id = None
    return int(role_id) if role_id else None


def _urgency_label_from_thread_name(thread_name: str) -> str | None:
    parts = [part.strip() for part in str(thread_name or "").split(" - ")]
    if len(parts) >= 2 and parts[0] == "2":
        return parts[1]
    return None


def _normalize_message(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _is_resolution_message(text: str) -> bool:
    normalized = _normalize_message(text)
    negative = (
        "nao resolveu",
        "nao funcionou",
        "ainda nao",
        "continua com",
        "continua dando",
        "nao deu certo",
    )
    if any(fragment in normalized for fragment in negative):
        return False
    positive = (
        "resolveu",
        "funcionou",
        "deu certo",
        "voltou ao normal",
        "esta funcionando agora",
    )
    return any(fragment in normalized for fragment in positive)


def _wants_human_support(text: str) -> bool:
    normalized = _normalize_message(text)
    negative = (
        "nao quero",
        "nao precisa",
        "sem atendente",
        "sem humano",
    )
    if any(fragment in normalized for fragment in negative):
        return False

    targets = (
        "atendente",
        "atendimento humano",
        "pessoa da equipe",
        "uma pessoa",
        "alguem",
        "ser humano",
        "humano",
        "suporte",
    )
    actions = (
        "quero",
        "gostaria",
        "preciso",
        "necessito",
        "falar",
        "cham",
        "intervir",
    )
    return (
        any(target in normalized for target in targets)
        and any(action in normalized for action in actions)
    )


def _offers_human_handoff(text: str) -> bool:
    normalized = _normalize_message(text)
    return "quer que eu chame uma pessoa da equipe" in normalized


def _is_affirmative_reply(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", _normalize_message(text))
    normalized = " ".join(normalized.split())
    return normalized in {
        "sim",
        "sim por favor",
        "pode",
        "pode chamar",
        "quero",
        "quero sim",
        "claro",
    }


def _is_negative_reply(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", _normalize_message(text))
    normalized = " ".join(normalized.split())
    return normalized in {
        "nao",
        "nao obrigado",
        "nao precisa",
        "quero continuar",
        "vamos continuar",
    }


def _requester_confirmed_human_handoff(
    text: str,
    *,
    awaiting_confirmation: bool,
) -> bool:
    """Só autoriza o acionamento após um pedido explícito do solicitante."""
    return _wants_human_support(text) or (
        awaiting_confirmation and _is_affirmative_reply(text)
    )


def _responses_are_similar(first: str, second: str) -> bool:
    first_normalized = " ".join(_normalize_message(first).split())
    second_normalized = " ".join(_normalize_message(second).split())
    if not first_normalized or not second_normalized:
        return False
    return difflib.SequenceMatcher(
        None,
        first_normalized,
        second_normalized,
    ).ratio() >= 0.82


def _context_with_session_details(context: str, session: dict[str, Any] | None) -> str:
    """Acrescenta dados estruturados da abertura sem poluir o chat do Discord."""
    details = sanitize_text(str((session or {}).get("initial_context") or ""))[:1200]
    diagnostic = format_diagnostic_state((session or {}).get("diagnostic"))
    sections = [context]
    if details:
        sections.append(f"Dados informados na abertura do chamado:\n{details}")
    if diagnostic:
        sections.append(diagnostic)
    return "\n\n".join(section for section in sections if section).strip()


def _is_permission_or_registration_case(text: str) -> bool:
    """Identifica casos que precisam de ajuste pela equipe, não de testes locais."""
    normalized = _normalize_message(text)
    signals = (
        "permiss",
        "cadastro",
        "conta bloqueada",
        "conta esta bloqueada",
        "usuario bloqueado",
        "usuario novo",
        "novo usuario",
        "sem acesso",
        "nao tenho acesso",
        "nao consigo entrar",
        "nao consigo visualizar",
        "nao enxergo",
        "liberar acesso",
        "acesso ao time",
        "incluir no time",
        "adicionar ao time",
        "perfil de acesso",
    )
    return any(signal in normalized for signal in signals)


def _permission_urgency_label(text: str) -> str:
    """Traduz a urgência informada de modo tolerante a respostas simples."""
    normalized = _normalize_message(text)
    if any(term in normalized for term in ("alto", "alta", "urgente", "essencial", "impede")):
        return "Alta"
    if any(term in normalized for term in ("medio", "media", "dificulta")):
        return "Média"
    return "Baixa"


def _permission_access_question(thread_name: str) -> str:
    parts = [part.strip() for part in str(thread_name or "").split(" - ")]
    system_name = parts[1] if len(parts) >= 2 and parts[0] == "1" else "sistema"
    return (
        f"Para eu chamar o TI sobre o acesso ao **{system_name}**, o que você precisa "
        "conseguir fazer? Por exemplo: entrar no sistema, ver uma fila ou acessar uma tarefa."
    )


async def _latest_bot_reply_text(thread: discord.Thread) -> str:
    """Obtém a última fala visível do bot antes da mensagem atual do usuário."""
    async for message in thread.history(limit=12):
        if not message.author.bot:
            continue
        parts = [message.content.strip()] if message.content.strip() else []
        for embed in message.embeds[:2]:
            if embed.description:
                parts.append(embed.description.strip())
        visible_text = "\n".join(part for part in parts if part).strip()
        if visible_text:
            return visible_text
    return ""


async def _send_conversation_reply(
    thread: discord.Thread,
    text: str,
    *,
    first_message: bool = False,
    urgency_label: str | None = None,
) -> None:
    chunks = split_discord_text(text, limit=1900)
    if not chunks:
        raise AIServiceError("A IA não retornou conteúdo para exibir.")

    if first_message:
        embed = discord.Embed(
            title="🤖 Atendimento inicial com IA",
            description=chunks[0],
            color=discord.Color.blurple(),
        )
        if urgency_label:
            embed.add_field(
                name="📊 Nível de urgência",
                value=urgency_label,
                inline=False,
            )
        embed.set_footer(
            text=(
                "Não envie CPF, senha ou código de acesso. "
                "Use !encerrar_ia para finalizar."
            )
        )
        await thread.send(
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        chunks = chunks[1:]

    for chunk in chunks:
        await thread.send(
            chunk,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def _send_summary(
    thread: discord.Thread,
    *,
    outcome: str,
) -> None:
    context = await collect_sanitized_context(
        thread,
        message_limit=60,
        character_limit=14000,
    )
    context = _context_with_session_details(context, _SESSIONS.get(thread.id))
    summary = await generate_case_summary(
        context,
        safe_thread_label(thread.name),
        outcome=outcome,
    )
    chunks = split_discord_text(summary)
    if not chunks:
        raise AIServiceError("A IA não retornou um resumo para exibir.")

    embed = discord.Embed(
        title="📋 Resumo e diagnóstico da IA",
        description=chunks[0],
        color=discord.Color.purple(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    embed.set_footer(text="Resumo sugerido por IA — valide antes de tomar decisões.")
    await thread.send(
        embed=embed,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    for chunk in chunks[1:]:
        await thread.send(
            chunk,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def _notify_human_support(
    thread: discord.Thread,
    *,
    reason: str = "o solicitante pediu atendimento humano",
) -> None:
    """Menciona imediatamente o cargo responsável antes de gerar o resumo."""
    session = _SESSIONS.get(thread.id) or {}
    configured_role_id = session.get("handoff_role_id")
    role_id = (
        int(configured_role_id)
        if configured_role_id
        else _human_support_role_id(thread.guild.id, thread.name)
    )
    if role_id:
        content = (
            f"👤 <@&{role_id}> {reason}.\n"
            "Estou preparando abaixo o resumo do problema, das tentativas e dos "
            "próximos passos recomendados."
        )
        allowed_mentions = discord.AllowedMentions(
            roles=True,
            users=False,
            everyone=False,
        )
    else:
        content = (
            f"👤 {reason.capitalize()}. Estou preparando abaixo "
            "o resumo para a equipe responsável."
        )
        allowed_mentions = discord.AllowedMentions.none()

    await thread.send(content, allowed_mentions=allowed_mentions)


async def _finish_session(
    thread: discord.Thread,
    *,
    outcome: str,
) -> None:
    session = _SESSIONS.get(thread.id)
    if session is not None:
        session["active"] = False
        session["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session["outcome"] = outcome
        diagnostic = session.setdefault("diagnostic", {})
        diagnostic["situacao"] = outcome
        _save_sessions()

    await _send_summary(thread, outcome=outcome)


async def start_ai_conversation(
    thread: discord.Thread,
    user: discord.Member | discord.User,
    *,
    urgency_label: str | None = None,
    force_permission_flow: bool = False,
    initial_context: str | None = None,
    handoff_role_id: int | None = None,
) -> None:
    """Inicia uma sessão conversacional e envia a primeira resposta no tópico."""
    if not config.GROQ_API_KEY:
        raise AIServiceError("A IA não está configurada neste bot.")
    if not _is_supported_thread(thread):
        raise AIServiceError("Este tipo de chamado não aceita atendimento com IA.")

    existing = _SESSIONS.get(thread.id)
    if existing and existing.get("active"):
        raise AIServiceError("A conversa com a IA já está ativa neste tópico.")
    if thread.id in _BUSY_THREADS:
        raise AIServiceError("A IA já está processando este tópico.")

    enriched_context = "\n".join(
        part for part in (
            sanitize_text(initial_context or "")[:1200],
            build_conversation_guide(initial_context or ""),
        ) if part
    )[:2400]
    _SESSIONS[thread.id] = {
        "active": True,
        "user_id": user.id,
        "turns": 0,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "initial_context": enriched_context,
        "diagnostic": initial_diagnostic_state(initial_context or ""),
        "handoff_role_id": int(handoff_role_id) if handoff_role_id else None,
    }
    _save_sessions()
    _BUSY_THREADS.add(thread.id)

    try:
        async with thread.typing():
            context = await collect_sanitized_context(thread)
            context = _context_with_session_details(
                context,
                _SESSIONS.get(thread.id),
            )
            permission_flow = (
                thread.name.startswith("1 -")
                and force_permission_flow
            )
            if permission_flow:
                reply = _permission_access_question(thread.name)
                _SESSIONS[thread.id]["permission_flow"] = True
                _SESSIONS[thread.id]["permission_stage"] = "awaiting_access"
            else:
                reply = await generate_conversation_reply(
                    context,
                    safe_thread_label(thread.name),
                    turn_number=1,
                )
        await _send_conversation_reply(
            thread,
            reply,
            first_message=True,
            urgency_label=(
                urgency_label or _urgency_label_from_thread_name(thread.name)
            ),
        )
        _SESSIONS[thread.id]["turns"] = 1
        _SESSIONS[thread.id]["awaiting_human_confirmation"] = (
            _offers_human_handoff(reply)
        )
        _save_sessions()
    except Exception:
        _SESSIONS.pop(thread.id, None)
        _save_sessions()
        raise
    finally:
        _BUSY_THREADS.discard(thread.id)


def setup(bot: commands.Bot) -> None:
    @bot.command(name="ajuda", aliases=["ajuda_ia"])
    async def ajuda_cmd(ctx: commands.Context) -> None:
        guild = ctx.guild
        thread = ctx.channel

        if not guild or not isinstance(thread, discord.Thread):
            await ctx.reply(
                "`!ajuda` só pode ser usado dentro de um tópico de atendimento.",
                mention_author=False,
            )
            return
        if thread.name.startswith("3 -"):
            await ctx.reply(
                "🔒 A IA é bloqueada em chamados de Recuperar Contato.",
                mention_author=False,
            )
            return
        if not _is_supported_thread(thread):
            await ctx.reply(
                "`!ajuda` só funciona em chamados de Sistemas ou Equipamentos.",
                mention_author=False,
            )
            return
        if not config.GROQ_API_KEY:
            await ctx.reply(
                "A IA não está configurada neste bot.",
                mention_author=False,
            )
            return

        existing = _SESSIONS.get(thread.id)
        if existing and existing.get("active"):
            if int(existing.get("user_id", 0)) == ctx.author.id:
                await ctx.reply(
                    "A conversa com a IA já está ativa. Pode responder normalmente neste tópico.",
                    mention_author=False,
                )
            else:
                await ctx.reply(
                    "Já existe um atendimento com IA ativo para outro participante.",
                    mention_author=False,
                )
            return
        if thread.id in _BUSY_THREADS:
            await ctx.reply(
                "A IA já está processando uma mensagem neste tópico.",
                mention_author=False,
            )
            return

        try:
            await start_ai_conversation(thread, ctx.author)
        except AIServiceError as exc:
            await ctx.reply(
                f"⚠️ {exc}",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(f"[IA] Erro ao iniciar conversa no tópico {thread.id}: {exc}")
            await ctx.reply(
                "⚠️ Não foi possível iniciar a conversa com IA agora.",
                mention_author=False,
            )

    @bot.command(name="resumo", aliases=["resumo_ia"])
    async def resumo_cmd(ctx: commands.Context) -> None:
        guild = ctx.guild
        thread = ctx.channel
        member = ctx.author if isinstance(ctx.author, discord.Member) else None

        if not guild or not _is_supported_thread(thread):
            await ctx.reply(
                "`!resumo` só funciona em chamados de Sistemas ou Equipamentos.",
                mention_author=False,
            )
            return
        if member is None or not _is_authorized(member, guild.id):
            await ctx.reply(
                "Apenas atendentes autorizados podem gerar o resumo.",
                mention_author=False,
            )
            return
        if thread.id in _BUSY_THREADS:
            await ctx.reply(
                "A IA já está processando este tópico.",
                mention_author=False,
            )
            return

        _BUSY_THREADS.add(thread.id)
        try:
            async with ctx.typing():
                await _finish_session(
                    thread,
                    outcome=f"Resumo solicitado por um atendente após {len(_SESSIONS.get(thread.id, {})) and _SESSIONS.get(thread.id, {}).get('turns', 0)} resposta(s) da IA.",
                )
            await ctx.reply(
                "✅ Resumo gerado. A conversa automática foi encerrada.",
                mention_author=False,
            )
        except AIServiceError as exc:
            await ctx.reply(f"⚠️ {exc}", mention_author=False)
        except Exception as exc:
            print(f"[IA] Erro ao resumir tópico {thread.id}: {exc}")
            await ctx.reply(
                "⚠️ Não foi possível gerar o resumo agora.",
                mention_author=False,
            )
        finally:
            _BUSY_THREADS.discard(thread.id)

    @bot.command(name="encerrar_ia", aliases=["parar_ia"])
    async def encerrar_ia_cmd(ctx: commands.Context) -> None:
        guild = ctx.guild
        thread = ctx.channel

        if not guild or not _is_supported_thread(thread):
            await ctx.reply(
                "`!encerrar_ia` só funciona em chamados de Sistemas ou Equipamentos.",
                mention_author=False,
            )
            return

        session = _SESSIONS.get(thread.id)
        member = ctx.author if isinstance(ctx.author, discord.Member) else None
        is_owner = bool(session and int(session.get("user_id", 0)) == ctx.author.id)
        is_staff = bool(member and _is_authorized(member, guild.id))
        if not is_owner and not is_staff:
            await ctx.reply(
                "Somente quem iniciou a conversa ou um atendente pode encerrá-la.",
                mention_author=False,
            )
            return
        if thread.id in _BUSY_THREADS:
            await ctx.reply(
                "A IA já está processando este tópico.",
                mention_author=False,
            )
            return

        _BUSY_THREADS.add(thread.id)
        try:
            async with ctx.typing():
                await _finish_session(
                    thread,
                    outcome="Conversa encerrada manualmente.",
                )
            await ctx.reply(
                "✅ Atendimento com IA encerrado e resumo gerado.",
                mention_author=False,
            )
        except AIServiceError as exc:
            await ctx.reply(f"⚠️ {exc}", mention_author=False)
        except Exception as exc:
            print(f"[IA] Erro ao encerrar sessão {thread.id}: {exc}")
            await ctx.reply(
                "⚠️ A conversa foi encerrada, mas não foi possível gerar o resumo.",
                mention_author=False,
            )
        finally:
            _BUSY_THREADS.discard(thread.id)

    @bot.command(name="ia")
    async def ia_cmd(ctx: commands.Context) -> None:
        guild = ctx.guild
        thread = ctx.channel
        member = ctx.author if isinstance(ctx.author, discord.Member) else None

        if not guild or not isinstance(thread, discord.Thread):
            await ctx.reply(
                "`!ia` só pode ser usado dentro de um tópico de atendimento.",
                mention_author=False,
            )
            return
        if thread.name.startswith("3 -"):
            await ctx.reply(
                "🔒 A IA é bloqueada em chamados de Recuperar Contato.",
                mention_author=False,
            )
            return
        if not _is_supported_thread(thread):
            await ctx.reply(
                "`!ia` só funciona em chamados de Sistemas ou Equipamentos.",
                mention_author=False,
            )
            return
        if member is None or not _is_authorized(member, guild.id):
            await ctx.reply(
                "Apenas atendentes autorizados podem usar `!ia`.",
                mention_author=False,
            )
            return
        if not config.GROQ_API_KEY:
            await ctx.reply(
                "A chave `GROQ_API_KEY` não está configurada no `.env`.",
                mention_author=False,
            )
            return
        if thread.id in _BUSY_THREADS:
            await ctx.reply(
                "A IA já está processando este tópico.",
                mention_author=False,
            )
            return

        _BUSY_THREADS.add(thread.id)
        try:
            async with ctx.typing():
                context = await collect_sanitized_context(thread)
                suggestion = await generate_support_suggestion(
                    context,
                    safe_thread_label(thread.name),
                )

            chunks = split_discord_text(suggestion)
            if not chunks:
                raise AIServiceError("A IA não retornou conteúdo para exibir.")

            embed = discord.Embed(
                title="🤖 Sugestão de diagnóstico",
                description=chunks[0],
                color=discord.Color.purple(),
            )
            embed.set_footer(
                text="Sugestão gerada por IA — o atendente deve validar antes de aplicar."
            )
            await ctx.reply(
                embed=embed,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            for chunk in chunks[1:]:
                await thread.send(
                    chunk,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except AIServiceError as exc:
            await ctx.reply(f"⚠️ {exc}", mention_author=False)
        except Exception as exc:
            print(f"[IA] Erro inesperado no tópico {thread.id}: {exc}")
            await ctx.reply(
                "⚠️ Não foi possível gerar a sugestão agora.",
                mention_author=False,
            )
        finally:
            _BUSY_THREADS.discard(thread.id)

    @bot.listen("on_message")
    async def ai_conversation_listener(message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if not isinstance(message.channel, discord.Thread):
            return
        if message.content.startswith("!"):
            return

        thread = message.channel
        session = _SESSIONS.get(thread.id)
        if not session or not session.get("active"):
            return
        if int(session.get("user_id", 0)) != message.author.id:
            return
        if thread.id in _BUSY_THREADS:
            return

        _BUSY_THREADS.add(thread.id)
        try:
            session["diagnostic"] = update_diagnostic_state(
                session.get("diagnostic") or {},
                message.content,
                attachment_count=len(message.attachments),
                previous_question=await _latest_bot_reply_text(thread),
            )
            _save_sessions()
            awaiting_human = bool(
                session.get("awaiting_human_confirmation")
            )
            if _requester_confirmed_human_handoff(
                message.content,
                awaiting_confirmation=awaiting_human,
            ):
                await thread.send(
                    "Entendido. Vou chamar uma pessoa da equipe agora.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                await _notify_human_support(thread)
                async with thread.typing():
                    await _finish_session(
                        thread,
                        outcome="Usuário solicitou atendimento humano.",
                    )
                return

            if awaiting_human and not _is_negative_reply(message.content):
                await thread.send(
                    "Só para confirmar: você quer que uma pessoa da equipe continue "
                    "o atendimento? Responda **sim** ou **não**.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return

            if awaiting_human and _is_negative_reply(message.content):
                if (
                    session.get("permission_flow")
                    and session.get("permission_stage")
                    == "awaiting_human_confirmation"
                ):
                    session["awaiting_human_confirmation"] = False
                    session["human_handoff_declined"] = True
                    session["permission_handoff_declined"] = True
                    _save_sessions()
                    await thread.send(
                        "Tudo bem. Como esse acesso depende de um ajuste do TI, não "
                        "há outro teste seguro para eu orientar agora. Quando quiser, "
                        "diga **“quero falar com um atendente”**.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    return

            if awaiting_human:
                session["awaiting_human_confirmation"] = False
                session["human_handoff_declined"] = True
                _save_sessions()

            if session.get("permission_flow"):
                stage = session.get("permission_stage")
                if stage == "awaiting_access":
                    session["permission_access_requested"] = message.content[:500]
                    session["permission_stage"] = "awaiting_urgency"
                    session["turns"] = int(session.get("turns", 0)) + 1
                    session["last_interaction_at"] = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    _save_sessions()
                    await thread.send(
                        "Isso impede alguma atividade essencial agora? Responda **alto**, "
                        "**médio** ou **baixo**.",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    return

                if stage == "awaiting_urgency":
                    urgency = _permission_urgency_label(message.content)
                    session["permission_urgency"] = urgency
                    session["permission_stage"] = "awaiting_human_confirmation"
                    session["awaiting_human_confirmation"] = True
                    session["last_interaction_at"] = datetime.datetime.now(
                        datetime.timezone.utc
                    ).isoformat()
                    _save_sessions()
                    await thread.send(
                        "Esse ajuste precisa ser feito pelo TI e não consigo concluí-lo "
                        "automaticamente.\n\n**Quer que eu chame uma pessoa da equipe? "
                        "Responda sim ou não.**",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    return

            if _is_resolution_message(message.content):
                await thread.send(
                    "Que bom que funcionou! Vou registrar o que foi feito e gerar o resumo do atendimento.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                async with thread.typing():
                    await _finish_session(
                        thread,
                        outcome="Usuário informou que o problema foi resolvido.",
                    )
                return

            next_turn = int(session.get("turns", 0)) + 1
            async with thread.typing():
                context = await collect_sanitized_context(thread)
                context = _context_with_session_details(context, session)
                previous_reply = await _latest_bot_reply_text(thread)
                reply = await generate_conversation_reply(
                    context,
                    safe_thread_label(thread.name),
                    turn_number=next_turn,
                    allow_human_handoff=not bool(
                        session.get("human_handoff_declined")
                    ),
                )
                if _responses_are_similar(previous_reply, reply):
                    print(
                        f"[IA] Repetição detectada no tópico {thread.id}; "
                        "gerando uma resposta reformulada."
                    )
                    reply = await generate_conversation_reply(
                        context,
                        safe_thread_label(thread.name),
                        turn_number=next_turn,
                        avoid_reply=previous_reply,
                        allow_human_handoff=not bool(
                            session.get("human_handoff_declined")
                        ),
                    )
                    if _responses_are_similar(previous_reply, reply):
                        reply = (
                            "Entendi sua resposta, mas ainda faltou uma informação para "
                            "continuarmos. Se você não souber, pode responder **“não sei”**. "
                            "Conte o que consegue observar e quais testes já tentou; se "
                            "preferir atendimento da equipe, diga **“quero falar com um "
                            "atendente”**."
                        )
            await _send_conversation_reply(thread, reply)
            session["turns"] = next_turn
            session["awaiting_human_confirmation"] = _offers_human_handoff(reply)
            session["last_interaction_at"] = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            _save_sessions()

            if next_turn >= _MAX_CONVERSATION_TURNS:
                if session.get("awaiting_human_confirmation"):
                    return
                await thread.send(
                    "Chegamos ao limite do diagnóstico automático e o caso precisa de "
                    "uma análise mais cuidadosa.\n\n**Quer que eu chame uma pessoa da "
                    "equipe? Responda sim ou não.**",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                session["awaiting_human_confirmation"] = True
                session["last_interaction_at"] = datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat()
                _save_sessions()
        except AIServiceError as exc:
            await thread.send(
                f"⚠️ {exc} A conversa continua ativa; tente responder novamente mais tarde.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception as exc:
            print(f"[IA] Erro na conversa do tópico {thread.id}: {exc}")
            await thread.send(
                "⚠️ Não consegui responder agora. A equipe pode continuar o atendimento normalmente.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            _BUSY_THREADS.discard(thread.id)
