import unittest
from unittest.mock import patch

from signin.core.config import BilibiliAccount, BrowserAuthConfig
from signin.scripts.bilibili import BilibiliTask, BilibiliVipPrivilegeTask, UserInfo


class BilibiliTaskTest(unittest.TestCase):
    def test_refresh_auth_updates_account_and_cookie_aliases(self):
        account = BilibiliAccount(
            name="账号1",
            DEDEUSERID="old-mid",
            SESSDATA="old-sess",
            BILI_JCT="old-jct",
        )
        browser_auth = BrowserAuthConfig(
            enabled=True,
            profileDir="config/bilibili-profile",
        )
        new_cookies = {
            "DEDEUSERID": "new-mid",
            "SESSDATA": "new-sess",
            "BILI_JCT": "new-jct",
        }

        with patch("signin.scripts.bilibili.BilibiliBrowserAuth") as auth_class:
            auth_class.return_value.get_cookies.return_value = new_cookies
            task = BilibiliTask(account, browser_auth=browser_auth)
            task._refresh_auth_from_browser()

        self.assertEqual(account.DEDEUSERID, "new-mid")
        self.assertEqual(account.SESSDATA, "new-sess")
        self.assertEqual(account.BILI_JCT, "new-jct")
        self.assertEqual(task.cookies["DEDEUSERID"], "new-mid")
        self.assertEqual(task.cookies["DedeUserID"], "new-mid")
        self.assertEqual(task.cookies["SESSDATA"], "new-sess")
        self.assertEqual(task.cookies["BILI_JCT"], "new-jct")
        self.assertEqual(task.cookies["bili_jct"], "new-jct")

    def test_wallet_lookup_failure_does_not_attempt_charge(self):
        account = BilibiliAccount(name="account", chargeForLove="123", chargeBpNum=5)
        parent = BilibiliTask(account)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_get_coupon_balance", return_value=None), \
                patch.object(task, "_charge_user") as charge:
            result = task._charge_with_bcoin_coupon()

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "获取B币券余额失败")
        charge.assert_not_called()

    def test_run_fetches_user_info_once(self):
        task = BilibiliTask(BilibiliAccount(name="account"), vip_only=True)
        user_info = UserInfo(mid=1, name="user", vip_type=0)

        with patch.object(task, "_get_user_info", return_value=user_info) as get_user_info:
            result = task.run()

        self.assertEqual(get_user_info.call_count, 1)
        self.assertEqual(result.status.value, "skipped")


if __name__ == "__main__":
    unittest.main()
