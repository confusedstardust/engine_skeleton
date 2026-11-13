"""Keep the game title background and collection cover on the same resource."""
from pathlib import Path
import os
import re
import uuid


def title_image(game_dir: Path) -> str:
    config = game_dir / "config.txt"
    if not config.exists():
        return ""
    match = re.search(r"^Title_img:([^;]*);", config.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip() if match else ""


def set_title_image(game_dir: Path, filename: str) -> None:
    config = game_dir / "config.txt"
    text = config.read_text(encoding="utf-8")
    line = f"Title_img:{filename};"
    if re.search(r"^Title_img:", text, re.MULTILINE):
        text = re.sub(r"^Title_img:[^\r\n]*", lambda _: line, text, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    temporary = config.with_name(f".config-{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)


def fill_empty_title_image(game_dir: Path) -> None:
    if not (game_dir / "config.txt").exists() or title_image(game_dir):
        return
    first = next((game_dir / "background").glob("*.webp"), None)
    if first:
        set_title_image(game_dir, first.name)


def local_title_cover(game_dir: Path) -> Path | None:
    name = title_image(game_dir)
    if not name or Path(name).name != name:
        return None
    path = game_dir / "background" / name
    return path if path.is_file() else None
