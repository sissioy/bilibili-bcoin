import tempfile
import unittest
from pathlib import Path

from signin.core.config import Config, load_config
from signin.core.exceptions import ConfigurationError


class ConfigTest(unittest.TestCase):
    def setUp(self):
        Config._instance = None

    def tearDown(self):
        Config._instance = None

    def load_from_text(self, text):
        with tempfile.TemporaryDirectory() as config_dir:
            Path(config_dir, "config.yml").write_text(text, encoding="utf-8")
            return load_config(config_dir)

    def test_single_account_uses_global_profile_dir(self):
        config = self.load_from_text("""
browserAuth:
  enabled: true
  profileDir: config/bilibili-profile
bilibili:
  enabled: true
  accounts:
    - name: account1
      DEDEUSERID: mid
      SESSDATA: sess
      BILI_JCT: jct
""")

        self.assertEqual(config.browserAuth.profileDir, "config/bilibili-profile")
        self.assertEqual(config.bilibili.accounts[0].profileDir, "")

    def test_charge_is_dry_run_by_default(self):
        config = self.load_from_text("""
bilibili:
  enabled: true
  accounts:
    - name: account1
""")

        self.assertTrue(config.bilibili.dryRunCharge)

    def test_multi_account_accepts_unique_account_profile_dirs(self):
        config = self.load_from_text("""
browserAuth:
  enabled: true
bilibili:
  enabled: true
  accounts:
    - name: account1
      profileDir: config/bilibili-profile-1
    - name: account2
      profileDir: config/bilibili-profile-2
""")

        self.assertEqual(config.bilibili.accounts[0].profileDir, "config/bilibili-profile-1")
        self.assertEqual(config.bilibili.accounts[1].profileDir, "config/bilibili-profile-2")

    def test_multi_account_requires_account_profile_dir(self):
        with self.assertRaises(ConfigurationError):
            self.load_from_text("""
browserAuth:
  enabled: true
  profileDir: config/bilibili-profile
bilibili:
  enabled: true
  accounts:
    - name: account1
    - name: account2
      profileDir: config/bilibili-profile-2
""")

    def test_multi_account_rejects_duplicate_profile_dir(self):
        with self.assertRaises(ConfigurationError):
            self.load_from_text("""
browserAuth:
  enabled: true
bilibili:
  enabled: true
  accounts:
    - name: account1
      profileDir: config/bilibili-profile
    - name: account2
      profileDir: config/bilibili-profile
""")

    def test_multi_account_rejects_equivalent_profile_dirs(self):
        with self.assertRaises(ConfigurationError):
            self.load_from_text("""
browserAuth:
  enabled: true
bilibili:
  enabled: true
  accounts:
    - name: account1
      profileDir: config/bilibili-profile
    - name: account2
      profileDir: ./config/bilibili-profile
""")


if __name__ == "__main__":
    unittest.main()
