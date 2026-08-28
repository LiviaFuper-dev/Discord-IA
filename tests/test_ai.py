import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import config
from modules.ia import (
    _context_with_session_details,
    _human_support_role_id,
    _is_affirmative_reply,
    _is_negative_reply,
    _is_permission_or_registration_case,
    _is_resolution_message,
    _offers_human_handoff,
    _permission_access_question,
    _permission_urgency_label,
    _requester_confirmed_human_handoff,
    _responses_are_similar,
    _urgency_label_from_thread_name,
    _wants_human_support,
)
from modules.sistemas._engine import _problem_type_context, _start_ai_support
from utils.error_search import extract_error_code, search_unknown_error_code
from utils.historical_knowledge import build_solution_patterns, retrieve_historical_solution_context
from utils.ai import (
    _complex_case_handoff_message,
    _extract_completion_text,
    safe_thread_label,
    sanitize_text,
    split_discord_text,
)
from utils.knowledge import (
    build_knowledge_context,
    has_local_error_guidance,
    load_institutional_knowledge,
    retrieve_relevant_pops,
)


class SanitizeTextTests(unittest.TestCase):
    def test_remove_sensitive_data_and_keep_error_code(self):
        raw = (
            "Erro 131049. CPF 123.456.789-00, email aluno@example.com, "
            "telefone (11) 99999-8888, <@123456789012345678>, "
            "https://example.com/segredo e gsk_abcdefghijklmnopqrstuvwxyz123456."
        )

        clean = sanitize_text(raw)

        self.assertIn("131049", clean)
        self.assertIn("[CPF REMOVIDO]", clean)
        self.assertIn("[E-MAIL REMOVIDO]", clean)
        self.assertIn("[TELEFONE REMOVIDO]", clean)
        self.assertIn("[MENÇÃO REMOVIDA]", clean)
        self.assertIn("[LINK REMOVIDO]", clean)
        self.assertIn("[CHAVE REMOVIDA]", clean)
        self.assertNotIn("123.456.789-00", clean)


class SplitDiscordTextTests(unittest.TestCase):
    def test_chunks_respect_limit_and_preserve_content(self):
        text = "linha curta\n" * 100
        chunks = split_discord_text(text, limit=120)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 120 for chunk in chunks))
        self.assertEqual("".join(chunks).replace("\n", ""), text.strip().replace("\n", ""))


class SafeThreadLabelTests(unittest.TestCase):
    def test_remove_requester_name_from_system_thread(self):
        self.assertEqual(
            safe_thread_label("1 - ChatGuru - Maria da Silva"),
            "Sistemas - ChatGuru",
        )

    def test_remove_requester_name_from_equipment_thread(self):
        self.assertEqual(
            safe_thread_label("2 - Alto - João"),
            "Equipamentos - urgência Alto",
        )


class CompletionTextTests(unittest.TestCase):
    def test_extract_string_content(self):
        data = {"choices": [{"message": {"content": "  Olá!  "}}]}
        self.assertEqual(_extract_completion_text(data), "Olá!")

    def test_empty_or_null_content_stays_empty(self):
        empty = {"choices": [{"message": {"content": ""}}]}
        null = {"choices": [{"message": {"content": None}}]}
        self.assertEqual(_extract_completion_text(empty), "")
        self.assertEqual(_extract_completion_text(null), "")


class ErrorCodeLookupTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_error_code_without_a_fixed_catalog(self):
        self.assertEqual(extract_error_code("ChatGuru: erro 131049"), "131049")
        self.assertEqual(extract_error_code("código 987654"), "987654")
        self.assertIsNone(extract_error_code("a tela não abre"))

    def test_knows_when_local_pop_contains_the_exact_code(self):
        self.assertTrue(has_local_error_guidance("Erro 131049 no ChatGuru"))
        self.assertFalse(has_local_error_guidance("Erro 987654 no ChatGuru"))

    async def test_does_not_search_web_when_feature_is_disabled(self):
        with patch("utils.error_search.config.ERROR_WEB_SEARCH_ENABLED", False):
            result = await search_unknown_error_code(
                "Erro 987654 no ChatGuru",
                "Sistemas - ChatGuru",
                has_local_guidance=False,
            )

        self.assertEqual(result, "")


