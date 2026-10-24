import { createHash } from 'node:crypto'
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'

// 复刻 src/index.js 的 packagedExecutable() 自定位逻辑，
// 从 DSH 实际加载的 node_modules 入口出发，验证能否解析到后端 exe。
const ENTRY =
  'C:/Users/Administrator/AppData/Roaming/dsh-desktop/harness/profiles/web/node_modules/@gd/gp/lib/index.js'

const metaUrl = pathToFileURL(ENTRY).href
const runtimesDir = fileURLToPath(new URL('../runtimes/', metaUrl))

console.log('ENTRY        :', ENTRY)
console.log('runtimesDir  :', runtimesDir)
console.log('[1] runtimes 目录存在  :', existsSync(runtimesDir))

const manifestPath = path.join(runtimesDir, 'win32-x64', 'runtime.json')
console.log('[2] runtime.json 存在  :', existsSync(manifestPath))
if (!existsSync(manifestPath)) process.exit(1)

const manifest = JSON.parse(readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''))
const topKeys = Object.keys(manifest)
console.log('    manifest keys      :', topKeys.join(', '))
console.log('    version / target   :', manifest.version, '/', manifest.target)

const exe = path.join(runtimesDir, 'win32-x64', 'gaussian-backend', 'gaussian-backend.exe')
console.log('[3] exe 路径长度       :', exe.length, exe.length < 260 ? 'PASS' : 'FAIL')
console.log('[4] exe 存在           :', existsSync(exe))
if (!existsSync(exe)) process.exit(1)

const h = createHash('sha256').update(readFileSync(exe)).digest('hex')
console.log('[5] exe sha256         :', h)

// 在 manifest 中定位该条目（兼容 files / entries / 嵌套结构）
const SEP = String.fromCharCode(92)
function collect(obj, out) {
  if (!obj || typeof obj !== 'object') return
  if (Array.isArray(obj)) {
    for (const v of obj) collect(v, out)
    return
  }
  const p = obj.path || obj.file
  if (typeof p === 'string' && p.includes('gaussian-backend.exe') && obj.sha256) {
    out.push(obj)
  }
  for (const k of Object.keys(obj)) {
    const v = obj[k]
    if (v && typeof v === 'object') collect(v, out)
  }
}
const found = []
collect(manifest, found)
const hit = found[0]
console.log('[6] manifest 条目      :', hit ? hit.path : '未找到')
console.log('[7] sha256 一致        :', hit ? (hit.sha256.toLowerCase() === h.toLowerCase() ? 'PASS' : 'FAIL') : 'N/A')

// 依赖是否健全（pydantic_core 空壳问题的回归检查）
const pc = path.join(runtimesDir, 'win32-x64', 'gaussian-backend', '_internal', 'pydantic_core')
const pcFiles = existsSync(pc) ? ['__init__.py', 'core_schema.py', 'py.typed'].map((f) => [f, existsSync(path.join(pc, f))]) : []
const pydHit = existsSync(pc) ? readdirSync(pc).filter((f) => f.endsWith('.pyd')) : []
console.log('[8] pydantic_core 完整  :')
for (const [f, ok] of pcFiles) console.log('      ', f.padEnd(16), ok ? 'PASS' : 'FAIL')
console.log('       binary          ', pydHit.length ? 'PASS (' + pydHit[0] + ')' : 'FAIL')
