import unittest
from unittest.mock import Mock, patch

from signin.core.config import BilibiliAccount, BrowserAuthConfig
from signin.core.exceptions import AuthenticationError, ConfigurationError, NetworkError
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
            "buvid3": "browser-fingerprint",
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
        self.assertEqual(task.cookies["buvid3"], "browser-fingerprint")

    def test_browser_failure_falls_back_to_valid_configured_cookies(self):
        browser_auth = BrowserAuthConfig(enabled=True, profileDir="config/profile")
        task = BilibiliTask(BilibiliAccount(name="account"), browser_auth=browser_auth)
        user_info = UserInfo(mid=1, name="user")

        with patch.object(
            task,
            "_refresh_auth_from_browser",
            side_effect=ConfigurationError("browser unavailable"),
        ), patch.object(task, "_get_user_info", return_value=user_info):
            self.assertTrue(task.check_authentication())

        self.assertIs(task.user_info, user_info)

    def test_browser_failure_and_invalid_configured_cookies_fail_authentication(self):
        browser_auth = BrowserAuthConfig(enabled=True, profileDir="config/profile")
        task = BilibiliTask(BilibiliAccount(name="account"), browser_auth=browser_auth)

        with patch.object(
            task,
            "_refresh_auth_from_browser",
            side_effect=ConfigurationError("browser unavailable"),
        ), patch.object(task, "_get_user_info", return_value=None):
            with self.assertRaises(AuthenticationError):
                task.check_authentication()

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

    @patch.object(BilibiliVipPrivilegeTask, "_get_bcoin_privilege", return_value={"state": 0, "period_end_unix": 1793635200})
    def test_vip_task_only_receives_bcoin_privilege(self, status):
        parent = BilibiliTask(BilibiliAccount(name="account"))
        parent.user_info = UserInfo(mid=1, vip_type=1, vip_status=1)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_receive_privilege", return_value={"code": 0}) as receive, \
                patch.object(
                    task,
                    "_charge_with_bcoin_coupon",
                    return_value={"success": True},
                ):
            result = task.execute()

        receive.assert_called_once_with(1)
        self.assertTrue(result["success"])
        self.assertEqual(result["privilege"]["code"], 0)

    def test_received_coupon_does_not_repeat_claim_or_charge(self):
        parent = BilibiliTask(BilibiliAccount(name="account"))
        parent.user_info = UserInfo(mid=1, vip_type=2, vip_status=1)
        task = BilibiliVipPrivilegeTask(parent)
        with patch.object(task, "_get_bcoin_privilege", return_value={"state": 1, "period_end_unix": 1793635200}), \
                patch.object(task, "_receive_privilege") as receive, \
                patch.object(task, "_charge_user") as charge:
            result = task.execute()
        self.assertTrue(result["skipped"])
        self.assertEqual(result["next_receive_time"], 1793635200)
        receive.assert_not_called()
        charge.assert_not_called()

    def test_coupon_only_guard_blocks_other_funds_and_unknown_balances(self):
        task = BilibiliVipPrivilegeTask(BilibiliTask(BilibiliAccount(name="account")))
        for wallet in (None, {}, {"couponBalance": 5},
                       {"couponBalance": 5, "defaultBp": 1, "iosBp": 0},
                       {"couponBalance": 5, "defaultBp": 0, "iosBp": 1},
                       {"couponBalance": 4, "defaultBp": 0, "iosBp": 0}):
            with self.subTest(wallet=wallet), patch.object(task, "_get_wallet", return_value=wallet), \
                    patch.object(task.http, "post") as post:
                self.assertEqual(task._charge_user("123", 5)["code"], -2)
                post.assert_not_called()

    def test_coupon_only_guard_allows_one_submission_with_no_other_funds(self):
        task = BilibiliVipPrivilegeTask(BilibiliTask(BilibiliAccount(name="account")))
        with patch.object(task, "_get_wallet", return_value={"couponBalance": 5, "defaultBp": 0, "iosBp": 0}), \
                patch.object(task.http, "post", side_effect=NetworkError("timeout")) as post:
            self.assertEqual(task._charge_user("123", 5)["code"], -1)
            post.assert_called_once()

    @patch("signin.scripts.bilibili.time.sleep")
    def test_privilege_receive_retries_network_error(self, sleep):
        task = BilibiliVipPrivilegeTask(BilibiliTask(BilibiliAccount(name="account")))
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 0}
        task.http = Mock()
        task.http.post.side_effect = [NetworkError("offline"), response]

        result = task._receive_privilege(1)

        self.assertEqual(result["code"], 0)
        self.assertEqual(task.http.post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("signin.scripts.bilibili.time.sleep")
    def test_privilege_receive_does_not_retry_business_error(self, sleep):
        task = BilibiliVipPrivilegeTask(BilibiliTask(BilibiliAccount(name="account")))
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"code": 123, "message": "rejected"}
        task.http = Mock()
        task.http.post.return_value = response

        result = task._receive_privilege(1)

        self.assertEqual(result["code"], 123)
        task.http.post.assert_called_once()
        sleep.assert_not_called()

    @patch("signin.scripts.bilibili.time.sleep")
    def test_privilege_receive_retries_transient_http_status(self, sleep):
        task = BilibiliVipPrivilegeTask(BilibiliTask(BilibiliAccount(name="account")))
        unavailable = Mock(status_code=429)
        response = Mock(status_code=200)
        response.json.return_value = {"code": 0}
        task.http = Mock()
        task.http.post.side_effect = [unavailable, response]

        result = task._receive_privilege(1)

        self.assertEqual(result["code"], 0)
        self.assertEqual(task.http.post.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch("signin.scripts.bilibili.time.sleep")
    def test_insufficient_coupon_balance_does_not_charge(self, sleep):
        account = BilibiliAccount(name="account", chargeForLove="123", chargeBpNum=5)
        parent = BilibiliTask(account, dry_run_charge=False)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_get_coupon_balance", return_value=0), \
                patch.object(task, "_charge_user") as charge:
            result = task._charge_with_bcoin_coupon()

        self.assertTrue(result["skipped"])
        charge.assert_not_called()

    @patch("signin.scripts.bilibili.time.sleep")
    def test_delayed_coupon_balance_is_charged_and_verified(self, sleep):
        account = BilibiliAccount(name="account", chargeForLove="123", chargeBpNum=5)
        parent = BilibiliTask(account, dry_run_charge=False)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_get_coupon_balance", side_effect=[0, 5, 5, 0]), \
                patch.object(task, "_charge_user", return_value={"code": 0, "data": {"status": 4}}) as charge:
            result = task._charge_with_bcoin_coupon()

        self.assertTrue(result["success"])
        self.assertEqual(result["coupon_balance_before"], 5)
        self.assertEqual(result["coupon_balance_after"], 0)
        charge.assert_called_once_with("123", 5)

    @patch("signin.scripts.bilibili.time.sleep")
    def test_ambiguous_charge_is_not_submitted_twice(self, sleep):
        account = BilibiliAccount(name="account", chargeForLove="123", chargeBpNum=5)
        parent = BilibiliTask(account, dry_run_charge=False)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_get_coupon_balance", side_effect=[5, 5, 5, 5, 5]), \
                patch.object(task, "_charge_user", return_value={"code": -1, "message": "timeout", "data": {}}) as charge:
            result = task._charge_with_bcoin_coupon()

        self.assertFalse(result["success"])
        self.assertTrue(result["uncertain"])
        charge.assert_called_once_with("123", 5)

    @patch("signin.scripts.bilibili.time.sleep")
    def test_lost_charge_response_is_confirmed_by_balance(self, sleep):
        account = BilibiliAccount(name="account", chargeForLove="123", chargeBpNum=5)
        parent = BilibiliTask(account, dry_run_charge=False)
        task = BilibiliVipPrivilegeTask(parent)

        with patch.object(task, "_get_coupon_balance", side_effect=[5, 0]), \
                patch.object(task, "_charge_user", return_value={"code": -1, "message": "timeout"}) as charge:
            result = task._charge_with_bcoin_coupon()

        self.assertTrue(result["success"])
        self.assertFalse(result["uncertain"])
        charge.assert_called_once_with("123", 5)

    def test_run_fetches_user_info_once(self):
        task = BilibiliTask(BilibiliAccount(name="account"), vip_only=True)
        user_info = UserInfo(mid=1, name="user", vip_type=0)

        with patch.object(task, "_get_user_info", return_value=user_info) as get_user_info:
            result = task.run()

        self.assertEqual(get_user_info.call_count, 1)
        self.assertEqual(result.status.value, "skipped")


if __name__ == "__main__":
    unittest.main()
