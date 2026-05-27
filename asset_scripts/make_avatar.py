"""Generate mini avatars from character sprites for WebGAL dialogue.

Usage:
  python make_avatar.py <image_path> [<image_path> ...] [--size 400] [--crop-ratio 0.40]

Options:
  --size N         Avatar square size in pixels (default: 400)
  --crop-ratio R   Top portion of image to crop for avatar (default: 0.40)
                   e.g. 0.40 = top 40% of the image (head + shoulders + chest)

Output:
  Saves miniavatar_<original_name>.webp in the same directory as the source.
  Only the base name changes: figure_baijuyi.webp → miniavatar_baijuyi.webp

Requires:
  pip install pillow
"""

import argparse
import os
import sys
from PIL import Image


def make_avatar(input_path, size, crop_ratio):
    img = Image.open(input_path)
    w, h = img.size

    crop_height = int(h * crop_ratio)
    upper = img.crop((0, 0, w, crop_height))

    # Resize maintaining aspect ratio, then center on square canvas
    ratio = size / max(w, crop_height) if max(w, crop_height) > 0 else 1
    new_w = int(w * ratio)
    new_h = int(crop_height * ratio)
    resized = upper.resize((new_w, new_h), Image.LANCZOS)

    avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    avatar.paste(resized, (offset_x, offset_y))

    return avatar


def derive_avatar_path(input_path):
    """Derive avatar filename: figure_xxx.webp → miniavatar_xxx.webp"""
    dirname = os.path.dirname(input_path)
    basename = os.path.basename(input_path)
    name_part = os.path.splitext(basename)[0]

    if name_part.startswith("figure_"):
        avatar_name = "miniavatar_" + name_part[len("figure_"):] + ".webp"
    else:
        avatar_name = f"miniavatar_{name_part}.webp"

    return os.path.join(dirname, avatar_name)


def main():
    parser = argparse.ArgumentParser(description="Generate mini avatars from character sprites")
    parser.add_argument("images", nargs="+", help="Image paths to process")
    parser.add_argument("--size", type=int, default=400, help="Avatar square size (default: 400)")
    parser.add_argument("--crop-ratio", type=float, default=0.40,
                        help="Top portion to crop (default: 0.40)")
    args = parser.parse_args()

    for input_path in args.images:
        avatar_path = derive_avatar_path(input_path)
        print(f"Generating: {os.path.basename(avatar_path)}")

        img = Image.open(input_path)
        w, h = img.size
        crop_height = int(h * args.crop_ratio)
        print(f"  Crop: {w}x{crop_height} → resize to {args.size}x{args.size}", end=" ", flush=True)

        avatar = make_avatar(input_path, args.size, args.crop_ratio)
        avatar.save(avatar_path, "WEBP", lossless=True)
        print(f"OK → {avatar_path}")

    print("\nAll done.")


if __name__ == "__main__":
    main()
