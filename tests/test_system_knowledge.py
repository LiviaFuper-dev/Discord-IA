import unittest

from utils.system_knowledge import retrieve_structured_system_knowledge


class SystemKnowledgeTests(unittest.TestCase):
    def test_error_code_uses_specific_chatguru_solution(self):
        context = retrieve_structured_system_knowledge(
            "Sistemas - ChatGuru\nParticipante: erro 131049"
        )
        self.assertIn("131049", context)
        self.assertIn("não insistir", context)

    def test_permission_does_not_receive_generic_tests(self):
        context = retrieve_structured_system_knowledge(
            "Sistemas - Clickup\nTipo de problema selecionado: permissao/cadastro"
        )
        self.assertIn("nenhum teste genérico", context)
        self.assertIn("qual espaço", context)
        self.assertNotIn("Ctrl+F5", context)

    def test_inss_robot_has_scope_questions(self):
        context = retrieve_structured_system_knowledge(
            "Área: Robôs/Automações. Subsistema: INSS"
        )
        self.assertIn("um, vários ou todos", context)
        self.assertIn("alterar a automação", context)


if __name__ == "__main__":
    unittest.main()
