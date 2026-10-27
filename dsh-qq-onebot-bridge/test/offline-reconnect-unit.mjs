/**
 * 断线恢复与主动回合保护：所有连接和模型调用均使用本地 mock。
 *
 * 同步阶段由 OneBotServer 的 dry-run 覆盖；真正危险的是**异步的 agent 回合**——
 * dry-run 窗口在 `#handleInjection` 结束时关掉，模型几秒后才回话，那条回复如果
 * 没人拦就会真的发出去（真机测试抓到过：注入触发了一轮真实模型回答）。
 *
 * 这里用 mock DSH 上下文把整条链路跑起来，驱动四种时序：
 *   ① 注入消息 + 模型回话 → 出站必须为空，且事件流里有"注入回合的模型回复已被拦截"
 *   ② 注入之后的**真人消息** → 必须恢复正常发送（不能被注入标记连坐）
 *   ③ 注入回合模型报错（没有 assistant/message）→ 记账要清掉，后续真人回复照常
 *   ④ 连续两次注入 → 两次回复都被拦下，不会漏掉第二次
 */
import { EventEmitter } from 'node:events'
import { appendFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { Config } from '../lib/index.js'
import { QQBridge } from '../lib/bridge.js'

let passed = 0
let failed = 0
function check(name, ok, extra = '') {
  if (ok) { passed++; console.log('PASS', name, extra) }
  else { failed++; console.log('FAIL', name, extra) }
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

class StubServer extends EventEmitter {
  constructor({ dryRun = false } = {}) {
    super()
    this.sent = []
    this.socket = { readyState: 1, OPEN: 1, send() {}, close() {} }
    this.dryRun = dryRun
    this.dryRunCalls = []
  }
  setDryRun(enabled, scope = null) {
    const previous = { enabled: this.dryRun, scope: this.dryRunScope ?? null }
    this.dryRun = enabled === true
    this.dryRunScope = this.dryRun && scope ? { ...scope } : null
    if (this.dryRun) this.dryRunCalls = []
    return previous
  }
  /** 只有命中作用域的调用才被拦（与 lib/onebot.js 的 #inDryRunScope 一致）。 */
  #inScope(params) {
    if (!this.dryRun) return false
    if (!this.dryRunScope) return true
    const { groupId = 0, userId = 0 } = this.dryRunScope
    if (groupId && Number(params?.group_id) === Number(groupId)) return true
    if (userId && Number(params?.user_id) === Number(userId)) return true
    return false
  }
  sendSegments(_bot, messageType, targetId, segments) {
    const params = messageType === 'group' ? { group_id: targetId, message: segments } : { user_id: targetId, message: segments }
    if (this.#inScope(params)) {
      this.dryRunCalls.push({ action: messageType === 'group' ? 'send_group_msg' : 'send_private_msg', params })
      return Promise.resolve({ message_id: `dry-${this.dryRunCalls.length}`, dryRun: true })
    }
    this.sent.push({ messageType, targetId, text: segments.map((segment) => segment.data?.text ?? '').join('') })
    return Promise.resolve({ message_id: `mid${this.sent.length}` })
  }
  takeDryRunCalls() { const calls = this.dryRunCalls.slice(); this.dryRunCalls = []; return calls }
  sendForwardMsg() { this.sent.push({ messageType: 'forward', targetId: 0, text: '[合并转发]' }); return Promise.resolve({ message_id: 'fwd1' }) }
  currentSocket() { return this.socket }
  async stop() {}
}

/**
 * mock DSH 上下文：`reply` 决定模型这一回合怎么回应（文本 / 报错 / 不回话）。
 * `emit` 让测试能精确控制"什么时候回话"，从而制造注入窗口关闭后才回话的时序。
 */
function makeCtx({ createDelayMs = 0 } = {}) {
  const handlers = new Map()
  const records = new Map()
  const registeredTools = []
  const emit = (sessionId, event) => {
    for (const handler of handlers.get('session/event') ?? []) handler({ id: sessionId }, event)
  }
  const build = async (sessionId, options) => {
    // 模拟真实宿主建会话的耗时：用来制造"注入派发仍在进行"的窗口
    if (createDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, createDelayMs))
    const record = { followups: [], sections: 0, tools: 0 }
    const agentCtx = {
      systemPrompt: { section: () => { record.sections += 1 } },
      tools: { guard: () => {}, register: (tool) => { record.tools += 1; registeredTools.push(tool); return tool } },
    }
    if (options.setup) await options.setup(agentCtx)
    record.sessionId = String(sessionId)
    const agent = {
      id: String(sessionId),
      status: 'idle',
      followup: (message) => {
        record.followups.push((message.content ?? []).map((block) => block.text ?? '').join(''))
      },
      cancel: () => {},
    }
    records.set(String(sessionId), record)
    return { agent, dispose: async () => {} }
  }
  const ctx = {
    on: (event, handler) => {
      if (!handlers.has(event)) handlers.set(event, new Set())
      handlers.get(event).add(handler)
      return () => handlers.get(event)?.delete(handler)
    },
    get: () => undefined,
    agents: {
      create: async ({ sessionId, setup }) => build(sessionId ?? `qq-mock-${records.size + 1}`, { setup }),
      resume: async ({ resumeSessionId, setup }) => build(resumeSessionId ?? `qq-mock-r${records.size + 1}`, { setup }),
    },
    agentDefaultModel: { currentSelection: () => ({}) },
  }
  return { ctx, emit, records, tools: registeredTools }
}

