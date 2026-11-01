"""Private immutable local artifacts; OSS migration is an explicit later step."""
import base64
import json
import re
import shutil
import uuid
from pathlib import Path


class ArtifactStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, owner: str, result: dict, source: str) -> str:
        if sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file()) > 500 * 1024 * 1024:
            raise ValueError("Local artifact quota reached; configure retention or OSS")
        identifier = uuid.uuid4().hex
        pending = self.root / (identifier + ".pending")
        pending.mkdir(mode=0o700)
        try:
            for key, limit in [("index.html", 2000000), ("preview.png", 3000000), ("mobile.png", 3000000)]:
                raw = base64.b64decode(result[key], validate=True)
                if len(raw) > limit:
                    raise ValueError("Artifact exceeds size limit")
                (pending / key).write_bytes(raw)
            (pending / "build.mjs").write_text(source, encoding="utf-8")
            (pending / "metadata.json").write_text(json.dumps({"owner": owner, "report": result["report"]}, ensure_ascii=False), encoding="utf-8")
            pending.rename(self.root / identifier)
            return identifier
        except Exception:
            shutil.rmtree(pending)
            raise

    def read(self, owner: str, identifier: str, filename: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{32}", identifier) or filename not in {"index.html", "preview.png", "mobile.png"}:
            raise FileNotFoundError
        directory = self.root / identifier
        meta = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if meta["owner"] != owner:
            raise FileNotFoundError
        return (directory / filename).read_bytes()
