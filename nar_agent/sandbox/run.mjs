// Trusted entrypoint, used only inside a disposable network-disabled container.
import { writeFileSync, renameSync, lstatSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { checkPage } from './browser-check.mjs';
setTimeout(() => { console.error('sandbox watchdog: 105s limit'); process.exit(124); }, 105000);

const source = Buffer.from(process.argv[2] || '', 'base64').toString('utf8');
const report = { passed: false, stage: 'source', checks: {}, visual_review: 'not_performed', teaching_review: 'not_performed' };
try {
  if (!source || Buffer.byteLength(source) > 96000) throw new Error('Invalid build source size');
  writeFileSync('/work/build.mjs', source);
  console.log('sandbox phase: build');
  report.stage = 'build';
  const build = spawnSync(process.execPath, ['/work/build.mjs'], {
    cwd: '/work', timeout: 45000, maxBuffer: 128000,
    uid: 65532, gid: 65532,
    env: { PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp', LANG: 'C.UTF-8' },
  });
  report.build_exit = build.status;
  report.build_signal = build.signal;
  report.build_error = build.error?.message;
  report.build_log = `${build.stdout || ''}\n${build.stderr || ''}`.slice(-12000);
  if (build.status !== 0) throw new Error('Build failed');
  const file = lstatSync('/work/index.html');
  if (!file.isFile() || file.size > 2000000) throw new Error('Expected regular index.html <= 2MB');
  console.log('sandbox phase: browser-check');
  report.stage = 'browser-check';
  report.checks = await checkPage('/work/index.html');
  report.passed = report.checks.errors.length === 0 && report.checks.figure && report.checks.controls > 0 && !report.checks.mobile_overflow;
  if (report.passed) writeFileSync('/results/index.html', readFileSync('/work/index.html'));
} catch (error) { report.error = String(error.message).slice(0, 2000); }
// Generated code cannot write /results or forge the completion report.
writeFileSync('/results/report.tmp', JSON.stringify(report));
renameSync('/results/report.tmp', '/results/report.json');
console.log('sandbox phase: report-ready');
console.log(JSON.stringify({ passed: report.passed }));
// Keep tmpfs alive until the broker has copied results and removes the container.
setTimeout(() => process.exit(report.passed ? 0 : 1), 115000);
