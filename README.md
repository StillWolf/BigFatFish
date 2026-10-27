# BigFatFish · 小肥鱼

一个会自己吃饭、摸鱼、刷视频、记日记的 QQ 聊天伴侣框架。基于 DeepSeek Harness 和 OneBot/NapCat，运行在自己的 Linux 机器上。

**无需本地 GPU，但不是离线模型**：聊天默认调用 DeepSeek API，语音默认使用在线 edge-tts。账号、聊天记忆、浏览器登录态和日记由部署者自己保管。

## 功能

| 能力 | 说明 |
| --- | --- |
| QQ 私聊与群聊 | 按准确账号配置家人、群友与群白名单；私聊、群内明确找她时免主动聊天限流 |
| 自然聊天 | 可分两三个短气泡，间隔约一秒；偶尔在文字后补一张贴切的收藏表情包 |
| 作息与活动 | 北京时间约9点起、23点睡，9:30/12:00/18:00附近随机吃饭，白天每小时随机短活动 |
| 主动聊天 | 找已配置的家人或水群；吃饭、上网活动本身静默，正常聊天时分享见闻 |
| B站观看 | 搜索、选片、实际播放30—45秒；本地字幕/语音、少量关键帧和缓存摘要，节省Token |
| 两本日记 | 约22:40—22:50整理共享本与私密本；共享本仅在核实账号的家人私聊里查看 |
| 图片与语音 | 看图、按需发语音，默认不为每条文字配音 |
| 微信（选装） | 官方 Linux 客户端 + 桌面自动化/数据库读取，与QQ会话隔离，共用生活活动 |

B站当前没有评论、点赞、发帖工具。微信属于实验性组件，真实收发需扫码后按自己的账号联调。

## 一键安装

### 准备

- Linux 64位：`x86_64/amd64` 或 `aarch64/arm64`。自动安装Docker支持Ubuntu/Debian，其他Linux请先安装Docker Engine与Compose v2。
- Python 3.10+；Ubuntu/Debian缺少Python时脚本会补齐。自动安装Docker需要root或sudo权限。
- DeepSeek API Key、给机器人准备的QQ账号。
- 建议从2核、4GB内存、20GB可用磁盘开始；微信组件开销更大，实际资源取决于开启的组件与并发数。
- 可访问npm、PyPI、Docker镜像和相应在线服务。首次安装需下载依赖、浏览器；B站语音模型在首次启动后后台下载。

下载源码、进入目录，执行：

```bash
bash install.sh
```

向导询问机器人QQ、哥哥/主人QQ、可选姐姐QQ、允许的群、主动水群目标、名字及组件选择。**API Key隐藏输入**，本地访问口令自动随机生成。

脚本保存私有配置，按需安装Docker，构建应用和本地桥插件，自动配置NapCat反向WS并启动服务。已有配置与数据保留；下载失败可重跑同一命令。

**一键安装不包含自动获取API Key或替你扫码登录。**

### 登录QQ

```bash
bash fishctl access
bash fishctl access --show-secrets
```

第一条显示地址；第二条仅在自己的终端显示NapCat和可选微信桌面口令，不显示API Key。

打开 <http://127.0.0.1:6099/webui>，输入口令，扫码并在手机确认。网络配置已经生成，无需手工填WS地址；设备验证按客户端提示操作。

DSH管理页面：<http://127.0.0.1:3080/>。**服务健康不等于QQ已扫码在线**。

### 远程服务器访问

网页默认仅发布到服务器回环地址。在自己电脑建立SSH转发：

```bash
ssh -N \
  -L 3080:127.0.0.1:3080 \
  -L 6099:127.0.0.1:6099 \
  -L 6082:127.0.0.1:6082 \
  -L 6081:127.0.0.1:6081 \
  user@your-server
```

然后在本机浏览器打开上述地址。改过 `.env` 端口时同步修改转发端口。

## 开始养鱼

用家人账号私聊，或在允许的群里@她。默认只接受白名单；群里普通群友也需加入 `friends` 或 `allowUsers`。QQ离线时会跳过当次主动聊天，连接恢复后按新日程继续；内部活动仍会进行。

- “今天吃了什么”“现在在干什么”：参考真实活动记录回答。
- “去B站找个鸣潮视频看看”，或发完整视频链接/BV号。
- “看看日记”，或 `/日记`、`/日记 列表`、`/日记 YYYY-MM-DD`。
- “发条语音说晚安”：按需调用语音工具。
- `/status` 查看会话，`/new` 开新会话，`/撤回` 撤回她最近发出的消息。

### 自定义

| 文件/字段 | 用途 |
| --- | --- |
| `config/persona.md` | 通用人设模板；身份和路径启动时填入 |
| `data/fish.config.json` | 实际身份、白名单、功能开关 |
| `qq.family.gege/jiejie` | 家人与共享日记权限，空缺的目标不发作息消息 |
| `qq.allowUsers` / `friends` | 普通群友，friends中的qq同样加入准入 |
| `qq.allowGroups` | 允许接入的群 |
| `qq.proactiveGroup` | 主动水群目标，必须先在群白名单里，留空则不水群 |
| `.env` | API Key、随机访问口令、镜像和宿主网页端口 |

修改配置或模板后：

```bash
bash fishctl configure
bash fishctl up
```

向导复用已有配置，`up`按所选功能重建镜像并生成运行配置。重启时保留面板和NapCat中其他自定义配置；账号、白名单和名为fish的连接由安装器管理，变更前保留私有备份。分条和补图沿用同一次模型生成，不为拆条额外请求模型。

