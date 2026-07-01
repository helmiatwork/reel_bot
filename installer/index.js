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
  ['postgres',     'pg_ctl -D ./data/pg -o "-p 5432" -l ./data/pg/server.log -w start'],
  ['cliproxy',     './data/bin/cli-proxy-api -config ./cliproxy/config.yaml'],
  ['openclaw',     'openclaw gateway --port 18789'],
  ['pipeline-api', 'bash -c "cd pipeline-api && source .venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000"'],
  ['arcreel',      'bash -c "cd data/arcreel && source .venv/bin/activate && uvicorn server.app:app --host 0.0.0.0 --port 1241"']
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
    ['initdb', () => {
      if (existsSync('./data/pg')) {
        console.log('  data/pg already exists, skipping initdb')
        return true
      }
      if (!run('initdb', ['-D', './data/pg', '-U', 'admin'])) return false
      return true
    }],
    ['start-cluster', () => {
      if (dryRun) return true
      // Start postgres cluster (pg_ctl -w waits for server to start)
      if (!run('pg_ctl', ['-D', './data/pg', '-o', '-p 5432', '-l', './data/pg/server.log', '-w', 'start'])) {
        console.error('  pg_ctl start failed')
        return false
      }
      // Verify connection (use postgres default database, which always exists)
      let ready = false
      for (let i = 0; i < 20; i++) {
        const r = spawnSync('psql', ['-h', 'localhost', '-U', 'admin', '-d', 'postgres', '-c', 'SELECT 1'], { stdio: 'pipe' })
        if (r.status === 0) {
          console.log('  postgres is ready')
          ready = true
          break
        }
        if (i === 0) console.log('  waiting for postgres to be ready...')
        spawnSync('sleep', ['0.5'], { stdio: 'ignore' })
      }
      return ready
    }],
    ['create-role', () => {
      if (dryRun) return true
      // Set admin password (idempotent, fails are allowed)
      run('psql', ['-h', 'localhost', '-U', 'admin', '-d', 'postgres', '-c', "ALTER ROLE admin WITH PASSWORD 'admin'"], { allowFail: true })
      return true
    }],
    ['createdbs', () => {
      if (dryRun) return true
      for (const db of ['arcreel', 'n8n', 'content_automation']) {
        run('createdb', ['-h', 'localhost', '-U', 'admin', db], { allowFail: true })
      }
      return true
    }]
  ]
  for (const [name, fn] of steps) {
    if (dryRun) { console.log(`[dry-run] postgres: ${name}`); continue }
    const ok = fn()
    if (!ok && name !== 'createdbs' && name !== 'create-role') {
      console.error(`✗ postgres ${name} failed`)
      exit(1)
    }
  }
}

// Services to provision for native run (Docker images + CLI tools are skipped)
// - openclaw: Docker image, installed globally via npm (no local provisioning)
// - video-analyzer, video-splitter: Docker images, git clone in container (no local provisioning)
// - yt-pipeline: Docker image, has yt_pipeline.py but runs in container (no local provisioning)
// - trends: doesn't exist in repo (was removed/never added)
// Only provision: pipeline-api (local Python project), arcreel (local Python + pnpm frontend)
const PY_SVCS = ['pipeline-api']

function provisionServices({ dryRun }) {
  for (const s of PY_SVCS) {
    if (dryRun) { console.log(`[dry-run] python3.12 -m venv ${s}/.venv && source ${s}/.venv/bin/activate && pip install [deps]`); continue }
    // Create venv and install deps from Dockerfile's pip install list
    const deps = [
      'fastapi', 'uvicorn', 'elevenlabs', 'gtts', 'yt-dlp[default]', 'curl_cffi',
      'httpx', 'psycopg[binary]', 'google-api-python-client', 'google-auth-oauthlib',
      'google-auth-httplib2', 'boto3', 'docker'
    ]
    if (!run('python3.12', ['-m', 'venv', `${s}/.venv`])) {
      console.error(`✗ venv creation for ${s} failed`)
      exit(1)
    }
    const activateCmd = `source ${s}/.venv/bin/activate && pip install ${deps.join(' ')}`
    if (!run('bash', ['-c', activateCmd])) {
      console.error(`✗ pip install for ${s} failed`)
      exit(1)
    }
  }
  // pipeline-api also needs deno (per Dockerfile)
  if (dryRun) { console.log('[dry-run] ensure deno is installed'); return }
  if (!has('deno')) {
    console.log('• Installing deno...')
    if (!run('brew', ['install', 'deno'])) {
      console.error('✗ deno installation failed (non-fatal, continuing)')
    }
  }
}

