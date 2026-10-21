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
  cls === 'pi' || cls.startsWith('pi-') || // icônes PrimeIcons (primeicons.css)
  cls.startsWith('bi-') || // icônes bootstrap-icons.css (servi par le seed)
  allowRegex.some((re) => re.test(cls))

// ---------------------------------------------------------------------------
// App avec son propre Tailwind : ses utilitaires TW (compilés depuis sa
// config, introuvables statiquement) sont signalés à part, pas en fantômes.
// ---------------------------------------------------------------------------
let twOwn = false
const pkgPath = join(root, 'package.json')
if (existsSync(pkgPath)) {
  try {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
    const deps = { ...pkg.dependencies, ...pkg.devDependencies }
    twOwn = Object.keys(deps).some((d) => d.includes('tailwind'))
  } catch { /* package.json illisible : tant pis */ }
}
const twPrefixes =
  'bg-|text-|border-|rounded-|shadow-|animate-|backdrop-|tracking-|leading-|font-|whitespace-|overflow-|opacity-|transition-|duration-|ease-|delay-|z-|top-|bottom-|left-|right-|inset-|w-|h-|min-w-|max-w-|min-h-|max-h-|p-|px-|py-|pt-|pb-|pl-|pr-|m-|mx-|my-|mt-|mb-|ml-|mr-|gap-|space-|grid-|col-|row-|flex-|items-|justify-|self-|place-|order-|ring-|outline-|divide-|underline-|decoration-|list-|object-|aspect-|columns-|break-|float-|clear-|isolate-|align-|table-|translate-|scale-|rotate-|drop-shadow-|from-|via-|to-|file:|uppercase|lowercase|capitalize|truncate|italic|not-italic|underline|line-through|no-underline|antialiased|sr-only|pointer-events-|select-|cursor-|appearance-|resize-|fill-|stroke-|accent-|caret-|scroll-|snap-|touch-|will-change-|content-|after:|before:|hover:|focus:|active:|visited:|disabled:|group-|peer-|dark:|first:|last:|odd:|even:|sm:|md:|lg:|xl:|2xl:|max-|min-|probe-'
const looksLikeTw = (cls) => {
  if (new RegExp(`^(${twPrefixes})`).test(cls)) return true
  const bare = cls.startsWith('-') ? cls.slice(1) : cls // utilitaires négatifs (-mb-px…)
  return new RegExp(`^(${twPrefixes})`).test(bare) || /^\S*\d/.test(bare) ||
    // utilitaires Tailwind « nus » (sans préfixe ni valeur numérique)
    /^(block|inline-block|inline|flex|inline-flex|grid|hidden|table|contents|flow-root|border|rounded|shadow|fixed|absolute|relative|sticky|static|visible|invisible|isolate|italic|underline|line-through|no-underline|truncate|uppercase|lowercase|capitalize|normal-case|antialiased|resize|ring|outline|filter|container|group|peer|transform|box-border|box-content|transition)$/.test(bare)
}

