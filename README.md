# B站签到助手

基于 Python 的 B 站自动任务工具，保留哔哩哔哩相关能力：

- 月初领取大会员权益
- 使用 B币券给指定 UID 充电
- 可从独立浏览器 Profile 自动读取 B 站登录态

## 环境要求

- Python 3.11+
- pip
- Playwright Chromium

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

复制并编辑配置文件：

```bash
cp config/config.example.yml config/config.yml
```

`config/config.yml` 示例：

```yaml
scheduled:
  cron: 0 1 4 1 * *

browserAuth:
  enabled: true
  authWaitSeconds: 120
  cdpUrl: http://127.0.0.1:9222
  authUrl: https://www.bilibili.com

msg:
  pushType: none
  pushConfig:
    mailbox:
      host: smtp.qq.com
      port: 465
      form: 签到系统<xxx@qq.com>
      username: xxxxxx@qq.com
      password: xxxxxx
      email: receiver@example.com
    server:
      key: your-server-chan-key

bilibili:
  enabled: true
  vipOnly: true
  dryRunCharge: true
  accounts:
    - name: 账号1
      profileDir: config/bilibili-profile-1
      DEDEUSERID: xxx
      SESSDATA: xxx
      BILI_JCT: xxx
      reserveCoins: 5
      upLive: 0
      chargeForLove: 0
      chargeBpNum: 5
      vipPrivilegeDays: 1
      userAgent: ""
    - name: 账号2
      profileDir: config/bilibili-profile-2
      DEDEUSERID: xxx
      SESSDATA: xxx
      BILI_JCT: xxx
      reserveCoins: 5
      upLive: 0
      chargeForLove: 0
      chargeBpNum: 5
      vipPrivilegeDays: 1
      userAgent: ""
```

首次运行会打开独立浏览器 Profile。扫码登录 B 站后，后续定时任务会在执行前主动打开 B 站页面，触发网页侧 Cookie 更新，再从该 Profile 读取最新 `DEDEUSERID`、`SESSDATA`、`BILI_JCT` 到内存中的账号配置。最新登录态由浏览器 Profile 保存，不会写入 `config.yml`；如果 B 站彻底要求重新登录，仍需人工扫码一次。

多账号必须给每个账号配置不同的 `profileDir`，避免两个账号共用同一个浏览器登录态。单账号可继续使用全局 `browserAuth.profileDir`。

运行：

```bash
python main.py --once
```

充电提交前停止：

```bash
python main.py --once --dry-run-charge
```

启动定时任务：

```bash
python main.py
```

## 配置说明

| 配置项 | 说明 |
| --- | --- |
| `browserAuth.enabled` | 是否自动读取 B 站登录态 |
| `browserAuth.profileDir` | 全局独立浏览器 Profile 目录；仅推荐单账号使用 |
| `browserAuth.authWaitSeconds` | 首次扫码登录等待秒数，默认 `120` |
| `browserAuth.cdpUrl` | 兼容旧方式的 Chrome 远程调试地址，默认 `http://127.0.0.1:9222` |
| `bilibili.vipOnly` | 是否只执行大会员权益和 B币券充电 |
| `bilibili.dryRunCharge` | 是否在调用充电接口前停止 |
| `profileDir` | 账号级独立浏览器 Profile 目录；多账号时必须唯一 |
| `DEDEUSERID` | B 站 Cookie 中的用户 ID |
| `SESSDATA` | B 站 Cookie 中的登录态 |
| `BILI_JCT` | B 站 Cookie 中的 CSRF token |
| `reserveCoins` | 投币任务保留的硬币数量 |
| `upLive` | 即将过期的直播礼物优先赠送的 UP 主 UID，`0` 表示使用推荐直播间 |
| `chargeForLove` | B币券充电对象 UID，`0` 表示不充电 |
| `chargeBpNum` | 每次最多使用多少 B币券/贝壳充电，默认 `5` |
| `vipPrivilegeDays` | 每月前 N 天领取大会员权益并尝试 B币券充电，默认 `7` |
| `userAgent` | 可选，自定义请求 User-Agent |

## 大会员权益和 B币券充电

月初权益任务会尝试领取以下权益：

- B币券
- 会员购优惠券
- 漫画福利券
- 会员购包邮券
- 漫画商城优惠券
- 装扮体验卡
- 课堂优惠券

领取后会查询钱包中的 `couponBalance`。只有当 B币券余额达到充电下限时，才会向 `chargeForLove` 配置的 UID 发起空间充电。

注意：B站充电接口本身是 B币/贝壳充电接口，公开参数里没有明确的“只使用B币券”开关。本工具会先检查 `couponBalance` 再充电，但如果账号同时存在普通 B币余额，建议先用小金额验证扣款来源。

`dryRunCharge` 默认为 `true`。确认目标 UID、金额和扣款来源后，再显式改为 `false`。

## Docker

构建镜像：

```bash
docker build -t bilibili-signin:latest .
```

运行容器：

```bash
docker run -d \
  --name bilibili-signin \
  -v /opt/docker/bilibili-signin/config:/app/config \
  -v /opt/docker/bilibili-signin/logs:/app/logs \
  bilibili-signin:latest
```

Docker 镜像未包含可交互的图形浏览器。容器部署时请设置 `browserAuth.enabled: false` 并在配置中提供 Cookie；首次扫码登录需在本地运行。

## 项目结构

```text
.
├── config/
│   └── config.yml
├── signin/
│   ├── core/
│   ├── scheduler/
│   └── scripts/
│       ├── base.py
│       └── bilibili.py
├── main.py
├── requirements.txt
├── Dockerfile
└── run.sh
```
