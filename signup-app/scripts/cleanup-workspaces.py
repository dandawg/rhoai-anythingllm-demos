#!/usr/bin/env python3
"""
AnythingLLM workspace cleanup utility.

Deletes workspaces by matching slug or name (case-insensitive exact match).
Useful for resetting demo environments between sessions.

Usage:
  # Delete specific workspaces only (match slug or full name)
  python cleanup-workspaces.py --include work,thinking

  # Delete ALL workspaces except these
  python cleanup-workspaces.py --exclude work,thinking,presenter-ws

  # Preview without deleting
  python cleanup-workspaces.py --exclude demo --dry-run

  # Delete ALL workspaces (use with caution)
  python cleanup-workspaces.py --exclude ""

Environment variables (or .env file):
  ANYTHINGLLM_URL      AnythingLLM base URL
  ANYTHINGLLM_API_KEY  Admin API key
"""

import argparse
import os
import sys
from urllib.parse import quote

try:
    import requests
except ImportError:
    print("Error: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def get_config() -> tuple[str, str]:
    url = os.getenv("ANYTHINGLLM_URL", "").rstrip("/")
    key = os.getenv("ANYTHINGLLM_API_KEY", "")
    if not url:
        print("Error: ANYTHINGLLM_URL is not set.")
        print("  Set it as an environment variable or in a .env file.")
        sys.exit(1)
    if not key:
        print("Error: ANYTHINGLLM_API_KEY is not set.")
        print("  Set it as an environment variable or in a .env file.")
        sys.exit(1)
    return url, key


def hdr(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def list_workspaces(url: str, key: str) -> list[dict]:
    resp = requests.get(f"{url}/api/v1/workspaces", headers=hdr(key), timeout=30)
    resp.raise_for_status()
    return resp.json().get("workspaces", [])


def delete_workspace(url: str, key: str, slug: str) -> bool:
    safe = quote(slug, safe="")
    resp = requests.delete(f"{url}/api/v1/workspace/{safe}", headers=hdr(key), timeout=120)
    return resp.status_code == 200


def workspace_tokens(w: dict) -> set[str]:
    """Lowercase tokens used for include/exclude matching (slug and name)."""
    out: set[str] = set()
    if w.get("slug"):
        out.add(str(w["slug"]).lower().strip())
    if w.get("name"):
        out.add(str(w["name"]).lower().strip())
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete AnythingLLM workspaces by include or exclude list (slug or name).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--include",
        metavar="SLUG_OR_NAME,...",
        help="Comma-separated list; delete only workspaces whose slug or name matches exactly (case-insensitive).",
    )
    group.add_argument(
        "--exclude",
        metavar="SLUG_OR_NAME,...",
        help="Comma-separated list to keep; delete all other workspaces.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without actually deleting.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    url, key = get_config()

    print(f"Connecting to AnythingLLM at {url} …")

    try:
        workspaces = list_workspaces(url, key)
    except requests.RequestException as exc:
        print(f"Error fetching workspaces: {exc}")
        sys.exit(1)

    if not workspaces:
        print("No workspaces found.")
        return

    print(f"Found {len(workspaces)} workspace(s):\n")
    for w in workspaces:
        print(f"  [{w.get('id', '?'):>4}]  slug={w.get('slug', '?')!r}  name={w.get('name', '?')!r}")
    print()

    if args.include is not None:
        targets_raw = {n.strip().lower() for n in args.include.split(",") if n.strip()}
        targets = [w for w in workspaces if targets_raw & workspace_tokens(w)]
        matched_tokens: set[str] = set()
        for w in targets:
            matched_tokens |= targets_raw & workspace_tokens(w)
        not_found = targets_raw - matched_tokens
        if not_found:
            print(f"Warning: no workspace matched these tokens: {', '.join(sorted(not_found))}")
    else:
        exclude_raw = {n.strip().lower() for n in args.exclude.split(",") if n.strip()}
        targets = [w for w in workspaces if not (exclude_raw & workspace_tokens(w))]

    if not targets:
        print("No workspaces matched the filter. Nothing to delete.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Will delete {len(targets)} workspace(s):")
    for w in targets:
        print(f"  - {w.get('name')} (slug={w.get('slug')})")
    print()

    if args.dry_run:
        print("[DRY RUN] No changes made. Remove --dry-run to proceed.")
        return

    try:
        confirm = input(f"Delete {len(targets)} workspace(s)? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return

    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    print()
    deleted = 0
    failed = 0
    for w in targets:
        slug = w.get("slug")
        name = w.get("name", slug)
        try:
            ok = delete_workspace(url, key, slug)
            if ok:
                print(f"  ✓ Deleted {name!r} ({slug})")
                deleted += 1
            else:
                print(f"  ✗ Failed to delete {name!r} (HTTP not 200)")
                failed += 1
        except requests.RequestException as exc:
            print(f"  ✗ Error deleting {name!r}: {exc}")
            failed += 1

    print()
    print(f"Done. {deleted} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
