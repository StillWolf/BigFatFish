# 参与开发

1. 从 `config/fish.example.json` 创建自己的私有配置，用独立机器人账号开发。
2. 代码改动分别落在 QQ 桥、微信桥、运行脚本或部署目录；上游派生代码保留原始署名和许可。
3. 不提交 `.env`、`data/`、二维码、浏览器 profile、客户端安装文件、模型缓存或真实聊天样本。问题示例使用虚构账号。
4. 检查修改的 Python/JavaScript/Shell 语法；涉及平台动作时说明是否实际发送过消息，不用真实群聊做无授权验证。
5. 发布源码使用 `bash fishctl release`，生成的包带文件清单及校验和。修改镜像或 SDK 版本时同步说明兼容范围。

运行时角色在 `config/persona.md`；开发约定在根目录 `AGENTS.md`。源码整理不会自动改动既有服务器上的部署。

离线回归检查（使用本地模拟，不登录账号、不发送平台消息）：

```bash
python3 -m unittest discover -s tests -p 'test_configuration.py' -v
node dsh-qq-onebot-bridge/test/offline-reconnect-unit.mjs
```

第二条需要先安装项目Node依赖；第一条需要PyYAML（应用镜像已安装）。完整容器构建和真实平台登录属于单独的部署验收。
