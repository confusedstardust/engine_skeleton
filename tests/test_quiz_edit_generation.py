from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from tests.test_teacher_ecosystem_quiz import _quiz_plan
from webgal_backend import app as backend
from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import read_json, write_json
from webgal_backend.validators import ValidationFailure


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    write_json(tmp_path / 'state/narrative_plan.json', {'title': '课文'})
    monkeypatch.setattr(backend, '_get_owned_job_or_404', lambda *args: {'id': 'job'})
    monkeypatch.setattr(backend, '_job_dir_or_404', lambda *args: tmp_path)
    return tmp_path


@pytest.mark.parametrize('low,high', [(4, 6), (6, 10), (10, 15), (15, 20)])
def test_generation_range_reaches_background_task(workspace, low, high):
    tasks = BackgroundTasks()
    backend.generate_quiz('job', backend.GenerateQuizRequest(min_questions=low, max_questions=high), tasks, None)
    assert tasks.tasks[0].args == ('job', low, high)
    with pytest.raises(HTTPException) as error:
        backend.generate_quiz('job', backend.GenerateQuizRequest(min_questions=9, max_questions=6), BackgroundTasks(), None)
    assert error.value.status_code == 422


def test_edit_saves_validated_content_and_rejects_bad_answer(workspace):
    plan = _quiz_plan()
    plan['questions'][0]['prompt'] = '教师修改的题目'
    result = backend.update_quiz('job', backend.UpdateQuizRequest(quiz_plan=plan), None)
    assert result['quiz']['questions'][0]['prompt'] == '教师修改的题目'
    invalid = deepcopy(plan)
    invalid['questions'][0]['correct_option_ids'] = ['Z']
    with pytest.raises(HTTPException) as error:
        backend.update_quiz('job', backend.UpdateQuizRequest(quiz_plan=invalid), None)
    assert error.value.status_code == 422
    assert read_json(workspace / 'state/quiz_plan.json') == plan
    write_json(workspace / 'state/quiz_generation.json', {'status': 'RUNNING'})
    with pytest.raises(HTTPException) as error:
        backend.update_quiz('job', backend.UpdateQuizRequest(quiz_plan=plan), None)
    assert error.value.status_code == 409


@pytest.mark.parametrize('low,high,count', [(6, 10, 8), (15, 20, 20)])
def test_pipeline_retries_validation_for_selected_range(workspace, monkeypatch, low, high, count):
    plan = _quiz_plan()
    plan['questions'].extend([{**deepcopy(plan['questions'][0]), 'id': f'q{i}'} for i in range(5, count + 1)])
    pipeline = object.__new__(WebGALPipeline)
    pipeline.store = SimpleNamespace(get=lambda _: {}, job_dir=lambda _: workspace, record_artifact=lambda *args: None)

    def generate(**kwargs):
        assert f'生成 {low}-{high} 道题' in kwargs['user_prompt']
        with pytest.raises(ValidationFailure):
            kwargs['semantic_validator'](_quiz_plan())
        kwargs['semantic_validator'](plan)
        return plan

    monkeypatch.setattr(pipeline, '_call_with_validation', generate)
    assert pipeline.generate_quiz('job', low, high) == plan
