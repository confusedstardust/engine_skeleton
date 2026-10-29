const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.CLASSROOM_TEST_URL || 'http://127.0.0.1:3017';
const output = process.env.CLASSROOM_SCREENSHOT_DIR;
const quiz = { title: '材料理解课后习题', introduction: '围绕文本中的概念展开练习。', questions: Array.from({ length: 4 }, (_, i) => ({
  id: `q${i + 1}`, type: i % 2 ? 'judgement' : 'single_choice', prompt: `请判断材料中的概念关系（${i + 1}）`,
  options: (i % 2 ? ['正确', '错误'] : ['符合材料', '混淆概念', '忽略条件', '改变范围']).map((text, j) => ({ id: 'ABCD'[j], text })),
  correct_option_ids: ['A'], explanation: '应结合材料中的条件和范围理解概念。', knowledge_point: '概念理解', difficulty: '基础', teaching_tip: '请说明判断依据。',
})) };
const assignment = { id: 'assignment-one', job_id: 'browser-job', class_id: 'class-one', class_name: '三年级二班', name: quiz.title, status: 'OPEN', submitted_count: 1, quiz_version_id: 'version-one', created_at: new Date().toISOString() };
const session = { id: 'student-one', credential: 'test-credential-long-enough' };
const submittedAt = new Date().toISOString();
let submitted = false, failSubmit = true;
const answers = Object.fromEntries(quiz.questions.map(q => [q.id, { selected_option_id: 'A', is_correct: true }]));
const attempt = () => ({ id: session.id, assignment_id: assignment.id, assignment_name: assignment.name, assignment_status: assignment.status, display_name: '小明', status: submitted ? 'SUBMITTED' : 'DRAFT', submitted_at: submitted ? submittedAt : null,
  quiz: submitted ? quiz : { ...quiz, questions: quiz.questions.map(({ id, type, prompt, options }) => ({ id, type, prompt, options })) }, answers: submitted ? answers : {} });
