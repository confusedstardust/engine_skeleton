"""Remove backgrounds from character sprites using rembg.

Usage:
  python remove_bg.py <image_path> [<image_path> ...]

Output:
  Overwrites each input image with a lossless WebP containing alpha channel.
  Supports .png, .jpg, .webp input.

Requires:
  pip install rembg pillow
"""

import sys
from PIL import Image
from rembg import remove, new_session


def remove_background(input_path):
    print(f"Processing: {input_path}")
    print(f"  Loading...", end=" ", flush=True)
    img = Image.open(input_path)
    original_mode = img.mode
    print(f"OK ({img.size[0]}x{img.size[1]}, mode={original_mode})")

    # RGBA input: preserve existing alpha by separating and re-compositing
    if original_mode == "RGBA":
        print(f"  Separating RGB and alpha channels...", end=" ", flush=True)
        r, g, b, alpha = img.split()
        img_rgb = Image.merge("RGB", (r, g, b))
        print(f"OK")

        print(f"  Removing background from RGB (u2netp model)...", end=" ", flush=True)
        session = new_session("u2netp")
        output_rgba = remove(img_rgb, session=session)
        print(f"OK")

        # Re-apply original alpha where it was more opaque than rembg result
        print(f"  Compositing original alpha...", end=" ", flush=True)
        out_r, out_g, out_b, out_a = output_rgba.split()
        # Use the more opaque alpha of the two
        from PIL import ImageChops
        merged_a = ImageChops.lighter(out_a, alpha)
        output = Image.merge("RGBA", (out_r, out_g, out_b, merged_a))
        print(f"OK")
    else:
        print(f"  Removing background (u2netp model ~4MB)...", end=" ", flush=True)
        session = new_session("u2netp")
        output = remove(img, session=session)
        print(f"OK")

    print(f"  Saving (lossless WebP)...", end=" ", flush=True)
    output.save(input_path, "WEBP", lossless=True)
    print(f"OK → {input_path} (alpha preserved)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python remove_bg.py <image_path> [<image_path> ...]")
        print("Example: python remove_bg.py figure/*.webp")
        sys.exit(1)

    for path in sys.argv[1:]:
        remove_background(path)
        print()

    print("All done.")


if __name__ == "__main__":
    main()
