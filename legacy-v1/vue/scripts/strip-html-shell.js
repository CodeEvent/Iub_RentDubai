#!/usr/bin/env node
// Strips the <!doctype>/<html>/<head>/<body> wrapper tags (and the
// charset/viewport meta the wrapper always supplies) from the
// single-file preview build, leaving just page content — the format
// artifact-hosting tools that supply their own document skeleton
// expect. Run after `npm run build:preview`.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const inputPath = path.join(__dirname, '..', 'dist-preview', 'index.html');
const outputPath = path.join(__dirname, '..', 'dist-preview', 'content-only.html');

const html = fs.readFileSync(inputPath, 'utf-8');

const headMatch = html.match(/<head>([\s\S]*?)<\/head>/);
const bodyMatch = html.match(/<body>([\s\S]*?)<\/body>/);
if (!headMatch || !bodyMatch) {
  console.error('Could not find <head>/<body> in', inputPath);
  process.exit(1);
}

let headInner = headMatch[1]
  .replace(/<meta charset="UTF-8">\s*/, '')
  .replace(/<meta name="viewport"[^>]*>\s*/, '');

const out = `${headInner.trim()}\n\n${bodyMatch[1].trim()}\n`;
fs.writeFileSync(outputPath, out, 'utf-8');
console.log(`Wrote ${outputPath} (${out.length} chars) — publish this file's content, not dist-preview/index.html.`);
