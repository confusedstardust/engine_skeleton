/* Trusted parent: accept writes only from its own iframe, to one resource namespace. */
(() => {
  const frame = document.querySelector('iframe[data-resource]');
  const key = `narrativeos-resource:${frame.dataset.resource}:`;
  const initial = {};
  for (const kind of ['localStorage', 'sessionStorage']) {
    try { initial[kind] = JSON.parse(window[kind].getItem(key + kind) || '[]'); }
    catch { initial[kind] = []; }
  }

  window.addEventListener('message', event => {
    if (event.source !== frame.contentWindow || event.origin !== 'null') return;
    const data = event.data;
    if (!data || data.type !== 'narrativeos-resource-storage' || !['localStorage', 'sessionStorage'].includes(data.kind)) return;
    if (!['set', 'remove', 'clear'].includes(data.op)) return;
    if (data.op !== 'clear' && typeof data.key !== 'string') return;
    if (data.op === 'set' && typeof data.value !== 'string') return;
    let current;
    try { current = new Map(JSON.parse(window[data.kind].getItem(key + data.kind) || '[]')); }
    catch { current = new Map(); }
    if (data.op === 'set') current.set(data.key, data.value);
    if (data.op === 'remove') current.delete(data.key);
    if (data.op === 'clear') current.clear();
    const serialized = JSON.stringify(Array.from(current));
    if (new TextEncoder().encode(serialized).length > 256 * 1024) return;
    try { window[data.kind].setItem(key + data.kind, serialized); }
    catch { console.warn('This browser could not persist resource storage.'); }
  });
  const bytes = new TextEncoder().encode(JSON.stringify(initial));
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 32768)
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  frame.src = frame.dataset.src + '#__nos_storage=' + encodeURIComponent(btoa(binary));
})();
