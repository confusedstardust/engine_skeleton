from pathlib import Path


def test_backend_image_includes_credit_system_package() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "docker" / "backend.Dockerfile"
    ).read_text(encoding="utf-8")

    assert "COPY credit_system ./credit_system" in dockerfile
