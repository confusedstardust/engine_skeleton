import { build } from 'esbuild';
import { mkdir, copyFile, readdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const root = resolve(import.meta.dirname);
const output = join(root, 'dist', 'gesture-sdk', 'v1');
const wasmSource = join(root, 'node_modules', '@mediapipe', 'tasks-vision', 'wasm');
const MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
await mkdir(join(output, 'wasm'), { recursive: true });
await mkdir(join(output, 'models'), { recursive: true });
await build({
  entryPoints: [join(root, 'src/kit/index.ts')],
  outfile: join(output, 'hand-gesture-kit.esm.js'),
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2020',
  legalComments: 'linked',
  sourcemap: false,
});
const wasmFiles = (await readdir(wasmSource)).filter(name => !name.startsWith('.'));
if (!wasmFiles.some(name => name.endsWith('.wasm'))) {
  throw new Error('MediaPipe WASM files were not installed');
}
for (const name of wasmFiles) {
  await copyFile(join(wasmSource, name), join(output, 'wasm', name));
}
// Fetch at build-time; production pages NEVER call this URL.
const response = await fetch(MODEL_URL, { signal: AbortSignal.timeout(45000) });
if (!response.ok) throw new Error('MediaPipe model download failed: HTTP ' + response.status);
const bytes = Buffer.from(await response.arrayBuffer());
if (bytes.length < 100000 || bytes.length > 30000000) throw new Error('Unexpected MediaPipe model size');
await writeFile(join(output, 'models', 'hand_landmarker.task'), bytes);
console.log('SDK resources built:', output, 'model bytes:', bytes.length);
