"""Inject BGM commands into WebGAL scene files at choice converge points.

Scans all scene files for choose: commands, identifies the converge labels
where all choice branches rejoin, and injects bgm: commands. BGM tracks are
randomly selected from the shared bgm_repo with no consecutive repeats.

Usage:
  python inject_bgm.py <project_root>
  python inject_bgm.py --dry-run <project_root>

The script:
  1. Scans scene files to count converge points (N)
  2. Randomly selects N tracks from the shared bgm_repo
  3. Copies only those N tracks to public/game/bgm/
  4. Injects bgm: commands after converge labels

Idempotent: running twice won't double-inject.
"""

import os
import re
import sys
import shutil
import random
from pathlib import Path

# --- Constants ---
SKILL_DIR = Path(__file__).resolve().parent.parent  # ~/.claude/skills/webgal-game/
BGM_REPO_DIR = SKILL_DIR / "shared" / "bgm_repo"


# --- Regex patterns ---
CHOOSE_RE = re.compile(r'^choose:(.+);$')
LABEL_RE = re.compile(r'^label:(\w+);$')
JUMP_RE = re.compile(r'^jumpLabel:(\w+)(?:\s+-when=.+)?;$')
BGM_RE = re.compile(r'^bgm:.+;$')


def load_bgm_repo(repo_dir):
    """List all .mp3 files in the BGM repository."""
    repo = Path(repo_dir)
    if not repo.is_dir():
        print(f"ERROR: BGM repo not found at {repo_dir}")
        sys.exit(1)
    tracks = sorted([f.name for f in repo.glob("*.mp3")])
    if not tracks:
        print(f"ERROR: No .mp3 files found in {repo_dir}")
        sys.exit(1)
    return tracks


def parse_choose_options(choose_line):
    """Extract target label names from a choose: command.

    Example:
      "choose:接受她的好意:choice_accept|婉言谢绝:choice_refuse|不置可否，先拖着:choice_delay;"
      -> ["choice_accept", "choice_refuse", "choice_delay"]
    """
    match = CHOOSE_RE.match(choose_line)
    if not match:
        return []
    content = match.group(1)
    options = []
    for segment in content.split("|"):
        segment = segment.strip()
        if ":" in segment:
            label = segment.rsplit(":", 1)[-1].strip()
            options.append(label)
    return options


