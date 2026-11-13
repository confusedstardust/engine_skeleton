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
let holdDetail = false, releaseDetail;
let detailGate;
const managementRequests = [];
const requests = [];
let submissionRows = [{ id: session.id, display_name: '小明', submitted_at: submittedAt }];
const reads = suffix => requests.filter(r => r.method === 'GET' && r.path.endsWith(suffix)).length;

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const errors = [];
  try {
    const context = await browser.newContext();
    await context.route('**/api/forge/**', async route => {
      const request = route.request(); const path = new URL(request.url()).pathname.replace('/api/forge', ''); const method = request.method();
      requests.push({ path, method });
      if (path.includes('/quiz/assignments') || path === '/quiz/classes') managementRequests.push(path);
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
      else if (path === '/public/jobs/browser-empty/quiz') data = { status: 'NOT_GENERATED', quiz: null, can_manage: true };
      else if (path === '/public/jobs/browser-practice/quiz') data = { status: 'READY', quiz, can_manage: false };
      else if (path === '/public/jobs/browser-job/quiz') data = { status: 'READY', quiz, can_manage: true };
      else if (path === '/jobs/browser-job/quiz' && method === 'PUT') {
        Object.assign(quiz, request.postDataJSON().quiz_plan);
        data = { status: 'READY', quiz };
      }
      else if (path === '/jobs/browser-job/quiz' && method === 'POST') {
        assert.equal(request.postDataJSON().min_questions, 6);
        assert.equal(request.postDataJSON().max_questions, 10);
        data = { status: 'READY', quiz };
      }
      else if (path === '/jobs/browser-job/quiz/assignments') {
        if (method === 'POST') data = { assignment_id: assignment.id, link_id: 'link-one', token: 'share-one', url: `${base}/practice/s/share-one/` };
        else data = { assignments: [assignment] };
      }
      else if (path === '/quiz/classes') data = { classes: [{ id: 'class-one', name: assignment.class_name }] };
      else if (path.endsWith('/share-links')) data = method === 'POST' ? { assignment_id: assignment.id, link_id: 'link-one', token: 'share-one', url: `${base}/practice/s/share-one/` } : { links: [{ id: 'link-one', created_at: submittedAt, revoked_at: null }] };
      else if (path.includes('/qr/')) { await new Promise(resolve => setTimeout(resolve, 700)); return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><rect width="300" height="300" fill="white"/><path d="M20 20h80v80h-80zM200 20h80v80h-80zM20 200h80v80h-80z" fill="black"/></svg>' }); }
      else if (path.endsWith('/submissions')) data = { submissions: submissionRows };
      else if (path.endsWith('/statistics')) data = { ...stats, submitted_count: submissionRows.length };
      else if (path.endsWith('/analyses/latest')) data = { analysis };
      else if (path.endsWith('/analyses')) { analysis = { ...report, status: 'QUEUED', result: null }; data = { id: report.id, created: true }; }
      else if (path === `/quiz/submissions/${session.id}`) { if (holdDetail) await detailGate; submitted = true; data = { ...attempt(), display_name: submissionRows.find(row => row.id === session.id)?.display_name || '小明' }; }
      else data = {};
      return route.fulfill({ json: data });
    });
    const practice = await context.newPage();
    await practice.goto(`${base}/practice/browser-practice/`);
    const firstCard = practice.locator('.quiz-card').first();
    await firstCard.getByRole('radio').nth(1).click();
    await firstCard.getByText('回答错误，正确答案：A', { exact: true }).waitFor();
    assert.equal(await firstCard.locator('.quiz-options .correct').count(), 1);
    assert.equal(await firstCard.locator('.quiz-options .wrong').count(), 1);
    assert.equal(await firstCard.getByRole('radio').first().isDisabled(), true);
    await practice.getByRole('button', { name: '重新作答', exact: true }).click();
    assert.equal(await practice.locator('.quiz-explanation').count(), 0);
    await practice.close();
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
    const setup = await context.newPage();
    await setup.goto(`${base}/practice/browser-empty/`);
    await setup.getByRole('combobox', { name: '题目数', exact: true }).click();
    assert.equal(await setup.getByRole('option').count(), 4);
    await setup.getByRole('option', { name: '15–20 题', exact: true }).click();
    if (output) await setup.screenshot({ path: `${output}/quiz-generation.png`, fullPage: true });
    await setup.close();
    const teacher = await context.newPage(); teacher.on('pageerror', e => errors.push(e.message)); teacher.setDefaultTimeout(10000);
    await teacher.goto(`${base}/practice/browser-job/`);
    await teacher.getByRole('button', { name: '编辑习题', exact: true }).waitFor();
    const beforeCards = await teacher.locator('.classroom-answer-card').count();
    await teacher.getByRole('button', { name: '编辑习题', exact: true }).click();
    assert.equal(await teacher.locator('.classroom-answer-card').count(), beforeCards);
    assert.equal(await teacher.locator('.cq-quiz-summary').count(), 1);
    assert.equal(await teacher.getByRole('combobox', { name: '最少题数', exact: true }).count(), 0);
    await teacher.getByRole('radio', { name: '第 1 题正确答案 B', exact: true }).check();
    if (output) { fs.mkdirSync(output, { recursive: true }); await teacher.screenshot({ path: `${output}/quiz-inline-edit.png`, fullPage: true }); }
    await teacher.setViewportSize({ width: 390, height: 844 });
    assert.equal(await teacher.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    if (output) await teacher.screenshot({ path: `${output}/quiz-inline-edit-mobile.png`, fullPage: true });
    await teacher.setViewportSize({ width: 1280, height: 900 });
    await teacher.getByRole('textbox', { name: '习题标题', exact: true }).fill('教师修改后的习题');
    await teacher.getByRole('textbox', { name: '第 1 题题干', exact: true }).first().fill('教师修改后的题干');
    await teacher.getByRole('button', { name: '保存修改', exact: true }).click();
    await teacher.getByRole('heading', { name: '教师修改后的习题', exact: true }).waitFor();
    await teacher.getByRole('heading', { name: '教师修改后的题干', exact: true }).waitFor();
    await teacher.reload();
    await teacher.getByRole('heading', { name: '教师修改后的题干', exact: true }).waitFor();
    if (output) await teacher.screenshot({ path: `${output}/quiz-toolbar.png`, fullPage: true });
    await teacher.getByRole('combobox', { name: '题目数', exact: true }).click();
    await teacher.getByRole('option', { name: '6–10 题', exact: true }).click();
    await teacher.getByRole('button', { name: '重新生成题目', exact: true }).click();
    await teacher.getByRole('button', { name: '确认', exact: true }).click();
    await teacher.getByRole('button', { name: '编辑习题', exact: true }).waitFor();
    await teacher.getByRole('button', { name: '班级答卷', exact: true }).click();
    await teacher.getByRole('button', { name: '查看答卷', exact: true }).waitFor();
    for (const endpoint of ['/quiz/classes', '/statistics', '/analyses/latest', '/share-links']) assert.equal(reads(endpoint), 0, `${endpoint} must not load on the submissions page`);
    assert.equal(reads('/quiz/assignments'), 1);
    const firstSubmissionReads = reads('/submissions');
    await teacher.waitForTimeout(5500);
    assert.ok(reads('/submissions') > firstSubmissionReads);
    assert.equal(reads('/quiz/assignments'), 1, 'polling submissions must not reload assignments');
    for (const endpoint of ['/quiz/classes', '/statistics', '/analyses/latest', '/share-links']) assert.equal(reads(endpoint), 0);

    const requestsBeforeView = managementRequests.length;
    holdDetail = true;
    detailGate = new Promise(resolve => { releaseDetail = resolve; });
    await teacher.getByRole('button', { name: '查看答卷', exact: true }).click();
    await teacher.getByText('正在读取答卷…', { exact: true }).waitFor();
    assert.equal(await teacher.getByRole('dialog').getByRole('button', { name: '关闭', exact: true }).isEnabled(), true);
    releaseDetail(); holdDetail = false;
    await teacher.getByRole('heading', { name: '小明的答卷', exact: true }).waitFor();
    await teacher.waitForTimeout(5500);
    assert.equal(managementRequests.length, requestsBeforeView, 'viewing a submitted answer must not trigger or poll management endpoints');
    assert.equal(await teacher.locator('[role="dialog"]').getByText('得分').count(), 0);
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    assert.equal(await teacher.getByRole('dialog').count(), 0, 'viewing must not lock the answer dialog');
    await teacher.waitForTimeout(200);
    assert.equal(managementRequests.length, requestsBeforeView, 'closing a read-only answer must not trigger an immediate full refresh');
    const detailReads = reads(`/quiz/submissions/${session.id}`);
    await teacher.getByRole('button', { name: '查看答卷', exact: true }).click();
    await teacher.getByRole('heading', { name: '小明的答卷', exact: true }).waitFor();
    assert.equal(reads(`/quiz/submissions/${session.id}`), detailReads, 'reopening a submitted answer reuses its cached detail');
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    await teacher.getByRole('button', { name: '分享二维码', exact: true }).click();
    await teacher.locator('.classroom-qr-loading').waitFor();
    assert.equal(await teacher.getByText('学生只需填写姓名，提交后查看答案。', { exact: true }).count(), 0);
    await teacher.getByAltText('班级练习分享二维码').waitFor();
    const qrDownload = teacher.waitForEvent('download');
    await teacher.getByRole('button', { name: '下载二维码', exact: true }).click();
    assert.equal((await qrDownload).suggestedFilename(), '班级练习二维码.png');
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    assert.equal(reads('/share-links'), 0, 'opening a QR must not fetch link management');
    const shareManagement = teacher.locator('summary').filter({ hasText: '分享链接管理' });
    await shareManagement.click();
    await teacher.locator('.cq-share-row').first().waitFor();
    assert.equal(reads('/share-links'), 1);
    await shareManagement.click(); await shareManagement.click();
    assert.equal(reads('/share-links'), 1, 'reopening link management reuses cached links');
    await shareManagement.click();
    await teacher.getByRole('button', { name: '学情分析', exact: true }).click();
    await teacher.getByRole('heading', { name: 'AI 教学分析', exact: true }).waitFor();
    const statsReads = reads('/statistics'), reportReads = reads('/analyses/latest');
    assert.equal(statsReads, 1); assert.equal(reportReads, 1);
    await teacher.waitForTimeout(5500);
    assert.equal(reads('/statistics'), statsReads, 'unchanged submissions must not refresh statistics');
    assert.equal(reads('/analyses/latest'), reportReads, 'reports never poll');
    submissionRows = [...submissionRows, { id: 'second-student', display_name: '小红', submitted_at: new Date().toISOString() }];
    await teacher.waitForResponse(response => response.url().endsWith('/statistics'), { timeout: 25000 });
    assert.equal(reads('/statistics'), statsReads + 1, 'a new submission refreshes visible statistics once');
    assert.equal(reads('/analyses/latest'), reportReads);

    await teacher.getByRole('button', { name: '一键 AI 分析', exact: true }).click();
    await teacher.getByRole('button', { name: '分析任务已提交', exact: true }).waitFor();
    const runningReportReads = reads('/analyses/latest');
    await teacher.waitForTimeout(3500);
    assert.equal(reads('/analyses/latest'), runningReportReads, 'a queued analysis must not start report polling');
    analysis = report;
    await teacher.getByRole('button', { name: '刷新分析结果', exact: true }).click();
    await teacher.getByText(report.result.overview, { exact: true }).waitFor();
    assert.equal(reads('/analyses/latest'), runningReportReads + 1);
    analysis = { ...report, id: 'analysis-two' , status: 'FAILED', result: null, stale: false, error: '更新分析暂时失败', previous: { result: report.result, snapshot: report.snapshot, created_at: report.created_at, stale: true, added_count: 1, voided_count: 0 } };
    await teacher.reload();
    await teacher.getByRole('button', { name: '学情分析', exact: true }).click();
    await teacher.getByText('报告生成后新增', { exact: false }).waitFor();
    const reportDownload = teacher.waitForEvent('download');
    await teacher.getByRole('button', { name: '导出分析报告', exact: true }).click();
    const reportPath = await (await reportDownload).path();
    assert.ok(fs.readFileSync(reportPath, 'utf8').includes('数据已变更，请更新分析'));
    assert.equal(await teacher.getByRole('button', { name: '分享给班级', exact: true }).count(), 0);
    await teacher.getByRole('button', { name: '班级答卷', exact: true }).click();
    const hiddenStatsReads = reads('/statistics'), hiddenReportReads = reads('/analyses/latest');
    submissionRows = submissionRows.map((row, i) => i ? row : { ...row, display_name: '姓名更正' });
    await teacher.waitForResponse(response => response.url().endsWith('/submissions'), { timeout: 25000 });
    await teacher.waitForTimeout(200);
    assert.equal(reads('/statistics'), hiddenStatsReads, 'changed submissions only invalidate hidden statistics');
    assert.equal(reads('/analyses/latest'), hiddenReportReads);
    const updatedStats = teacher.waitForResponse(response => response.url().endsWith('/statistics'), { timeout: 10000 });
    await teacher.getByRole('button', { name: '学情分析', exact: true }).click();
    await updatedStats;
    assert.equal(reads('/statistics'), hiddenStatsReads + 1);
    assert.equal(reads('/analyses/latest'), hiddenReportReads, 'reopening analysis does not silently refresh reports');
    await teacher.getByRole('button', { name: '班级答卷', exact: true }).click();
    assert.equal(reads('/quiz/classes'), 0);
    await teacher.getByRole('button', { name: '分享给班级', exact: true }).click();
    await teacher.getByRole('combobox', { name: '班级', exact: true }).click();
    await teacher.getByRole('option', { name: '新建班级', exact: true }).click();
    await teacher.getByRole('textbox', { name: '班级名称', exact: true }).fill('三年级三班');
    await teacher.getByRole('button', { name: '生成分享二维码', exact: true }).last().click();
    await teacher.getByAltText('班级练习分享二维码').waitFor();
    await teacher.getByRole('button', { name: '关闭', exact: true }).click();
    if (output) await teacher.screenshot({ path: `${output}/teacher-analysis.png`, fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: name modal, no pre-submit answers, refresh recovery, incomplete answers, network retry, locked submission, mobile layout, teacher collection/detail, QR, AI dashboard, assignment creation.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
