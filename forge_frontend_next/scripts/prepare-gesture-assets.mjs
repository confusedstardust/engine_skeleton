import {copyFileSync,cpSync,existsSync,mkdirSync,readFileSync,readdirSync,statSync,writeFileSync} from "node:fs";
import {resolve,join} from "node:path";

const root = process.cwd();
const manifestSource = [
  resolve(root,"../nar_agent/gesture/manifest.v0.2.json"),
  resolve(root,"gesture-input/manifest.v0.2.json")
].find(existsSync);
if (!manifestSource) throw new Error("Gesture Manifest missing in monorepo / Docker build context");
const dest = resolve(root,"public/gesture");
mkdirSync(dest,{recursive:true});
copyFileSync(manifestSource,join(dest,"manifest.v0.2.json"));

const wasmSource = resolve(root,"node_modules/@mediapipe/tasks-vision/wasm");
const wasmDest = join(dest,"wasm");
if (!existsSync(wasmSource)) throw new Error("Pinned @mediapipe/tasks-vision WASM assets missing");
mkdirSync(wasmDest,{recursive:true});
for(const name of readdirSync(wasmSource)) {
  if (/^vision_wasm.*\.(wasm|js)$/.test(name)) copyFileSync(join(wasmSource,name),join(wasmDest,name));
}
const model = join(dest,"hand_landmarker.task");
const modelUrl = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
if (!existsSync(model) || statSync(model).size < 100000) {
  // Download only at build/setup time; end-user camera frames never go to the network.
  const response = await fetch(modelUrl,{signal:AbortSignal.timeout(60000)});
  if (!response.ok) throw new Error("Unable to download pinned MediaPipe hand model: HTTP " + response.status);
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length < 100000 || bytes.length > 20000000) throw new Error("Unexpected hand model size");
  writeFileSync(model,bytes);
}
const manifest = JSON.parse(readFileSync(join(dest,"manifest.v0.2.json"),"utf8"));
if (manifest.schemaVersion !== "0.2.0" || manifest.gestures.length !== 4) throw new Error("Gesture manifest version/count drift");
console.log("Prepared self-hosted gesture assets");
