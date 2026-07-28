"""Batch generate images through an OpenAI-compatible image API.

Usage:
  python generate_assets.py assets_manifest.json

Environment:
  WEBGAL_IMAGE_BASE_URL - OpenAI-compatible image API base URL.
  WEBGAL_IMAGE_MODEL - Image generation model.
  WEBGAL_IMAGE_API_KEY_ENV - Name of the env var containing the API key.

Legacy ARK env vars remain supported:
  ARK_IMAGE_BASE_URL
  ARK_IMAGE_MODEL
  ARK_API_KEY
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from openai import OpenAI
from PIL import Image


DEFAULT_BASE_URL = (
    os.getenv("WEBGAL_IMAGE_BASE_URL")
    or os.getenv("ARK_IMAGE_BASE_URL")
    or "https://ark.cn-beijing.volces.com/api/v3"
).rstrip("/")
DEFAULT_MODEL = os.getenv("WEBGAL_IMAGE_MODEL") or os.getenv("ARK_IMAGE_MODEL") or "doubao-seedream-4-5-251128"
DEFAULT_API_KEY_ENV = os.getenv("WEBGAL_IMAGE_API_KEY_ENV", "ARK_API_KEY").strip() or "ARK_API_KEY"
MAX_WORKERS = int(os.getenv("WEBGAL_IMAGE_MAX_WORKERS", "3"))


def _api_key_from_env() -> tuple[str, str]:
    api_key_env = DEFAULT_API_KEY_ENV
    api_key = os.getenv(api_key_env, "").strip()
    return api_key_env, api_key


QWEN_IMAGE_MAX_SIZES = (
    (1664, 928),
    (1472, 1104),
    (1328, 1328),
    (1104, 1472),
    (928, 1664),
)


def _parse_size(size: str) -> tuple[int, int]:
    width, height = size.lower().replace("*", "x").split("x", 1)
    return int(width), int(height)


def _qwen_size(model: str, size: str) -> str:
    width, height = _parse_size(size)
    if model == "qwen-image-max":
        target_ratio = width / height
        width, height = min(
            QWEN_IMAGE_MAX_SIZES,
            key=lambda candidate: abs((candidate[0] / candidate[1]) - target_ratio),
        )
    return f"{width}*{height}"


def _worker_count_for_model(model: str) -> int:
    return 1 if model.lower().startswith("qwen-image") else MAX_WORKERS


def _qwen_image_url(result: dict[str, Any]) -> str:
    try:
        content = result["output"]["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"invalid DashScope image response: {result.get('code') or result.get('message') or result}"
        ) from exc
    for item in content:
        if isinstance(item, dict) and item.get("image"):
            return str(item["image"])
    raise RuntimeError("DashScope image response did not contain an image URL")


def _generate_qwen_image(base_url: str, api_key: str, model: str, prompt: str, size: str) -> str:
    url = f"{base_url.rstrip('/')}/services/aigc/multimodal-generation/generation"
    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ]
        },
        "parameters": {
            "size": _qwen_size(model, size),
            "n": 1,
            "prompt_extend": True,
            "watermark": False,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DashScope API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DashScope network error: {exc}") from exc
    return _qwen_image_url(result)


def generate_image(
    client: OpenAI | None,
    model: str,
    prompt: str,
    output_path: str,
    size: str,
    base_url: str,
    api_key: str,
) -> bool:
    """Generate one image, download it, and convert it to WebP."""
    print("  Generating...", end=" ", flush=True)

    try:
        if model.lower().startswith("qwen-image"):
            image_url = _generate_qwen_image(base_url, api_key, model, prompt, size)
        else:
            if client is None:
                raise RuntimeError("OpenAI-compatible image client is not configured")
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                n=1,
                extra_body={
                "sequential_image_generation": "disabled",
                "watermark": False,
                },
            )
            image_url = response.data[0].url
    except Exception as exc:
        print(f"API ERROR: {exc}")
        return False

    if not image_url:
        print("FAILED - no URL returned")
        return False

    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            img_data = resp.read()
    except Exception as exc:
        print(f"DOWNLOAD FAILED: {exc}")
        return False

    try:
        img = Image.open(io.BytesIO(img_data))
        img = img.convert("RGB")
        img.save(output_path, "WEBP", quality=85)
        print(f"OK -> {output_path} ({img.size[0]}x{img.size[1]})")
        return True
    except Exception as exc:
        print(f"CONVERT FAILED: {exc}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch generate images for WebGAL visual novels")
    parser.add_argument("manifest", help="Path to assets_manifest.json")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as file:
        manifest = json.load(file)

    base_dir = manifest["base_dir"]
    model = manifest.get("model") or DEFAULT_MODEL
    images = manifest["images"]

    api_key_env, api_key = _api_key_from_env()
    if not api_key:
        print(f"ERROR: {api_key_env} not set.")
        print(f"  Option 1: export {api_key_env}='your-key' (bash) / $env:{api_key_env}='your-key' (PowerShell)")
        print(f"  Option 2: Create .env file in project root with {api_key_env}=your-key")
        sys.exit(1)

    is_qwen = model.lower().startswith("qwen-image")
    worker_count = _worker_count_for_model(model)
    client = None if is_qwen else OpenAI(base_url=DEFAULT_BASE_URL, api_key=api_key)
    print(
        f"Image API: model={model}, base_url={DEFAULT_BASE_URL}, "
        f"api_key_env={api_key_env}, workers={worker_count}"
    )

    subdirs = {img["subdir"] for img in images}
    for subdir in subdirs:
        os.makedirs(os.path.join(base_dir, subdir), exist_ok=True)

    total = len(images)
    generated = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for index, img in enumerate(images, 1):
            output_path = os.path.join(base_dir, img["subdir"], f"{img['filename']}.webp")
            print(f"[{index}/{total}] {img['filename']} ({img['subdir']})")
            future = executor.submit(
                generate_image,
                client,
                model,
                img["prompt"],
                output_path,
                img["size"],
                DEFAULT_BASE_URL,
                api_key,
            )
            futures[future] = img

        for future in as_completed(futures):
            img = futures[future]
            try:
                ok = future.result()
                if ok:
                    generated += 1
                else:
                    failed += 1
            except Exception as exc:
                print(f"FAILED [{img['filename']}]: {exc}")
                failed += 1

    print(f"\nDone: {generated} generated, {failed} failed.")
    if failed > 0:
        print("Rerun to retry failed images.")


if __name__ == "__main__":
    main()
