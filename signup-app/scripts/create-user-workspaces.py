#!/usr/bin/env python3
"""
Create an AnythingLLM workspace for each selected user and point chat at a model.

Uses the instance default LLM endpoint/credentials; only the workspace chat model
name is set (and optionally the provider slug if your stack needs it).

For each user:
  1. POST /api/v1/workspace/new
  2. POST /api/v1/admin/workspaces/{slug}/manage-users  (grant access)
  3. POST /api/v1/workspace/{slug}/update  (chatModel / optional chatProvider)

Usage:
  python create-user-workspaces.py --model-name qwen3-vl-8b --exclude admin

  python create-user-workspaces.py --model-name my-lab-model --include alice,bob

  python create-user-workspaces.py --model-name x --exclude "" --dry-run

  # If the default provider must be set explicitly (e.g. generic-openai):
  python create-user-workspaces.py --model-name x --exclude admin --chat-provider generic-openai

Environment variables (or .env file):
  ANYTHINGLLM_URL      AnythingLLM base URL
  ANYTHINGLLM_API_KEY  Admin API key
"""

from __future__ import annotations

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


def list_users(url: str, key: str) -> list[dict]:
    resp = requests.get(f"{url}/api/v1/admin/users", headers=hdr(key), timeout=15)
    resp.raise_for_status()
    return resp.json().get("users", [])


def create_workspace(url: str, key: str, name: str) -> dict | None:
    resp = requests.post(
        f"{url}/api/v1/workspace/new",
        headers=hdr(key),
        json={"name": name},
        timeout=30,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("workspace")


def assign_users(url: str, key: str, slug: str, user_ids: list[int]) -> bool:
    safe = quote(slug, safe="")
    resp = requests.post(
        f"{url}/api/v1/admin/workspaces/{safe}/manage-users",
        headers=hdr(key),
        json={"userIds": user_ids, "reset": False},
        timeout=30,
    )
    return resp.status_code == 200


def update_workspace_model(
    url: str, key: str, slug: str, model_name: str, chat_provider: str | None
) -> bool:
    safe = quote(slug, safe="")
    body: dict = {"chatModel": model_name}
    if chat_provider:
        body["chatProvider"] = chat_provider
    resp = requests.post(
        f"{url}/api/v1/workspace/{safe}/update",
        headers=hdr(key),
        json=body,
        timeout=30,
    )
    return resp.status_code == 200


def default_workspace_name(username: str, model_name: str) -> str:
    return f"{username} ({model_name})"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a workspace per user with a given chat model name.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--model-name",
        required=True,
        metavar="NAME",
        help="Value for workspace chatModel (OpenAI-compatible model id as configured on the instance).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--include",
        metavar="USER,...",
        help="Comma-separated usernames to provision (only these users).",
    )
    group.add_argument(
        "--exclude",
        metavar="USER,...",
        help="Comma-separated usernames to skip; provision everyone else.",
    )
    parser.add_argument(
        "--workspace-name-template",
        metavar="TEMPLATE",
        default="{username} ({model})",
        help='Display name for each workspace. Use "{username}" and "{model}" placeholders. Default: "%(default)s"',
    )
    parser.add_argument(
        "--chat-provider",
        metavar="PROVIDER",
        default=None,
        help="If set, sent as chatProvider on workspace update (e.g. generic-openai). Omit to only set chatModel.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without calling create/update APIs.",
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

    if args.include is not None:
        want = {n.strip().lower() for n in args.include.split(",") if n.strip()}
        selected = [u for u in users if u["username"].lower() in want]
        missing = want - {u["username"].lower() for u in selected}
        if missing:
            print(f"Warning: unknown usernames (skipped): {', '.join(sorted(missing))}")
    else:
        skip = {n.strip().lower() for n in args.exclude.split(",") if n.strip()}
        selected = [u for u in users if u["username"].lower() not in skip]

    if not selected:
        print("No users matched the filter. Nothing to do.")
        return

    model = args.model_name.strip()
    print(f"\nModel name: {model!r}")
    if args.chat_provider:
        print(f"Chat provider: {args.chat_provider!r}")
    print(f"\nWill provision {len(selected)} workspace(s):\n")
    for u in selected:
        wname = args.workspace_name_template.format(username=u["username"], model=model)
        print(f"  - {u['username']!r} → workspace {wname!r}")
    print()

    if args.dry_run:
        print("[DRY RUN] No changes made. Remove --dry-run to proceed.")
        return

    try:
        confirm = input(f"Create {len(selected)} workspace(s)? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return

    if confirm not in ("y", "yes"):
        print("Aborted.")
        return

    print()
    ok_n = 0
    fail_n = 0
    for u in selected:
        username = u["username"]
        uid = int(u["id"])
        wname = args.workspace_name_template.format(username=username, model=model)
        try:
            ws = create_workspace(url, key, wname)
            if not ws or not ws.get("slug"):
                print(f"  ✗ {username}: workspace create failed")
                fail_n += 1
                continue
            slug = ws["slug"]
            if not assign_users(url, key, slug, [uid]):
                print(f"  ✗ {username}: manage-users failed (workspace {slug!r} created)")
                fail_n += 1
                continue
            if not update_workspace_model(url, key, slug, model, args.chat_provider):
                print(f"  ✗ {username}: model update failed (workspace {slug!r} created + assigned)")
                fail_n += 1
                continue
            print(f"  ✓ {username} → {wname!r} (slug={slug})")
            ok_n += 1
        except requests.RequestException as exc:
            print(f"  ✗ {username}: {exc}")
            fail_n += 1

    print()
    print(f"Done. {ok_n} succeeded, {fail_n} failed.")


if __name__ == "__main__":
    main()
