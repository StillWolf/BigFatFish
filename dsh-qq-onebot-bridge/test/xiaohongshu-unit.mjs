import assert from 'node:assert/strict'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { registerXiaohongshuTools } from '../lib/xiaohongshu.js'

const root = mkdtempSync(join(tmpdir(), 'fish-xhs-test-'))
try {
  const tools = []
  const ctx = { tools: { register: (tool) => tools.push(tool) } }
  assert.equal(registerXiaohongshuTools(ctx, { root }), false)
  assert.deepEqual(tools, [])
  writeFileSync(join(root, 'runtime.env'), 'XHS_TOKEN=synthetic-test-token\n', { mode: 0o600 })
  process.env.FISH_XHS_ENABLED = '0'
  assert.equal(registerXiaohongshuTools(ctx, { root }), false)
  delete process.env.FISH_XHS_ENABLED
  assert.equal(registerXiaohongshuTools(ctx, { root, blocked: () => true }), true)
  assert.deepEqual(tools.map((tool) => tool.name), ['xhs_status', 'xhs_feed', 'xhs_search', 'xhs_read', 'xhs_comments', 'xhs_watch'])
  for (const tool of tools) {
    await assert.rejects(() => tool.execute({}), /调试或已停止/)
  }
  console.log('小红书工具注册与调试隔离：通过')
} finally {
  rmSync(root, { recursive: true, force: true })
}
