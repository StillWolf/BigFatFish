#!/usr/bin/env node
// Local operator utility. It never sends messages or changes the QQ profile.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { McpClient } from '../dsh-wechat-ai-bridge/lib/mcp-client.js';
import { WechatApi } from '../dsh-wechat-ai-bridge/lib/wechat-api.js';
import { resolveToken } from '../dsh-wechat-ai-bridge/lib/util.js';

const root = process.env.FISH_PROJECT_ROOT || fileURLToPath(new URL('../', import.meta.url));
const filename = path.join(root, 'data/wechat-bridge/bindings.json');
const [command = 'status', ...args] = process.argv.slice(2);
const logger = { rate() {}, info() {}, warn() {}, error() {} };
const readBindings = () => JSON.parse(fs.readFileSync(filename, 'utf8'));
const saveBindings = value => {
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  if (fs.existsSync(filename)) fs.copyFileSync(filename, filename + '.bak');
  fs.writeFileSync(filename + '.tmp', JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  fs.renameSync(filename + '.tmp', filename);
};
const requireId = value => {
  if (!value || !/^[A-Za-z0-9_@.\-]+$/.test(value)) throw new Error('请提供准确微信 username 或群 ID，不使用昵称代替');
  return value;
};

let client;
try {
  if (['status', 'contacts'].includes(command)) {
    client = new McpClient({ url: process.env.FISH_WECHAT_MCP_URL || 'http://127.0.0.1:18100/mcp',
      token: resolveToken({ tokenFile: path.join(process.env.FISH_WECHAT_RUNTIME || path.join(root, 'data/wechat-runtime'), 'runtime.env') }), timeoutMs: 15000, logger });
    const api = new WechatApi(client);
    if (command === 'status') {
      const status = await api.runtimeStatus();
      console.log(JSON.stringify({ database: status.database, services: status.services,
        bindings: readBindings() }, null, 2));
    } else {
      const contacts = args.length
        ? (await api.searchContacts(args.join(' '), 50)).contacts
        : (await api.recentChats(50)).chats.map(row => row.contact);
      console.log(JSON.stringify(contacts.map(row => ({ username: row.username,
        name: row.display_name || row.nick_name, remark: row.remark, is_chatroom: row.is_chatroom })), null, 2));
    }
  } else {
    const data = readBindings();
    if (command === 'allow' || command === 'group') {
      const key = command === 'allow' ? 'contacts' : 'groups';
      const id = requireId(args[0]);
      if (command === 'group' && !id.endsWith('@chatroom')) throw new Error('群 ID 必须以 @chatroom 结尾');
      data[key] = [...new Set([...(data[key] || []), id])];
    } else if (command === 'role') {
      if (!['gege', 'jiejie'].includes(args[0])) throw new Error('role 只支持 gege 或 jiejie');
      data.roles = { ...data.roles, [args[0]]: requireId(args[1]) };
    } else if (command === 'target') {
      if (!['gege', 'jiejie', 'group'].includes(args[0])) throw new Error('target 只支持 gege、jiejie、group');
      data.targets = { ...data.targets, [args[0]]: [...new Set([...(data.targets?.[args[0]] || []), requireId(args[1])])] };
    } else if (command === 'remove') {
      const id = requireId(args[0]);
      for (const key of ['contacts', 'groups']) data[key] = (data[key] || []).filter(value => value !== id);
      data.roles = Object.fromEntries(Object.entries(data.roles || {}).filter(([, value]) => value !== id));
      data.targets = Object.fromEntries(Object.entries(data.targets || {}).map(([key, values]) => [key, (Array.isArray(values) ? values : [values]).filter(value => value !== id)]));
    } else if (command === 'pause' || command === 'resume') data.enabled = command === 'resume';
    else throw new Error('用法: status | contacts [关键词] | allow <username> | group <群ID> | role gege|jiejie <username> | target gege|jiejie|group <ID> | remove <ID> | pause | resume');
    saveBindings(data);
    console.log('微信绑定配置已保存，自动生效');
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  client?.close();
}
