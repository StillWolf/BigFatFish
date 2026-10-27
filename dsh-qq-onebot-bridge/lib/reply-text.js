/**
 * 出站正文清理（[大肥鱼补丁] 内心戏过滤）。
 *
 * reasoning 块在读取 assistant/message 时本就被丢掉；可有时模型在正文(text)里
 * 接着写“下一步该怎么调工具”这类英文筹划，于是跟着回复一起发进 QQ。
 * 这里只删**尾巴上**这种段落：中英混排、像英文行动筹划、而非代码块或纯英文回复。
 */

const CJK = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/
const PLANNING = /\b(?:let me|i(?:'ll|'m|'ve| should| need| want| think| will| can| could| would| might| must| better)|we(?:'ll|'re|'ve| should| need| can)|the user|the message|the reply|tool call|tool result|tool output|next (?:step|action)|use (?:the )?(?:tool|qq_|bash|react|poke|face|send)|qq_[a-z_]+|maybe|perhaps|actually|alternatively|hmm|wait|careful|note that|follow[- ]?up|respond|send (?:a|the|him|her|them)|check (?:the|if|whether)|need to|should (?:be|use|send|call|check|have))\b/i

const cjkCount = (text) => (text.match(CJK) || []).length
const latinCount = (text) => (text.match(/[A-Za-z]/g) || []).length

/** 一段疑似漏出来的英文筹划：够长、够英文、够像“下一步要做什么”。 */
function looksInternal(part) {
  const text = String(part ?? '').trim()
  if (text === '' || text.startsWith('```')) return false
  if (text.length < 12) return false
  const latin = latinCount(text)
  if (latin < 10) return false
  const cjk = cjkCount(text)
  // 中文为主的段落不删；漏出来的筹划以英文为主，偶尔夹几个中文词。
  if (cjk > 0 && latin < cjk * 5) return false
  if (text.split(/\s+/).filter(Boolean).length < 3) return false
  return PLANNING.test(text)
}

/**
 * 删掉一条回复尾部漏出来的英文筹划段。
 * 整条都是纯英文时不猜（无法区分正经英文回复），保持原样。
 * @param {string} text 模型给这条回复的正文
 * @returns {string} 可发送的正文
 */
export function stripInternalMonologue(text) {
  if (typeof text !== 'string') return text
  const trimmed = text.trim()
  if (trimmed === '') return trimmed
  const paragraphs = trimmed.split(/\n{2,}/)
  if (!paragraphs.some((paragraph) => CJK.test(paragraph))) return trimmed
  const kept = paragraphs.slice()
  while (kept.length > 1 && looksInternal(kept[kept.length - 1])) kept.pop()
  // 漏出来的筹划也可能贴在最后一段末尾，单独一行。
  const last = kept[kept.length - 1]
  const lines = last.split('\n')
  while (lines.length > 1 && looksInternal(lines[lines.length - 1])) lines.pop()
  kept[kept.length - 1] = lines.join('\n')
  return kept.join('\n\n').trim()
}

/** Model-authored bubble boundaries; ordinary paragraphs and code stay intact. */
export function parseReplyPresentation(value) {
  const lines = String(value ?? '').replace(/\r\n?/g, '\n').split('\n')
  const outside = []
  let fence = null
  for (const line of lines) {
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line)
    outside.push(fence === null && marker === null)
    if (marker && fence === null) fence = { char: marker[1][0], length: marker[1].length }
    else if (marker && marker[1][0] === fence?.char && marker[1].length >= fence.length && marker[2].trim() === '') fence = null
  }
  let last = lines.length - 1
  while (last >= 0 && lines[last].trim() === '') last -= 1
  const sticker = last >= 0 && outside[last] ? /^ {0,3}\[sticker:([^\]\r\n]{1,80})\]\s*$/.exec(lines[last]) : null
  const stickerName = sticker ? sticker[1].trim() : ''
  if (sticker) lines[last] = ''
  const chunks = ['']
  for (let i = 0; i < lines.length; i += 1) {
    if (outside[i] && /^ {0,3}\[next\]\s*$/.test(lines[i])) chunks.push('')
    else chunks[chunks.length - 1] += lines[i] + '\n'
  }
  const nonempty = chunks.map((chunk) => chunk.trim()).filter(Boolean)
  // Preserve overflow instead of silently dropping a technical answer.
  const parts = nonempty.length <= 3 ? nonempty : [...nonempty.slice(0, 2), nonempty.slice(2).join('\n\n')]
  return { parts, text: parts.join('\n\n'), stickerName }
}
