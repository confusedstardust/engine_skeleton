"""Synthetic, in-memory UI fixtures; never imports or writes the application's database.

python tests/classroom_quiz_preview.py --port 3022
Point a separate Next dev instance's FORGE_BACKEND_URL to this server.
"""
import argparse
import asyncio
import copy
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse


app = FastAPI()
stamp = datetime(2026, 10, 29, 4, 10, tzinfo=timezone.utc)
prompts = [
    '关于陶渊明在彭泽县署深夜独坐时的核心内心矛盾，下列理解最准确的是？',
    '督邮将至只是陶渊明辞官的直接导火索，他内心早已积累了对官场束缚的倦意。',
    '“不能为五斗米折腰”在叙事中主要体现的是陶渊明怎样的心理转变？',
    '翟氏在故事中只是一个对陶渊明归隐的抱怨者。',
    '陶渊明选择归乡后，如何看待现实生活中的困难？',
    '归隐意味着作者从此不再面对任何生活困难。',
    '文章中关于田园与仕途的对照，主要突出了哪一层含义？',
    '作者对自然生活的向往，与其追求自主选择的人生态度密切相关。',
]
quiz = {'title': '《归去来兮辞》课后习题', 'introduction': '阅读理解', 'questions': []}
for index, prompt in enumerate(prompts):
    judgement = bool(index % 2)
    texts = ['正确', '错误'] if judgement else ['厌倦官场束缚，渴望回归乡土与自然中寻找真实的自我', '担忧家书未回，牵挂家人温饱', '因督邮将至而恐惧惩罚，犹豫是否出逃', '后悔离家出仕，只想立刻辞官回乡享乐']
    quiz['questions'].append({'id': f'q{index + 1}', 'type': 'judgement' if judgement else 'single_choice', 'prompt': prompt,
        'options': [{'id': chr(65 + i), 'text': text} for i, text in enumerate(texts)], 'correct_option_ids': ['A'],
        'explanation': '教师答卷不应显示本段解析', 'knowledge_point': '文本理解', 'difficulty': '基础', 'teaching_tip': '回到文本核对'})

assignments = [
    {'id': 'round-two', 'job_id': 'ui-preview', 'class_id': 'class-one', 'class_name': '高一（2）班', 'name': quiz['title'], 'status': 'OPEN', 'submitted_count': 0, 'quiz_version_id': 'v1', 'created_at': stamp.isoformat()},
    {'id': 'round-one', 'job_id': 'ui-preview', 'class_id': 'class-one', 'class_name': '高一（2）班', 'name': quiz['title'], 'status': 'OPEN', 'submitted_count': 24, 'quiz_version_id': 'v1', 'created_at': (stamp - timedelta(hours=3)).isoformat()},
]
names = ['陈同学', '林同学', '周同学', '李同学', '王同学', '赵同学', '刘同学', '吴同学', '许同学', '杨同学', '郑同学', '孙同学', '沈同学', '冯同学', '徐同学', '朱同学', '蒋同学', '何同学', '马同学', '邓同学', '宋同学', '黄同学', '张同学', '罗同学']
records = [{'id': f'student-{i}', 'display_name': name, 'submitted_at': (stamp - timedelta(minutes=i * 2)).isoformat()} for i, name in enumerate(names)]
counts = [[10, 8, 4, 2], [20, 4], [12, 7, 3, 2], [9, 15], [17, 3, 2, 2], [14, 10], [18, 3, 2, 1], [21, 3]]


def stats(aid):
    result = {'submitted_count': 24 if aid == 'round-one' else 0, 'latest_submission': stamp.isoformat() if aid == 'round-one' else None, 'questions': [], 'knowledge_points': []}
    for q, choices in zip(quiz['questions'], counts):
        number = 24 if aid == 'round-one' else 0
        options = []
        offset = 0
        for option, count in zip(q['options'], choices):
            options.append({**option, 'count': count if number else 0, 'rate': count / number if number else None,
                            'students': [{'id': r['id'], 'name': r['display_name']} for r in records[offset:offset + count]] if number else []})
            offset += count
        result['questions'].append({'id': q['id'], 'type': q['type'], 'prompt': q['prompt'], 'knowledge_point': q['knowledge_point'],
                                   'total': number, 'correct': choices[0] if number else 0, 'incorrect': number - choices[0] if number else 0,
                                   'correct_rate': choices[0] / number if number else None, 'options': options})
    return result


