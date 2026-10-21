#!/usr/bin/env node
/**
 * verify-ui.mjs — Smoke UI par styles calculés (item 4, contrat HUBCSS/CASCADE).
 *
 * Monte dans un vrai Chromium une fixture HTML chargant les CSS RÉELLEMENT
 * buildés de l'app (seed HUBCSS + bundle dist), puis asserte les styles
 * calculés de sentinelles — aux viewports mobile (375px) et desktop (1280px).
 * C'est la preuve runtime que ni un reset sauvage, ni une classe morte, ni un
 * mapping de token n'a cassé le rendu (bugs invisibles à la relecture de code).
 *
 * Usage :
 *   node scripts/verify-ui.mjs <racine-frontend-app>
 * Config : <racine>/scripts/verify-ui.config.json
 *   { "checks": [ { "desc": "...", "html": "<div id=\"c-x\" class=\"...\">",
 *                   "selector": "#c-x", "property": "padding-top",
 *                   "expect": "notEquals", "value": "0px" } ] }
 *   expect ∈ equals | notEquals | contains
 *
 * Dépendance : playwright (npm i -D playwright && npx playwright install chromium)
 * Exit codes : 0 = OK · 1 = échecs · 2 = setup invalide.
 */
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs'
import { join, dirname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import http from 'node:http'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const root = process.argv[2] ? String(process.argv[2]) : dirname(scriptDir)

// ── setup : chemins ──
const seedPath = join(root, 'public', 'design-system', 'current', 'global.css')
if (!existsSync(seedPath)) {
  console.error(`❌ Seed design system introuvable : ${seedPath}\n   Lancez « make update-ds ».`)
  process.exit(2)
}
const assetsDir = join(root, 'dist', 'assets')
if (!existsSync(assetsDir)) {
  console.error(`❌ dist/ introuvable — lancez « npm run build » d'abord.`)
  process.exit(2)
}
const configPath = join(root, 'scripts', 'verify-ui.config.json')
if (!existsSync(configPath)) {
  console.error(`❌ Config introuvable : ${configPath}`)
  process.exit(2)
}
const config = JSON.parse(readFileSync(configPath, 'utf8'))
if (!Array.isArray(config.checks) || !config.checks.length) {
  console.error('❌ Config sans checks.')
  process.exit(2)
}

// CSS de l'app = le plus récent index-*.css de dist/assets
const cssFile = readdirSync(assetsDir)
  .filter((f) => /^index-[\w-]+\.css$/.test(f))
  .map((f) => ({ f, t: statSync(join(assetsDir, f)).mtimeMs }))
  .sort((a, b) => b.t - a.t)[0]
if (!cssFile) {
  console.error('❌ Aucun dist/assets/index-*.css trouvé.')
  process.exit(2)
}

// ── playwright (import paresseux, message d'aide si absent) ──
let chromium
try {
  const pw = await import('playwright')
  chromium = pw.chromium
} catch {
  console.error('❌ Playwright absent. Dans ce paquet : npm i -D playwright && npx playwright install chromium')
  process.exit(2)
}

// ── mini serveur HTTP : /global.css, /app.css, / (fixture) ──
const seedCss = readFileSync(seedPath, 'utf8')
const appCss = readFileSync(join(assetsDir, cssFile.f), 'utf8')
const fixtureHtml = `<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/global.css">
<link rel="stylesheet" href="/app.css">
</head><body>
<div id="fixture">
${config.checks.map((c) => c.html).join('\n')}
</div>
</body></html>`

const server = http.createServer((req, res) => {
  if (req.url === '/global.css') {
    res.writeHead(200, { 'content-type': 'text/css' }).end(seedCss)
  } else if (req.url === '/app.css') {
    res.writeHead(200, { 'content-type': 'text/css' }).end(appCss)
  } else {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(fixtureHtml)
  }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const baseUrl = `http://127.0.0.1:${server.address().port}`

// ── exécution ──
const VIEWPORTS = [
  { name: 'mobile 375px', width: 375, height: 812 },
  { name: 'desktop 1280px', width: 1280, height: 900 },
]
let browser
try {
  browser = await chromium.launch()
} catch (e) {
  console.error(`❌ Chromium ne démarre pas : ${e.message.split('\n')[0]}\n   Essaie : npx playwright install chromium`)
  server.close()
  process.exit(2)
}

const rel = (p) => {
  const r = relative(process.cwd(), p)
  return r.startsWith('..') ? p : r
}
console.log('verify-ui — styles calculés (fixture = CSS buildés de l\'app)')
console.log(`  seed + ${cssFile.f} · ${config.checks.length} sentinelles · ${VIEWPORTS.length} viewports`)

let failures = 0
const page = await browser.newPage()
for (const vp of VIEWPORTS) {
  await page.setViewportSize({ width: vp.width, height: vp.height })
  await page.goto(baseUrl, { waitUntil: 'networkidle' })
  for (const check of config.checks) {
    let actual = null
    let error = null
    try {
      actual = await page.$eval(check.selector, (el, prop) => {
        const cs = getComputedStyle(el)
        return cs.getPropertyValue(prop).trim() || cs.getPropertyValue(prop)
      }, check.property)
    } catch (e) {
      error = e.message.split('\n')[0]
    }
    let ok = false
    if (!error) {
      const want = String(check.value)
      if (check.expect === 'notEquals') ok = actual !== want
      else if (check.expect === 'contains') ok = actual.includes(want)
      else ok = actual === want
    }
    if (ok) continue
    failures++
    console.log(
      `  ❌ [${vp.name}] ${check.desc}\n` +
      `     ${check.selector} · ${check.property}` +
      ` — attendu ${check.expect} « ${check.value} », obtenu « ${error ?? actual} »`
    )
  }
}
await browser.close()
server.close()

if (failures) {
  console.log(`\n❌ ${failures} vérification(s) échouée(s).`)
  process.exit(1)
}
console.log('\n✅ Toutes les sentinelles de styles calculés passent (mobile + desktop).')
process.exit(0)
