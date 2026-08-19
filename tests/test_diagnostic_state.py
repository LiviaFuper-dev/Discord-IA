import unittest

from utils.diagnostic_state import (
    format_diagnostic_state,
    initial_diagnostic_state,
    update_diagnostic_state,
)


class DiagnosticStateTests(unittest.TestCase):
    def test_collects_code_scope_test_and_evidence_without_raw_text(self):
        state = initial_diagnostic_state(
            "Sistema: ChatGuru. Tipo de problema selecionado: Mensagem de erro."
        )
        state = update_diagnostic_state(
            state,
            "O erro é 131049 e acontece com vários contatos.",
            previous_question="Qual é o código do erro?",
        )
        state = update_diagnostic_state(
            state,
            "Já tentei e não resolveu.",
            previous_question="Você já tentou limpar o cache?",
        )
        state = update_diagnostic_state(state, "", attachment_count=1)

        self.assertEqual(state["codigo_erro"], "131049")
        self.assertEqual(state["abrangencia"], "vários")
        self.assertEqual(state["tentativas"]["cache"], "tentado_sem_resolver")
        self.assertEqual(state["evidencia"], "anexo ou print enviado")
        self.assertNotIn("vários contatos", format_diagnostic_state(state))

    def test_does_not_treat_unrelated_number_as_error_code(self):
        state = initial_diagnostic_state("Sistema: Clickup.")
        state = update_diagnostic_state(state, "Meu ramal é 123456")

        self.assertEqual(state["codigo_erro"], "")

    def test_automation_area_is_registered_as_system(self):
        state = initial_diagnostic_state("Área: Robôs/Automações. Subsistema: INSS.")

        self.assertEqual(state["sistema"], "Robôs/Automações")
        self.assertEqual(state["subsistema"], "INSS")


if __name__ == "__main__":
    unittest.main()
