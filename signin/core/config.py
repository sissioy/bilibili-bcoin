"""
配置加载模块
负责加载和解析YAML配置文件
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any
import yaml

from .exceptions import ConfigurationError


@dataclass
class Account:
    """账号基类"""
    name: str


@dataclass
class BilibiliAccount(Account):
    """哔哩哔哩账号"""
    DEDEUSERID: str = ""
    SESSDATA: str = ""
    BILI_JCT: str = ""
    profileDir: str = ""
    reserveCoins: int = 5
    upLive: str = "0"
    chargeForLove: str = "0"
    chargeBpNum: int = 5
    vipPrivilegeDays: int = 7
    userAgent: str = ""


@dataclass
class MailboxConfig:
    """邮箱配置"""
    host: str = "smtp.qq.com"
    port: int = 465
    form: str = ""
    username: str = ""
    password: str = ""
    email: str = ""


@dataclass
class ServerConfig:
    """Server酱配置"""
    key: str = ""


@dataclass
class PushConfig:
    """推送配置"""
    mailbox: MailboxConfig = field(default_factory=MailboxConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


@dataclass
class MsgConfig:
    """消息配置"""
    pushType: str = "none"
    pushConfig: PushConfig = field(default_factory=PushConfig)


@dataclass
class ScheduledConfig:
    """定时任务配置"""
    cron: str = "0 1 4 * * *"


@dataclass
class BrowserAuthConfig:
    """浏览器登录态配置"""
    enabled: bool = False
    profileDir: str = ""
    cdpUrl: str = "http://127.0.0.1:9222"
    authUrl: str = "https://www.bilibili.com"
    authWaitSeconds: int = 120


@dataclass
class AppConfig:
    """应用主配置"""
    scheduled: ScheduledConfig = field(default_factory=ScheduledConfig)
    msg: MsgConfig = field(default_factory=MsgConfig)


@dataclass
class BilibiliConfig:
    """哔哩哔哩配置"""
    enabled: bool = False
    vipOnly: bool = False
    dryRunCharge: bool = True
    accounts: List[BilibiliAccount] = field(default_factory=list)


class Config:
    """
    全局配置类
    管理所有平台和应用的配置
    """

    _instance = None
    _config_dir: Path = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.app: AppConfig = AppConfig()
        self.browserAuth: BrowserAuthConfig = BrowserAuthConfig()
        self.bilibili: BilibiliConfig = BilibiliConfig()

    @property
    def config_dir(self) -> Path:
        """获取配置文件目录"""
        if self._config_dir is None:
            self._config_dir = Path(os.getcwd()) / "config"
        return self._config_dir

    @config_dir.setter
    def config_dir(self, path: str):
        """设置配置文件目录"""
        self._config_dir = Path(path)

    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        加载YAML配置文件

        Args:
            filename: 配置文件名

        Returns:
            解析后的字典
        """
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _parse_scheduled(self, data: Dict[str, Any]):
        """解析定时任务配置"""
        scheduled_data = data.get('scheduled', {})
        self.app.scheduled.cron = scheduled_data.get('cron', '0 1 4 * * *')

    def _parse_msg(self, data: Dict[str, Any]):
        """解析消息推送配置"""
        msg_data = data.get('msg', {})
        self.app.msg.pushType = msg_data.get('pushType', 'none')

        push_config = msg_data.get('pushConfig', {})
        mailbox = push_config.get('mailbox', {})
        self.app.msg.pushConfig.mailbox.host = mailbox.get('host', 'smtp.qq.com')
        self.app.msg.pushConfig.mailbox.port = mailbox.get('port', 465)
        self.app.msg.pushConfig.mailbox.form = mailbox.get('form', '')
        self.app.msg.pushConfig.mailbox.username = mailbox.get('username', '')
        self.app.msg.pushConfig.mailbox.password = mailbox.get('password', '')
        self.app.msg.pushConfig.mailbox.email = mailbox.get('email', '')

        server = push_config.get('server', {})
        self.app.msg.pushConfig.server.key = server.get('key', '')

    def _parse_browser_auth(self, data: Dict[str, Any]):
        """解析浏览器登录态配置"""
        browser_auth = data.get('browserAuth', {})
        self.browserAuth.enabled = browser_auth.get('enabled', False)
        self.browserAuth.profileDir = browser_auth.get('profileDir', '')
        self.browserAuth.cdpUrl = browser_auth.get('cdpUrl', 'http://127.0.0.1:9222')
        self.browserAuth.authUrl = browser_auth.get('authUrl', 'https://www.bilibili.com')
        self.browserAuth.authWaitSeconds = int(browser_auth.get('authWaitSeconds', 120))

    def _parse_bilibili(self, data: Dict[str, Any]):
        """解析哔哩哔哩配置"""
        bilibili_data = data.get('bilibili', {})
        self.bilibili.enabled = bilibili_data.get('enabled', False)
        self.bilibili.vipOnly = bilibili_data.get('vipOnly', False)
        self.bilibili.dryRunCharge = bilibili_data.get('dryRunCharge', True)
        accounts = bilibili_data.get('accounts', [])
        self.bilibili.accounts = [
            BilibiliAccount(
                name=acc.get('name', ''),
                DEDEUSERID=acc.get('DEDEUSERID', ''),
                SESSDATA=acc.get('SESSDATA', ''),
                BILI_JCT=acc.get('BILI_JCT', ''),
                profileDir=str(acc.get('profileDir', '')),
                reserveCoins=acc.get('reserveCoins', 5),
                upLive=str(acc.get('upLive', '0')),
                chargeForLove=str(acc.get('chargeForLove', '0')),
                chargeBpNum=int(acc.get('chargeBpNum', 5)),
                vipPrivilegeDays=int(acc.get('vipPrivilegeDays', 7)),
                userAgent=acc.get('userAgent', '')
            )
            for acc in accounts
        ]

    def _validate_bilibili_browser_auth(self):
        if not self.browserAuth.enabled or len(self.bilibili.accounts) <= 1:
            return

        profiles = {}
        for account in self.bilibili.accounts:
            profile_dir = account.profileDir
            if not profile_dir:
                raise ConfigurationError(
                    f"多账号启用 browserAuth 时，账号 {account.name} 必须配置独立 profileDir"
                )
            normalized_profile = str(Path(profile_dir).expanduser().resolve())
            if normalized_profile in profiles:
                raise ConfigurationError(
                    f"账号 {profiles[normalized_profile]} 和 {account.name} 使用了相同 profileDir: {profile_dir}"
                )
            profiles[normalized_profile] = account.name

    def load_from_single_file(self):
        """从单一配置文件加载所有配置"""
        data = self.load_yaml("config.yml")
        if not data:
            return False

        self._parse_scheduled(data)
        self._parse_msg(data)
        self._parse_browser_auth(data)
        self._parse_bilibili(data)
        self._validate_bilibili_browser_auth()

        return True

    def load_from_multiple_files(self):
        """从多个配置文件加载配置（兼容旧版本）"""
        self.load_app_config()
        self.load_bilibili_config()
        self._validate_bilibili_browser_auth()

    def load_app_config(self):
        """加载应用主配置"""
        data = self.load_yaml("appconfig.yml")
        if not data:
            return

        self._parse_scheduled(data)
        self._parse_msg(data)
        self._parse_browser_auth(data)

    def load_bilibili_config(self):
        """加载哔哩哔哩配置"""
        data = self.load_yaml("bilibili.yml")
        if not data:
            return

        self._parse_bilibili({'bilibili': data})

    def load_all(self):
        """加载所有配置（优先使用单一配置文件）"""
        if self.load_from_single_file():
            return

        self.load_from_multiple_files()


def load_config(config_dir: str = None) -> Config:
    """
    加载配置的便捷函数

    Args:
        config_dir: 配置文件目录路径

    Returns:
        Config实例
    """
    config = Config()
    if config_dir:
        config.config_dir = config_dir
    config.load_all()
    return config
