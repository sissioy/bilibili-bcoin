"""
哔哩哔哩签到模块
"""
import random
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from signin.core import SyncHttpClient, random_sleep, BilibiliBrowserAuth
from signin.core.config import BilibiliAccount, BrowserAuthConfig
from signin.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    TaskExecutionError,
)
from signin.core.message import MessageService
from signin.scripts.base import BaseTask, register_task, CompositeTask


@dataclass
class UserInfo:
    """用户信息"""
    mid: int = 0
    name: str = ""
    level: int = 0
    coins: float = 0.0
    vip_type: int = 0
    vip_status: int = 0


@register_task
class BilibiliTask(CompositeTask):
    """
    哔哩哔哩签到任务
    包含多个子任务的复合任务
    """

    task_name = "bilibili"
    platform = "bilibili"

    def __init__(
        self,
        account: BilibiliAccount,
        message_service: Optional[MessageService] = None,
        browser_auth: Optional[BrowserAuthConfig] = None,
        vip_only: bool = False,
        dry_run_charge: bool = True
    ):
        super().__init__(account.name)
        self.account = account
        self.message_service = message_service
        self.browser_auth = browser_auth
        self.vip_only = vip_only
        self.dry_run_charge = dry_run_charge
        self.http = SyncHttpClient()
        self.headers = {
            "User-Agent": account.userAgent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        }
        self.cookies = {}
        self._sync_cookie_dict()
        self.user_info: Optional[UserInfo] = None

        self._setup_sub_tasks()

    def _setup_sub_tasks(self):
        """设置子任务"""
        if self.vip_only:
            self.add_sub_task(BilibiliVipPrivilegeTask(self))
            return

        self.add_sub_task(BilibiliVideoWatchTask(self))
        self.add_sub_task(BilibiliCoinAddTask(self))
        self.add_sub_task(BilibiliMangaSignTask(self))
        self.add_sub_task(BilibiliMangaReadTask(self))
        self.add_sub_task(BilibiliLiveCheckinTask(self))
        self.add_sub_task(BilibiliGiveGiftTask(self))
        self.add_sub_task(BilibiliVipPrivilegeTask(self))

    def check_authentication(self) -> bool:
        """检查登录状态"""
        browser_error = None
        try:
            self._refresh_auth_from_browser()
        except (AuthenticationError, ConfigurationError) as e:
            browser_error = e
            logger.warning(f"浏览器登录态刷新失败，尝试使用配置中的Cookie: {e}")

        self.user_info = self._get_user_info()
        if self.user_info is not None and self.user_info.mid > 0:
            return True
        if browser_error:
            raise AuthenticationError(
                "浏览器登录态刷新失败，且配置中的Cookie无效",
                platform=self.platform,
            ) from browser_error
        return False

    def execute(self) -> Dict[str, Any]:
        """执行签到任务"""
        logger.info(f"用户: {self.user_info.name}, 硬币: {self.user_info.coins}")

        return super().execute()

    def on_error(self, error: Exception) -> None:
        """错误处理"""
        super().on_error(error)
        if isinstance(error, AuthenticationError) and self.message_service:
            self.message_service.notify_cookie_expired("哔哩哔哩", self.account_name)

    def _refresh_auth_from_browser(self) -> None:
        if not self.browser_auth or not self.browser_auth.enabled:
            return

        source = (
            f"独立浏览器 Profile {self.browser_auth.profileDir}"
            if self.browser_auth.profileDir
            else f"Chrome 调试端口 {self.browser_auth.cdpUrl}"
        )
        logger.info(f"从{source}刷新 B站登录态")
        cookies = BilibiliBrowserAuth(self.browser_auth).get_cookies()
        self.account.DEDEUSERID = cookies["DEDEUSERID"]
        self.account.SESSDATA = cookies["SESSDATA"]
        self.account.BILI_JCT = cookies["BILI_JCT"]
        self._sync_cookie_dict(cookies)
        logger.info(f"已从{source}刷新 B站登录态")

    def _sync_cookie_dict(self, browser_cookies: Optional[Dict[str, str]] = None) -> None:
        self.cookies.clear()
        if browser_cookies:
            self.cookies.update(browser_cookies)
        if self.account.DEDEUSERID:
            self.cookies["DEDEUSERID"] = self.account.DEDEUSERID
            self.cookies["DedeUserID"] = self.account.DEDEUSERID
        if self.account.SESSDATA:
            self.cookies["SESSDATA"] = self.account.SESSDATA
        if self.account.BILI_JCT:
            self.cookies["BILI_JCT"] = self.account.BILI_JCT
            self.cookies["bili_jct"] = self.account.BILI_JCT

    def _get_user_info(self) -> Optional[UserInfo]:
        """获取用户信息"""
        url = "https://api.bilibili.com/x/web-interface/nav"
        response = self.http.get(url, headers=self.headers, cookies=self.cookies)
        data = response.json()

        if data.get('code') == 0 and data.get('data', {}).get('isLogin'):
            info = data.get('data', {})
            return UserInfo(
                mid=info.get('mid', 0),
                name=info.get('uname', ''),
                level=info.get('level_info', {}).get('current_level', 0),
                coins=float(info.get('money', 0)),
                vip_type=info.get('vipType', 0),
                vip_status=info.get('vipStatus', 0),
            )
        if data.get('code') == 0 or data.get('code') == -101:
            return None
        raise TaskExecutionError(
            f"获取用户信息失败: {data.get('message') or data.get('msg') or data.get('code')}",
            task_name=self.task_name,
            account_name=self.account_name,
        )

    def _get_daily_task_status(self) -> Dict[str, Any]:
        """获取每日任务状态"""
        url = "https://api.bilibili.com/x/member/web/exp/reward"
        try:
            response = self.http.get(url, headers=self.headers, cookies=self.cookies)
            data = response.json()
            if data.get('code') == 0:
                return data.get('data', {})
        except Exception as e:
            logger.error(f"获取任务状态失败: {e}")
        return {}

    def _get_region_videos(self, rid: int = 1, num: int = 50) -> list:
        """获取分区视频列表"""
        url = f"https://api.bilibili.com/x/web-interface/dynamic/region?ps={num}&rid={rid}"
        try:
            response = self.http.get(url, headers=self.headers)
            data = response.json()
            if data.get('code') == 0:
                archives = data.get('data', {}).get('archives', [])
                return [a.get('bvid', '') for a in archives if a.get('bvid')]
        except Exception as e:
            logger.error(f"获取分区视频失败: {e}")
        return []


class BilibiliSubTask(BaseTask):
    """B站子任务基类"""

    platform = "bilibili"

    def __init__(self, parent: BilibiliTask):
        super().__init__(parent.account_name)
        self.parent = parent
        self.http = parent.http
        self.headers = parent.headers
        self.cookies = parent.cookies
        self.account = parent.account


class BilibiliVideoWatchTask(BilibiliSubTask):
    """观看分享视频任务"""

    task_name = "bilibili_video_watch"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        task_status = self.parent._get_daily_task_status()
        results = {"watch": False, "share": False}

        if not task_status.get('watch', False):
            videos = self.parent._get_region_videos()
            if videos:
                bvid = random.choice(videos)
                if self._watch_video(bvid):
                    results["watch"] = True
                    logger.info("观看视频成功")
        else:
            results["watch"] = True
            logger.info("今日观看视频任务已完成")

        if not task_status.get('share', False):
            videos = self.parent._get_region_videos()
            if videos:
                bvid = random.choice(videos)
                if self._share_video(bvid):
                    results["share"] = True
                    logger.info("分享视频成功")
        else:
            results["share"] = True
            logger.info("今日分享视频任务已完成")

        results["success"] = results["watch"] and results["share"]
        return results

    def _watch_video(self, bvid: str) -> bool:
        url = "https://api.bilibili.com/x/click-interface/web/heartbeat"
        data = {"bvid": bvid, "played_time": random.randint(1, 90)}
        try:
            response = self.http.post(url, data=data, headers=self.headers, cookies=self.cookies)
            return response.json().get('code') == 0
        except Exception:
            return False

    def _share_video(self, bvid: str) -> bool:
        url = "https://api.bilibili.com/x/web-interface/share/add"
        data = {"bvid": bvid, "csrf": self.account.BILI_JCT}
        try:
            response = self.http.post(url, data=data, headers=self.headers, cookies=self.cookies)
            return response.json().get('code') == 0
        except Exception:
            return False


class BilibiliCoinAddTask(BilibiliSubTask):
    """投币任务"""

    task_name = "bilibili_coin_add"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        task_status = self.parent._get_daily_task_status()
        coins_today = task_status.get('coins', 0)

        need_coins = 5 - coins_today
        if need_coins <= 0:
            logger.info("今日投币任务已完成")
            return {"success": True, "coins_added": 0, "message": "已完成"}

        balance = self.parent.user_info.coins if self.parent.user_info else 0
        reserve = self.account.reserveCoins

        if balance <= reserve:
            logger.info(f"硬币余额 {balance} 低于预留 {reserve}，跳过投币")
            return {"success": False, "skipped": True, "coins_added": 0, "message": "余额不足"}

        available = int(balance - reserve)
        need_coins = min(need_coins, available)

        logger.info(f"需要投币 {need_coins} 枚")

        videos = self.parent._get_region_videos(num=50)
        if not videos:
            return {"success": False, "coins_added": 0, "message": "未获取到视频"}

        success_count = 0
        for bvid in videos:
            if success_count >= need_coins:
                break

            if self._check_coin_status(bvid) > 0:
                continue

            random_sleep(500, 2000)
            if self._add_coin(bvid):
                success_count += 1
                logger.info(f"投币成功 ({success_count}/{need_coins})")

        return {
            "success": success_count == need_coins,
            "coins_added": success_count,
            "target": need_coins,
        }

    def _check_coin_status(self, bvid: str) -> int:
        url = f"https://api.bilibili.com/x/web-interface/coin/info?bvid={bvid}"
        try:
            response = self.http.get(url, headers=self.headers, cookies=self.cookies)
            data = response.json()
            if data.get('code') == 0:
                return data.get('data', {}).get('multiply', 0)
        except Exception:
            pass
        return 0

    def _add_coin(self, bvid: str) -> bool:
        url = "https://api.bilibili.com/x/web-interface/coin/add"
        data = {
            "bvid": bvid,
            "multiply": 1,
            "select_like": 1,
            "cross_domain": "true",
            "csrf": self.account.BILI_JCT,
        }
        try:
            response = self.http.post(url, data=data, headers=self.headers, cookies=self.cookies)
            return response.json().get('code') == 0
        except Exception:
            return False


class BilibiliMangaSignTask(BilibiliSubTask):
    """漫画签到"""

    task_name = "bilibili_manga_sign"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        url = "https://manga.bilibili.com/twirp/activity.v1.Activity/ClockIn"
        data = {"platform": "android"}
        try:
            response = self.http.post(url, json_data=data, headers=self.headers, cookies=self.cookies)
            success = response.json().get('code') == 0
            if success:
                logger.info("漫画签到成功")
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}


class BilibiliMangaReadTask(BilibiliSubTask):
    """漫画阅读"""

    task_name = "bilibili_manga_read"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        url = "https://manga.bilibili.com/twirp/activity.v1.Activity/ReadComics"
        data = {"device": "pc", "platform": "web", "comic_id": 27355, "ep_id": 381662}
        try:
            response = self.http.post(url, json_data=data, headers=self.headers, cookies=self.cookies)
            success = response.json().get('code') == 0
            if success:
                logger.info("漫画阅读成功")
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}


class BilibiliLiveCheckinTask(BilibiliSubTask):
    """直播签到"""

    task_name = "bilibili_live_checkin"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        url = "https://api.live.bilibili.com/xlive/web-ucenter/v1/sign/DoSign"
        try:
            response = self.http.get(url, headers=self.headers, cookies=self.cookies)
            result = response.json()
            if result.get('code') == 0:
                data = result.get('data', {})
                logger.info(f"直播签到成功: {data.get('text')}")
                return {"success": True, "reward": data.get('text')}
            return {"success": False, "message": result.get('message')}
        except Exception as e:
            return {"success": False, "error": str(e)}


class BilibiliGiveGiftTask(BilibiliSubTask):
    """送出即将过期的礼物"""

    task_name = "bilibili_give_gift"

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        gifts = self._get_gift_list()
        if not gifts:
            logger.info("背包没有礼物")
            return {"gifts_sent": 0}

        now_time = int(datetime.now().timestamp())
        sent = 0

        for gift in gifts:
            expire_at = gift.get('expire_at', 0)
            if expire_at == 0 or (expire_at - now_time) >= 60 * 60 * 25:
                continue

            room_id, uid = self._get_live_room()
            if room_id and uid:
                if self._send_gift(room_id, uid, gift):
                    sent += 1
                    logger.info(f"送出礼物: {gift.get('gift_name')} x {gift.get('gift_num')}")

        return {"gifts_sent": sent}

    def _get_gift_list(self) -> list:
        url = "https://api.live.bilibili.com/xlive/web-room/v1/gift/bag_list"
        try:
            response = self.http.get(url, headers=self.headers, cookies=self.cookies)
            data = response.json()
            if data.get('code') == 0:
                return data.get('data', {}).get('list', [])
        except Exception:
            pass
        return []

    def _get_live_room(self) -> tuple:
        if self.account.upLive != "0":
            url = f"http://api.live.bilibili.com/room/v1/Room/getRoomInfoOld?mid={self.account.upLive}"
            try:
                response = self.http.get(url, headers=self.headers)
                data = response.json()
                if data.get('code') == 0:
                    room_id = data.get('data', {}).get('roomid', '0')
                    if room_id != '0':
                        return str(room_id), self.account.upLive
            except Exception:
                pass

        url = "https://api.live.bilibili.com/relation/v1/AppWeb/getRecommendList"
        try:
            response = self.http.get(url, headers=self.headers)
            data = response.json()
            if data.get('code') == 0:
                room_id = data.get('data', {}).get('list', [])[6].get('roomid', '')
                room_url = f"https://api.live.bilibili.com/xlive/web-room/v1/index/getInfoByRoom?room_id={room_id}"
                room_resp = self.http.get(room_url, headers=self.headers)
                room_data = room_resp.json()
                uid = room_data.get('data', {}).get('room_info', {}).get('uid', '')
                return str(room_id), str(uid)
        except Exception:
            pass
        return "", ""

    def _send_gift(self, room_id: str, uid: str, gift: dict) -> bool:
        url = "https://api.live.bilibili.com/gift/v2/live/bag_send"
        data = {
            "uid": self.account.DEDEUSERID,
            "biz_id": room_id,
            "ruid": uid,
            "bag_id": gift.get('bag_id', 0),
            "gift_id": gift.get('gift_id', 0),
            "gift_num": gift.get('gift_num', 0),
            "csrf": self.account.BILI_JCT,
        }
        try:
            response = self.http.post(url, data=data, headers=self.headers, cookies=self.cookies)
            return response.json().get('code') == 0
        except Exception:
            return False


