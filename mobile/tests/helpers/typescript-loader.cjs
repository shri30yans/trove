const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function createLoader(mocks = {}, globals = {}) {
  const cache = new Map();
  function load(file) {
    file = path.resolve(file);
    if (cache.has(file)) return cache.get(file).exports;
    const mod = { exports: {} };
    cache.set(file, mod);
    const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
    vm.runInNewContext(code, { module: mod, exports: mod.exports, process, console, URL, URLSearchParams, Date, Math, Error, TypeError, Promise, Map, Set, AbortController, Headers, setTimeout, clearTimeout,
      require: (name) => mocks[name] ?? (name.startsWith('.') ? load(path.resolve(path.dirname(file), name + '.ts')) : require(name)), ...globals });
    return mod.exports;
  }
  return load;
}
module.exports = { createLoader };
