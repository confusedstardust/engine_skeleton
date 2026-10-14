from __future__ import annotations

import re


_COMMAND_FOLDERS = {
    "changeBg": "background",
    "changeFigure": "figure",
    "miniAvatar": "figure",
    "bgm": "bgm",
    "playEffect": "vocal",
}


def rewrite_webgal_asset_urls(text: str, urls: dict[str, str]) -> str:
    """Resolve game asset filenames to immutable OSS URLs in executable WebGAL text."""
    lines: list[str] = []
    for line in text.splitlines():
        rewritten = line
        command = re.match(r"^(?P<indent>\s*)(?P<command>changeBg|changeFigure|miniAvatar|bgm|playEffect):(?P<asset>[^\s;]+)(?P<tail>.*)$", rewritten)
        if command:
            asset = command.group("asset")
            if asset.lower() != "none" and not asset.startswith(("http://", "https://")):
                folder = _COMMAND_FOLDERS[command.group("command")]
                filename = asset.replace("\\", "/").split("/")[-1]
                url = urls.get(f"{folder}/{filename}")
                if url:
                    rewritten = f"{command.group('indent')}{command.group('command')}:{url}{command.group('tail')}"

        def replace_explicit_vocal(match: re.Match[str]) -> str:
            value = match.group("value")
            if value.startswith(("http://", "https://")):
                return match.group(0)
            filename = value.replace("\\", "/").split("/")[-1]
            url = urls.get(f"vocal/{filename}")
            return f"{match.group('prefix')}{url}" if url else match.group(0)

        rewritten = re.sub(
            r"(?P<prefix>\s-vocal(?:=|\s))(?P<value>[^\s;]+)",
            replace_explicit_vocal,
            rewritten,
            flags=re.IGNORECASE,
        )

        def replace_shorthand_vocal(match: re.Match[str]) -> str:
            filename = match.group("filename")
            url = urls.get(f"vocal/{filename}")
            return f" -vocal={url}" if url else match.group(0)

        rewritten = re.sub(
            r"\s-(?P<filename>[A-Za-z0-9_.-]+\.(?:wav|mp3|ogg))(?=\s|;|$)",
            replace_shorthand_vocal,
            rewritten,
            flags=re.IGNORECASE,
        )
        lines.append(rewritten)
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix
