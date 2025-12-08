
import unittest
import os
import json
from unittest.mock import patch, mock_open
from src.utils import load_config

class TestConfig(unittest.TestCase):

    @patch('src.utils.os.getenv')
    @patch('src.utils.os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='{"folder_structure": {"presidents_folder": "P", "intro_folder": "I", "output_folder": "O", "temp_folder": "T"}}')
    def test_load_config_success(self, mock_file, mock_exists, mock_getenv):
        # Setup mocks
        mock_getenv.return_value = "/fake/root/path"
        mock_exists.return_value = True

        config = load_config("config/config.json")
        
        self.assertEqual(config["paths"]["library_base"], os.path.join("/fake/root/path", "P"))
        self.assertEqual(config["paths"]["output_folder"], os.path.join("/fake/root/path", "O"))

    @patch('src.utils.os.getenv')
    def test_load_config_missing_env_var(self, mock_getenv):
        mock_getenv.return_value = None
        with self.assertRaises(EnvironmentError):
            load_config("config/config.json")

    @patch('src.utils.os.getenv')
    @patch('src.utils.os.path.exists')
    def test_load_config_invalid_root_path(self, mock_exists, mock_getenv):
        mock_getenv.return_value = "/invalid/path"
        mock_exists.return_value = False
        with self.assertRaises(FileNotFoundError):
            load_config("config/config.json")

if __name__ == '__main__':
    unittest.main()
