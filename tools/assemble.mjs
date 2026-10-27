#!/usr/bin/env node
/**
 * Put Engismart into a Chromosome Angular remote (the mfe-boilerplate-code project).
 *
 *   node tools/assemble.mjs --template <project folder or template .zip> --out <new folder>     build a complete copy
 *   node tools/assemble.mjs --template <your GitLab clone> --in-place                          add Engismart to a clone
 *   options: --remote-name <name>   name the host uses for this remote (default: engismart)
 *            --base-href </mf1/engismart/>   set baseHref + deployUrl in angular.json (the template still has another app's path; ask the platform team)
 *
 * It copies src/app/engismart and edits: federation.config.js, src/app/app.routes.ts, src/app/app.config.ts,
 * src/environments/*.ts (adds engismartUrl), package.json (adds marked + dompurify). Safe to run twice. Node standard library only.
 */
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';

const HERE = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const opt = (name, fallback) => (args.includes(name) ? args[args.indexOf(name) + 1] : fallback);
const template = opt('--template');
const out = opt('--out');
const inPlace = args.includes('--in-place');
const remoteName = opt('--remote-name', 'engismart');
const baseHref = opt('--base-href', '');
if (!template || (!out && !inPlace)) {
  console.error('usage: node tools/assemble.mjs --template <folder|zip> (--out <new folder> | --in-place) [--remote-name engismart]');
  process.exit(2);
}

const report = [];
const SKIP = new Set(['.git', 'node_modules', 'dist', '.angular']);

function read(path) {
  const raw = readFileSync(path, 'utf8');
  return { text: raw.replace(/\r\n/g, '\n'), crlf: raw.includes('\r\n') }; // edits are written for LF; Windows clones (CRLF) are handled
}
function edit(path, label, change) {
  if (!existsSync(path)) return report.push(`MISSING   ${label}: ${path} not found - see docs/MERGE_INSTRUCTIONS.md`);
  const { text, crlf } = read(path);
  const next = change(text);
  if (next === null) return report.push(`already   ${label}`);
  if (next === text) return report.push(`UNCHANGED ${label}: could not find the place to edit - add the lines by hand`);
  writeFileSync(path, crlf ? next.replace(/\n/g, '\r\n') : next);
  report.push(`edited    ${label}`);
}
const copyTree = (src, dst) => cpSync(src, dst, { recursive: true, filter: (p) => !SKIP.has(p.split(/[\\/]/).pop()) });

let root = resolve(template);
let tmp = null;
if (statSync(root).isFile() && root.endsWith('.zip')) {
  tmp = mkdtempSync(join(tmpdir(), 'mfe_'));
  execFileSync('unzip', ['-q', root, '-d', tmp]); // on Windows use a folder instead (extract the zip first)
  const kids = readdirSync(tmp);
  root = kids.length === 1 && !existsSync(join(tmp, 'angular.json')) ? join(tmp, kids[0]) : tmp;
}
if (!existsSync(join(root, 'federation.config.js'))) {
  console.error(`${root} does not look like the Angular remote template (federation.config.js is missing)`);
  process.exit(2);
}
let project = root;
if (!inPlace) {
  project = resolve(out);
  if (existsSync(project) && readdirSync(project).length) {
    console.error(`${project} is not empty`);
    process.exit(2);
  }
  mkdirSync(project, { recursive: true });
  copyTree(root, project);
  report.push(`copied    template -> ${project}`);
}

// 1. our code
copyTree(join(HERE, 'src/app/engismart'), join(project, 'src/app/engismart'));
mkdirSync(join(project, 'docs/engismart'), { recursive: true });
copyTree(join(HERE, 'docs'), join(project, 'docs/engismart'));
cpSync(join(HERE, 'overlay/START_HERE.md'), join(project, 'ENGISMART_START_HERE.md'));
report.push('copied    src/app/engismart, docs/engismart, ENGISMART_START_HERE.md');

