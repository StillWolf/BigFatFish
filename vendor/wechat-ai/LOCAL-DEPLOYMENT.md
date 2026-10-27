# 本项目使用的上游版本

- 来源：https://github.com/ChisBread/wechat-ai
- 提交：`a1aa88c3d68f2dbe77709c51c8d2dcbe80189d97`
- 上游许可：GPL-3.0-or-later，保留本目录的 LICENSE 与 CREDITS.md。
- 下载归档 SHA256：`0d9bf382b665ec4f562d175fb904be207fd9b80164bfe6a8628a84d9aff55df4`

CPU 服务器使用原生 ARM64 微信、Xvfb/Openbox、独立 Python 3.12 venv。
上游 `sqlcipher3-binary==0.6.0` 没有可用的 ARM64 wheel，因此用本地编译的
SQLCipher 4.6.1 与链接该库的 `sqlcipher3` 替代；其余 Python 依赖按上游 requirements.txt 安装。
编译库安装到微信运行目录，不替换系统 SQLCipher，也不修改 QQ 的 Python/Node 环境。

选装时由 `deploy/Dockerfile.wechat` 构建独立镜像，运行数据在私有的 data 目录。
客户端与 MCP 由项目 `scripts/wechat-runtime.py` 管理；配置和凭据在运行目录中，不存入仓库。
