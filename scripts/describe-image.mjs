#!/usr/bin/env node
// 大肥鱼的看图工具：把本地图片交给 deepseek-flash 视觉模型，输出文字描述。
// 用法：node describe-image.mjs <图片路径> [补充问题]
// 依赖：DEEPSEEK_API_KEY 环境变量；GIF 首帧转换用到 ~/.dsh/profiles 里的 sharp。
import fs from 'node:fs'
import path from 'node:path'

const [file, ...question] = process.argv.slice(2)
if (!file) { console.error('用法: node describe-image.mjs <图片路径> [补充问题]'); process.exit(1) }
if (!fs.existsSync(file)) { console.error(`图片不存在: ${file}`); process.exit(1) }

const apiKey = process.env.DEEPSEEK_API_KEY
if (!apiKey) { console.error('缺 DEEPSEEK_API_KEY 环境变量'); process.exit(1) }

let imagePath = file
const lower = file.toLowerCase()
// GIF/动图：sharp 抽第一帧转 PNG（模型对动图支持不稳）
if (lower.endsWith('.gif')) {
  try {
    const { createRequire } = await import('node:module')
    const require2 = createRequire(path.join(process.env.HOME, '.dsh/profiles/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js'))
    const sharp = require2('sharp')
    const out = file.replace(/\.gif$/i, '') + '-frame.png'
    if (!fs.existsSync(out)) await sharp(file, { failOn: 'none' }).png().toFile(out)
    imagePath = out
  } catch (e) {
    console.error('GIF 抽帧失败（将按原图尝试）:', e.message)
  }
}

const realExt = path.extname(imagePath).toLowerCase().replace('.', '') || 'jpeg'
const mime = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif' }[realExt] || 'image/jpeg'
const b64 = fs.readFileSync(imagePath).toString('base64')

const prompt = question.length > 0
  ? `请用中文描述这张图片，重点回答这个问题：${question.join(' ')}`
  : '请用中文详细描述这张图片的内容（画面里有什么、什么风格、有没有文字）。'

const res = await fetch('https://api.deepseek.com/chat/completions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
  body: JSON.stringify({
    model: 'deepseek-flash',
    messages: [{
      role: 'user',
      content: [
        { type: 'image_url', image_url: { url: `data:${mime};base64,${b64}` } },
        { type: 'text', text: prompt },
      ],
    }],
    max_tokens: 1024,
  }),
})

if (!res.ok) {
  console.error(`API 错误 ${res.status}:`, (await res.text()).slice(0, 300))
  process.exit(1)
}
const data = await res.json()
const text = data?.choices?.[0]?.message?.content
if (!text) { console.error('响应里没有内容:', JSON.stringify(data).slice(0, 300)); process.exit(1) }
console.log(text.trim())