class HistoricalKnowledgeTests(unittest.TestCase):
    def test_aggregates_only_classification_and_solution_fields(self):
        tasks = [
            {
                "name": "Cliente 123.456.789-00",
                "description": "Não deve entrar no aprendizado.",
                "custom_fields": [
                    {"name": "Sistema", "value": "ChatGuru"},
                    {"name": "Tipo de problema", "value": "Erro 131049"},
                    {"name": "Solução aplicada", "value": "Usar template aprovado"},
                    {"name": "Resultado final", "value": "Resolvido"},
                ],
            }
        ]

        patterns = build_solution_patterns(tasks)

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["sistema"], "ChatGuru")
        self.assertEqual(patterns[0]["ocorrencias"], 1)
        self.assertNotIn("123.456", str(patterns))
        self.assertNotIn("aprendizado", str(patterns))

    def test_retrieves_only_relevant_historical_pattern(self):
        fixture = Path(__file__).parent / "fixtures" / "clickup_solution_patterns.json"
        with patch("utils.historical_knowledge._PATTERNS_FILE", fixture):
            result = retrieve_historical_solution_context(
                "ChatGuru erro 131049 ao enviar mensagem"
            )

        self.assertIn("PADRÕES HISTÓRICOS DO CLICKUP", result)
        self.assertIn("template aprovado", result)

    def test_reads_only_labeled_resolution_lines_from_description(self):
        tasks = [
            {
                "description": (
                    "Cliente: pessoa@example.com\n"
                    "Sistema: ChatGuru\n"
                    "Problema: Erro 130429\n"
                    "Solução aplicada: Aguardar limite de envio.\n"
                    "Resultado final: Resolvido"
                ),
                "custom_fields": [],
            }
        ]

        patterns = build_solution_patterns(tasks)

        self.assertEqual(patterns[0]["sistema"], "ChatGuru")
        self.assertEqual(patterns[0]["problema"], "Erro 130429")
        self.assertNotIn("pessoa@example.com", str(patterns))

    def test_uses_resolved_checklist_action_when_no_solution_field_exists(self):
        tasks = [
            {
                "custom_fields": [
                    {"name": "Sistema", "value": 0, "type_config": {"options": [{"orderindex": 0, "name": "ChatGuru"}]}},
                    {"name": "Tipo de bug", "value": 0, "type_config": {"options": [{"orderindex": 0, "name": "Lentidão/travamento"}]}},
                    {"name": "Cache limpo", "value": 1, "type_config": {"options": [{"orderindex": 0, "name": "Não resolveu"}, {"orderindex": 1, "name": "Resolveu"}]}},
                ]
            }
        ]

        patterns = build_solution_patterns(tasks)

        self.assertEqual(patterns[0]["sistema"], "ChatGuru")
        self.assertEqual(patterns[0]["problema"], "Lentidão/travamento")
        self.assertEqual(patterns[0]["solucao"], "Cache limpo")


class ConversationIntentTests(unittest.TestCase):
    def test_detect_resolution_without_false_positive(self):
        self.assertTrue(_is_resolution_message("Agora funcionou, obrigado!"))
        self.assertTrue(_is_resolution_message("Deu certo aqui."))
        self.assertFalse(_is_resolution_message("Ainda não resolveu."))
        self.assertFalse(_is_resolution_message("Não funcionou."))

    def test_detect_human_handoff(self):
        self.assertTrue(_wants_human_support("Quero falar com um atendente."))
        self.assertTrue(_wants_human_support("Pode chamar o suporte?"))
        self.assertTrue(_wants_human_support("Gostaria de alguém humano."))
        self.assertTrue(_wants_human_support("Quero falar com um ser humano."))
        self.assertTrue(_wants_human_support("Precisa chamar uma pessoa."))
        self.assertFalse(_wants_human_support("Pode continuar me ajudando."))
        self.assertFalse(_wants_human_support("Não quero um atendente."))


