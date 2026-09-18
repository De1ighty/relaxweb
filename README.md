# RelaxWeb · 直播间 + 游戏厅

一个自托管的直播间：WebRTC 看直播、实时聊天与弹幕、金币系统（转账 / 竞猜 / 游戏厅），
以及内置的两个多人小游戏——德州扑克与 UNO。后端 Python 3 标准库 + `websockets`，
前端原生 ES Module，**没有构建步骤**，改完文件刷新页面即生效。

## 功能

- **直播**：MediaMTX 推流，页面用 WebRTC（WHEP）拉流；播放器支持音量、静音、全屏、弹幕开关
- **账号**：邀请码注册、会话 token 自动续期、资料编辑（昵称/头像）、注销账号
- **聊天**：聊天室 + 弹幕（含流主/管理员标识）、在线列表、历史消息
- **金币**：注册奖励、转账（带拼音排序的收款人选择）、金币流水明细
- **竞猜**：主播/管理员出题，观众下注，开奖后按注额分配
- **游戏厅**：德州扑克（盲注轮转、边池、全下跑马、一手结束后结算投票）与 UNO（剩牌赔付），
  房间制、金币买入、离桌自动结算，手机横屏有专门布局

## 目录结构

```
chat_server.py        聊天/账号/金币/竞猜/游戏厅的 WebSocket 服务
auth_server.py        拉流鉴权（仅监听本机，供 MediaMTX authExternalUrl 调用）
config.py             配置加载：config.json + 环境变量覆盖
admin.py              金币管理命令行（list/set/add/sub/restore）
manage_invite.py      邀请码管理命令行（gen/list）
games/                游戏引擎（纯逻辑，可脱离网络单测）
  base.py             房间基类：成员、计时器、注册表
  holdem.py           德州扑克：牌力、边池、状态机
  uno.py              UNO：牌堆、出牌判定、一局流程
deploy/
  serve.py            静态服务：白名单 + 注入客户端配置
  systemd/            systemd 单元模板
  README.md           部署说明（配置、单元安装、反代、推流）
assets/
  css/                样式，按功能/游戏拆分（games/poker.css、games/uno.css …）
  js/                 游戏厅前端模块（core/registry/hall/room/games/*）
  app.js reader.js    直播间前端（含 WebRTC 播放器与弹幕）
  transfer-select.js  转账收款人选择组件
index.html            直播间页面      game.html  游戏厅页面
tests/test_games.py   引擎单元测试
live-test/            联调与协议测试（git submodule，独立仓库）
```

## 快速开始（本地）

```bash
python3 -m pip install --user websockets

# 1) 配置
cp config.example.json config.json
$EDITOR config.json            # 至少改 stream.publish_password

# 2) 建库并生成邀请码（首次运行会自动建表）
python3 manage_invite.py gen 3

# 3) 起服务（两个终端，或直接用 systemd，见 deploy/README.md）
python3 chat_server.py         # ws://localhost:8765
python3 deploy/serve.py        # http://localhost:8000

# 4) 打开 http://localhost:8000 ，用邀请码注册账号
```

直播间需要 MediaMTX 提供推流与拉流；只玩聊天与游戏厅不需要它。

## 配置

所有部署相关参数集中在 `config.json`（**不进版本库**，模板见 `config.example.json`）：

| 配置项 | 说明 |
| --- | --- |
| `site.title` / `site.brand` / `site.game_title` | 浏览器标题与页面品牌文案 |
| `servers.chat_host` / `servers.chat_port` | 聊天与游戏服务监听地址、端口 |
| `servers.web_port` | 静态页面端口 |
| `servers.auth_host` / `servers.auth_port` | 拉流鉴权监听地址、端口 |
| `stream.whep_port` / `stream.path` | 页面拉流地址（`http://<host>:<whep_port>/<path>/whep`） |
| `stream.publish_user` / `stream.publish_password` | 推流账号与口令（鉴权服务用它校验） |
| `database.file` | SQLite 数据库路径 |
| `economy.new_user_coins` | 新用户注册赠送金币 |

环境变量优先级高于配置文件，便于临时覆盖与 CI：
`LIVE_CONFIG_FILE`、`LIVE_CHAT_HOST`、`LIVE_CHAT_PORT`、`LIVE_WEB_PORT`、
`LIVE_AUTH_HOST`、`LIVE_AUTH_PORT`、`LIVE_DB_FILE`、`NEW_USER_COINS`、
`STREAM_PUBLISH_USER`、`STREAM_PUBLISH_PASSWORD`。

页面里的 `window.LIVE_CONFIG` 由 `deploy/serve.py` 注入，只包含展示文案与端口，
**不包含推流口令**；`config.json` 本身也不对外提供（静态服务只放行 `assets/` 下的静态资源）。

## 测试

```bash
python3 tests/test_games.py            # 引擎纯逻辑（不需要起服务）

git submodule update --init live-test  # 协议级联调脚本
bash live-test/reset.sh                # 重置测试库、重建测试账号、重启服务
python3 live-test/proto_test.py        # 聊天/账号/房间生命周期等 16 项协议测试
python3 live-test/uno_proto_test.py    # UNO 协议测试
```

## 部署

见 [deploy/README.md](deploy/README.md)：systemd 单元安装、nginx 反代、推流命令。

## 数据库与用户数据

- 数据库为单文件 SQLite（默认 `users.db`），**已在 `.gitignore` 中**，不会进版本库
- 口令只存 PBKDF2 哈希与盐，会话 token 只存 SHA-256 哈希
- 备份时直接复制该文件即可；`admin.py restore` 可把金币一键还原

## 许可

[MIT](LICENSE) © 2026 LuHongYi