const ARCREEL_REPO = 'https://github.com/ArcReel/ArcReel.git'
const ARCREEL_REF = 'main' // ponytail: pin to a release tag once chosen

function provisionArcreel({ dryRun, os }) {
  if (os === 'windows') console.log('NOTE: ArcReel native on Windows is partial (POSIX isolation degrades). WSL2 recommended.')
  if (dryRun) { console.log(`[dry-run] clone ${ARCREEL_REPO}@${ARCREEL_REF} → data/arcreel; uv sync; pnpm install + build`); return }
  if (!existsSync('./data/arcreel')) {
    if (!run('git', ['clone', '--depth', '1', '--branch', ARCREEL_REF, ARCREEL_REPO, 'data/arcreel'])) {
      console.error('✗ arcreel clone failed')
      exit(1)
    }
  }
  // Use uv sync to create and install venv
  const syncResult = spawnSync('uv', ['sync', '--project', 'data/arcreel'], { stdio: 'inherit' })
  if (syncResult.status !== 0) {
    console.error('✗ arcreel uv sync failed')
    exit(1)
  }
  // Frontend uses pnpm (pnpm-lock.yaml exists)
  if (!has('pnpm')) {
    console.log('• Installing pnpm via npm...')
    run('npm', ['install', '-g', 'pnpm'])
  }
  run('pnpm', ['install', '-C', 'data/arcreel/frontend'], { allowFail: true })
  run('pnpm', ['build', '-C', 'data/arcreel/frontend'], { allowFail: true })
}

function provisionCliproxy({ dryRun, os }) {
  if (dryRun) { console.log('[dry-run] ensure cli-proxy-api binary exists at data/bin/cli-proxy-api'); return }
  if (existsSync('./data/bin/cli-proxy-api')) return
  // cliproxy is a Go binary from a separate repo (not included in this codebase)
  // Without the source or prebuilt binary, we cannot provision it natively
  console.error(`✗ cliproxy: no prebuilt binary at ./data/bin/cli-proxy-api`)
  console.error(`  The cliproxy source is not in this repo. Options:`)
  console.error(`  1. Download a prebuilt darwin binary and place it at ./data/bin/cli-proxy-api`)
  console.error(`  2. Or skip cliproxy and use Docker: docker compose up cliproxy`)
  console.error(`  Proceeding without cliproxy — other services may fail if they depend on it.`)
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
      console.log('• Launching supervisor with pm2 (per-process management)...')
      // Ensure pm2 is installed
      if (!has('pm2')) {
        console.log('  Installing pm2 globally...')
        if (!run('npm', ['install', '-g', 'pm2'])) {
          console.error('✗ Failed to install pm2')
          exit(1)
        }
      }
      // Start each service via pm2 (one service failure doesn't kill others)
      const procLines = buildProcfile(os).split('\n').filter(l => l.trim())
      for (const line of procLines) {
        const [name, cmd] = line.split(': ')
        if (!name || !cmd) continue
        console.log(`  Starting ${name}...`)
        if (!run('pm2', ['start', '--name', name, cmd])) {
          console.error(`✗ Failed to start ${name} (non-fatal, continuing)`)
        }
      }
      console.log('\n• All services launched. Monitor with: pm2 monit')
      console.log('  Stop all:     pm2 kill')
      console.log('  View logs:    pm2 logs')
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

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(e.message); exit(1) })
}
