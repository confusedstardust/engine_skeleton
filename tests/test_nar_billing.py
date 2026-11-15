from credit_system.models import CreditReservation
from webgal_backend.nar_billing import (
    NarTurnBilling, safe_usage_metadata, usage_totals, task_usage_metadata,
)


class FakeCreditService:
    def __init__(self):
        self.events = []

    def ensure_signup_credits(self, user_id):
        self.events.append(("signup", user_id))

    def ensure_billable_job(self, **kwargs):
        self.events.append(("job", kwargs))

    def reserve_for_game(self, **kwargs):
        self.events.append(("reserve", kwargs))
        return CreditReservation("b" * 32, kwargs["user_id"], kwargs["job_id"],
                                 kwargs["operation_key"], kwargs["units"], "RESERVED", True)

    def find_reservation(self, **kwargs):
        self.events.append(("find", kwargs))
        return CreditReservation("b" * 32, kwargs["user_id"], kwargs["job_id"],
                                 kwargs["operation_key"], 20, "RESERVED", False)

    def capture(self, reservation_id, units, settlement):
        self.events.append(("capture", units, settlement))

    def release(self, reservation_id):
        self.events.append(("release", reservation_id))


def test_provider_usage_aggregates_models_and_excludes_cached_from_billable_input():
    totals = usage_totals({
        "model-a": {"input_tokens": 100, "output_tokens": 80,
                    "input_token_details": {"cache_read": 25}},
        "model-b": {"input_tokens": 50, "output_tokens": 20},
    })
    assert (totals.input_tokens, totals.output_tokens, totals.cached_input_tokens) == (150, 100, 25)
    assert usage_totals({"model-x": {}}) is None
    assert usage_totals({}) is None


def test_successful_turn_captures_model_reported_usage_not_fake_character_count():
    service = FakeCreditService()
    biller = NarTurnBilling(service)
    reservation = biller.reserve("owner", "a" * 32, "chat")
    assert reservation.units == 20
    assert biller.find("owner", "a" * 32).reservation_id == reservation.reservation_id
    receipt = biller.settle(reservation,
                            {"model-a": {"input_tokens": 15000, "output_tokens": 1500}},
                            definite_success=True, duration_ms=1200)
    assert receipt["usageStatus"] == "reported"
    assert receipt["inputTokens"] == 15000
    assert receipt["outputTokens"] == 1500
    assert receipt["chargedCredits"] >= 1
    assert receipt["billingStatus"] == "captured"
    assert service.events[-1][0] == "capture"
    assert service.events[-1][1] == receipt["chargedCredits"]


def test_missing_usage_is_released_without_estimated_charge():
    service = FakeCreditService()
    biller = NarTurnBilling(service)
    reservation = biller.reserve("owner", "a" * 32, "html")
    receipt = biller.settle(reservation, {}, definite_success=True)
    assert receipt["billingStatus"] == "unmetered_released"
    assert receipt["chargedCredits"] == 0
    assert service.events[-1][0] == "release"


def test_failed_turn_releases_and_disabled_mode_does_not_claim_credits_spent():
    service = FakeCreditService()
    biller = NarTurnBilling(service)
    reservation = biller.reserve("owner", "a" * 32, "animation")
    receipt = biller.settle(reservation, {"model": {"input_tokens": 42, "output_tokens": 3}},
                            definite_success=False)
    assert receipt["billingStatus"] == "released"
    assert receipt["chargedCredits"] == 0
    assert safe_usage_metadata({"model": {"input_tokens": 42, "output_tokens": 3}})["chargedCredits"] is None
    assert task_usage_metadata(None)["usageStatus"] == "unavailable"
