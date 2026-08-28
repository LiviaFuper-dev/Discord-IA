import unittest
from unittest.mock import patch

import config
from utils.clickup import ClickUpError, _ensure_configuration, _error_for_status


class ClickUpConfigurationTests(unittest.TestCase):
    def test_missing_token_is_rejected(self):
        with patch.object(config, "CLICKUP_API_TOKEN", ""):
            with self.assertRaises(ClickUpError):
                _ensure_configuration()

    def test_missing_lists_are_rejected(self):
        with patch.object(config, "CLICKUP_API_TOKEN", "pk_valid_token"):
            with patch.object(config, "CLICKUP_SUPPORT_LIST_IDS", ()):
                with self.assertRaises(ClickUpError):
                    _ensure_configuration()

    def test_api_errors_are_safe(self):
        self.assertIn("recusado", str(_error_for_status(401)))
        self.assertIn("acesso", str(_error_for_status(403)))
        self.assertIn("não foi encontrada", str(_error_for_status(404)))


if __name__ == "__main__":
    unittest.main()