def report(aid):
    if aid != 'round-one':
        return None
    items = [
        {'kind': '共性误区', 'text': '部分学生可能把辞官的直接诱因与长期形成的价值选择混为一谈。讲评时可让学生分别寻找外部事件与人物内心变化的文本依据。', 'question_ids': ['q1', 'q3']},
        {'kind': '优先讲评', 'text': '建议先围绕家庭成员的不同立场组织讨论，再引导学生理解人物选择背后的现实牵挂，避免将人物关系理解为单纯的支持或反对。', 'question_ids': ['q4']},
        {'kind': '知识点回顾', 'text': '将叙事情节中的具体选择与文章的情感主旨对应起来，重点回顾归隐、自主与现实责任之间的关系。', 'question_ids': ['q3', 'q6']},
        {'kind': '教学建议', 'text': '可以设置对照阅读任务，让学生分别用原文解释“为什么离开”与“选择怎样生活”，再交换观点并核对依据。', 'question_ids': ['q1', 'q7']},
        {'kind': '题目质量', 'text': '建议复核人物关系题中的限定词，引导学生区分“部分情节中的态度”与“人物整体作用”，避免因绝对化表述产生误读。', 'question_ids': ['q4']},
    ]
    return {'id': 'report-one', 'status': 'READY', 'created_at': stamp.isoformat(), 'stale': False, 'added_count': 0, 'voided_count': 0,
            'result': {'overview': '本班对归隐主题已有基本理解，主要分歧集中在人物动机与家庭关系的辨析。建议围绕文本证据展开讲评，将情节理解进一步连接到人物的价值选择。', 'items': items},
            'snapshot': {'quiz': quiz, 'statistics': stats(aid), 'attempt_ids': [r['id'] for r in records]}, 'previous': None}