def parse_scene(filepath):
    """Parse a scene file into structured data.

    Returns dict with:
      choices: [(line_idx, option_labels, line_text), ...]
      labels: {label_name: line_idx}
      jumps: [(line_idx, target_label), ...]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    choices = []
    labels = {}
    jumps = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect choose: command
        if CHOOSE_RE.match(stripped):
            option_labels = parse_choose_options(stripped)
            if option_labels:
                choices.append((i, option_labels, stripped))
        # Detect label: definition
        label_match = LABEL_RE.match(stripped)
        if label_match:
            labels[label_match.group(1)] = i
        # Detect jumpLabel: command
        jump_match = JUMP_RE.match(stripped)
        if jump_match:
            jumps.append((i, jump_match.group(1)))

    return {"lines": lines, "choices": choices, "labels": labels, "jumps": jumps}


def find_converge_labels(scene_data):
    """Find converge labels — labels where all branches of a choice rejoin.

    For each choice, traces each option's branch to its jumpLabel target.
    If all branches jump to the same label, it's a converge point.
    Returns a set of label names (deduplicated).
    """
    labels = scene_data["labels"]
    lines = scene_data["lines"]

    converge_labels = set()

    for _choice_idx, option_labels, _choice_text in scene_data["choices"]:
        jump_targets = []

        for opt_label in option_labels:
            if opt_label not in labels:
                continue  # Should not happen in valid scene files

            # Trace forward from the label to find its jumpLabel
            start = labels[opt_label]
            target = None
            for j in range(start + 1, len(lines)):
                jump_match = JUMP_RE.match(lines[j].strip())
                if jump_match:
                    target = jump_match.group(1)
                    break
            if target:
                jump_targets.append(target)

        # If all branches jump to the same label, it's a converge
        if jump_targets and all(t == jump_targets[0] for t in jump_targets):
            converge_labels.add(jump_targets[0])

    return converge_labels


def find_all_converges(scene_dir):
    """Scan all scene files and return converge labels per scene.

    Returns: {scene_filename: set(converge_labels)}
    """
    scene_path = Path(scene_dir)
    if not scene_path.is_dir():
        print(f"ERROR: Scene directory not found at {scene_dir}")
        sys.exit(1)

    all_converges = {}
    for txt_file in sorted(scene_path.glob("*.txt")):
        scene_data = parse_scene(txt_file)
        converges = find_converge_labels(scene_data)
        if converges:
            all_converges[txt_file.name] = converges

    return all_converges


def select_tracks(repo_tracks, count, last_track=None):
    """Randomly select `count` tracks with no consecutive repeats.

    Args:
      repo_tracks: list of all available track filenames
      count: number of tracks to select
      last_track: the previously selected track (to avoid repeat)

    Returns: list of selected track filenames
    """
    # Shuffle for initial order
    pool = list(repo_tracks)
    random.shuffle(pool)

    selected = []
    prev = last_track

    for _ in range(count):
        # Prefer a track different from previous
        candidates = [t for t in pool if t != prev]
        if not candidates:
            # Only one unique track available — allow repeat
            candidates = pool
        if not candidates:
            break
        pick = candidates[0]
        selected.append(pick)
        pool.remove(pick)
        prev = pick

    return selected


def find_already_injected(scene_dir, all_converges):
    """Check which converge labels already have a bgm: command injected.

    Returns: {(scene_name, label_name)} — converge points already handled.
    """
    already = set()
    scene_path = Path(scene_dir)
    for scene_name, converges in all_converges.items():
        scene_file = scene_path / scene_name
        with open(scene_file, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
        for i, line in enumerate(lines):
            label_match = LABEL_RE.match(line.strip())
            if not label_match:
                continue
            label_name = label_match.group(1)
            if label_name not in converges:
                continue
            next_idx = i + 1
            if next_idx < len(lines) and BGM_RE.match(lines[next_idx].strip()):
                already.add((scene_name, label_name))
    return already


def copy_selected(src_dir, dest_dir, selected):
    """Copy only the selected BGM files from repo to game directory."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    copied = []
    for filename in selected:
        src_file = Path(src_dir) / filename
        dest_file = dest / filename
        if not dest_file.exists():
            shutil.copy2(src_file, dest_file)
            copied.append(filename)
    return copied


