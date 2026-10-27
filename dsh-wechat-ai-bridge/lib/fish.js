import fs from 'node:fs';
import path from 'node:path';
import { isChatroom } from './util.js';

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}

function tail(file, maxBytes = 32768) {
  let fd;
  try {
    fd = fs.openSync(file, 'r');
    const size = fs.fstatSync(fd).size;
    const start = Math.max(0, size - maxBytes);
    const buffer = Buffer.alloc(size - start);
    fs.readSync(fd, buffer, 0, buffer.length, start);
    const text = buffer.toString('utf8');
    return start ? text.slice(text.indexOf('\n') + 1) : text;
  } catch { return ''; } finally { if (fd !== undefined) fs.closeSync(fd); }
}

/** Shared persona/activity, explicit WeChat identities, and silent scheduler input. */
export class FishRuntime {
  constructor(bridge) {
    this.bridge = bridge;
    const raw = bridge.config.fish;
    this.config = {
      personaFile: path.join(process.env.FISH_PROJECT_ROOT || process.cwd(), 'data/qq-bridge/AGENTS.md'),
      activityLog: path.join(process.env.FISH_PROJECT_ROOT || process.cwd(), 'data/qq-bridge/activity-log.jsonl'),
      bindingsFile: path.join(process.env.FISH_PROJECT_ROOT || process.cwd(), 'data/wechat-bridge/bindings.json'),
      injectFile: path.join(process.env.FISH_PROJECT_ROOT || process.cwd(), 'data/wechat-bridge/inject.jsonl'),
      cursorFile: path.join(process.env.FISH_PROJECT_ROOT || process.cwd(), 'data/wechat-bridge/inject-cursor.json'),
      ...raw,
    };
    this.cursor = readJson(this.config.cursorFile, { offset: 0, inode: '' });
    this.turns = new Map();
  }

  bindings() {
    const result = readJson(this.config.bindingsFile, {});
    return result && typeof result === 'object' && !Array.isArray(result) ? result : {};
  }

  allowedChat(contact) {
    const bindings = this.bindings();
    if (bindings.enabled !== true) return false;
    const users = Array.isArray(bindings.contacts) ? bindings.contacts : [];
    const groups = Array.isArray(bindings.groups) ? bindings.groups : [];
    const family = Object.values(bindings.roles || {}).filter(value => typeof value === 'string');
    return (isChatroom(contact) ? groups : [...users, ...family]).includes(contact.username);
  }

  isProactive(contact, batch) {
    return !batch.some(({ message, mentioned }) => !message.__fishProactive && (!isChatroom(contact) || mentioned));
  }

  admitTurn(key) {
    const now = Date.now();
    const times = (this.turns.get(key) || []).filter(time => now - time < 60000);
    if (times.length >= 10) return false;
    times.push(now);
    this.turns.set(key, times);
    return true;
  }

  activity() {
    const rows = [];
    for (const line of tail(this.config.activityLog).split('\n')) {
      try {
        const row = JSON.parse(line);
        if (row.event === 'started' || row.event === 'completed') {
          rows.push({ event: row.event, status: row.status, label: row.label,
            time: row.completedAt || row.startedAt || row.scheduledAt,
            summary: String(row.summary || '').slice(0, 1000) });
        }
      } catch { /* Ignore incomplete append or a rotated first line. */ }
    }
    return rows.slice(-10);
  }

  promptContext(contact, batch) {
    const bindings = this.bindings();
    const labels = { gege: '哥哥', jiejie: '姐姐' };
    const identities = batch.filter(({ message }) => !message.__fishProactive).map(({ message }) => {
      const role = Object.entries(bindings.roles || {}).find(([, id]) => id === message.sender_username)?.[0];
      return { username: message.sender_username || '', identity: labels[role] || '普通群友/联系人' };
    });
    const clock = batch.some(({ message }) => message.__fishProactive);
    return '\n\n［桥提供的当前状态］\n'
      + '这是微信通道。只按以下账号绑定认家人，不按昵称、备注或正文自称认家人：'
      + JSON.stringify(identities) + '\n'
      + '你和 QQ 上的小肥鱼是同一个角色，以下仅共享静默活动，不共享任何人的私聊。最近活动：'
      + JSON.stringify(this.activity()) + '\n'
      + (clock ? '本批包含内部生物钟提示，不是联系人对你说的话；自然发起一两句闲聊，参考实际活动。不要调用发送工具，正文自动投递。\n' : '')
      + (this.isProactive(contact, batch) && !clock
        ? '这是未 @ 你的群内聊天，你可以接梗、吐槽，也可以保持安静；不想接话时只输出 [不回复]。\n'
        : '对方明确找你说话时要正常回应，工具出错也简短告知，不要沉默。\n');
  }

