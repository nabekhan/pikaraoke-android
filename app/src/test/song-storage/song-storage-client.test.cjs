const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const template = fs.readFileSync(
  path.join(__dirname, '../../../build/generated/python/pikaraoke/templates/partials/song_storage.html'), 'utf8'
);
const script = template.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/\{\{\s*_\('([^']+)'\)\s*\|\s*tojson\s*\}\}/g, (_, text) => JSON.stringify(text))
  .replace("{{ url_for('preferences.change_preferences') | tojson }}", JSON.stringify('/api/change_preferences'));
const markup = template.replace(/<script>[\s\S]*?<\/script>/, '').replace(/\{%[\s\S]*?%\}/g, '');
assert(!script.includes('{{'));

function fixture(saved) {
  const dom = new JSDOM(markup.replace('{{ max_song_storage_bytes }}', String(saved)), { runScripts: 'outside-only' });
  const { window } = dom;
  const posts = [];
  window.$ = callback => callback();
  window.$.post = (url, data) => {
    posts.push({ url, ...data });
    const result = {
      done(callback) { callback([true, 'saved']); return result; },
      fail() { return result; },
      always(callback) { callback(); return result; },
    };
    return result;
  };
  window.showNotification = () => {};
  window.eval(script);
  window.eval(script); // SPA insertion and script replay must bind only once.
  const input = window.document.getElementById('song-storage-limit');
  const unit = window.document.getElementById('song-storage-unit');
  const save = () => window.document.getElementById('song-storage-form').dispatchEvent(
    new window.Event('submit', { cancelable: true })
  );
  return { dom, window, posts, input, unit, save };
}

for (const [saved, value, unit] of [[0, '0', '1000000000'], [500000000, '500', '1000000'], [1500000000, '1.5', '1000000000']]) {
  const f = fixture(saved);
  assert.equal(f.input.value, value);
  assert.equal(f.unit.value, unit);
  assert.equal(f.posts.length, 0, 'Opening settings must not save or prune');
  f.dom.window.close();
}

const f = fixture(0);
for (const [value, unit, expected] of [['1.5', '1000000000', '1500000000'], ['250', '1000000', '250000000'], ['0', '1000000000', '0']]) {
  f.input.value = value;
  f.unit.value = unit;
  const before = f.posts.length;
  f.save();
  assert.equal(f.posts.length, before + 1, 'One save after SPA script replay sends one request');
  assert.deepEqual(f.posts.at(-1), { url: '/api/change_preferences', pref: 'max_song_storage_bytes', val: expected });
}
const count = f.posts.length;
for (const invalid of ['-1', '', '100000000000']) {
  f.input.value = invalid;
  f.save();
  assert.equal(f.posts.length, count);
  assert(f.input.validationMessage);
}
f.unit.dispatchEvent(new f.window.Event('change'));
assert.equal(f.input.validationMessage, '');
assert.equal(f.window.document.querySelector('button').disabled, false);
f.dom.window.close();
console.log('Song storage UI: MB/GB conversion, explicit save, disabled default and invalid limits passed');
