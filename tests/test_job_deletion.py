import io
from contextlib import nullcontext
from urllib.error import HTTPError

import pytest
from fastapi import HTTPException
import webgal_backend.app as backend
from webgal_backend.storage import JobStore
import webgal_backend.teacher_ecosystem as ecosystem


@pytest.fixture
def task(tmp_path, monkeypatch):
    store = JobStore(tmp_path / "jobs")
    job = store.create("test", {}, {"type": "sso", "user_id": "owner"})
    monkeypatch.setattr(backend, "store", store)
    monkeypatch.setattr(backend, "_identity_from_request", lambda request: {"type": "sso", "user_id": "owner"})
    monkeypatch.setattr(backend.classroom_quiz, "has_assignments", lambda job_id: False)
    monkeypatch.setattr(backend.classroom_quiz, 'job_guard', lambda job_id: nullcontext())
    monkeypatch.delenv("TEACHER_ECOSYSTEM_API_URL", raising=False)
    return store, job


def test_delete_hides_task_and_blocks_stale_writes_and_play(task):
    store, job = task
    path = store.job_file(job["id"])
    assert backend.delete_owned_job(job["id"], None) == {"deleted": True}
    assert path.exists()  # Keep source files and accounting references.
    with pytest.raises(FileNotFoundError):
        store.get(job["id"])
    with pytest.raises(FileNotFoundError):
        store.save(job)
    with pytest.raises(HTTPException) as error:
        backend.play_game_with_slash(job["id"])
    assert error.value.status_code == 404


def test_classroom_exercises_block_deletion_before_unpublishing(task, monkeypatch):
    store, job = task
    monkeypatch.setattr(backend.classroom_quiz, 'has_assignments', lambda job_id: True)
    monkeypatch.setattr(backend, 'unpublish_work', lambda *args: pytest.fail('must not unpublish'))
    with pytest.raises(HTTPException) as error:
        backend.delete_owned_job(job['id'], None)
    assert error.value.status_code == 409
    assert store.get(job['id'])


@pytest.mark.parametrize("status,build", [("RUNNING", "NONE"), ("QUEUED", "NONE"), ("DONE", "BUILDING")])
def test_cannot_delete_active_task(task, status, build):
    store, job = task
    job.update(status=status, build_state=build)
    store.save(job)
    with pytest.raises(HTTPException) as error:
        backend.delete_owned_job(job["id"], None)
    assert error.value.status_code == 409
    assert store.get(job["id"])


def test_cannot_delete_another_users_task(task, monkeypatch):
    store, job = task
    monkeypatch.setattr(backend, "_identity_from_request", lambda request: {"type": "sso", "user_id": "other"})
    with pytest.raises(HTTPException) as error:
        backend.delete_owned_job(job["id"], None)
    assert error.value.status_code == 404
    assert store.get(job["id"])


def test_unpublish_failure_keeps_task(task, monkeypatch):
    store, job = task
    (store.job_dir(job["id"]) / "public/game/config.txt").write_text("test")
    monkeypatch.setenv("TEACHER_ECOSYSTEM_API_URL", "https://example.invalid")
    def fail(*args):
        raise backend.TeacherEcosystemError("offline")
    monkeypatch.setattr(backend, "unpublish_work", fail)
    with pytest.raises(HTTPException) as error:
        backend.delete_owned_job(job["id"], None)
    assert error.value.status_code == 503
    assert store.get(job["id"])


def test_unpublish_before_deleting(task, monkeypatch):
    store, job = task
    (store.job_dir(job["id"]) / "public/game/config.txt").write_text("test")
    monkeypatch.setenv("TEACHER_ECOSYSTEM_API_URL", "https://example.invalid")
    calls = []
    def unpublish(owner, job_id):
        assert store.get(job_id)
        calls.append((owner, job_id))
    monkeypatch.setattr(backend, "unpublish_work", unpublish)
    backend.delete_owned_job(job["id"], None)
    assert calls == [("owner", job["id"])]
    with pytest.raises(FileNotFoundError):
        store.get(job["id"])


@pytest.mark.parametrize("remote_status", [404, 401, 403, 500, 503])
def test_delete_handles_real_ecosystem_http_errors(task, monkeypatch, remote_status):
    store, job = task
    (store.job_dir(job["id"]) / "public/game/config.txt").write_text("test")
    monkeypatch.setenv("TEACHER_ECOSYSTEM_API_URL", "https://example.invalid/works")
    monkeypatch.setenv("TEACHER_ECOSYSTEM_SERVICE_TOKEN", "test-token")

    def remote_error(request, **kwargs):
        assert request.get_method() == "DELETE"
        assert store.get(job["id"])
        raise HTTPError(request.full_url, remote_status, "remote error", {},
                        io.BytesIO(b'{"error":"publication unavailable"}'))

    monkeypatch.setattr(ecosystem, "urlopen", remote_error)
    if remote_status == 404:
        assert backend.delete_owned_job(job["id"], None) == {"deleted": True}
        with pytest.raises(FileNotFoundError):
            store.get(job["id"])
    else:
        with pytest.raises(HTTPException) as error:
            backend.delete_owned_job(job["id"], None)
        assert error.value.status_code == 503
        assert store.get(job["id"])
