# B站与省Token

工具：bili_feed、bili_search、bili_watch、bili_status、bili_comments、bili_comment、bili_reply。专用Chromium浏览器真实播放视频，账号由主人在专用桌面完成官方登录，不从聊天读取Cookie或凭据。

通常一次看30—45秒，默认45秒，允许12—90秒。保存实际区间，明确区分片段、全片和旧缓存，不依据标题编剧情。

1. 候选最多6条短标题/链接，不传完整HTML。
2. 优先片段字幕，否则CPU本地转写音轨，不消耗模型Token。
3. 最多4帧，有文字时用首尾2帧，拼一张小图，低分辨率处理。
4. 新片段只做一次非思考摘要，输出上限384Token，给聊天约260字，不传长转写或图片。
5. 成功结果缓存7天，暂不可理解的结果缓存5分钟；实际usage留在私有记录，不声称固定计费数。

ASR默认small，可在.env改FISH_ASR_MODEL=base。首次后台下载，失败稍后重试；期间可继续看抽样画面。自动转写可能误听，不能当逐字原话。

桌面默认http://127.0.0.1:6082/，远程访问走SSH。`bash fishctl bili status`查状态。API18160仅在应用共享网络回环可达，随机token鉴权。

`bili_comments`读取最多五条视频评论，每条最多附两条回复，返回精简文本和用于回复的编号。小肥鱼可以自己决定用`bili_comment`发表一级评论或用`bili_reply`回复刚读取的评论。评论属于公开内容；仅在已登录、功能开启且已有实际观看记录时允许提交。默认限制每天十六次、间隔120秒，同一视频24小时一次；失败或结果不明也计入限制，不自动重试。评论工具使用站点当前接口，接口变更、审核或风控可能导致无法读取、无法发表或发表后不显示；账号验证需要主人处理。评论内容不会额外触发模型请求，也不向 QQ 发送通知。点赞和动态发帖未接入。

公开评论默认关闭。部署者确认账号与公开发表范围后运行`bash fishctl bili comments-enable`开启，`bash fishctl bili comments-disable`随时关闭；`bash fishctl bili status`查看开关和登录状态。开关保存在私有B站数据目录，不能加入发布包。

`bili_profile`查看自己的公开昵称和签名；`bili_profile_update`可修改其一。`bili_avatar_options`列出专用头像目录中的候选图片，`bili_avatar_make`可用本地绘图制作简单的小鱼图标，`bili_avatar_set`提交候选图片作为头像。内置图标不是AI生图；也可把希望公开使用的PNG/JPEG放在`data/app/bilibili/avatars`目录。图片会裁成正方形并移除元数据，不自动使用聊天或日记图片。

资料修改默认关闭，`bash fishctl bili profile-enable`开启，`bash fishctl bili profile-disable`关闭。每类资料24小时最多尝试一次；账号中心可能要求验证、审核，修改昵称可能消耗B站硬币。工具只报告提交结果，无法保证审核通过；结果不明时不会自动重试。资料使用B站账号中心网页流程，页面变化可能使操作失败。

社交工具包括 `bili_creator`、`bili_user_search`、`bili_replies`、`bili_followings`、`bili_followers`、`bili_creator_videos`、`bili_follow`、`bili_sessions`、`bili_dm_read` 和 `bili_dm_send`。可获取视频作者、搜索用户、查看“回复我的”消息、查看已关注用户及其视频、查看自己的粉丝、关注作者、阅读及发送文字私信。私信、关注默认关闭，部署者可用 `bash fishctl bili social-enable` 开启、`social-disable` 关闭。开启后后台约每三分钟查询一次未读会话元数据；有新私信才创建处理回合，不为轮询发起模型请求。活动摘要不保存私信内容。回复对方主动来信不受主动聊天频率限制，针对同一条来信防止重复回复；主动私信及主动关注分别每天最多十二次、间隔至少60秒。接口返回失败或结果未知不会自动重试。平台权限、验证或风控可能阻止互动。

参考：[Playwright](https://playwright.dev/python/docs/browsers)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/)。
