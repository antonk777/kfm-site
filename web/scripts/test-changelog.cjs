const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

const filename = path.resolve(__dirname, '../src/lib/changelog.ts');
const compiled = new Module(filename, module);
compiled.filename = filename;
compiled.paths = module.paths;
compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, filename);
const { groupNotes, previewGroups } = compiled.exports;

const entries = [
  { when: '17.11.2026 12:00', en: 'Removed map.', ru: 'Карта удалена.' },
  { when: '17.11.2026 09:00', en: 'Added weapon.', ru: 'Добавлено оружие.' },
  { when: '16.11.2026 10:00', en: 'Bug fix.' },
  { when: '14.11.2026 10:00', en: 'New effects.' },
  { when: '01.11.2026 10:00', en: 'Archive.' },
];
const summaries = [
  { day: '17.11.2026', en: 'A new weapon joins the trader.', ru: 'У торговца новое оружие.' },
  { day: '16.11.2026', en: '', ru: '' },
  { day: '14.11.2026', en: 'Blood effects have been redesigned.' },
];
const groups = groupNotes(entries, 'ru', summaries);
assert.equal(groups[0].day, '17 ноября 2026');
assert.equal(groups[0].summary, 'У торговца новое оружие.');
assert.deepEqual(groups[0].notes, ['Карта удалена.', 'Добавлено оружие.']);
assert.equal(groups[1].summary, '');
assert.equal(groups[2].summary, 'Blood effects have been redesigned.');
assert.equal(groups[3].summary, '');
assert.equal(groups.reduce((count, group) => count + group.notes.length, 0), entries.length);
const preview = previewGroups(entries, 'en', 1, summaries);
assert.equal(preview.length, 1);
assert.equal(preview[0].notes.length, 2, 'A preview retains the complete day, not a truncated list');
assert.equal(previewGroups(entries, 'en', 3, summaries).length, 2, 'Fix-only and archive days stay out of the highlights');
assert.equal(groupNotes(entries, 'en').flatMap((group) => group.notes).length, entries.length, 'Old deployed JSON still has every note');
console.log('Changelog grouping, localization, archive and preview checks passed.');
