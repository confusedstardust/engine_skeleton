/* Runs in the opaque sandbox before authored scripts. Storage belongs only to this resource. */
(() => {
  let initial = {};
  try {
    const marker = '#__nos_storage=';
    if (location.hash.startsWith(marker)) {
      const bytes = Uint8Array.from(atob(decodeURIComponent(location.hash.slice(marker.length))), c => c.charCodeAt(0));
      initial = JSON.parse(new TextDecoder().decode(bytes));
      location.hash = '';
    }
  } catch {}
  for (const kind of ['localStorage', 'sessionStorage']) {
    const entries = Array.isArray(initial[kind]) ? initial[kind] : [];
    const values = new Map(entries.filter(row => Array.isArray(row) && row.length === 2 && row.every(v => typeof v === 'string')));
    function publish(next, change) {
      const rows = Array.from(next);
      if (new TextEncoder().encode(JSON.stringify(rows)).length > 256 * 1024)
        throw new DOMException('Resource storage exceeds 256 KB', 'QuotaExceededError');
      values.clear();
      for (const [key, value] of next) values.set(key, value);
      if (parent !== window) parent.postMessage({ type: 'narrativeos-resource-storage', kind, ...change }, '*');
    }
    const methods = {
      getItem: key => values.get(String(key)) ?? null,
      setItem: (key, value) => publish(new Map(values).set(String(key), String(value)), { op: 'set', key: String(key), value: String(value) }),
      removeItem: key => { const next = new Map(values); next.delete(String(key)); publish(next, { op: 'remove', key: String(key) }); },
      clear: () => publish(new Map(), { op: 'clear' }),
      key: index => Array.from(values.keys())[Number(index) >>> 0] ?? null,
    };
    const storage = new Proxy(Object.create(null), {
      get: (_, key) => key === 'length' ? values.size : Object.hasOwn(methods, key) ? methods[key] : values.get(key),
      set: (_, key, value) => { methods.setItem(key, value); return true; },
      deleteProperty: (_, key) => { methods.removeItem(key); return true; },
      ownKeys: () => Array.from(values.keys()),
      getOwnPropertyDescriptor: (_, key) => values.has(key) ? { configurable: true, enumerable: true, writable: true, value: values.get(key) } : undefined,
    });
    Object.defineProperty(window, kind, { value: storage });
  }
})();
