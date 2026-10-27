/** Section 34 static accessibility smoke tests. Run: node tests/section34-ui.mjs */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const shell=readFileSync(resolve(root,'components/Shell.tsx'),'utf8');
const css=readFileSync(resolve(root,'app/styles.css'),'utf8');
const layout=readFileSync(resolve(root,'app/layout.tsx'),'utf8');
assert.match(shell,/className="skipLink" href="#main-content"/);
assert.match(shell,/<main className="main" id="main-content" tabIndex=\{-1\}>/);
assert.match(shell,/aria-label="ناوبری مدیریت"/);
assert.match(shell,/aria-current=/);
assert.match(css,/:focus-visible/);
assert.match(css,/prefers-reduced-motion:reduce/);
assert.match(css,/\.sidebar nav\{overflow-x:auto;overflow-y:hidden;max-height:none/);
assert.match(layout,/dir=\{lang==='en'\?'ltr':'rtl'\}/);
console.log('PASS section34 static accessibility smoke checks');
