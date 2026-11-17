"""HTTP/type based public error classification; does not import model packages."""
from nar_agent.app.failure_classification import classify_html_exception


class ProviderException(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


def test_safe_status_classification_does_not_leak_provider_exception_text():
    cases = [
        (401, "MODEL_AUTH_FAILED"),
        (403, "MODEL_AUTH_FAILED"),
        (429, "MODEL_RATE_LIMIT"),
        (400, "MODEL_REQUEST_REJECTED"),
        (422, "MODEL_REQUEST_REJECTED"),
        (503, "MODEL_SERVICE_UNAVAILABLE"),
    ]
    for status, expected in cases:
        error = ProviderException(status)
        error.args = ("INTERNAL_TOKEN=secret-do-not-expose",)
        code, public = classify_html_exception(error)
        assert code == expected
        assert "secret-do-not-expose" not in public


def test_unknown_execution_failure_is_traceable_not_disguised_as_user_error():
    code, public = classify_html_exception(RuntimeError("private invalid tool state"))
    assert code == "AGENT_ERROR"
    assert "private invalid tool state" not in public
    assert "任务编号" in public


def test_chained_error_uses_inner_upstream_http_status():
    try:
        try:
            raise ProviderException(429)
        except ProviderException as error:
            raise RuntimeError("wrapper secret") from error
    except RuntimeError as error:
        code, public = classify_html_exception(error)
    assert code == "MODEL_RATE_LIMIT"
    assert "wrapper secret" not in public
