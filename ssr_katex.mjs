// Pre-render KaTeX math server-side.
//
// Pipeline:
//   1. Parse index.html with cheerio.
//   2. Walk every text node not inside <script>, <style>, <code>, <pre>,
//      .katex (already rendered), .mermaid, or any element with class
//      "no-math".
//   3. Find \(...\) (inline) and \[...\] (display) delimiters, render
//      with KaTeX, replace the delimited slice with the HTML output.
//   4. Drop the client-side KaTeX runtime loader (the auto-render script
//      and katex.min.js) since math is now baked in — keep katex CSS.
//
// Saves ~280KB of JS download + eliminates KaTeX flash on cold load.
// Mermaid stays client-side (only 13 diagrams; mermaid SSR needs Chrome).

import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import * as cheerio from 'cheerio';
import katex from 'katex';

const __dirname = dirname(fileURLToPath(import.meta.url));
const INPUT  = resolve(__dirname, 'index.html');
const OUTPUT = resolve(__dirname, 'index.html');  // overwrite in place

const SKIP_TAGS = new Set(['script', 'style', 'code', 'pre', 'textarea']);
const SKIP_CLASSES = ['katex', 'katex-display', 'mermaid', 'no-math'];

function shouldSkip($, node) {
  let p = node.parent;
  while (p && p.type === 'tag') {
    if (SKIP_TAGS.has(p.name)) return true;
    const cls = $(p).attr('class') || '';
    for (const c of SKIP_CLASSES) if (cls.split(/\s+/).includes(c)) return true;
    p = p.parent;
  }
  return false;
}

// Render one delimited math chunk. Returns HTML string (KaTeX span).
function renderMath(latex, displayMode) {
  try {
    return katex.renderToString(latex, {
      displayMode,
      throwOnError: false,
      strict: false,
      output: 'html',
      trust: false
    });
  } catch (e) {
    console.warn(`KaTeX failed on: ${latex.slice(0, 80)}  — ${e.message}`);
    // Fall back to original delimited text
    return displayMode ? `\\[${latex}\\]` : `\\(${latex}\\)`;
  }
}

// Take a text-node value, return either { changed: false } or { changed: true, html }.
// Handles BOTH \[ ... \] (display, outermost first) and \( ... \) (inline).
function transformText(text) {
  let changed = false;
  let out = '';
  let i = 0;
  while (i < text.length) {
    // Try display \[ ... \]
    if (text[i] === '\\' && text[i + 1] === '[') {
      const end = text.indexOf('\\]', i + 2);
      if (end !== -1) {
        const latex = text.slice(i + 2, end);
        out += renderMath(latex, true);
        i = end + 2;
        changed = true;
        continue;
      }
    }
    // Try inline \( ... \)
    if (text[i] === '\\' && text[i + 1] === '(') {
      const end = text.indexOf('\\)', i + 2);
      if (end !== -1) {
        const latex = text.slice(i + 2, end);
        out += renderMath(latex, false);
        i = end + 2;
        changed = true;
        continue;
      }
    }
    out += text[i];
    i++;
  }
  return { changed, html: out };
}

console.log('Reading', INPUT);
const html = readFileSync(INPUT, 'utf8');
console.log(`  ${html.length.toLocaleString()} bytes in`);

const $ = cheerio.load(html, { decodeEntities: false });

let inline = 0, display = 0, nodesTouched = 0;

// Walk all text nodes
$('*').contents().each(function () {
  if (this.type !== 'text') return;
  if (shouldSkip($, this)) return;
  const t = this.data;
  if (!t || (t.indexOf('\\(') === -1 && t.indexOf('\\[') === -1)) return;
  const { changed, html: newHtml } = transformText(t);
  if (changed) {
    // Count before replacing
    inline  += (newHtml.match(/class="katex"(?! katex-display)/g) || []).length;
    display += (newHtml.match(/class="katex-display"/g) || []).length;
    nodesTouched++;
    $(this).replaceWith(newHtml);
  }
});

console.log(`  Rendered: ${inline} inline, ${display} display  (across ${nodesTouched} text nodes)`);

// Drop the client-side KaTeX runtime (keep CSS)
let dropped = 0;
$('script').each(function () {
  const src = $(this).attr('src') || '';
  const code = $(this).html() || '';
  if (src.includes('katex') || code.includes('renderMathInElement')) {
    $(this).remove();
    dropped++;
  }
});
console.log(`  Dropped ${dropped} KaTeX runtime script tag(s)`);

// Mark that SSR ran (small build banner via comment)
const stamp = `<!-- KaTeX SSR: ${new Date().toISOString()}; inline=${inline}, display=${display} -->`;
$('head').append('\n' + stamp + '\n');

const out = $.html();
writeFileSync(OUTPUT, out, 'utf8');
console.log(`  ${out.length.toLocaleString()} bytes out  ->  ${OUTPUT}`);
