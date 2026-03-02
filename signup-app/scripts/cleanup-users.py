#!/usr/bin/env python3
"""
AnythingLLM user cleanup utility.

Deletes users from an AnythingLLM instance, optionally filtered by an include
or exclude list. Useful for resetting demo environments between sessions.

Usage:
  # Delete specific users only
  python cleanup-users.py --include alice,bob,charlie

  # Delete ALL users except these (e.g. keep admin accounts)
  python cleanup-users.py --exclude admin,presenter

  # Preview what would be deleted without making changes
  python cleanup-users.py --exclude admin --dry-run

  # Delete ALL users (no filter — use with caution!)
  python cleanup-users.py --exclude ""

Environment variables (or .env file):
  ANYTHINGLLM_URL      AnythingLLM base URL  (e.g. https://anythingllm-demo-apps.apps.cluster.example.com)
  ANYTHINGLLM_API_KEY  Admin API key
"""

import argparse
import os
import sys

try:
    import requests
except ImportError:
    print("Error: 'requests' is not installed. Run: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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


def headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def list_users(url: str, key: str) -> list[dict]:
    resp = requests.get(f"{url}/api/v1/admin/users", headers=headers(key), timeout=15)
    resp.raise_for_status()
    return resp.json().get("users", [])


def delete_user(url: str, key: str, user_id: int) -> bool:
    resp = requests.delete(f"{url}/api/v1/admin/users/{user_id}", headers=headers(key), timeout=15)
    return resp.status_code == 200 and resp.json().get("success", False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete AnythingLLM users by include or exclude list.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--include",
        metavar="USER,...",
        help="Comma-separated list of usernames to delete (delete only these).",
    )
    group.add_argument(
        "--exclude",
        metavar="USER,...",
        help="Comma-separated list of usernames to keep (delete everyone else).",
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
        users = list_users(url, key)
    except requests.RequestException as exc:
        print(f"Error fetching users: {exc}")
        sys.exit(1)

    if not users:
        print("No users found.")
        return

    print(f"Found {len(users)} user(s):\n")
    for u in users:
        print(f"  [{u['id']:>4}]  {u['username']:<32}  role={u.get('role', '?')}")
    print()

    # Determine target set
    if args.include is not None:
        targets_raw = {n.strip().lower() for n in args.include.split(",") if n.strip()}
        targets = [u for u in users if u["username"].lower() in targets_raw]
        not_found = targets_raw - {u["username"].lower() for u in targets}
        if not_found:
            print(f"Warning: these usernames were not found: {', '.join(sorted(not_found))}")
    else:
        exclude_raw = {n.strip().lower() for n in args.exclude.split(",") if n.strip()}
        targets = [u for u in users if u["username"].lower() not in exclude_raw]

    if not targets:
        print("No users matched the filter. Nothing to delete.")
        return

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Will delete {len(targets)} user(s):")
    for u in targets:
        print(f"  - {u['username']} (id={u['id']})")
    print()

    if args.dry_run:
        print("[DRY RUN] No changes made. Remove --dry-run to proceed.")
        return

    # Confirm
    try:
        confirm = input(f"Delete {len(targets)} user(s)? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return

    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    print()
    deleted = 0
    failed = 0
    for u in targets:
        try:
            ok = delete_user(url, key, u["id"])
            if ok:
                print(f"  ✓ Deleted {u['username']}")
                deleted += 1
            else:
                print(f"  ✗ Failed to delete {u['username']} (API returned failure)")
                failed += 1
        except requests.RequestException as exc:
            print(f"  ✗ Error deleting {u['username']}: {exc}")
            failed += 1

    print()
    print(f"Done. {deleted} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
