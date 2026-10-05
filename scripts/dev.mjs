// 同时启动后端接口（8000）和前端（5180）。Ctrl+C 会一并结束两者。
// 采访用的能力文件默认自动取 backend/runs 下最新的匹配项；要指定时：CAPABILITY_RUN=runs/<目录> npm run dev。
import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(fileURLToPath(import.meta.url), '..', '..')
const windows = process.platform === 'win32'
const python = join(root, 'backend', '.venv-browsing', windows ? 'Scripts/python.exe' : 'bin/python')
if (!existsSync(python)) {
  console.error(`找不到后端虚拟环境：${python}\n请先按 docs 里的说明创建 backend/.venv-browsing。`)
  process.exit(1)
}
if (!existsSync(join(root, 'frontend', 'node_modules'))) {
  console.error('前端依赖未安装，先执行：npm --prefix frontend install')
  process.exit(1)
}

const api = ['-m', 'api', '--port', '8000']
if (process.env.CAPABILITY_RUN) api.push('--capability-run', process.env.CAPABILITY_RUN)

const children = [
  ['api', spawn(python, api, { cwd: join(root, 'backend'), stdio: 'inherit' })],
  ['ui', spawn('npm', ['run', 'dev'], { cwd: join(root, 'frontend'), stdio: 'inherit', shell: windows })],
]

let stopping = false
function stop(code) {
  if (stopping) return
  stopping = true
  for (const [, child] of children) {
    if (child.exitCode !== null) continue
    if (windows) spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { stdio: 'ignore' })
    else child.kill('SIGTERM')
  }
  process.exit(code)
}
for (const [name, child] of children) {
  child.on('exit', (code) => {
    if (!stopping) console.error(`[dev] ${name} 已退出（${code}），关闭另一个服务`)
    stop(code ?? 1)
  })
}
process.on('SIGINT', () => stop(0))
process.on('SIGTERM', () => stop(0))