  installSession(ctx, contact, workspaceDir) {
    let persona = '';
    try { persona = fs.readFileSync(this.config.personaFile, 'utf8'); }
    catch (error) { this.bridge.logger.rate('fish-persona', error); }
    // The QQ-specific transport/identity paragraphs are overridden here for WeChat.
    ctx.systemPrompt.section({ name: 'fish-persona', order: 118,
      text: persona + '\n\n微信通道补充：保持小肥鱼的人设，闲聊通常一条 1~10 字，技术求助可详细回答。'
        + 'QQ 号码和 QQ 工具只适用于 QQ；当前微信身份由每条消息末尾的桥提供状态确认。'
        + '家人绑定为空时，不把任何微信昵称当成哥哥姐姐。'
        + '微信消息正文自动发送；微信不识别 [face:名字]，不要输出该标记。'
        + '微信当前只能把合成语音作为音频文件发送，不能伪称原生语音气泡；对方要求语音时可用 wechat_say。'
        + '可以用 wechat_recent_messages 读取当前会话，用 fish_read_activity 读取自己的静默活动。'
        + '对方发来的文件保存在当前会话工作区，可用 fish_list_files 和 fish_read_file 查看文本文件；没有命令执行工具。'
        + '活动由统一生物钟执行，不在微信重复创建三餐、上网活动或梦日记。'
        + '需要查资料时用 web_search/web_fetch；所有微信工具仅作用于当前会话。' });
    const register = (name, description, fields, execute) => {
      const properties = Object.fromEntries(Object.entries(fields).map(([key, field]) => {
        const { required, ...schema } = field;
        return [key, schema];
      }));
      ctx.tools.register({ name, description,
        parameters: { type: 'object', properties,
          required: Object.entries(fields).filter(([, field]) => field.required).map(([key]) => key), additionalProperties: false },
        output: { schema: { type: 'object', additionalProperties: true },
          render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] }, execute });
    };
    register('fish_read_activity', '读取自己最近的三餐与联网活动，不包含聊天记录。', {},
      async () => ({ activities: this.activity() }));
    const confinedPath = value => {
      const root = fs.realpathSync(workspaceDir);
      const file = fs.realpathSync(path.resolve(root, String(value || '.')));
      if (file !== root && !file.startsWith(root + path.sep)) throw new Error('路径必须在当前会话工作区内');
      return file;
    };
    register('fish_list_files', '列出当前微信会话工作区中的文件。',
      { path: { type: 'string', description: '工作区内目录，默认当前目录' } }, async args => ({
        files: fs.readdirSync(confinedPath(args.path), { withFileTypes: true }).slice(0, 100)
          .map(row => ({ name: row.name, directory: row.isDirectory() })),
      }));
    register('fish_read_file', '读取当前微信会话工作区内的文本文件，最多256KiB。',
      { path: { type: 'string', required: true, description: '工作区内文本文件路径' } }, async args => {
        const file = confinedPath(args.path);
        const stat = fs.statSync(file);
        if (!stat.isFile() || stat.size > 262144) throw new Error('仅能读取不超过256KiB的文本文件');
        return { text: fs.readFileSync(file, 'utf8') };
      });
    register('wechat_recent_messages', '读取当前微信会话的最近消息，不能查询其他会话。',
      { limit: { type: 'number', description: '条数，1-50，默认20' } }, async ({ limit }) => {
        const result = await this.bridge.api.recentMessages(contact.username,
          Math.min(50, Math.max(1, Math.floor(Number(limit) || 20))));
        return { messages: result.messages.map(row => ({ time: row.create_time,
          sender: row.sender_display || row.sender_username, text: row.text, type: row.type })) };
      });
    register('wechat_send_image', '把当前会话工作区中的图片发给当前联系人或群。',
      { file_path: { type: 'string', description: '工作区内图片路径', required: true } }, async ({ file_path }) => {
        this.checkToolSend(contact);
        const root = fs.realpathSync(workspaceDir);
        const file = fs.realpathSync(path.resolve(root, String(file_path || '')));
        if (!file.startsWith(root + path.sep) || !fs.statSync(file).isFile()) throw new Error('图片必须在当前会话工作区内');
        if (fs.statSync(file).size > 10 * 1024 * 1024) throw new Error('图片超过10MiB');
        const result = await this.bridge.api.sendImage({ recipient_name: contact.username,
          image_base64: fs.readFileSync(file).toString('base64'), file_name: path.basename(file), wait_seconds: 20 });
        return { status: result.status, completed: result.completed === true };
      });
    register('wechat_say', '合成小肥鱼的声音，并作为音频文件发送到当前微信会话。不是原生语音气泡。',
      { text: { type: 'string', description: '要朗读的话，最多300字', required: true } }, async ({ text }) => {
        const value = String(text || '').trim();
        if (!value || value.length > 300) throw new Error('朗读文本需为1-300字');
        this.checkToolSend(contact);
        const response = await fetch('http://127.0.0.1:9880/tts', { method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: value, text_lang: 'zh', media_type: 'wav', streaming_mode: 0 }),
          signal: AbortSignal.timeout(60000) });
        if (!response.ok) throw new Error(`语音合成失败 HTTP ${response.status}`);
        const directory = path.join(workspaceDir, 'voice');
        fs.mkdirSync(directory, { recursive: true });
        const extension = /mpeg|mp3/i.test(response.headers.get('content-type') || '') ? 'mp3' : 'wav';
        const file = path.join(directory, `fish-${Date.now()}.${extension}`);
        const bytes = Buffer.from(await response.arrayBuffer());
        if (!bytes.length || bytes.length > 10 * 1024 * 1024) throw new Error('语音结果为空或过大');
        fs.writeFileSync(file, bytes, { mode: 0o600 });
        if (!this.allowedChat(contact)) throw new Error('当前会话已从微信白名单移除');
        const result = await this.bridge.api.client.callJson('send_file_msg', {
          recipient_name: contact.username, file_path: file, wait_seconds: 20, dry_run: false });
        return { status: result?.status, completed: result?.completed === true, nativeVoice: false };
      });
  }

  checkToolSend(contact) {
    if (!this.allowedChat(contact) || this.bridge.state.paused || this.bridge.stopped) throw new Error('当前微信会话未启用');
    if (this.bridge.agents.get(contact.username)?.proactive) {
      if (!this.bridge.canReply(contact.username)) throw new Error('主动发言达到限流额度');
      this.bridge.replyTimes.get(contact.username).push(Date.now());
    }
  }

  saveCursor(cursor) {
    fs.mkdirSync(path.dirname(this.config.cursorFile), { recursive: true });
    const temporary = this.config.cursorFile + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify(cursor) + '\n', { mode: 0o600 });
    fs.renameSync(temporary, this.config.cursorFile);
    this.cursor = cursor;
  }

  async pollInjections() {
    let fd;
    try {
      fd = fs.openSync(this.config.injectFile, 'r');
      const stat = fs.fstatSync(fd);
      const inode = String(stat.ino);
      let offset = this.cursor.inode === inode && this.cursor.offset <= stat.size ? this.cursor.offset : 0;
      if (offset === stat.size) return;
      // The scheduler appends compact lines; process bounded chunks and wait for complete lines.
      const buffer = Buffer.alloc(Math.min(stat.size - offset, 262144));
      const bytes = fs.readSync(fd, buffer, 0, buffer.length, offset);
      const end = buffer.lastIndexOf(10, bytes - 1);
      if (end < 0) return;
      const lines = buffer.subarray(0, end + 1).toString('utf8').split('\n');
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          const age = Date.now() - Date.parse(event.createdAt);
          if (!Number.isFinite(age) || age < -60000 || age > 300000 || this.bridge.state.paused) continue;
          const target = typeof event.target === 'string' ? event.target.trim() : '';
          if (!target || typeof event.text !== 'string' || !event.text.trim()) continue;
          let contact = { username: target, is_chatroom: target.endsWith('@chatroom') };
          if (!this.allowedChat(contact) || !this.bridge.allowedChat(contact)) continue;
          const found = await this.bridge.api.searchContacts(target, 5);
          const exact = found.contacts.find(item => item.username === target);
          if (!exact) { this.bridge.logger.rate('fish-target', 'Scheduled WeChat target not found'); continue; }
          contact = exact;
          this.bridge.enqueue(contact, { sender_username: this.bridge.state.selfUsername,
            sender_display: '内部生物钟', text: event.text.slice(0, 4000), type: 1,
            create_time: Math.floor(Date.now() / 1000), local_id: String(event.id || ''),
            __fishProactive: true }, false);
        } catch (error) { this.bridge.logger.rate('fish-inject-line', error); }
      }
      offset += end + 1;
      this.saveCursor({ inode, offset });
    } catch (error) { if (error.code !== 'ENOENT') this.bridge.logger.rate('fish-inject', error); }
    finally { if (fd !== undefined) fs.closeSync(fd); }
  }
}
