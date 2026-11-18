"""Independent gesture lesson fixtures prove capability is not tied to gesture-cards."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/"examples"
def test_non_card_gesture_game_examples():
    for name in ("gesture-classification.html","gesture-seasons.html"):
        source=(ROOT/name).read_text(encoding="utf-8")
        assert 'data-nar-gesture="v1"' in source
        assert "window.NarrativeGesture?.on" in source
        assert "getUserMedia" not in source
        assert "/gesture-sdk/" not in source
        assert "data-gesture-dwell" in source
        assert "onpointerdown" in source or '"pointerdown"' in source
        assert len(source.encode("utf-8"))<96000
