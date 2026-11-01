// Fixed trusted helper: Docker's archive API cannot copy tmpfs contents.
import { lstatSync, readFileSync } from 'node:fs';

const limits = { 'report.json': 128000, 'index.html': 2000000, 'preview.png': 3000000, 'mobile.png': 3000000 };
const name = process.argv[2];
if (!Object.hasOwn(limits, name)) process.exit(4);
try {
  const path = '/results/' + name;
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.size > limits[name]) process.exit(4);
  const content = readFileSync(path);
  if (content.length > limits[name]) process.exit(4);
  process.stdout.write(content);
} catch (error) {
  process.exit(error.code === 'ENOENT' ? 3 : 4);
}