@app.api_route('/{path:path}', methods=['GET', 'POST', 'PATCH', 'DELETE'])
async def fixture(path: str, request: Request):
    bits = path.split('/')
    aid = bits[2] if path.startswith('quiz/assignments/') else 'round-one'
    if path == 'jobs':
        await asyncio.sleep(getattr(app.state, 'jobs_delay', 0))
        if getattr(app.state, 'jobs_failure', False):
            return JSONResponse({'detail': '作品暂时读取失败，请稍后重试。'}, status_code=503)
        if getattr(app.state, 'flow_failure', False):
            return {'jobs': [{'id': 'ui-preview', 'title': '页面验收作品', 'status': 'SUCCEEDED', 'has_published_build': True, 'published_revision': 1, 'created_at': stamp.isoformat()}]}
        return {'jobs': []}
    if path.endswith('/published-flow'):
        await asyncio.sleep(6)
        return JSONResponse({'detail': '流程图暂时读取失败，请稍后重试。'}, status_code=503)
    if path == 'auth/me': return {'id': 'preview-teacher', 'auth_type': 'sso', 'nickname': '教师预览'}
    if path == 'auth/config': return {'mode': 'sso'}
    if path == 'admin/dashboard':
        totals = {key: 0 for key in ['tasks','completed','failed','new_users','active_users','input_tokens','output_tokens','cached_input_tokens','images','tts_characters','credits','settlements','settlements_with_usage','tokens']}
        return {'timezone': 'Asia/Shanghai', 'start': '2026-10-01', 'end': '2026-10-29', 'totals': totals, 'daily': [{'date': '2026-10-29', **totals}]}
    if path == 'admin/users':
        return {'items': [{'id': 'preview-user', 'nickname': '页面验收用户', 'email': 'preview@example.test', 'blocked': False}], 'has_more': False, 'page': 1, 'total': 1, 'total_pages': 1}
    if path == 'admin/me': return {'admin': False}
    if path == 'credits/balance': return {'available': 100, 'total': 100, 'reserved': 0}
    if path == 'community/questions' and request.method == 'POST' and getattr(app.state, 'community_failure', False):
        return JSONResponse({'detail': '发送失败，请稍后重试。你填写的内容已保留。'}, status_code=503)
    if path.startswith('community/') and request.method == 'GET':
        return {'questions': [], 'announcements': [], 'has_more': False}
    if path == 'community': return {'announcements': [], 'questions': []}
    if path.startswith('public/jobs/') and path.endswith('/quiz'): return {'status': 'READY', 'can_manage': True, 'quiz': quiz}
    if path.startswith('jobs/') and path.endswith('/quiz/assignments'):
        if request.method == 'GET':
            await asyncio.sleep(getattr(app.state, 'assignments_delay', 0))
            failures = getattr(app.state, 'assignment_failures', 0)
            if failures:
                app.state.assignment_failures = failures - 1
                return JSONResponse({'detail': '班级练习暂时读取失败，请稍后重试。'}, status_code=503)
            return {'assignments': assignments}
        return {'assignment_id': 'round-one', 'link_id': 'link-one', 'token': 'preview-token', 'url': 'http://127.0.0.1:3021/practice/s/preview-token/', 'reused': True}
    if path == 'quiz/classes': return {'classes': [{'id': 'class-one', 'name': '高一（2）班'}]}
    if '/qr/' in path:
        import qrcode
        import qrcode.image.svg
        image = qrcode.make('http://127.0.0.1:3021/practice/s/preview-token/', image_factory=qrcode.image.svg.SvgPathImage)
        return Response(image.to_string(), media_type='image/svg+xml')
    if path.endswith('/share-links'):
        if request.method == 'GET': return {'links': [{'id': 'link-one', 'created_at': stamp.isoformat(), 'revoked_at': None}]}
        return {'assignment_id': aid, 'link_id': 'link-one', 'token': 'preview-token', 'url': 'http://127.0.0.1:3021/practice/s/preview-token/'}
    if path.endswith('/submissions'): return {'submissions': records if aid == 'round-one' else []}
    if path.endswith('/statistics'): return stats(aid)
    if path.endswith('/analyses/latest'): return {'analysis': report(aid)}
    if path.endswith('/analyses'): return {'id': 'report-one', 'created': False}
    if path.startswith('quiz/submissions/'):
        row = next((r for r in records if r['id'] == bits[2]), records[0])
        answers = {}
        for q, options in zip(quiz['questions'], counts):
            # Alternate correctness to exercise equal-height single-choice and judgement cards.
            selected = 'B' if int(row['id'].split('-')[-1]) % 2 == 0 and int(q['id'][1:]) % 2 else 'A'
            answers[q['id']] = {'selected_option_id': selected, 'is_correct': selected == 'A'}
        return {**row, 'assignment_id': 'round-one', 'assignment_name': quiz['title'], 'assignment_status': 'OPEN', 'status': 'SUBMITTED', 'quiz': quiz, 'answers': answers}
    return {}


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3022)
    parser.add_argument('--jobs-delay', type=float, default=0, help='Delay the in-memory jobs response for loading-state checks')
    parser.add_argument('--assignment-failures', type=int, default=0, help='Fail the first N assignment reads for feedback checks')
    parser.add_argument('--community-failure', action='store_true', help='Simulate a community message failure without writing data')
    parser.add_argument('--jobs-failure', action='store_true')
    parser.add_argument('--assignments-delay', type=float, default=0)
    parser.add_argument('--flow-failure', action='store_true')
    args = parser.parse_args()
    app.state.flow_failure = args.flow_failure
    app.state.jobs_failure = args.jobs_failure
    app.state.assignments_delay = max(0, args.assignments_delay)
    app.state.community_failure = args.community_failure
    app.state.assignment_failures = max(0, args.assignment_failures)
    app.state.jobs_delay = max(0, args.jobs_delay)
    uvicorn.run(app, host='127.0.0.1', port=args.port)
