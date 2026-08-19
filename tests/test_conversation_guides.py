import unittest

from utils.conversation_guides import build_conversation_guide


class ConversationGuideTests(unittest.TestCase):
    def test_chatguru_keeps_legacy_diagnostic_goals(self):
        guide = build_conversation_guide(
            "Sistema: ChatGuru. Tipo de problema selecionado: Mensagem de erro."
        )
        self.assertIn("código", guide)
        self.assertIn("Ctrl+F5", guide)
        self.assertIn("ROTEIRO INTERNO", guide)

    def test_inss_robot_keeps_three_old_questions(self):
        guide = build_conversation_guide(
            "Área: Robôs/Automações. Subsistema: INSS."
        )
        self.assertIn("documentos no download", guide)
        self.assertIn("um cliente, vários ou todos", guide)
        self.assertIn("mesmo documento", guide)

    def test_permission_flow_avoids_generic_cache_steps(self):
        guide = build_conversation_guide(
            "Sistema: Whom. Tipo de problema selecionado: Permissão ou cadastro."
        )
        self.assertIn("qual acesso ou cadastro", guide)
        self.assertNotIn("limpar cache", guide)


if __name__ == "__main__":
    unittest.main()
