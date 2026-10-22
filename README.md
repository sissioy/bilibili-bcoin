# B站签到助手

基于 Python 的 B 站自动任务工具，保留哔哩哔哩相关能力：

- 月初领取大会员 B币券
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
  cron: 0 0 11 1-7 * *

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
| `vipPrivilegeDays` | 保留兼容旧配置，实际领取周期以账户接口为准 |
| `userAgent` | 可选，自定义请求 User-Agent |

## 大会员权益和 B币券充电

任务以账户接口返回的 B币券领取周期为准，只领取 B币券。已领取的周期直接跳过，不重复充电。领取后查询钱包中的 `couponBalance`，只有 B币券余额达到充电金额时，才会向 `chargeForLove` 配置的 UID 发起空间充电。

登录态刷新失败时，程序会先验证配置中的 Cookie。GET、B币券领取和钱包查询遇到网络错误、HTTP 408、429 或 5xx 时最多尝试 3 次。充电提交不会自动重试；提交后会轮询 B币券余额，只有确认余额按计划扣减才报告成功，状态不明确时停止并等待下次调度。

充电提交前再次查询钱包，要求 `couponBalance` 足够且普通 B币余额 `defaultBp`、`iosBp` 均为零。余额字段缺失、余额不足或存在普通 B币时，阻止提交并报告失败。接口没有明确的“只使用B币券”开关，因此不要在自动任务执行期间同时充值或消费钱包。

`dryRunCharge` 默认为 `true`。确认目标 UID、金额和扣款来源后，再显式改为 `false`。

macOS 本机使用 Codex Schedule 时，应让任务调用项目虚拟环境：

```bash
.venv/bin/python main.py --once
```

建议在每月 1 至 7 日 11:00 执行，以便临时网络或登录态故障可以在月初窗口内自动补偿。持久化浏览器 Profile 需要可用的 macOS 图形会话。

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
