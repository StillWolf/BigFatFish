import { appendFileSync, existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync } from 'node:fs'
import { join, resolve, sep } from 'node:path'

export const DIARY_FAMILY = new Set(String(process.env.FISH_DIARY_FAMILY_QQ || '').split(',').map(Number).filter((id) => Number.isSafeInteger(id) && id > 0))
const DAY_FILE = /^\d{4}-\d{2}-\d{2}\.md$/

export function beijingDate(now = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
}

export class DiaryStore {
  constructor(cwd, privateRoot) {
    this.sharedRoot = join(cwd, 'diary-shared')
    this.momentsFile = join(cwd, 'diary-moments.jsonl')
    this.privateRoot = privateRoot
  }

  canRead(route) {
    return route?.messageType === 'private' && DIARY_FAMILY.has(Number(route.targetId))
  }

  guardArguments(execution, route) {
    let text = ''
    try { text = JSON.stringify(execution?.arguments ?? {}) } catch { return '工具参数不可用于日记访问校验' }
    if (text.includes('fish-private-diary') || text.includes(this.privateRoot)) {
      return '私密日记只供内部独处回顾，聊天工具不能读取、搜索、导出或分享。'
    }
    if (!this.canRead(route) && (text.includes('diary-shared') || text.includes(this.sharedRoot))) {
      return '可分享日记仅供哥哥姐姐在各自私聊中查看。'
    }
  }

  dates(limit = 30) {
    if (!existsSync(this.sharedRoot)) return []
    return readdirSync(this.sharedRoot, { withFileTypes: true })
      .filter(row => row.isFile() && !row.isSymbolicLink() && DAY_FILE.test(row.name))
      .map(row => row.name.slice(0, -3)).sort().reverse().slice(0, limit)
  }

  read(day = '') {
    const selected = String(day || this.dates(1)[0] || '')
    const parsed = new Date(selected + 'T00:00:00Z')
    if (!/^\d{4}-\d{2}-\d{2}$/.test(selected)
      || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== selected) {
      throw new Error(selected ? '日期格式应为 YYYY-MM-DD' : '还没有写好的日记')
    }
    const file = join(this.sharedRoot, selected + '.md')
    if (!existsSync(file)) throw new Error('这天还没有写好的日记')
    if (lstatSync(file).isSymbolicLink() || realpathSync(file) !== join(realpathSync(this.sharedRoot), selected + '.md')) {
      throw new Error('日记文件不可用')
    }
    return { date: selected, content: readFileSync(file, 'utf8').slice(0, 8500) }
  }

  isPrivatePath(raw) {
    const file = existsSync(raw) ? realpathSync(raw) : resolve(raw)
    const root = resolve(this.privateRoot)
    return file === root || file.startsWith(root + sep)
  }

  canSend(route, raw) {
    if (this.isPrivatePath(raw)) return false
    const file = existsSync(raw) ? realpathSync(raw) : resolve(raw)
    const root = existsSync(this.sharedRoot) ? realpathSync(this.sharedRoot) : resolve(this.sharedRoot)
    return !(file === root || file.startsWith(root + sep)) || this.canRead(route)
  }

  note(text, category = 'fun') {
    const value = String(text || '').trim()
    if (!value || value.length > 600) throw new Error('请用1到600字记下自己的见闻')
    if (/Bearer\s+|\bsk-[A-Za-z0-9_-]{10,}|\/(?:home|root|etc|proc)\//i.test(value)) {
      throw new Error('只记录自己的生活见闻，不记录凭据或机器信息')
    }
    mkdirSync(resolve(this.momentsFile, '..'), { recursive: true, mode: 0o700 })
    appendFileSync(this.momentsFile, JSON.stringify({ date: beijingDate(), at: new Date().toISOString(),
      category: ['important', 'fun', 'daily'].includes(category) ? category : 'fun', text: value }) + '\n',
      { encoding: 'utf8', mode: 0o600 })
    return { saved: true }
  }
}
