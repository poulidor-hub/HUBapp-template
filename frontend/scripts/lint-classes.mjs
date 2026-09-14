#!/usr/bin/env node
/**
 * lint-classes.mjs — Lint anti-classes-fantômes (contrat HUBCSS/CASCADE).
 *
 * Détecte, avant le runtime :
 *   1. les classes utilisées dans le JSX/HTML mais ABSENTES du build
 *      (seed `public/design-system/current/global.css` + CSS applicatif)
 *      — ex. `mb-2`/`mb-3` après le retrait de Tailwind du build ;
 *   2. (avertissement) les resets universels `* { … }` hors `@layer` dans le
 *      CSS applicatif — ils écrasent les paddings/margins des composants
 *      `hub-*` (voir HUBCSS/docs/CASCADE.md, cas exports v0.1.2).
 *
 * Usage :
 *   npm run lint:classes            # racine = frontend/ (défaut)
 *   node scripts/lint-classes.mjs [racine-frontend-alternative]
 *
 * Exit codes : 0 = OK · 1 = classes fantômes · 2 = setup invalide.
 * Aucune dépendance externe.
 */
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join, dirname, relative, extname } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const root = process.argv[2] ? String(process.argv[2]) : dirname(scriptDir)

// ---------------------------------------------------------------------------
// Allowlist optionnelle : <racine>/scripts/lint-classes.allowlist.json
// (ou à côté du script). Format :
// { "classes": ["classe-dynamique-voulue", "/^prefix-dynamique-/"] }
// ---------------------------------------------------------------------------
const allowExact = new Set()
const allowRegex = []
for (const allowlistFile of [
  join(root, 'scripts', 'lint-classes.allowlist.json'),
  join(scriptDir, 'lint-classes.allowlist.json'),
]) {
  if (!existsSync(allowlistFile)) continue
  try {
    const parsed = JSON.parse(readFileSync(allowlistFile, 'utf8'))
    for (const entry of parsed.classes ?? []) {
      if (entry.startsWith('/') && entry.endsWith('/') && entry.length > 2) {
        allowRegex.push(new RegExp(entry.slice(1, -1)))
      } else {
        allowExact.add(entry)
      }
    }
  } catch (e) {
    console.error(`❌ Allowlist illisible (${allowlistFile}) : ${e.message}`)
    process.exit(2)
  }
}

const isAllowed = (cls) =>
  allowExact.has(cls) ||
  cls.startsWith('bi-') || // icônes bootstrap-icons.css (servi par le seed)
  allowRegex.some((re) => re.test(cls))

// ---------------------------------------------------------------------------
// 1. Classes connues = seed HUBCSS buildé + CSS applicatif (src/**/*.css)
// ---------------------------------------------------------------------------
const seedPath = join(root, 'public', 'design-system', 'current', 'global.css')
if (!existsSync(seedPath)) {
  console.error(
    `❌ Seed design system introuvable : ${relative(process.cwd(), seedPath)}\n` +
      `   Lancez « make refresh-design-seed » (ou build HUBCSS) puis réessayez.`
  )
  process.exit(2)
}

const classFromCssRe = /\.((?:\\.|[A-Za-z0-9_-])+)/g
const known = new Set()
function collectKnownFromCss(cssText) {
  for (const m of cssText.matchAll(classFromCssRe)) {
    known.add(m[1].replace(/\\(.)/g, '$1')) // désechappe \: \[ \] etc.
  }
}
collectKnownFromCss(readFileSync(seedPath, 'utf8'))
const knownFromSeed = known.size