class PermissionFlowTests(unittest.TestCase):
    def test_identifies_permission_and_registration_cases(self):
        self.assertTrue(
            _is_permission_or_registration_case(
                "Não consigo acessar a fila e preciso de permissão."
            )
        )
        self.assertTrue(
            _is_permission_or_registration_case("Minha conta está bloqueada."))
        self.assertFalse(
            _is_permission_or_registration_case("O sistema está lento desde cedo.")
        )

    def test_asks_for_required_access_and_urgency(self):
        question = _permission_access_question("1 - ClickUp - Maria")
        self.assertIn("ClickUp", question)
        self.assertEqual(
            _permission_urgency_label("Está impedindo um processo essencial"),
            "Alta",
        )
        self.assertEqual(
            _permission_urgency_label("Dificulta, mas consigo trabalhar"),
            "Média",
        )
        self.assertEqual(_permission_urgency_label("É só uma dúvida"), "Baixa")


class UrgencyLabelTests(unittest.TestCase):
    def test_extract_equipment_urgency(self):
        self.assertEqual(
            _urgency_label_from_thread_name("2 - Médio - Maria"),
            "Médio",
        )

    def test_ignore_non_equipment_thread(self):
        self.assertIsNone(
            _urgency_label_from_thread_name("1 - ChatGuru - Maria")
        )


class RepeatedResponseTests(unittest.TestCase):
    def test_detect_nearly_identical_questions(self):
        first = (
            "Qual a resolução atual? Você já tentou trocar o cabo "
            "ou usar outra porta?"
        )
        second = (
            "Qual a resolução atual? Você já tentou trocar o cabo "
            "ou usar outro porta?"
        )
        self.assertTrue(_responses_are_similar(first, second))

    def test_allow_a_genuinely_different_reply(self):
        self.assertFalse(
            _responses_are_similar(
                "Qual a resolução atual do monitor?",
                "Entendi. Se você não souber, abra Configurações de exibição.",
            )
        )


class SessionContextTests(unittest.TestCase):
    def test_adds_sanitized_opening_details(self):
        context = _context_with_session_details(
            "Participante: A página não abre.",
            {"initial_context": "Sistema: E-mail. Conta: usuario@example.com"},
        )

        self.assertIn("Dados informados na abertura", context)
        self.assertIn("Sistema: E-mail", context)
        self.assertIn("[E-MAIL REMOVIDO]", context)
        self.assertNotIn("usuario@example.com", context)

    def test_system_problem_type_is_passed_to_ai(self):
        context = _problem_type_context("Clickup", "mensagem_de_erro")

        self.assertEqual(
            context,
            "Sistema: Clickup. Tipo de problema selecionado: Mensagem de erro.",
        )


class SystemAiRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_starts_ai_with_system_role_and_without_pinging(self):
        thread = SimpleNamespace(send=AsyncMock())
        user = SimpleNamespace(id=123)

        with patch(
            "modules.ia.start_ai_conversation",
            new_callable=AsyncMock,
        ) as start:
            started = await _start_ai_support(
                thread,
                user,
                initial_context="Sistema: Clickup.",
                handoff_role_id=456,
            )

        self.assertTrue(started)
        start.assert_awaited_once_with(
            thread,
            user,
            force_permission_flow=False,
            initial_context="Sistema: Clickup.",
            handoff_role_id=456,
        )
        thread.send.assert_not_awaited()


