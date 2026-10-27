# B站与省Token

工具：bili_feed、bili_search、bili_watch、bili_status。专用Chromium浏览器真实播放视频，游客可看实际可播放的公开视频；账号由主人在专用桌面完成官方登录，不从聊天读取Cookie或凭据。

通常一次看30—45秒，默认45秒，允许12—90秒。保存实际区间，明确区分片段、全片和旧缓存，不依据标题编剧情。

1. 候选最多6条短标题/链接，不传完整HTML。
2. 优先片段字幕，否则CPU本地转写音轨，不消耗模型Token。
3. 最多4帧，有文字时用首尾2帧，拼一张小图，低分辨率处理。
4. 新片段只做一次非思考摘要，输出上限384Token，给聊天约260字，不传长转写或图片。
5. 成功结果缓存7天，暂不可理解的结果缓存5分钟；实际usage留在私有记录，不声称固定计费数。

ASR默认small，可在.env改FISH_ASR_MODEL=base。首次后台下载，失败稍后重试；期间可继续看抽样画面。自动转写可能误听，不能当逐字原话。

桌面默认http://127.0.0.1:6082/，远程访问走SSH。`bash fishctl bili status`查状态。API18160仅在应用共享网络回环可达，随机token鉴权。

目前仅观看，没有评论/点赞/发帖工具。静默活动不发QQ消息，实际观看记录供日记参考。

参考：[Playwright](https://playwright.dev/python/docs/browsers)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)、[yt-dlp](https://github.com/yt-dlp/yt-dlp)、[DeepSeek API](https://api-docs.deepseek.com/api/create-chat-completion/)。