const stats = { submitted_count: 1, latest_submission: submittedAt, questions: quiz.questions.map(q => ({ ...q, total: 1, correct: 1, incorrect: 0, correct_rate: 1, options: q.options.map(o => ({ ...o, count: o.id === 'A' ? 1 : 0, rate: o.id === 'A' ? 1 : 0, students: o.id === 'A' ? [{ id: session.id, name: '小明' }] : [] })) })), knowledge_points: [{ name: '概念理解', question_ids: quiz.questions.map(q => q.id), total: 4, correct: 4, correct_rate: 1 }] };
const report = { id: 'analysis-one', status: 'READY', created_at: submittedAt, stale: false, added_count: 0, voided_count: 0, snapshot: { quiz, statistics: stats, attempt_ids: [session.id] }, result: { overview: '概念辨析需要结合原文检查。', items: ['共性误区', '优先讲评', '知识点回顾', '教学建议', '题目质量'].map(kind => ({ kind, text: '建议引导学生说明依据，并回到材料核对。', question_ids: ['q1'] })) }, previous: null };
let analysis = null;

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const errors = [];
  try {
    const context = await browser.newContext();
    await context.route('**/api/forge/**', async route => {
      const request = route.request(); const path = new URL(request.url()).pathname.replace('/api/forge', ''); const method = request.method();
      let data;
      if (path === '/auth/me') data = { id: 'teacher', auth_type: 'sso', nickname: '教师' };
      else if (path === '/auth/config') data = { mode: 'sso' };
      else if (path === '/admin/me') data = { admin: false };
      else if (path === '/credits/balance') data = { available: 100, total: 100, reserved: 0 };
      else if (path === '/public/quiz/share-one') data = { name: assignment.name, status: 'OPEN' };
      else if (path.endsWith('/join')) data = session;
      else if (path.endsWith('/submit')) {
        if (failSubmit) { failSubmit = false; return route.fulfill({ status: 503, json: { detail: '网络暂不可用，答案已保留' } }); }
        assert.equal(request.postDataJSON().answers.length, 4); submitted = true; data = attempt();
      }
      else if (path === `/public/quiz/attempts/${session.id}`) data = attempt();
      else if (path === '/public/jobs/browser-job/quiz') data = { status: 'READY', quiz, can_manage: true };
      else if (path === '/jobs/browser-job/quiz/assignments') {
        if (method === 'POST') data = { assignment_id: assignment.id, link_id: 'link-one', token: 'share-one', url: `${base}/practice/s/share-one/` };
        else data = { assignments: [assignment] };
      }
      else if (path === '/quiz/classes') data = { classes: [{ id: 'class-one', name: assignment.class_name }] };
      else if (path.endsWith('/share-links')) data = method === 'POST' ? { assignment_id: assignment.id, link_id: 'link-one', token: 'share-one', url: `${base}/practice/s/share-one/` } : { links: [{ id: 'link-one', created_at: submittedAt, revoked_at: null }] };
      else if (path.includes('/qr/')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="300" height="300" fill="white"/><path d="M20 20h80v80h-80zM200 20h80v80h-80zM20 200h80v80h-80z" fill="black"/></svg>' });
      else if (path.endsWith('/submissions')) data = { submissions: [{ id: session.id, display_name: '小明', submitted_at: submittedAt }] };
      else if (path.endsWith('/statistics')) data = stats;
      else if (path.endsWith('/analyses/latest')) data = { analysis };
      else if (path.endsWith('/analyses')) { analysis = report; data = { id: report.id, created: true }; }
      else if (path === `/quiz/submissions/${session.id}`) { submitted = true; data = attempt(); }
      else data = {};
      return route.fulfill({ json: data });
    });
    const student = await context.newPage(); student.on('pageerror', e => errors.push(e.message));
    student.setDefaultTimeout(10000);
    await student.goto(`${base}/practice/s/share-one/`);
    await student.getByRole('textbox', { name: '姓名', exact: true }).fill('小明');
    assert.equal(await student.getByText('确认班级').count(), 0);
    await student.getByRole('button', { name: '开始答题', exact: true }).click();
    await student.locator('#question-q1').getByRole('radio').first().click();
    await student.reload();
    await student.locator('#question-q1 [aria-checked="true"]').waitFor();
    assert.equal(await student.locator('.quiz-explanation').count(), 0);
    await student.getByRole('button', { name: '更换作答人', exact: true }).click();
    await student.getByRole('button', { name: '确认', exact: true }).click();
    await student.getByRole('textbox', { name: '姓名', exact: true }).fill('小明');
    await student.getByRole('button', { name: '开始答题', exact: true }).click();
    await student.locator('#question-q1').waitFor();
    assert.equal(await student.locator('[aria-checked="true"]').count(), 0);
    await student.getByRole('button', { name: '提交答卷', exact: true }).click();
    await student.getByRole('alert').filter({ hasText: '请完成全部题目' }).waitFor();
    for (const q of quiz.questions) await student.locator(`#question-${q.id}`).getByRole('radio').first().click();
    await student.getByRole('button', { name: '提交答卷', exact: true }).click();
    await student.getByRole('alert').filter({ hasText: '网络暂不可用' }).waitFor();
    assert.equal(await student.locator('[aria-checked="true"]').count(), 4);
    await student.getByRole('button', { name: '提交答卷', exact: true }).click();
    await student.getByText('提交成功', { exact: true }).waitFor();
    assert.equal(await student.locator('.quiz-explanation').count(), 4);
    assert.equal(await student.getByRole('button', { name: '提交答卷', exact: true }).count(), 0);
    await student.reload(); await student.getByText('提交成功', { exact: true }).waitFor();
    await student.setViewportSize({ width: 390, height: 844 });
    assert.equal(await student.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (output) { fs.mkdirSync(output, { recursive: true }); await student.screenshot({ path: `${output}/student-submitted.png`, fullPage: true }); }
    assert.equal(await student.getByRole('button', { name: '下一位同学使用本设备', exact: true }).count(), 0);
    const teacher = await context.newPage(); teacher.on('pageerror', e => errors.push(e.message)); teacher.setDefaultTimeout(10000);
    await teacher.goto(`${base}/practice/browser-job/`);
    await teacher.getByRole('button', { name: '班级答卷', exact: true }).click();
    await teacher.getByRole('button', { name: '查看答卷', exact: true }).click();
    await teacher.getByRole('heading', { name: '小明的答卷', exact: true }).waitFor();
    assert.equal(await teacher.locator('[role="dialog"]').getByText('得分').count(), 0);
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    await teacher.getByRole('button', { name: '分享二维码', exact: true }).click();
    await teacher.getByAltText('班级练习分享二维码').waitFor();
    const qrDownload = teacher.waitForEvent('download');
    await teacher.getByRole('button', { name: '下载二维码', exact: true }).click();
    assert.equal((await qrDownload).suggestedFilename(), '班级练习二维码.png');
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    await teacher.getByRole('button', { name: '学情分析', exact: true }).click();
    await teacher.getByRole('button', { name: '一键 AI 分析', exact: true }).click();
    await teacher.getByRole('heading', { name: 'AI 教学分析', exact: true }).waitFor();
    analysis = { ...report, id: 'analysis-two', status: 'FAILED', result: null, stale: false, error: '更新分析暂时失败', previous: { result: report.result, snapshot: report.snapshot, created_at: report.created_at, stale: true, added_count: 1, voided_count: 0 } };
    await teacher.reload();
    await teacher.getByRole('button', { name: '学情分析', exact: true }).click();
    await teacher.getByText('报告生成后新增', { exact: false }).waitFor();
    const reportDownload = teacher.waitForEvent('download');
    await teacher.getByRole('button', { name: '导出分析报告', exact: true }).click();
    const reportPath = await (await reportDownload).path();
    assert.ok(fs.readFileSync(reportPath, 'utf8').includes('数据已变更，请更新分析'));
    assert.equal(await teacher.getByRole('button', { name: '分享给班级', exact: true }).count(), 0);
    await teacher.getByRole('button', { name: '班级答卷', exact: true }).click();
    await teacher.getByRole('button', { name: '分享给班级', exact: true }).click();
    await teacher.getByLabel('班级', { exact: true }).selectOption('');
    await teacher.getByRole('textbox', { name: '班级名称', exact: true }).fill('三年级三班');
    await teacher.getByRole('button', { name: '生成分享二维码', exact: true }).last().click();
    await teacher.getByAltText('班级练习分享二维码').waitFor();
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    if (output) await teacher.screenshot({ path: `${output}/teacher-analysis.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: name modal, no pre-submit answers, refresh recovery, incomplete answers, network retry, locked submission, mobile layout, teacher collection/detail, QR, AI dashboard, assignment creation.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