// ---------------------------------------------------------------------------
// 2. Reset universel hors @layer (avertissement) — parser à profondeur bornée
// ---------------------------------------------------------------------------
function findUniversalResets(cssText) {
  const stripped = cssText.replace(/\/\*[\s\S]*?\*\//g, '')
  const findings = []
  const stack = [] // true = bloc ouvert par un @layer
  const segRe = /([^{}]+)\{|\}/g
  let m
  while ((m = segRe.exec(stripped)) !== null) {
    if (m[1] === undefined) { // '}'
      stack.pop()
      continue
    }
    const segment = m[1].trim()
    const isLayerPrelude = /@layer\b/.test(segment.split(',')[0])
    // sélecteurs multiples : chaque sélecteur séparé par ','
    const isUniversal = segment
      .split(',')
      .some((sel) => /^\*(?:[\s.,:>+~[~]|$)/.test(sel.trim()))
    if (isUniversal && !isLayerPrelude && !stack.some(Boolean)) {
      const line = stripped.slice(0, m.index).split('\n').length
      findings.push(line)
    }
    stack.push(isLayerPrelude)
  }
  return findings
}

const resetWarnings = []
function scanCssFile(path) {
  const text = readFileSync(path, 'utf8')
  collectKnownFromCss(text)
  for (const line of findUniversalResets(text)) {
    resetWarnings.push({ file: path, line })
  }
}

// ---------------------------------------------------------------------------
// 3. Extraction des classes utilisées (JSX/JS/TS + index.html)
// ---------------------------------------------------------------------------
const SRC_EXTENSIONS = new Set(['.jsx', '.js', '.tsx', '.ts'])
const used = new Map() // classe -> [{ file, line }]
let dynamicCount = 0

const directAttrRe = /className\s*=\s*"([^"]*)"|className\s*=\s*'([^']*)'/g
const bracedAttrRe = /className\s*=\s*\{([^}]*)\}/g
const quotedInExprRe = /"([^"]*)"|'([^']*)'|`([^`]*)`/g
const interpolationRe = /\$\{[^}]*\}/g
const htmlClassRe = /\bclass\s*=\s*"([^"]*)"/g
const garbageRe = /[<>{}`$;=&|!()[\]]/ // résidus d'expression → jeton non vérifiable

function record(cls, file, line) {
  if (!used.has(cls)) used.set(cls, [])
  used.get(cls).push({ file, line })
}

function recordTokens(text, file, line) {
  for (const token of text.split(/\s+/)) {
    if (!token || garbageRe.test(token)) continue
    record(token, file, line)
  }
}

function scanSource(path, isHtml) {
  const text = readFileSync(path, 'utf8')
  const lines = text.split('\n')

  const lineOf = (index) => text.slice(0, index).split('\n').length

  for (const m of text.matchAll(directAttrRe)) {
    const value = m[1] ?? m[2]
    recordTokens(value, path, lineOf(m.index))
  }
  for (const m of text.matchAll(bracedAttrRe)) {
    const expr = m[1]
    const line = lineOf(m.index)
    // template literals : retirer les interpolations (invérifiables)
    const literalParts = []
    for (const q of expr.matchAll(quotedInExprRe)) {
      const value = q[1] ?? q[2] ?? q[3]
      if (q[3] !== undefined) {
        const staticParts = value.replace(interpolationRe, ' ')
        if (staticParts.trim()) literalParts.push(staticParts)
        else dynamicCount++
      } else {
        literalParts.push(value)
      }
    }
    // expression sans aucune chaîne littérale → dynamique pure
    if (!literalParts.length && expr.trim() && !/["'`]/.test(expr)) dynamicCount++
    for (const part of literalParts) recordTokens(part, path, line)
  }
  if (isHtml) {
    for (const m of text.matchAll(htmlClassRe)) {
      recordTokens(m[1], path, lineOf(m.index))
    }
  }
  void lines // (réserve : rapports par ligne plus fins si besoin)
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const st = statSync(full)
    if (st.isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue
      walk(full, files)
    } else {
      files.push(full)
    }
  }
  return files
}

const srcDir = join(root, 'src')
const sourceFiles = existsSync(srcDir) ? walk(srcDir) : []
const indexPath = join(root, 'index.html')
if (existsSync(indexPath)) sourceFiles.push(indexPath)

for (const file of sourceFiles) {
  const ext = extname(file)
  if (SRC_EXTENSIONS.has(ext)) scanSource(file, false)
  else if (ext === '.html') scanSource(file, true)
  else if (ext === '.css') scanCssFile(file)
}

// ---------------------------------------------------------------------------
// 4. Rapport
// ---------------------------------------------------------------------------
const rel = (p) => {
  const r = relative(process.cwd(), p)
  return r.startsWith('..') ? p : r // ne pas afficher des '../../../..' illisibles
}
const ghosts = [...used.keys()]
  .filter((cls) => !known.has(cls) && !isAllowed(cls))
  .sort()

console.log('lint-classes — classes JSX vs build HUBCSS')
console.log(
  `  seed : ${knownFromSeed} classes connues · ` +
    `${sourceFiles.length} fichiers scannés · ` +
    `${used.size} classes utilisées` +
    (dynamicCount ? ` · ${dynamicCount} expressions dynamiques ignorées` : '')
)

if (resetWarnings.length) {
  console.log('\n⚠️  Resets universels hors @layer (écrasent les composants hub-* —')
  console.log('    voir HUBCSS/docs/CASCADE.md) :')
  for (const w of resetWarnings) {
    console.log(`    ${rel(w.file)}:${w.line}`)
  }
}

if (ghosts.length) {
  console.log(`\n❌ ${ghosts.length} classe(s) fantôme(s) — utilisées mais absentes du build :`)
  for (const cls of ghosts) {
    console.log(`\n  .${cls}`)
    for (const { file, line } of used.get(cls)) {
      console.log(`    ${rel(file)}:${line}`)
    }
  }
  console.log(
    `\n  → Définis-les dans app.css (hors layer, valeurs via tokens --hub-*)` +
      ` ou corrige le nom. Allowlist : scripts/lint-classes.allowlist.json.`
  )
  process.exit(1)
}

console.log('\n✅ Aucune classe fantôme.')
if (resetWarnings.length) console.log('⚠️  Des avertissements reset méritent une relecture.')
process.exit(0)