const dir = mkdtempSync(join(tmpdir(), 'qq-inject-guard-'))
const injectFile = join(dir, 'qq-inject.jsonl')
const config = Config({
  cwd: dir,
  allowUsers: [1001],
  allowGroups: [2002],
  botQq: 999,
  adminUsers: [1001],
  sessionMode: 'chat',
  sessionResumeEnabled: false,
  actionAuditEnabled: false,
  memoryEnabled: true,
  ttsEnabled: false,
  sttEnabled: false,
  notifyEnabled: false,
  traceEnabled: true,
  traceLevel: 'debug',
  recordInbound: false,
  // 走真实注入通道：注入只在会话空闲时投递（这是"记账不错位"的前提）
  injectEnabled: true,
  injectFile,
  injectIntervalMs: 500,
  injectDryRun: true,
})
config.injectDryRun = true

/** 追加一行到注入队列（模拟控制台写入）。 */
function queueInjection(spec) {
  appendFileSync(injectFile, `${JSON.stringify(spec)}\n`, 'utf8')
}

/** 轮询等待一个条件成立。 */
async function waitFor(predicate, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (predicate()) return true
    await sleep(80)
  }
  return predicate()
}

const server = new StubServer()
const activeSocket = server.socket
server.socket = null
server.getStatus = async () => ({ online: true, good: true })
const mock = makeCtx()
const bridge = new QQBridge(mock.ctx, config, server, { info() {}, warn() {}, error() {} })
bridge.start()
const followups = () => [...mock.records.values()].flatMap((record) => record.followups)

try {
  // A real scheduled QQ message must not start a model turn while disconnected.
  queueInjection({ kind: 'message', userId: 1001, groupId: 2002, atMe: true, text: '离线主动', proactive: true, dryRun: false })
  check('离线主动提示已消费', await waitFor(() => bridge.injectConsumed >= 1))
  check('离线主动提示没有创建模型会话', mock.records.size === 0)
  check('离线主动提示没有出站', server.sent.length === 0)

  // Dry-run remains useful without any live transport.
  queueInjection({ kind: 'message', userId: 1001, groupId: 2002, atMe: true, text: '离线干跑', dryRun: true })
  check('离线干跑仍可调用模拟模型', await waitFor(() => followups().some((text) => text.includes('离线干跑'))))
  const session = bridge.sessions.get('g:2002')
  check('离线会话最初没有连接', session?.route.bot == null)

  server.socket = activeSocket
  server.emit('bot-connect', activeSocket)
  check('重新连接查询实际在线状态', await waitFor(() => bridge.botOnline === true))
  check('重新连接修复会话和工具共享的路由', session.route.bot === activeSocket)

  // A live inbound message also rebinds an existing stale route.
  session.route.bot = null
  server.emit('message', { bot: activeSocket, messageType: 'group', groupId: 2002, userId: 1001,
    text: '模拟真人请求', atMe: true, ats: [999], senderName: '模拟用户', messageId: 'fake-live-1',
    records: [], images: [], files: [], forwards: [], reply: null, raw: { message: [] } })
  check('真人消息继续进入模型', await waitFor(() => followups().some((text) => text.includes('模拟真人请求'))))
  check('真人消息恢复路由连接', session.route.bot === activeSocket)

  queueInjection({ kind: 'message', userId: 1001, groupId: 2002, atMe: true, text: '在线主动', proactive: true, dryRun: false })
  check('在线主动聊天仍能运行', await waitFor(() => followups().some((text) => text.includes('在线主动'))))
  check('模拟回合未发送任何QQ消息', server.sent.length === 0)

  server.socket = null
  server.emit('bot-disconnect', activeSocket)
  check('断开连接及时标记离线', bridge.botOnline === false)
  queueInjection({ kind: 'activity', id: 'mock-meal', activityType: 'meal', label: '早餐',
    scheduledAt: new Date().toISOString(), text: '模拟内部饭点' })
  check('离线时内部活动仍然运行', await waitFor(() => followups().some((text) => text.includes('模拟内部饭点'))))

  let resolveProbe
  server.getStatus = () => new Promise((resolve) => { resolveProbe = resolve })
  server.socket = activeSocket
  server.emit('bot-connect', activeSocket)
  server.socket = null
  server.emit('bot-disconnect', activeSocket)
  resolveProbe({ online: true })
  await sleep(30)
  check('过期的状态响应不会覆盖后来的断线', bridge.botOnline === false)
} finally {
  bridge.stop()
  await sleep(50)
  rmSync(dir, { recursive: true, force: true })
}
console.log(`结果：${passed} 通过，${failed} 失败`)
if (failed > 0) process.exitCode = 1