// 2. federation.config.js: remote name + expose the routes
edit(join(project, 'federation.config.js'), 'federation.config.js', (t) => {
  if (t.includes("'./Routes'") && t.includes(`name: '${remoteName}'`)) return null;
  let n = t.replace(/name:\s*'[^']*'/, `name: '${remoteName}'`);
  n = n.replace(/exposes:\s*\{[^}]*\}/, "exposes: {\n    './Routes': './src/app/app.routes.ts',\n  }");
  return n;
});

// 2b. angular.json: only when asked (the template carries the path of the app it was copied from)
if (baseHref) {
  edit(join(project, 'angular.json'), 'angular.json (baseHref / deployUrl)', (t) => {
    const n = t.replace(/("baseHref":\s*")[^"]*(")/, `$1${baseHref}$2`).replace(/("deployUrl":\s*")[^"]*(")/, `$1${baseHref}$2`);
    return n;
  });
}

// 3. app.routes.ts: the host loads these
edit(join(project, 'src/app/app.routes.ts'), 'src/app/app.routes.ts', (t) => {
  if (t.includes('engismart')) return null;
  if (/export const routes:\s*Routes\s*=\s*\[\s*\];?/.test(t)) {
    return "// The host loads these with loadRemoteModule('" + remoteName + "', './Routes')\nexport { engismartRoutes as routes } from './engismart/engismart.routes';\n";
  }
  return t; // not the empty template: reported as UNCHANGED
});

// 3b. app.html: the template's placeholder page would show above our routes when the remote runs on its own
edit(join(project, 'src/app/app.html'), 'src/app/app.html', (t) => (t.includes('Delete the template below') ? '<router-outlet />\n' : null));

// 3c. app.scss: only used when the remote runs on its own (full height, a normal font); the host never loads App
edit(join(project, 'src/app/app.scss'), 'src/app/app.scss', (t) =>
  t.includes('--engismart') || t.trim() !== '' ? null : ':host { display: block; height: 100vh; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; /* --engismart standalone */ }\n');

// 4. app.config.ts: dev-only token for `ng serve` (the host's interceptor does it when hosted)
edit(join(project, 'src/app/app.config.ts'), 'src/app/app.config.ts', (t) => {
  if (t.includes('devTokenInterceptor')) return null;
  let n = t.replace("import { provideHttpClient } from '@angular/common/http';",
    "import { provideHttpClient, withInterceptors } from '@angular/common/http';\nimport { devTokenInterceptor } from './engismart/core/dev-token.interceptor';");
  n = n.replace('provideHttpClient()', 'provideHttpClient(withInterceptors([devTokenInterceptor]))');
  return n;
});

// 5. environments: engismartUrl next to apiUrl (the gateway path is an assumption: confirm it with the team)
for (const f of readdirSync(join(project, 'src/environments')).filter((x) => x.endsWith('.ts'))) {
  edit(join(project, 'src/environments', f), `src/environments/${f}`, (t) => {
    if (t.includes('engismartUrl')) return null;
    const m = t.match(/^\s*apiUrl:\s*['"]((?:https?:\/\/[^/'"]+)?)([^'"]*?)\/api\/v1\/?['"]/m);
    const base = m ? `${m[1]}${m[2]}` : '';
    const line = `    // Engismart backend (assumed gateway path /engismart/api/v1 + module prefix /engismart: confirm with the platform team)\n    engismartUrl: '${base}/engismart/api/v1/engismart',\n`;
    return t.replace(/(export const environment\s*=\s*\{\n)/, `$1${line}`);
  });
}

// 6. package.json: two small libraries for the answer text
edit(join(project, 'package.json'), 'package.json', (t) => {
  const pkg = JSON.parse(t);
  if (pkg.dependencies?.marked && pkg.dependencies?.dompurify) return null;
  pkg.dependencies = { ...pkg.dependencies, dompurify: '^3.2.0', marked: '^15.0.0' };
  pkg.dependencies = Object.fromEntries(Object.entries(pkg.dependencies).sort(([a], [b]) => a.localeCompare(b)));
  return JSON.stringify(pkg, null, 2) + '\n';
});

if (tmp) rmSync(tmp, { recursive: true, force: true });
console.log(report.join('\n'));
console.log('Next: npm install && npm run build   (see docs/MERGE_INSTRUCTIONS.md)');
