# 组件来源与许可

根目录 MIT LICENSE 覆盖本项目新增代码；不覆盖下表中另行授权的第三方代码、客户端、模型和服务。保留各子目录的原始 LICENSE 与作者署名。

| 组件 | 来源与版本 | 许可 / 分发方式 |
| --- | --- | --- |
| DeepSeek Harness | [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)，固定 npm `0.2.1-rc.2` | MIT；由 npm 安装 |
| QQ 桥 | [cheesehaqi/dsh-qq-onebot-bridge](https://github.com/cheesehaqi/dsh-qq-onebot-bridge)，本地扩展版 `0.6.16` | 原目录 MIT LICENSE；本地变更见 CHANGELOG |
| 微信 DSH 桥 | [Windfarer/dsh-wechat-ai-bridge](https://github.com/Windfarer/dsh-wechat-ai-bridge)，上游提交 `2516b699e10213df3c1ced2fa7c0c51a8b01044b` | MIT；本地变更见 LOCAL-CHANGES |
| Linux 微信自动化 | [ChisBread/wechat-ai](https://github.com/ChisBread/wechat-ai)，提交 `a1aa88c3d68f2dbe77709c51c8d2dcbe80189d97` | **GPL-3.0-or-later**；完整源码、LICENSE、CREDITS 保留在 `vendor/wechat-ai`；`deploy/Dockerfile.wechat` 由其构建配方改编，沿用 GPL |
| NapCat | [NapNeko/NapCat-Docker](https://github.com/NapNeko/NapCat-Docker) | 从上游拉取镜像；不在源码包中附带 QQ/NapCat 可执行安装目录 |
| Playwright | [microsoft/playwright-python](https://github.com/microsoft/playwright-python) | 按依赖包自身许可安装；浏览器另行下载 |
| faster-whisper | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT；公共模型从 Hugging Face 下载并遵循模型卡许可 |
| yt-dlp | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 按安装包附带的许可使用 |
| edge-tts | [rany2/edge-tts](https://github.com/rany2/edge-tts) | 按上游许可安装；音频合成使用在线服务 |
| SQLCipher | [sqlcipher/sqlcipher](https://github.com/sqlcipher/sqlcipher)，可选微信镜像编译 `4.6.1` | 按上游 BSD 风格许可；构建时获取源码并校验 SHA256 |

微信选装目录及其派生配方不能被改标成 MIT。QQ、微信的官方客户端和各在线服务保留各自权利与使用条款。发布本项目源码不包含任何实际账号、API Key、登录态、聊天记录或日记。
