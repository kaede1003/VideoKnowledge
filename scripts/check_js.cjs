'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
function walk(dir) {
  return fs.readdirSync(dir, {withFileTypes:true}).flatMap(e => e.isDirectory() ? walk(path.join(dir,e.name)) : /\.(js|cjs)$/.test(e.name) ? [path.join(dir,e.name)] : []);
}
let failures = 0, count = 0;
for (const dir of ['extension', 'scripts', 'tests']) for (const file of walk(path.join(root,dir))) {
  const result = spawnSync(process.execPath, ['--check',file], {stdio:'inherit'});
  if (result.status !== 0 || result.error) failures++;
  count++;
}
console.log(`JavaScript syntax: ${count} files, ${failures} failures.`);
process.exit(failures ? 1 : 0);
