"""Search the asset repository for images matching a query.

Usage:
  python search_assets.py "<query>" --repo "C:\...\assets repo"
  python search_assets.py "<query>" --repo "C:\...\assets repo" --category figure
  python search_assets.py "<query>" --repo "C:\...\assets repo" --threshold 0.3

Output (JSON):
  {"found": true, "filename": "figure_tang_scholar_...webp", "score": 0.75, "category": "figure"}
  {"found": false, "best_match": null}

Logic:
  Splits the query into keywords, scores each entry in index.json by keyword
  overlap against the stored prompt + tags. Returns the best match above threshold.
"""

import argparse
import json
import os
import re
import sys


def load_index(repo_path):
    index_path = os.path.join(repo_path, "index.json")
    if not os.path.exists(index_path):
        return {}
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def tokenize(text):
    """Lowercase, split on non-alphanumeric, filter short tokens."""
    tokens = re.findall(r"[a-zA-Z0-9一-鿿]+", text.lower())
    return [t for t in tokens if len(t) >= 2]


def score_entry(query_tokens, entry):
    """Score an index entry against query tokens.

    Checks prompt text (weight 1.0) and tags (weight 1.5 per tag match).
    Returns 0.0-1.0 normalized score.
    """
    prompt_text = entry.get("prompt", "")
    tags = entry.get("tags", [])

    prompt_tokens = set(tokenize(prompt_text))
    tag_tokens = set()
    for tag in tags:
        tag_tokens.update(tokenize(tag))

    if not prompt_tokens and not tag_tokens:
        return 0.0

    query_set = set(query_tokens)
    if not query_set:
        return 0.0

    # Jaccard-like: intersection / union, with tag bonus
    prompt_overlap = len(query_set & prompt_tokens)
    tag_overlap = len(query_set & tag_tokens)

    # Weighted score
    max_prompt = max(len(prompt_tokens), 1)
    max_tag = max(len(tag_tokens), 1)

    prompt_score = prompt_overlap / max(len(query_set), 1) if prompt_overlap > 0 else 0
    tag_score = (tag_overlap * 1.5) / max(len(query_set), 1) if tag_overlap > 0 else 0

    # Bonus for exact multi-word phrase match in prompt
    phrase_bonus = 0
    query_phrase = " ".join(query_tokens)
    if query_phrase in prompt_text.lower():
        phrase_bonus = 0.3

    return min(prompt_score + tag_score + phrase_bonus, 1.0)


def search(repo_path, query, category=None, threshold=0.2):
    """Search the asset repo. Returns (best_filename, best_score, best_category) or (None, 0, None)."""
    index = load_index(repo_path)
    if not index:
        return None, 0, None

    query_tokens = tokenize(query)
    if not query_tokens:
        return None, 0, None

    best_filename = None
    best_score = 0.0
    best_category = None

    for filename, entry in index.items():
        if category and entry.get("category") != category:
            continue
        s = score_entry(query_tokens, entry)
        if s > best_score:
            best_score = s
            best_filename = filename
            best_category = entry.get("category", "")

    if best_score >= threshold:
        return best_filename, best_score, best_category
    return None, best_score, None


def main():
    parser = argparse.ArgumentParser(description="Search the WebGAL asset repository")
    parser.add_argument("query", help="Search query (prompt text or keywords)")
    parser.add_argument("--repo", required=True, help="Path to asset repository")
    parser.add_argument("--category", choices=["figure", "background", "avatar"],
                        help="Limit search to one category")
    parser.add_argument("--threshold", type=float, default=0.2,
                        help="Minimum match score (default: 0.2)")
    args = parser.parse_args()

    filename, score, category = search(args.repo, args.query, args.category, args.threshold)

    result = {
        "found": filename is not None,
        "best_match": filename,
        "score": round(score, 3),
        "category": category,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
