#!/usr/bin/env node
// reelbot-installer — one-command bootstrap for the Reelbot stack.
// Node built-ins only (no deps), so `npx reelbot-installer` is instant.

import { spawnSync } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync, readdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { join } from 'node:path'
import { createInterface } from 'node:readline/promises'
import { stdin, stdout, platform, argv, exit } from 'node:process'

const DEFAULT_REPO = 'git@workspace:helmiatwork/reel_bot.git'

// Service hostnames to rewrite to localhost for native mode
const SERVICE_HOSTS = ['cliproxy', 'openclaw', 'pipeline-api', 'arcreel', 'trends', 'postgres']

// Secrets we auto-generate so the stack can boot unattended.
const AUTOGEN = ['POSTGRES_PASSWORD', 'DASHBOARD_PASSWORD', 'N8N_ENCRYPTION_KEY', 'N8N_PASSWORD']
// Keys the user must fill for features to actually work (warned, never invented).
const NEEDED = [
  'TELEGRAM_BOT_TOKEN', 'OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_REELBOT',
  'ARCREEL_TOKEN', 'GEMINI_API_KEY'
]
const PLACEHOLDER = /^(|change_this.*|your_.*|change_this_to_.*)$/i

const rnd = () => randomBytes(24).toString('base64').replace(/[^a-zA-Z0-9]/g, '').slice(0, 28)

