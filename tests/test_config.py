import os
import unittest
from unittest.mock import patch, mock_open

from src.utils import load_config


CONFIG_JSON = (
    '{"folder_structure": {"presidents_folder": "P", "intro_folder": "I", '
    '"output_folder": "O", "temp_folder": "T"}}'
)


class TestConfig(unittest.TestCase):
    @patch("src.utils.resolve_tiktok_root")
    @patch("src.utils.os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data=CONFIG_JSON)
    def test_load_config_success(self, _mock_file, mock_exists, mock_resolve):
        mock_resolve.return_value = "/fake/root/path"
        mock_exists.return_value = True

        config = load_config("config/config.json")

        self.assertEqual(
            config["paths"]["library_base"],
            os.path.join("/fake/root/path", "P"),
        )
        self.assertEqual(
            config["paths"]["output_folder"],
            os.path.join("/fake/root/path", "O"),
        )

    @patch("src.utils.resolve_tiktok_root")
    @patch("builtins.open", new_callable=mock_open, read_data=CONFIG_JSON)
    def test_load_config_missing_root(self, _mock_file, mock_resolve):
        # resolve_tiktok_root devuelve None cuando ni env ni auto-detect encuentran ruta
        mock_resolve.return_value = None
        with self.assertRaises(EnvironmentError):
            load_config("config/config.json")


if __name__ == "__main__":
    unittest.main()