// ---------------------------------------------------------------------------
// 1. Classes connues = seed HUBCSS buildé + CSS applicatif (src/**/*.css)
// ---------------------------------------------------------------------------
const seedPath = join(root, 'public', 'design-system', 'current', 'global.css')
if (!existsSync(seedPath)) {
  console.error(
    `❌ Seed design system introuvable : ${relative(process.cwd(), seedPath)}\n` +
      `   Lancez « make update-ds » (ou build HUBCSS) puis réessayez.`
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
const bracedAttrRe = /className\s*=\s*\{/g
const htmlClassRe = /\bclass\s*=\s*"([^"]*)"/g
const garbageRe = /[<>{}`$;=&|!()[\]]/ // résidus d'expression → jeton non vérifiable
const trailingDashRe = /-$/ // fragment tronqué (préfixe de classe dynamique)

function record(cls, file, line) {
  if (!used.has(cls)) used.set(cls, [])
  used.get(cls).push({ file, line })
}

function recordTokens(text, file, line) {
  for (const token of text.split(/\s+/)) {
    if (!token || garbageRe.test(token) || trailingDashRe.test(token)) continue
    record(token, file, line)
  }
}

// Extrait l'expression className={...} avec accolades équilibrées
// (l'interpolation ${...} contient des '}' qui casserait [^}]*)
function matchBracedExpr(text, startIndex) {
  let depth = 1
  for (let i = startIndex; i < text.length; i++) {
    const ch = text[i]
    if (ch === '{') depth++
    else if (ch === '}') {
      depth--
      if (depth === 0) return text.slice(startIndex, i)
    }
  }
  return text.slice(startIndex) // non équilibré : on prend tout
}

// Parties statiques d'une expression className : chaînes '...' / "..." hors
// interpolations, et parties hors ${...} des template literals.
function staticClassStrings(expr) {
  const parts = []
  let i = 0
  while (i < expr.length) {
    const ch = expr[i]
    if (ch === '"' || ch === "'" || ch === '`') {
      const quote = ch
      let j = i + 1
      let literal = ''
      // chaîne dans une comparaison (=== "x", !== 'y') → valeur, pas classe
      let k = i - 1
      while (k >= 0 && /\s/.test(expr[k])) k--
      const isComparison = quote !== '`' && k >= 0 && /[=!<>]/.test(expr[k])
      while (j < expr.length && expr[j] !== quote) {
        if (expr[j] === '\\') { // échappement
          literal += expr[j + 1] ?? ''
          j += 2
          continue
        }
        if (quote === '`' && expr[j] === '$' && expr[j + 1] === '{') {
          // interpolation : sauter jusqu'à l'accolade fermante équilibrée
          let d = 1
          j += 2
          const start = j
          while (j < expr.length && d > 0) {
            if (expr[j] === '{') d++
            else if (expr[j] === '}') d--
            if (d > 0) j++
          }
          dynamicCount++
          j++ // consommer '}'
          continue
        }
        literal += expr[j]
        j++
      }
      if (isComparison) {
        // valeur comparée, pas une classe : ignorer proprement
        i = j + 1
        continue
      }
      parts.push(literal)
      i = j + 1
      continue
    }
    i++
  }
  return parts
}

function scanSource(path, isHtml) {
  const text = readFileSync(path, 'utf8')

  const lineOf = (index) => text.slice(0, index).split('\n').length

  for (const m of text.matchAll(directAttrRe)) {
    const value = m[1] ?? m[2]
    recordTokens(value, path, lineOf(m.index))
  }
  for (const m of text.matchAll(bracedAttrRe)) {
    const expr = matchBracedExpr(text, m.index + m[0].length)
    const line = lineOf(m.index)
    const parts = staticClassStrings(expr)
    // expression sans aucune partie statique → dynamique pure
    if (!parts.length && expr.trim() && !/["'`]/.test(expr.trim()[0] ?? '')) dynamicCount++
    for (const part of parts) recordTokens(part, path, line)
  }
  if (isHtml) {
    for (const m of text.matchAll(htmlClassRe)) {
      recordTokens(m[1], path, lineOf(m.index))
    }
  }
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    if (/\.(bak|orig|rej)$/.test(entry)) continue // sauvegardes : hors scan
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
const unknown = [...used.keys()].filter((cls) => !known.has(cls) && !isAllowed(cls))
const ghosts = unknown.filter((cls) => !(twOwn && looksLikeTw(cls))).sort()
const twUnverified = unknown.length - ghosts.length

console.log('lint-classes — classes JSX vs build HUBCSS')
console.log(
  `  seed : ${knownFromSeed} classes connues · ` +
    `${sourceFiles.length} fichiers scannés · ` +
    `${used.size} classes utilisées` +
    (dynamicCount ? ` · ${dynamicCount} expressions dynamiques ignorées` : '')
)
if (twOwn && twUnverified) {
  console.log(
    `  ℹ️  App avec Tailwind propre : ${twUnverified} classe(s) TW non ` +
      `vérifiables statiquement (ignorées — compilées par ${'`'}tailwindcss${'`'}).`
  )
}

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