// Pure: rewrite .env.example text → .env text. Returns { text, stillEmpty }.
export function seedEnv(text) {
  const stillEmpty = []
  const lines = text.split('\n').map((line) => {
    const m = line.match(/^([A-Z0-9_]+)=(.*?)(\s+#.*)?$/)
    if (!m) return line
    const [, key, rawVal, comment = ''] = m
    const val = rawVal.trim()
    if (AUTOGEN.includes(key) && PLACEHOLDER.test(val)) {
      return `${key}=${rnd()}${comment}`
    }
    if (NEEDED.includes(key) && PLACEHOLDER.test(val)) stillEmpty.push(key)
    return line
  })
  return { text: lines.join('\n'), stillEmpty }
}

// Pure: rewrite docker service hostnames to localhost for native mode
export function nativeEnv(text) {
  return text.split('\n').map((line) => {
    if (!/^[A-Z0-9_]+=/.test(line)) return line
    let out = line
    for (const host of SERVICE_HOSTS) {
      out = out
        .replace(new RegExp(`//${host}:`, 'g'), '//localhost:')
        .replace(new RegExp(`@${host}:`, 'g'), '@localhost:')
        .replace(new RegExp(`=${host}$`), '=localhost')
    }
    return out
  }).join('\n')
}

const PROC = [
  ['postgres',     'postgres -D ./data/pg'],
  ['cliproxy',     './data/bin/cli-proxy-api --port 8317'],
  ['openclaw',     'npm --prefix openclaw start'],
  ['pipeline-api', 'uv run --project pipeline-api uvicorn main:app --host 0.0.0.0 --port 8000'],
  ['trends',       'uv run --project trends uvicorn app:app --host 0.0.0.0 --port 8200'],
  ['arcreel',      'uv run --project data/arcreel uvicorn app.main:app --host 0.0.0.0 --port 1241'],
  ['n8n',          'n8n start']
]

export function buildProcfile(platform) {
  return PROC.map(([name, cmd]) => `${name}: ${cmd}`).join('\n') + '\n'
}

export function detectOS(p = process.platform) {
  if (p === 'darwin') return 'mac'
  if (p === 'win32') return 'windows'
  return 'linux'
}

export const PREREQS = {
  mac:     { manager: 'brew',   packages: ['postgresql@16', 'node', 'python@3.12', 'uv', 'ffmpeg'] },
  linux:   { manager: 'apt',    packages: ['postgresql-16', 'nodejs', 'python3.12', 'ffmpeg'] }, // uv via curl
  windows: { manager: 'winget', packages: ['PostgreSQL.PostgreSQL', 'OpenJS.NodeJS', 'Python.Python.3.12', 'Gyan.FFmpeg'] }
}

function ensurePrereqs(os, { dryRun }) {
  const { manager, packages } = PREREQS[os]
  if (!has(manager, ['--version'])) {
    console.error(`Missing package manager '${manager}'. Install it first:`)
    console.error({ brew: 'https://brew.sh', apt: 'use your distro', winget: 'https://aka.ms/getwinget' }[manager])
    exit(1)
  }
  for (const pkg of packages) {
    const cmd = manager === 'brew' ? ['brew', ['install', pkg]]
      : manager === 'apt' ? ['sudo', ['apt-get', 'install', '-y', pkg]]
      : ['winget', ['install', '-e', '--id', pkg]]
    if (dryRun) { console.log(`[dry-run] ${cmd[0]} ${cmd[1].join(' ')}`); continue }
    run(cmd[0], cmd[1])
  }
}

function provisionPostgres({ dryRun }) {
  const steps = [
    ['initdb', () => existsSync('./data/pg') || run('initdb', ['-D', './data/pg', '-U', 'admin'])],
    ['createdbs', () => {
      for (const db of ['arcreel', 'n8n', 'content_automation']) {
        run('createdb', ['-h', 'localhost', '-U', 'admin', db], { allowFail: true })
      }
    }]
  ]
  for (const [name, fn] of steps) {
    if (dryRun) { console.log(`[dry-run] postgres: ${name}`); continue }
    fn()
  }
}

const NODE_SVCS = ['openclaw']
const PY_SVCS = ['pipeline-api', 'trends', 'video-analyzer', 'video-splitter', 'yt-pipeline']

function provisionServices({ dryRun }) {
  for (const s of NODE_SVCS) {
    if (dryRun) { console.log(`[dry-run] npm ci --prefix ${s}`); continue }
    run('npm', ['ci', '--prefix', s])
  }
  for (const s of PY_SVCS) {
    if (dryRun) { console.log(`[dry-run] uv sync --project ${s}`); continue }
    run('uv', ['sync', '--project', s])
  }
}

const ARCREEL_REPO = 'https://github.com/ArcReel/ArcReel.git'
const ARCREEL_REF = 'main' // ponytail: pin to a release tag once chosen

function provisionArcreel({ dryRun, os }) {
  if (os === 'windows') console.log('NOTE: ArcReel native on Windows is partial (POSIX isolation degrades). WSL2 recommended.')
  if (dryRun) { console.log(`[dry-run] clone ${ARCREEL_REPO}@${ARCREEL_REF} → data/arcreel; uv sync; build frontend`); return }
  if (!existsSync('./data/arcreel')) run('git', ['clone', '--depth', '1', '--branch', ARCREEL_REF, ARCREEL_REPO, 'data/arcreel'])
  run('uv', ['sync', '--project', 'data/arcreel'])
  run('npm', ['ci', '--prefix', 'data/arcreel/frontend'], { allowFail: true })
  run('npm', ['run', 'build', '--prefix', 'data/arcreel/frontend'], { allowFail: true })
}

function provisionCliproxy({ dryRun, os }) {
  if (dryRun) { console.log('[dry-run] download cli-proxy-api prebuilt binary → data/bin/'); return }
  if (existsSync('./data/bin/cli-proxy-api')) return
  if (has('go', ['version'])) run('go', ['build', '-o', 'data/bin/cli-proxy-api', './cliproxy/...'])
  else { console.error('cliproxy: no prebuilt binary and Go not installed. Install Go or add the binary to data/bin/.'); exit(1) }
}

export function conflictingPorts(ports, isBusy) {
  return ports.filter((p) => isBusy(p))
}

function run(cmd, args, opts = {}) {
  const { allowFail, ...spawnOpts } = opts
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...spawnOpts })
  if (!allowFail && r.status !== 0) return false
  return r.status === 0
}

