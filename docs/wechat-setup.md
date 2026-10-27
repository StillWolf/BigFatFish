# 可选Linux微信

`bash install.sh --wechat`安装独立官方客户端、桌面与wechat-ai MCP；QQ不依赖微信登录。x86_64/ARM64由构建架构选择客户端。

首次下载客户端、CPU视觉依赖并编译独立SQLCipher4.6.1，比QQ组件构建更久。源码标签固定并校验SHA256，不替换宿主系统库。

桌面http://127.0.0.1:6081/，用户名fish，随机密码通过 `bash fishctl access --show-secrets` 查看。扫码确认后：

```bash
bash fishctl wechat contacts '准确备注'
bash fishctl wechat role gege wxid_example
bash fishctl wechat allow wxid_friend
bash fishctl wechat group 'example@chatroom'
bash fishctl wechat target group 'example@chatroom'
bash fishctl wechat resume
```

默认暂停且准入为空。allow为联系人准入，group为群准入，role为家人，target为主动目标；昵称不建立身份。绑定文件data/app/wechat-bridge/bindings.json可热更新。

QQ/微信会话隔离，共用人设和生活活动。私聊和群内@免主动额度。可以发音频文件，未声称支持原生微信语音气泡。

该通道仍是实验性组件：原部署待扫码，新容器路线只做静态检查；登录后的数据库、真实收发与媒体需要部署者自己确认。运行数据在data/app/wechat-runtime/config，MCP8000不对宿主发布。

为读取同容器内微信进程的数据库密钥，容器启用SYS_PTRACE与独立seccomp设置，不使用宿主PID命名空间。

上游与许可见[NOTICE](../NOTICE.md)、vendor/wechat-ai/LOCAL-DEPLOYMENT.md和dsh-wechat-ai-bridge/LOCAL-CHANGES.md。
