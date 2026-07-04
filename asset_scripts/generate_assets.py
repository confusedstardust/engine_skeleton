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
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    if not api_key and api_key_env != "ARK_API_KEY":
        api_key = os.getenv("ARK_API_KEY", "").strip()
        if api_key:
            return "ARK_API_KEY", api_key
    return api_key_env, api_key


def generate_image(client: OpenAI, model: str, prompt: str, output_path: str, size: str) -> bool:
    """Generate one image, download it, and convert it to WebP."""
    print("  Generating...", end=" ", flush=True)

    try:
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
    except Exception as exc:
        print(f"API ERROR: {exc}")
        return False

    image_url = response.data[0].url
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

    client = OpenAI(base_url=DEFAULT_BASE_URL, api_key=api_key)
    print(f"Image API: model={model}, base_url={DEFAULT_BASE_URL}, api_key_env={api_key_env}")

    subdirs = {img["subdir"] for img in images}
    for subdir in subdirs:
        os.makedirs(os.path.join(base_dir, subdir), exist_ok=True)

    total = len(images)
    generated = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
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