function has(cmd, args = ['--version']) {
  const r = spawnSync(cmd, args, { stdio: 'ignore' })
  return r.status === 0
}

function getArg(flag) {
  const i = argv.indexOf(flag)
  return i !== -1 ? argv[i + 1] : undefined
}

async function main() {
  if (argv.includes('--selfcheck')) return selfcheck()

  const useNative = argv.includes('--native') || !argv.includes('--docker')
  const useDocker = argv.includes('--docker')
  const dryRun = argv.includes('--dry-run')
  const skipUp = argv.includes('--skip-up')

  console.log('\n🎬 reelbot-installer\n')

  if (useNative) {
    // Native installer path
    const os = detectOS()
    if (dryRun) console.log('[dry-run] Mode: native installer')
    ensurePrereqs(os, { dryRun })
    // Provision postgres, services, arcreel, cliproxy (Tasks 5-8)
    provisionPostgres({ dryRun })
    provisionServices({ dryRun })
    provisionArcreel({ dryRun, os })
    provisionCliproxy({ dryRun, os })
    // Task 8a: seed and rewrite .env to localhost
    if (existsSync('./.env')) {
      const envText = readFileSync('./.env', 'utf8')
      const rewritten = nativeEnv(envText)
      if (dryRun) {
        console.log('[dry-run] .env → rewrite docker hosts to localhost')
      } else {
        writeFileSync('./.env', rewritten)
        console.log('• .env rewired for native (localhost)')
      }
    } else if (existsSync('./.env.example')) {
      const exampleText = readFileSync('./.env.example', 'utf8')
      const { text, stillEmpty } = seedEnv(exampleText)
      const rewritten = nativeEnv(text)
      if (dryRun) {
        console.log('[dry-run] .env → seed secrets + rewrite docker hosts to localhost')
      } else {
        writeFileSync('./.env', rewritten)
        console.log('• Wrote .env (auto-generated secrets: ' + AUTOGEN.join(', ') + ')')
        if (stillEmpty.length) {
          console.log('\n⚠  Fill these in ./.env before features work:')
          stillEmpty.forEach((k) => console.log('     ' + k))
        }
        console.log('• .env rewired for native (localhost)')
      }
    }
    // Task 9: write Procfile
    const procfile = buildProcfile(os)
    if (dryRun) {
      console.log('[dry-run] Would write Procfile:')
      console.log(procfile)
    } else {
      writeFileSync('./Procfile', procfile)
      console.log('• Wrote Procfile')
    }
    // Task 9: launch supervisor (unless --skip-up)
    if (!skipUp && !dryRun) {
      console.log('• Launching supervisor...')
      if (!run('npx', ['foreman', 'start', '-f', 'Procfile'])) {
        console.error('\n✗ Supervisor failed.')
        exit(1)
      }
    }
    if (dryRun || skipUp) {
      console.log('\n• Dry-run/skip-up complete.')
    }
  } else {
    // Docker installer path (original)
    const isMac = platform === 'darwin'
    const repo = getArg('--repo') || DEFAULT_REPO
    const ref = getArg('--ref')
    const posArg = argv[2] && !argv[2].startsWith('-') ? argv[2] : undefined
    const target = getArg('--dir') || posArg || 'reelbot'

    // 1. preflight
    const miss = []
    if (!has('git')) miss.push('git')
    if (!has('docker')) miss.push('docker')
    if (miss.length) {
      console.error(`✗ Missing: ${miss.join(', ')}.`)
      console.error('  Install Docker Desktop (or colima) + git, then re-run.')
      exit(1)
    }
    if (!has('docker', ['compose', 'version'])) {
      console.error('✗ `docker compose` v2 not available. Update Docker Desktop.')
      exit(1)
    }

    // 2. clone (skip if dir already populated)
    if (existsSync(target) && readdirSync(target).length) {
      console.log(`• ${target}/ already exists — skipping clone.`)
    } else {
      console.log(`• Cloning ${repo} → ${target}/`)
      const args = ['clone', '--depth', '1']
      if (ref) args.push('--branch', ref)
      args.push(repo, target)
      if (!run('git', args)) {
        console.error(`\n✗ Clone failed. This repo is private over SSH (host alias in the URL).`)
        console.error(`  On a new machine you need your SSH key + ~/.ssh/config alias set up.`)
        console.error(`  Test with:  git ls-remote ${repo}`)
        exit(1)
      }
    }

    // 3. seed .env
    const envPath = join(target, '.env')
    const examplePath = join(target, '.env.example')
    if (existsSync(envPath)) {
      console.log('• .env already present — leaving it untouched.')
    } else if (existsSync(examplePath)) {
      const { text, stillEmpty } = seedEnv(readFileSync(examplePath, 'utf8'))
      writeFileSync(envPath, text)
      console.log('• Wrote .env (auto-generated secrets: ' + AUTOGEN.join(', ') + ')')
      if (stillEmpty.length) {
        console.log('\n⚠  Fill these in ' + envPath + ' before features work:')
        stillEmpty.forEach((k) => console.log('     ' + k))
      }
    } else {
      console.log('• No .env.example found — skipping env step.')
    }

    // 4. bring the stack up
    const composeArgs = isMac
      ? ['compose', '-f', 'docker-compose.yml', '-f', 'docker-compose.mac.yml', 'up', '-d', '--build']
      : ['compose', '-f', 'docker-compose.yml', 'up', '-d', '--build']

    if (skipUp) {
      console.log('\n• --skip-up set. Start later with:\n   cd ' + target + ' && docker ' + composeArgs.join(' '))
    } else {
      if (isMac) {
        console.log('\n⚠  Mac: cli-proxy-api runs NATIVELY on host:8317 (not in Docker).')
        console.log('   Start it on the host first, otherwise openclaw/pipeline-api can\'t reach it.')
        const rl = createInterface({ input: stdin, output: stdout })
        const ans = (await rl.question('   Bring the Docker stack up now? (y/N): ')).trim().toLowerCase()
        rl.close()
        if (ans !== 'y') { console.log('   Skipped. Run later: cd ' + target + ' && docker ' + composeArgs.join(' ')); printDone(target, isMac); return }
      }
      console.log('\n• Starting stack…')
      if (!run('docker', composeArgs, { cwd: target })) {
        console.error('\n✗ docker compose up failed — check output above.')
        exit(1)
      }
    }

    printDone(target, isMac)
  }
}

