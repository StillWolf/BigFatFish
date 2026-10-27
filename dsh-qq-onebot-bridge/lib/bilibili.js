import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { defineTool } from '@deepseek-ai/dsh-tools'

function token() {
  const source = readFileSync(join(process.env.FISH_BILIBILI_ROOT || join(process.env.FISH_PROJECT_ROOT || fileURLToPath(new URL('../../', import.meta.url)), 'data/bilibili'), 'runtime.env'), 'utf8')
  const value = /^BILIBILI_TOKEN=(.+)$/m.exec(source)?.[1]?.trim()
  if (!value) throw new Error('B站浏览器尚未配置')
  return value
}

async function call(action, args = {}) {
  let response
  try {
    response = await fetch(`${(process.env.FISH_BILIBILI_URL || 'http://127.0.0.1:18160').replace(/\/$/, '')}/api/${action}`, {
      method: 'POST', headers: { Authorization: 'Bearer ' + token(), 'Content-Type': 'application/json' },
      body: JSON.stringify(args), signal: AbortSignal.timeout(action === 'watch' ? 285000 : 75000),
    })
  } catch (error) {
    throw new Error(`B站浏览器暂不可用：${error.name === 'TimeoutError' ? '操作超时' : '连接失败'}`)
  }
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.error || `B站浏览器 HTTP ${response.status}`)
  return result
}

function compactWatch(result) {
  return { title: result.title, url: result.url, watched: result.watched,
    ...(result.part > 1 ? { part: result.part } : {}),
    summary: String(result.summary || '').slice(0, 280), cached: result.cached,
    watchedAt: result.watchedAt,
    limitations: result.limitations, textSource: result.textSource }
}

export function registerBilibiliTools(ctx, { blocked = () => false } = {}) {
  const register = (name, description, parameters, execute) => ctx.tools.register(defineTool({
    name, description, parameters,
    output: { schema: { type: 'object', additionalProperties: false,
      properties: { data: { type: 'string', required: true } } },
      render: (_args, result) => [{ type: 'text', text: result.data }] },
    async execute(args) {
      if (blocked()) throw new Error('当前为调试或已停止的回合，不访问真实 B站')
      return { data: JSON.stringify(await execute(args)) }
    },
  }))
  register('bili_feed', 'List up to six real Bilibili popular videos: short titles, URLs and previouslyWatched flags.',
    { limit: { type: 'number', description: 'How many titles, 1-6; default 5.' } },
    args => call('feed', { limit: Math.max(1, Math.min(6, Number(args.limit) || 5)) }))
  register('bili_search', 'Search real Bilibili videos, returning up to six short titles and URLs. Use bili_watch to actually watch.',
    { query: { type: 'string', description: 'A short search phrase about what you want to watch.' },
      limit: { type: 'number', description: '1-6 results; default 5.' } },
    args => call('search', { query: String(args.query || '').trim().slice(0, 100), limit: Math.max(1, Math.min(6, Number(args.limit) || 5)) }))
  register('bili_watch', 'Play a real video clip; return a compact cached summary from local subtitles/ASR and sampled frames. Claims cover only the observed interval; cached means past viewing. No posts or QQ messages.',
    { video: { type: 'string', description: 'BV id or https://www.bilibili.com/video/BV… URL.' },
      seconds: { type: 'number', description: 'Playback seconds, 12-90; default 45. Usually 30-45 is enough to browse.' },
      start: { type: 'number', description: 'Start position in seconds; default 0.' } },
    async args => compactWatch(await call('watch', { video: String(args.video || '').trim(),
      seconds: Math.max(12, Math.min(90, Number(args.seconds) || 45)), start: Math.max(0, Math.min(7200, Number(args.start) || 0)) })))
  register('bili_status', 'Get current/last viewing and browser login status; no credentials.', {},
    async () => {
      const result = await call('status')
      return { ready: result.ready, loggedIn: result.loggedIn, current: result.current,
        lastWatch: result.lastWatch ? compactWatch(result.lastWatch) : null, commentsAvailable: false }
    })
}
