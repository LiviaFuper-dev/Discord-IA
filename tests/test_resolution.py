import unittest

from utils.resolution import build_resolution_payload, resolution_log_block


class ResolutionPayloadTests(unittest.TestCase):
    def test_builds_human_and_automation_fields(self):
        payload = build_resolution_payload(
            category="configuracao_corrigida",
            result="resolvido",
            description="Ajustado o perfil padrão do sistema.",
            resolver="Equipe TI",
        )

        self.assertEqual(payload["resultado_final"], "resolvido")
        self.assertEqual(payload["Resultado final"], "Resolvido")
        self.assertIn("Configuração corrigida", payload["Solução final"])
        self.assertNotIn("None", resolution_log_block(payload))


if __name__ == "__main__":
    unittest.main()