def inject_bgm_into_scene(scene_path, converge_labels, track_map):
    """Inject bgm: commands after converge labels.

    Args:
      scene_path: path to the scene .txt file
      converge_labels: set of label names to inject after
      track_map: {label_name: track_filename}

    Returns: list of (line_number, label, track) for each injection
    """
    with open(scene_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    injections = []
    # Process lines in reverse so line indices stay valid during insertion
    for i in range(len(lines) - 1, -1, -1):
        stripped = lines[i].strip()
        label_match = LABEL_RE.match(stripped)
        if not label_match:
            continue

        label_name = label_match.group(1)
        if label_name not in converge_labels:
            continue

        if label_name not in track_map:
            continue

        # Check idempotency: is the next line already a bgm command?
        next_idx = i + 1
        if next_idx < len(lines) and BGM_RE.match(lines[next_idx].strip()):
            continue  # Already injected — skip

        bgm_line = f"bgm:{track_map[label_name]} -enter=1500;"
        lines.insert(next_idx, bgm_line)
        injections.append((next_idx, label_name, track_map[label_name]))

    if injections:
        with open(scene_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # Sort by line number for readable output
    injections.sort()
    return injections


def resolve_bgm_dest(project_root):
    """Resolve the BGM destination directory within the project."""
    return Path(project_root) / "public" / "game" / "bgm"


def resolve_scene_dir(project_root):
    """Resolve the scene directory within the project."""
    return Path(project_root) / "public" / "game" / "scene"


def main():
    dry_run = False
    args = sys.argv[1:]

    if "--dry-run" in args:
        dry_run = True
        args.remove("--dry-run")

    if len(args) < 1:
        print("Usage: python inject_bgm.py [--dry-run] <project_root>")
        print("Example: python inject_bgm.py c:/SelfCreated/MyProject/libai")
        sys.exit(2)

    project_root = args[0]
    scene_dir = resolve_scene_dir(project_root)
    bgm_dest = resolve_bgm_dest(project_root)

    # --- Step 1: Load BGM repo ---
    print("=" * 60)
    print("WebGAL BGM Injection")
    print("=" * 60)
    print(f"\nBGM repo: {BGM_REPO_DIR}")
    print(f"Scene dir: {scene_dir}")
    print(f"BGM dest:  {bgm_dest}")

    repo_tracks = load_bgm_repo(BGM_REPO_DIR)
    print(f"Available tracks in repo: {len(repo_tracks)}")

    # --- Step 2: Find all converge points ---
    all_converges = find_all_converges(scene_dir)

    if not all_converges:
        print("\nNo choice converge points found. Nothing to inject.")
        return

    # Filter out already-injected converge points
    already_injected = find_already_injected(scene_dir, all_converges)

    # Build a flat ordered list of (scene, label) pairs for track assignment
    converge_pairs = []
    skipped_pairs = []
    for scene_name in sorted(all_converges):
        for label in sorted(all_converges[scene_name]):
            if (scene_name, label) in already_injected:
                skipped_pairs.append((scene_name, label))
            else:
                converge_pairs.append((scene_name, label))

    N = len(converge_pairs)
    print(f"\nConverge points: {N} new, {len(skipped_pairs)} already injected (skipped)")
    for scene_name, label in converge_pairs:
        print(f"  {scene_name} -> {label}")
    for scene_name, label in skipped_pairs:
        print(f"  {scene_name} -> {label}  (SKIPPED)")

    if N == 0:
        print("\nAll converge points already have BGM. Nothing to do.")
        return

    # --- Step 3: Select tracks ---
    selected_tracks = select_tracks(repo_tracks, N)
    print(f"\nSelected tracks: {len(selected_tracks)}")
    for t in selected_tracks:
        print(f"  {t}")

    # Build track map: label_name -> track_filename
    track_map = {}
    for (scene_name, label), track in zip(converge_pairs, selected_tracks):
        track_map[label] = track

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN — no files modified")
        print("=" * 60)
        print("\nWould copy to BGM dest:")
        for t in selected_tracks:
            print(f"  {t}")
        print("\nWould inject:")
        for scene_name, label in converge_pairs:
            print(f"  {scene_name}: after label:{label}; -> bgm:{track_map[label]} -enter=1500;")
        return

    # --- Step 4: Copy selected tracks ---
    print(f"\nCopying {len(selected_tracks)} tracks...")
    copied = copy_selected(BGM_REPO_DIR, bgm_dest, selected_tracks)
    print(f"Copied: {len(copied)}")

    # --- Step 5: Inject BGM commands ---
    print("\nInjecting BGM commands...")
    total_injections = 0
    for scene_name in sorted(all_converges):
        scene_path = Path(scene_dir) / scene_name
        converges = all_converges[scene_name]
        injections = inject_bgm_into_scene(str(scene_path), converges, track_map)
        if injections:
            print(f"  {scene_name}:")
            for line_no, label, track in injections:
                print(f"    line {line_no + 1}: after label:{label}; -> bgm:{track} -enter=1500;")
                total_injections += 1

    print(f"\nTotal injections: {total_injections}")
    print("Done.")


if __name__ == "__main__":
    main()
