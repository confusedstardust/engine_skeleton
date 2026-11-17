"""In-process Forge RPG API contract. Side effects are stubs, no DB/LLM required."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from credit_system.billing import estimate_hold
from webgal_backend.nar_conversation_routes import create_router
from webgal_backend.nar_conversation_store import ConversationConflict, ConversationMissing


CID, MID, JOB = "a" * 32, "b" * 32, "c" * 32
OWNER = "ci-rpg-owner"
OPTIONS = {"specVersion": 1, "durationMinutes": 20, "generateImages": True, "enableVoice": False}


class FakeRpgLedger:
    def __init__(self):
        self.reject_next_start_transition = False
        self.rpg = {
            "schema_version": 1, "state": "PREPARED", "spec_version": 1,
            "spec": {"topic": "琵琶行", "source_ref": {"type": "origin_user_message"},
                     "duration_minutes": 20, "generate_images": True, "enable_voice": False},
            "job_id": None, "confirmed_options": None, "confirmed_hold_credits": None,
            "last_error_code": None,
        }

    def get_owned_rpg_message(self, owner, cid, message_id):
        if owner != OWNER or cid != CID or message_id != MID:
            raise ConversationMissing("Not owned")
        return {"message_id": MID, "rpg": self.rpg,
                "original_prompt": "把《琵琶行》做成 RPG，玩家扮演琵琶女，三个结局"}

    def claim_rpg_message(self, owner, cid, message_id, *, version, confirmed_options, hold):
        self.get_owned_rpg_message(owner, cid, message_id)
        if self.rpg["state"] != "PREPARED" or version != 1:
            return False
        self.rpg.update(state="CLAIMED", confirmed_options=confirmed_options,
                        confirmed_hold_credits=hold)
        return True

    def attach_rpg_job(self, owner, cid, message_id, job_id):
        self.get_owned_rpg_message(owner, cid, message_id)
        if self.rpg["state"] != "CLAIMED" or self.rpg["job_id"] is not None:
            raise ConversationConflict("Job bound")
        self.rpg.update(job_id=job_id, state="JOB_CREATED")

    def transition_rpg_message(self, owner, cid, message_id, expected_state, state, error_code=None):
        self.get_owned_rpg_message(owner, cid, message_id)
        if expected_state == "JOB_CREATED" and self.reject_next_start_transition:
            self.reject_next_start_transition = False
            raise ConversationConflict("Simulated transition failure")
        if self.rpg["state"] != expected_state:
            raise ConversationConflict("State changed")
        self.rpg.update(state=state, last_error_code=error_code)

    def cancel_rpg_message(self, owner, cid, message_id):
        self.get_owned_rpg_message(owner, cid, message_id)
        if self.rpg["state"] != "PREPARED":
            return False
        self.rpg["state"] = "CANCELLED"
        return True


def setup(*, balance=200, fail_run=False, fail_run_status=None):
    ledger = FakeRpgLedger()
    events = []
    def create(owner, request_body):
        events.append("create")
        assert owner == OWNER
        assert request_body["options"]["generation_mode"] == "auto"
        assert "三个结局" in request_body["source_material"]
        return {"id": JOB}
    def get(owner, job_id):
        if owner != OWNER or job_id != JOB:
            raise HTTPException(404, "Job not owned")
        return {"id": JOB}
    def run(job_id, request, tasks):
        assert job_id == JOB
        assert ledger.rpg["state"] == "STARTING"
        assert ledger.rpg["job_id"] == JOB
        events.append("run")
        if fail_run_status is not None:
            raise HTTPException(fail_run_status, "Already running or uncertain")
        if fail_run:
            raise HTTPException(402, "Insufficient balance")
        return {"id": JOB, "status": "QUEUED"}
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda req: {"id": req.headers.get("x-test-owner", OWNER),
                                      "auth_type": "sso"},
        store=ledger, works=object(), rpg_create=create,
        rpg_get=get, rpg_run=run, rpg_quote=lambda options: estimate_hold(options)[0],
        rpg_balance=lambda owner: balance,
    ))
    return TestClient(app), ledger, events


def path(suffix=""):
    return f"/nar-agent/conversations/{CID}/messages/{MID}/rpg{suffix}"


def test_quote_is_side_effect_free_and_confirm_is_at_most_once():
    client, ledger, events = setup()
    assert client.get(path()).json()["state"] == "PREPARED"
    quote = client.post(path("/quote"), json=OPTIONS,
                        headers={"X-NarAgent-Action": "chat"})
    assert quote.status_code == 200
    hold = quote.json()["holdCredits"]
    assert hold == 70
    assert events == []
    payload = {**OPTIONS, "acceptedHoldCredits": hold}
    first = client.post(path("/confirm"), json=payload,
                        headers={"X-NarAgent-Action": "chat"})
    assert first.status_code == 202
    assert first.json()["state"] == "STARTED"
    assert first.json()["jobId"] == JOB
    repeated = client.post(path("/confirm"), json=payload,
                           headers={"X-NarAgent-Action": "chat"})
    assert repeated.status_code == 202
    assert repeated.json()["jobId"] == JOB
    assert events == ["create", "run"]
    changed = client.post(path("/confirm"), json={**payload, "enableVoice": True},
                          headers={"X-NarAgent-Action": "chat"})
    assert changed.status_code == 409
    assert events == ["create", "run"]
    assert client.post(path("/cancel"),
                       headers={"X-NarAgent-Action": "chat"}).json()["state"] == "STARTED"
    assert ledger.rpg["state"] == "STARTED"


def test_price_changed_and_insufficient_balance_never_create_job():
    client, ledger, events = setup()
    bad_price = client.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 1},
        headers={"X-NarAgent-Action": "chat"})
    assert bad_price.status_code == 409
    assert ledger.rpg["state"] == "PREPARED"
    assert events == []
    low, low_ledger, low_events = setup(balance=0)
    result = low.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 70},
        headers={"X-NarAgent-Action": "chat"})
    assert result.status_code == 402
    assert low_ledger.rpg["state"] == "PREPARED"
    assert low_events == []


def test_run_refusal_preserves_job_and_cross_owner_is_denied():
    client, ledger, events = setup(fail_run=True)
    denied = client.get(path(), headers={"x-test-owner": "other"})
    assert denied.status_code == 404
    assert client.post(path("/quote"), json=OPTIONS,
        headers={"x-test-owner": "other", "X-NarAgent-Action": "chat"}).status_code == 404
    result = client.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 70},
        headers={"X-NarAgent-Action": "chat"})
    assert result.status_code == 202
    assert result.json()["state"] == "START_REJECTED"
    assert result.json()["jobId"] == JOB
    assert events == ["create", "run"]
    repeat = client.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 70},
        headers={"X-NarAgent-Action": "chat"})
    assert repeat.status_code == 202
    assert events == ["create", "run"]


def test_unwired_webgal_callbacks_fail_closed_without_creating_jobs():
    ledger = FakeRpgLedger()
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda req: {"id": OWNER, "auth_type": "sso"},
        store=ledger, works=object(),
    ))
    client = TestClient(app)
    result = client.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 70},
        headers={"X-NarAgent-Action": "chat"})
    assert result.status_code == 503
    assert "尚未配置" in result.text
    assert ledger.rpg["state"] == "PREPARED"


def test_job_bound_then_transition_fails_is_manual_review_without_duplicate():
    client, ledger, events = setup()
    ledger.reject_next_start_transition = True
    payload = {**OPTIONS, "acceptedHoldCredits": 70}
    res = client.post(path("/confirm"), json=payload,
                      headers={"X-NarAgent-Action": "chat"})
    assert res.status_code == 202
    assert res.json()["state"] == "NEEDS_REVIEW"
    assert res.json()["jobId"] == JOB
    assert events == ["create"]  # No run accepted; no replacement job.
    repeat = client.post(path("/confirm"), json=payload,
                         headers={"X-NarAgent-Action": "chat"})
    assert repeat.status_code == 202
    assert repeat.json()["jobId"] == JOB
    assert events == ["create"]


def test_run_409_already_running_is_not_misrepresented_as_definite_rejection():
    client, ledger, events = setup(fail_run_status=409)
    result = client.post(path("/confirm"),
        json={**OPTIONS, "acceptedHoldCredits": 70},
        headers={"X-NarAgent-Action": "chat"})
    assert result.status_code == 202
    assert result.json()["state"] == "NEEDS_REVIEW"
    assert result.json()["jobId"] == JOB
    assert events == ["create", "run"]
