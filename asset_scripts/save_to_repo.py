"""Save a generated/processed image to the asset repository.

Usage:
  python save_to_repo.py <image_path> --repo "C:\...\assets repo" \
      --category figure --prompt "A full-body portrait of..." \
      --tags "tang,scholar,male,cyan-robe"

The image is copied to the repo under <category>/ with its current filename.
Metadata (prompt, tags, category, size, date) is written to index.json.

If an entry with the same filename already exists, it is updated.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import date
from PIL import Image


REPO_INDEX = "index.json"


def load_index(repo_path):
    index_path = os.path.join(repo_path, REPO_INDEX)
    if not os.path.exists(index_path):
        return {}
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(repo_path, index):
    index_path = os.path.join(repo_path, REPO_INDEX)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def save_to_repo(image_path, repo_path, category, prompt, tags):
    if not os.path.exists(image_path):
        print(f"ERROR: Image not found: {image_path}")
        return False

    filename = os.path.basename(image_path)
    category_dir = os.path.join(repo_path, category)
    os.makedirs(category_dir, exist_ok=True)

    # Copy image to repo
    dest_path = os.path.join(category_dir, filename)
    shutil.copy2(image_path, dest_path)
    print(f"Copied: {filename} → {category}/")

    # Get image dimensions
    try:
        img = Image.open(image_path)
        size = f"{img.size[0]}x{img.size[1]}"
    except Exception:
        size = "unknown"

    # Update index
    index = load_index(repo_path)
    index[filename] = {
        "category": category,
        "prompt": prompt,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "size": size,
        "saved_at": str(date.today()),
    }
    save_index(repo_path, index)
    print(f"Indexed: {filename} (category={category}, tags={tags})")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Save an image to the WebGAL asset repository")
    parser.add_argument("image", help="Path to the image file")
    parser.add_argument("--repo", required=True, help="Path to asset repository")
    parser.add_argument("--category", required=True,
                        choices=["figure", "background", "avatar"],
                        help="Asset category")
    parser.add_argument("--prompt", required=True,
                        help="Original generation prompt (for future search)")
    parser.add_argument("--tags", default="",
                        help="Comma-separated keyword tags (e.g. 'tang,scholar,male')")
    args = parser.parse_args()

    ok = save_to_repo(args.image, args.repo, args.category, args.prompt, args.tags)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