有权使用的表情图放到 `data/app/qq-bridge/qq-faces/`，起易懂文件名，如 `猫猫震惊.png`，重启应用后登记。源码不包含原作者的收藏、头像或账号数据。

## 微信选装

安装时选择微信，或运行：

```bash
bash install.sh --wechat
```

桌面默认 <http://127.0.0.1:6081/>，用户名 `fish`，随机密码见 `bash fishctl access --show-secrets`。扫码确认后绑定准确微信ID：

```bash
bash fishctl wechat status
bash fishctl wechat contacts '准确备注或昵称'
bash fishctl wechat role gege wxid_example
bash fishctl wechat allow wxid_friend
bash fishctl wechat group 'example@chatroom'
bash fishctl wechat target group 'example@chatroom'
bash fishctl wechat resume
```

默认联系人/群为空、回复暂停。昵称不会授予家人身份。`role`允许该家人私聊；群准入与定时水群目标分开设置。

独立微信镜像需下载客户端和CPU视觉依赖，构建时间较长。QQ不依赖微信登录。详见[微信说明](docs/wechat-setup.md)。

## 管理命令

```bash
bash fishctl status           # 容器与应用状态
bash fishctl logs -f fish      # 主进程日志
bash fishctl logs -f napcat    # QQ登录和连接
bash fishctl component-logs dsh # 主模型/桥的详细日志（其他组件可换diary等）
bash fishctl restart fish     # 重载配置与内部服务
bash fishctl up               # 构建/更新本地代码并重建容器
bash fishctl down             # 停止，保留数据
bash fishctl bili status      # B站浏览器状态
bash fishctl wechat pause     # 暂停微信回复
bash fishctl release          # 导出纯源码包
```

脚本不会删除用户数据，也不会给群发“安装完成”消息。

只生成配置：`bash install.sh --configure-only`。

非交互安装：先按 `config/fish.example.json` 填好JSON，再通过环境变量提供密钥：

```bash
read -r -s -p 'DeepSeek API Key: ' DEEPSEEK_API_KEY; echo
export DEEPSEEK_API_KEY
bash install.sh --non-interactive --config /path/to/your-fish.json
unset DEEPSEEK_API_KEY
```

### 版本与网络

DSH固定 `0.2.1-rc.2`，Node固定 `22.22.0`；不会启动时自动 `npx latest`。NapCat由 `.env` 的 `NAPCAT_IMAGE` 指定，默认上游 `latest`，需要固定版本可换上游标签/digest。

模型默认从Hugging Face下载；可在 `.env` 改 `HF_ENDPOINT` 为自己信任的镜像。`FISH_ASR_MODEL=base` 可降低语音模型开销，默认 `small`。镜像拉取代理需配置Docker daemon。

## 数据与迁移

| 路径 | 内容 |
| --- | --- |
| `.env` / `data/fish.config.json` | 私有密钥、身份、白名单 |
| `data/app/qq-bridge` | QQ记忆、活动、共享日记、表情与媒体 |
| `data/dsh` | DSH会话及独立私密日记，仅应用容器挂载 |
| `data/app/diary-service` | 日记进度，防止重复生成 |
| `data/app/bilibili` | B站登录态、缓存、ASR模型 |
| `data/napcat-qq` / `data/napcat-config` | QQ登录态及NapCat配置 |
| `data/app/wechat-runtime/config` | 微信登录态、数据库与界面配置 |
| `data/app/logs` | 各组件运行日志 |

迁移：先 `bash fishctl down`，私下备份 `.env` 与完整 `data/`，复制到同版源码后 `bash fishctl up`。这些备份含私人内容，**不进入公开仓库或附件**。重启保留数据，但平台仍可能要求重新验证。

源码升级：先备份数据，更新自己的代码，再 `bash fishctl up`；不自动执行未知版本迁移。

## 源码结构

```text
install.sh / fishctl         安装与管理入口
compose.yaml / deploy/      容器及镜像构建
config/                     人设模板、示例配置
scripts/                    作息、日记、浏览器、语音、运行编排
dsh-qq-onebot-bridge/        QQ桥与本地扩展
dsh-wechat-ai-bridge/        微信桥
vendor/wechat-ai/            保留许可的微信自动化源码
docs/                       组件及发布说明
data/                       私有运行数据，不分发
```

详细说明：[部署排错](docs/qq-setup.md)、[B站与Token](docs/bilibili.md)、[双日记](docs/diary-system.md)、[分条聊天](docs/qq-reply-style.md)、[源码发布](docs/open-source.md)。

## 验证范围

核心功能来自现有CPU部署。开源版加入通用配置、容器配方和源码导出：已用合成配置验证安装配置生成、配置保留，并在CPU机器隔离启动DSH与QQ桥；未登录账号、调用模型或发送消息。**尚未在全新机器完整构建Docker并扫码验收**。微信原部署也仍处于待扫码阶段，不把进程健康当作真实收发已验证。

## 来源与许可

新增代码使用[MIT](LICENSE)。微信自动化上游及其派生Docker配方是**GPL-3.0-or-later**，其他组件保留各自许可证，见[NOTICE](NOTICE.md)。源码不附带商业客户端安装目录、模型缓存或原部署者的账号数据。

部署依据：[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、[NapCat官方Docker](https://github.com/NapNeko/NapCat-Docker)、[Docker安装](https://docs.docker.com/engine/install/)、[wechat-ai](https://github.com/ChisBread/wechat-ai)。
