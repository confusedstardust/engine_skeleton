const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('../../forge_frontend_next/node_modules/typescript');

function loadFrontendTs(filename, mocks = {}, cache = new Map()) {
  filename = path.resolve(filename);
  if (cache.has(filename)) return cache.get(filename).exports;
  const loaded = new Module(filename);
  loaded.paths = Module._nodeModulePaths(path.dirname(filename));
  cache.set(filename, loaded);
  const originalRequire = loaded.require.bind(loaded);
  loaded.require = name => {
    if (Object.hasOwn(mocks, name)) return name === 'react' ? { ...originalRequire(name), ...mocks[name] } : mocks[name];
    // Node has no CSS loader. Component behavior tests use stable CSS-module keys;
    // computed styles and layout remain covered by browser tests.
    if (/\.module\.(css|scss)$/.test(name)) {
      const source = path.resolve(path.dirname(filename), name);
      if (!fs.existsSync(source)) throw new Error(`Missing stylesheet: ${source}`);
      return { __esModule: true, default: new Proxy({}, { get: (_, key) => String(key) }) };
    }
    const resolve = Module.createRequire(filename).resolve;
    let resolved;
    try { resolved = resolve(name); }
    catch (error) {
      if (!name.startsWith('.')) throw error;
      resolved = ['.ts', '.tsx'].map(ext => path.resolve(path.dirname(filename), name + ext)).find(fs.existsSync);
      if (!resolved) throw error;
    }
    return /\.tsx?$/.test(resolved) ? loadFrontendTs(resolved, mocks, cache) : originalRequire(name);
  };
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
  });
  loaded._compile(compiled.outputText, filename);
  return loaded.exports;
}

module.exports = { loadFrontendTs };