function printDone(target, isMac) {
  console.log('\n✅ Done.')
  console.log('   Dir:     ' + target + '/')
  console.log('   Status:  cd ' + target + ' && docker compose ps')
  console.log('   Logs:    docker compose logs -f')
  if (isMac) console.log('   Reminder: keep cli-proxy-api running on host:8317.')
  console.log('')
}

function selfcheck() {
  const sample = [
    'POSTGRES_PASSWORD=change_this_to_strong_password',
    'DASHBOARD_PASSWORD=change_this',
    'GEMINI_API_KEY=',
    'OPENAI_API_KEY=sk-already-set'
  ].join('\n')
  const { text, stillEmpty } = seedEnv(sample)
  const out = Object.fromEntries(text.split('\n').map((l) => l.split('=')))
  if (PLACEHOLDER.test(out.POSTGRES_PASSWORD)) throw new Error('POSTGRES_PASSWORD not generated')
  if (out.POSTGRES_PASSWORD.length < 20) throw new Error('generated secret too short')
  if (out.OPENAI_API_KEY !== 'sk-already-set') throw new Error('existing value clobbered')
  if (!stillEmpty.includes('GEMINI_API_KEY')) throw new Error('empty needed-key not reported')
  console.log('selfcheck OK')
}

main().catch((e) => { console.error(e.message); exit(1) })