class HumanHandoffTests(unittest.TestCase):
    def test_detect_handoff_offer(self):
        self.assertTrue(
            _offers_human_handoff(
                "O caso precisa de acesso administrativo.\n"
                "Quer que eu chame uma pessoa da equipe? Responda sim ou não."
            )
        )

    def test_understand_short_confirmation_only_in_confirmation_flow(self):
        self.assertTrue(_is_affirmative_reply("Sim, por favor!"))
        self.assertTrue(_is_affirmative_reply("Pode chamar"))
        self.assertTrue(_is_negative_reply("Não precisa."))
        self.assertFalse(_is_affirmative_reply("Sim, o monitor está ligado"))

    def test_only_requester_confirmation_authorizes_handoff(self):
        self.assertTrue(
            _requester_confirmed_human_handoff(
                "Quero falar com um atendente.",
                awaiting_confirmation=False,
            )
        )
        self.assertTrue(
            _requester_confirmed_human_handoff(
                "Sim, por favor!",
                awaiting_confirmation=True,
            )
        )
        self.assertFalse(
            _requester_confirmed_human_handoff(
                "Sim, o monitor está ligado.",
                awaiting_confirmation=False,
            )
        )
        self.assertFalse(
            _requester_confirmed_human_handoff(
                "O caso parece muito complexo.",
                awaiting_confirmation=False,
            )
        )

    def test_block_physical_risk_before_model_generation(self):
        reply = _complex_case_handoff_message(
            "O notebook está com cheiro de queimado.",
            turn_number=1,
        )
        self.assertIn("risco físico", reply)
        self.assertIn("Responda sim ou não", reply)

    def test_do_not_offer_human_again_after_decline(self):
        reply = _complex_case_handoff_message(
            "O notebook está com cheiro de queimado.",
            turn_number=2,
            allow_human_handoff=False,
        )
        self.assertIn("não vou orientar outros testes", reply)
        self.assertNotIn("Responda sim ou não", reply)

    def test_simple_case_continues_with_ai(self):
        self.assertIsNone(
            _complex_case_handoff_message(
                "Meu mouse parou de funcionar.",
                turn_number=1,
            )
        )

    def test_select_equipment_role_for_handoff(self):
        guild_id = 1516880237743439913
        expected = config.SERVIDORES[guild_id]["ti"]["cargo_equipamentos"]
        self.assertEqual(
            _human_support_role_id(guild_id, "2 - Alto - Maria"),
            expected,
        )

    def test_select_systems_ti_role_for_permission_handoff(self):
        guild_id = 1516880237743439913
        expected = config.SERVIDORES[guild_id]["sistemas"]["cargo_ti"]
        self.assertEqual(
            _human_support_role_id(guild_id, "1 - ClickUp - Maria"),
            expected,
        )


class KnowledgeBaseTests(unittest.TestCase):
    def test_load_institutional_roles_and_limits(self):
        knowledge = load_institutional_knowledge()

        self.assertIn("Fuper", knowledge)
        self.assertIn("MLR Advogados", knowledge)
        self.assertIn("escritório de advocacia", knowledge)
        self.assertIn("Não prometer", knowledge)

    def test_build_context_includes_institutional_reference(self):
        context = build_knowledge_context(
            "A Fuper vai cuidar do meu processo?",
            "Chamado de suporte",
        )

        self.assertIn("REFERÊNCIA INSTITUCIONAL", context)
        self.assertIn("representação jurídica", context)
        self.assertLessEqual(len(context), 12000)

    def test_retrieve_only_relevant_pop(self):
        pops_dir = Path(__file__).parent / "fixtures" / "pops"
        with patch("utils.knowledge._POPS_DIR", pops_dir):
            result = retrieve_relevant_pops(
                "O monitor está sem imagem no cabo HDMI"
            )

        self.assertIn("monitor.md", result)
        self.assertIn("Confira o cabo HDMI", result)
        self.assertNotIn("impressora.md", result)

    def test_retrieve_auxilio_acidente_pop_for_relevant_question(self):
        result = retrieve_relevant_pops(
            "Tive um acidente, fiquei com sequela e não consigo mais exercer minha função. "
            "Posso ter auxílio-acidente?"
        )

        self.assertIn("auxilio-acidente-qualificacao.md", result)
        self.assertIn("Não é parecer jurídico", result)

    def test_retrieve_chatguru_error_pop_by_error_code(self):
        result = retrieve_relevant_pops(
            "No ChatGuru apareceu erro 131049 quando tentei enviar a mensagem."
        )

        self.assertIn("chatguru-erros.md", result)
        self.assertIn("spam/engajamento", result)

    def test_new_documentation_pops_do_not_store_access_secrets(self):
        pops_dir = Path("knowledge_base/pops/documentacao")
        text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in pops_dir.glob("*.md")
        ).lower()

        self.assertNotIn("395.228", text)
        self.assertNotIn("senha do gov.br é", text)


if __name__ == "__main__":
    unittest.main()
