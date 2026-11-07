'use strict';
// Avoid shell globs so every *.test.js is discovered on Windows and Linux.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const tests = fs.readdirSync(path.join(root, 'tests')).filter(n => n.endsWith('.test.js')).sort();
if (!tests.length) { console.error('No JavaScript tests found.'); process.exit(2); }
const run = spawnSync(process.execPath, ['--test', ...tests.map(n => path.join('tests', n))], {cwd: root, stdio: 'inherit'});
if (run.error) { console.error(run.error.message); process.exit(2); }
process.exit(run.status === null ? 2 : run.status);