class BilibiliVipPrivilegeTask(BilibiliSubTask):
    """领取大会员权益并使用B币券充电"""

    task_name = "bilibili_vip_privilege"
    BCOIN_PRIVILEGE_TYPE = 1
    POST_ATTEMPTS = 3
    BALANCE_POLL_DELAYS = (0, 2, 4, 8)

    def check_authentication(self) -> bool:
        return True

    def execute(self) -> Dict[str, Any]:
        if (
            not self.parent.user_info
            or self.parent.user_info.vip_type == 0
            or self.parent.user_info.vip_status != 1
        ):
            logger.info("非有效大会员，跳过领取权益")
            return {"success": False, "skipped": True, "reason": "非有效大会员"}

        status = self._get_bcoin_privilege()
        if status is None:
            return {"success": False, "reason": "获取B币券领取周期失败"}
        next_receive_time = status.get("period_end_unix")
        logger.info(f"B币券领取周期结束时间: {next_receive_time}")
        if status.get("state") == 1:
            return {
                "success": True,
                "skipped": True,
                "reason": "本周期B币券已领取，不重复充电",
                "next_receive_time": next_receive_time,
            }
        if status.get("state") != 0:
            return {"success": False, "reason": "B币券领取状态不明"}

        privilege = self._receive_privilege(self.BCOIN_PRIVILEGE_TYPE)
        code = privilege.get("code")
        if code == 0:
            logger.info("领取B币券成功")
        elif code == 69801:
            logger.info("B币券已领取")
            return {
                "success": True,
                "skipped": True,
                "reason": "本周期B币券已领取，不重复充电",
                "next_receive_time": next_receive_time,
            }
        else:
            logger.warning(f"领取B币券失败: {privilege.get('message') or privilege.get('msg')}")
            return {
                "success": False,
                "reason": "领取B币券失败",
                "privilege": privilege,
            }

        charge_result = self._charge_with_bcoin_coupon()
        charge_succeeded = charge_result.get("success") is True

        return {
            "success": charge_succeeded,
            "privilege": privilege,
            "charge": charge_result,
            "next_receive_time": next_receive_time,
        }

    def _get_bcoin_privilege(self):
        response = self.http.get(
            "https://api.bilibili.com/x/vip/privilege/my",
            headers=self.headers,
            cookies=self.cookies,
        )
        result = response.json()
        if result.get("code") == 0:
            for privilege in result.get("data", {}).get("list", []):
                if privilege.get("type") == self.BCOIN_PRIVILEGE_TYPE:
                    return privilege
        return None

    def _receive_privilege(self, privilege_type: int) -> Dict[str, Any]:
        url = "https://api.bilibili.com/x/vip/privilege/receive"
        data = {"type": privilege_type, "csrf": self.account.BILI_JCT}
        return self._post_json_with_retry(url, data=data)

    def _charge_with_bcoin_coupon(self) -> Dict[str, Any]:
        if self.account.chargeForLove == "0":
            logger.info("未配置充电对象UID，跳过B币券充电")
            return {"success": False, "skipped": True, "reason": "未配置充电对象UID"}

        charge_bp_num = self.account.chargeBpNum
        coupon_balance = self._poll_coupon_balance(
            lambda balance: balance >= charge_bp_num,
        )
        if coupon_balance is None:
            return {"success": False, "reason": "获取B币券余额失败"}
        if int(coupon_balance) < charge_bp_num:
            logger.info(f"B币券余额 {coupon_balance}，低于计划充电 {charge_bp_num}，跳过")
            return {
                "success": False,
                "skipped": True,
                "reason": "B币券余额不足",
                "coupon_balance": coupon_balance,
            }

        if self.parent.dry_run_charge:
            logger.info(f"dry-run: 将给 UID {self.account.chargeForLove} 充电 {charge_bp_num} 贝壳，已停止在提交前")
            return {
                "success": True,
                "dry_run": True,
                "target_uid": self.account.chargeForLove,
                "bp_num": charge_bp_num,
                "coupon_balance_before": coupon_balance,
            }

        result = self._charge_user(self.account.chargeForLove, charge_bp_num)
        if result.get("code") == -2:
            return {"success": False, "reason": result["message"], "response": result}
        balance_after = self._poll_coupon_balance(
            lambda balance: coupon_balance - balance >= charge_bp_num,
        )
        balance_confirmed = (
            balance_after is not None
            and coupon_balance - balance_after >= charge_bp_num
        )
        response_data = result.get("data") or {}
        response_succeeded = result.get("code") == 0 and response_data.get("status") == 4

        if balance_confirmed:
            logger.info(
                f"B币券余额已扣减，已给 UID {self.account.chargeForLove} "
                f"充电 {charge_bp_num} 贝壳"
            )
        elif result.get("code") == -1 or response_succeeded:
            logger.warning("充电响应或余额状态不明确，本次不再提交充电请求")
        else:
            logger.warning(f"B币券充电失败: {response_data.get('msg') or result.get('message')}")

        return {
            "success": balance_confirmed,
            "uncertain": not balance_confirmed and (
                result.get("code") == -1 or response_succeeded
            ),
            "reason": None if balance_confirmed else (
                "充电状态不明"
                if result.get("code") == -1 or response_succeeded
                else "B币券充电失败"
            ),
            "target_uid": self.account.chargeForLove,
            "bp_num": charge_bp_num,
            "coupon_balance_before": coupon_balance,
            "coupon_balance_after": balance_after,
            "response": result,
        }

    def _get_coupon_balance(self) -> Optional[float]:
        wallet = self._get_wallet()
        if wallet is not None and "couponBalance" in wallet:
            return float(wallet["couponBalance"])
        return None

    def _get_wallet(self):
        url = "https://pay.bilibili.com/paywallet/wallet/getUserWallet"
        now_ms = int(datetime.now().timestamp() * 1000)
        data = {
            "platformType": "3",
            "timestamp": now_ms,
            "traceId": now_ms,
            "version": "1.0",
        }
        result = self._post_json_with_retry(url, json_data=data)
        if result.get("code") == 0:
            return result.get("data")
        logger.warning(f"获取B币券余额失败: {result.get('message') or result.get('msg')}")
        return None

    def _poll_coupon_balance(self, predicate) -> Optional[float]:
        last_balance = None
        for delay in self.BALANCE_POLL_DELAYS:
            if delay:
                time.sleep(delay)
            balance = self._get_coupon_balance()
            if balance is None:
                return None
            last_balance = balance
            if predicate(balance):
                return balance
        return last_balance

    def _post_json_with_retry(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        for attempt in range(self.POST_ATTEMPTS):
            try:
                response = self.http.post(
                    url,
                    data=data,
                    json_data=json_data,
                    headers=self.headers,
                    cookies=self.cookies,
                )
            except NetworkError as e:
                if attempt + 1 == self.POST_ATTEMPTS:
                    return {"code": -1, "message": str(e)}
                self._wait_before_post_retry(attempt, str(e))
                continue

            if response.status_code not in (408, 429) and response.status_code < 500:
                try:
                    return response.json()
                except ValueError as e:
                    return {"code": -1, "message": str(e)}
            if attempt + 1 == self.POST_ATTEMPTS:
                return {"code": -1, "message": f"HTTP {response.status_code}"}
            self._wait_before_post_retry(attempt, f"HTTP {response.status_code}")

        return {"code": -1, "message": "请求失败"}

    def _wait_before_post_retry(self, attempt: int, reason: str) -> None:
        delay = 2 ** attempt
        logger.warning(
            f"B币券安全请求失败，{delay}秒后重试 "
            f"({attempt + 1}/{self.POST_ATTEMPTS - 1}): {reason}"
        )
        time.sleep(delay)

    def _charge_user(self, uid: str, bp_num: int) -> Dict[str, Any]:
        wallet = self._get_wallet()
        if (
            not wallet
            or any(type(wallet.get(key)) not in (int, float)
                   for key in ("couponBalance", "defaultBp", "iosBp"))
            or not wallet["couponBalance"] >= bp_num
            or wallet["defaultBp"] != 0
            or wallet["iosBp"] != 0
        ):
            logger.warning("无法保证只使用B币券，已阻止充电提交")
            return {"code": -2, "message": "只用B币券检查未通过，未提交充电", "data": {}}
        url = "https://api.bilibili.com/x/ugcpay/web/v2/trade/elec/pay/quick"
        data = {
            "bp_num": bp_num,
            "is_bp_remains_prior": "true",
            "up_mid": uid,
            "otype": "up",
            "oid": uid,
            "csrf": self.account.BILI_JCT,
        }
        try:
            response = self.http.post(url, data=data, headers=self.headers, cookies=self.cookies)
            return response.json()
        except Exception as e:
            return {"code": -1, "message": str(e), "data": {}}
