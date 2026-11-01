import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export async function checkPage(file) {
  const chrome = spawn(process.env.CHROME_PATH || '/usr/bin/chromium', [
    '--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--no-first-run',
    '--remote-debugging-port=9222', '--user-data-dir=/tmp/chrome-profile',
    '--enable-unsafe-swiftshader', 'about:blank',
  ], { stdio: 'ignore', uid: 65532, gid: 65532 });
  let socket;
  const errors = [];
  try {
    let target;
    for (let i = 0; i < 80; i++) {
      try { const response = await fetch('http://127.0.0.1:9222/json/new?about:blank', { method: 'PUT', signal: AbortSignal.timeout(1000) }); target = await response.json(); break; }
      catch { await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    if (!target) throw new Error('Chromium startup failed');
    socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Chromium WebSocket startup timeout')), 5000);
      socket.onopen = () => { clearTimeout(timer); resolve(); };
      socket.onerror = () => { clearTimeout(timer); reject(new Error('Chromium WebSocket startup failed')); };
    });
    let id = 0;
    const pending = new Map();
    socket.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.id && pending.has(data.id)) { pending.get(data.id)(data); pending.delete(data.id); }
      if (data.method === 'Runtime.exceptionThrown') errors.push(String(data.params.exceptionDetails.exception?.description || data.params.exceptionDetails.text).slice(0, 800));
      if (data.method === 'Runtime.consoleAPICalled' && data.params.type === 'error') errors.push(data.params.args.map(arg => arg.value || arg.description).join(' ').slice(0, 800));
    };
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const call = ++id;
      const timer = setTimeout(() => { pending.delete(call); reject(new Error(`CDP timeout: ${method}`)); }, 10000);
      pending.set(call, data => { clearTimeout(timer); if (data.error) reject(new Error(data.error.message)); else resolve(data.result); });
      socket.send(JSON.stringify({ id: call, method, params }));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result?.value;
    };
    await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
    await send('Network.setBlockedURLs', { urls: ['http://*', 'https://*', 'ws://*', 'wss://*'] });
    await send('Emulation.setDeviceMetricsOverride', { width: 1100, height: 800, deviceScaleFactor: 1, mobile: false });
    await send('Page.navigate', { url: pathToFileURL(file).href });
    await new Promise(resolve => setTimeout(resolve, 2000));
    const figure = await evaluate('!!document.querySelector("svg,canvas")');
    const controls = await evaluate('document.querySelectorAll("button,input,select,[role=button],[tabindex]").length');
    const external = await evaluate('Array.from(document.querySelectorAll("script[src],link[href],img[src]")).map(e=>e.src||e.href).filter(u=>/^(https?:|file:)/.test(u))');
    if (external.length) errors.push('Page must be standalone: external resources detected');
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync('/results/preview.png', Buffer.from(shot.data, 'base64'));
    await evaluate('document.querySelector("button,[role=button]")?.click()');
    await evaluate('document.querySelector("[tabindex]")?.focus()');
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await new Promise(resolve => setTimeout(resolve, 300));
    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    await new Promise(resolve => setTimeout(resolve, 300));
    const mobile_overflow = await evaluate('document.documentElement.scrollWidth > innerWidth + 1');
    const mobile = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync('/results/mobile.png', Buffer.from(mobile.data, 'base64'));
    return { errors: errors.slice(0, 20), figure, controls, mobile_overflow, interaction_attempted: true };
  } finally { socket?.close(); chrome.kill('SIGKILL'); }
}
