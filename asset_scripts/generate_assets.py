"""Batch generate images via 火山引擎 ARK (豆包 Seedream) for WebGAL visual novels.

Usage:
  python generate_assets.py assets_manifest.json

Environment:
  ARK_API_KEY — 火山引擎 ARK API key (required when generating new images)

Manifest format (assets_manifest.json):
{
  "base_dir": "c:/path/to/game",
  "model": "doubao-seedream-5-0-260128",
  "images": [
    {
      "filename": "figure_tang_scholar_bai_juyi_cyan_robe_standing",
      "subdir": "figure",
      "size": "1440x2560",
      "prompt": "A full-body character portrait..."
    }
  ]
}
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI
from PIL import Image

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedream-4-5-251128"
ARK_API_KEY = "ark-3e941fe9-5b17-4260-ad1f-84037db96e88-997a4"
MAX_WORKERS = 3


def generate_image(client, model, prompt, output_path, size):
    """Generate one image via ARK API, download, convert to WebP."""
    print(f"  Generating...", end=" ", flush=True)

    try:
        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            n=1,
            extra_body={
                "sequential_image_generation": "disabled",
                "watermark": False
            }
        )
    except Exception as e:
        print(f"API ERROR: {e}")
        return False

    image_url = response.data[0].url
    if not image_url:
        print("FAILED — no URL returned")
        return False

    try:
        req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            img_data = resp.read()
    except Exception as e:
        print(f"DOWNLOAD FAILED: {e}")
        return False

    try:
        img = Image.open(io.BytesIO(img_data))
        img = img.convert("RGB")
        img.save(output_path, "WEBP", quality=85)
        print(f"OK -> {output_path} ({img.size[0]}x{img.size[1]})")
        return True
    except Exception as e:
        print(f"CONVERT FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Batch generate images for WebGAL visual novels")
    parser.add_argument("manifest", help="Path to assets_manifest.json")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    base_dir = manifest["base_dir"]
    model = manifest.get("model", DEFAULT_MODEL)
    images = manifest["images"]

    api_key = ARK_API_KEY
    if not api_key:
        env_file = os.path.join(base_dir, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ARK_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val and val != "your-ark-api-key-here":
                            api_key = val
                            print(f"  Using ARK_API_KEY from {env_file}")
                            break
    if not api_key:
        print("ERROR: ARK_API_KEY not set.")
        print("  Option 1: export ARK_API_KEY='your-key' (bash) / $env:ARK_API_KEY='your-key' (PowerShell)")
        print("  Option 2: Create .env file in project root with ARK_API_KEY=your-key")
        print("            cp .env.example .env and edit with your real key")
        sys.exit(1)

    client = OpenAI(base_url=ARK_BASE_URL, api_key=api_key)

    subdirs = set(img["subdir"] for img in images)
    for subdir in subdirs:
        os.makedirs(os.path.join(base_dir, subdir), exist_ok=True)

    total = len(images)
    generated = 0
    failed = 0

    # =========================
 
    # 并行生成（最多3个任务）
 
    # =========================
 
 
 
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
 
 
 
        futures = {}
 
 
 
        for i, img in enumerate(images, 1):
 
 
 
            output_path = os.path.join(
 
                base_dir,
 
                img["subdir"],
 
                f"{img['filename']}.webp"
 
            )
 
            print(f"[{i}/{total}] {img['filename']} ({img['subdir']})")
 
            future = executor.submit(
                generate_image,
                client,
                model,
                img["prompt"],
                output_path,
                img["size"]
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
 
            except Exception as e:
                print(f"FAILED [{img['filename']}]: {e}")
                failed += 1

    print(f"\nDone: {generated} generated, {failed} failed.")
    if failed > 0:
        print("Rerun to retry failed images.")


if __name__ == "__main__":
    main()
