#!/usr/bin/env python3
"""Fetch and update the monthly 280blocker AdGuard DNS blocklist."""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

TARGET_PATH = "/opt/dnsfilter/work/userfilters/280blocker.txt"
URL_TEMPLATE = "https://280blocker.net/files/280blocker_domain_ag_{yyyymm}.txt"
ADGUARD_REFRESH_URL = "http://127.0.0.1:3000/control/filtering/refresh"
SERVICE_NAME = "dnsfilter"
USER_AGENT = "HomeNetwork-DnsFilter-Updater/1.0"
MIN_VALID_BYTES = 1000


def build_month_candidates(today: datetime.date | None = None) -> list[str]:
    """Return [current YYYYMM, previous YYYYMM] for monthly 280blocker files."""
    if today is None:
        today = datetime.date.today()
    first_of_this_month = today.replace(day=1)
    last_month = first_of_this_month - datetime.timedelta(days=1)
    return [today.strftime("%Y%m"), last_month.strftime("%Y%m")]


def is_valid_filter(content: bytes) -> bool:
    """Verify the downloaded payload looks like a non-empty filter text file."""
    if len(content) < MIN_VALID_BYTES:
        return False
    head = content[:512].lstrip().lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html"):
        return False
    return True


def fetch_latest_filter() -> tuple[str, bytes] | tuple[None, None]:
    """Try current and previous month URLs and return (url, content) on success."""
    for yyyymm in build_month_candidates():
        url = URL_TEMPLATE.format(yyyymm=yyyymm)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if is_valid_filter(data):
                        return url, data
                    print(f"Downloaded content from {url} failed validation", file=sys.stderr)
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} fetching {url}", file=sys.stderr)
        except urllib.error.URLError as e:
            print(f"Network error fetching {url}: {e.reason}", file=sys.stderr)
    return None, None


def file_sha256(path: str) -> str | None:
    """Return SHA-256 hex digest of an existing file, or None if missing."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_atomic(path: str, data: bytes) -> None:
    """Atomically write data to path with 0644 permissions."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".280blocker_", dir=parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def refresh_dnsfilter() -> None:
    """Ask AdGuard Home to reload blocklists, falling back to service restart if auth is enabled."""
    payload = json.dumps({"whitelist": False}).encode("utf-8")
    req = urllib.request.Request(
        ADGUARD_REFRESH_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if 200 <= resp.status < 300:
                return
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Web UI authentication is configured; restart service so local filter change is loaded.
            subprocess.run(["systemctl", "try-restart", SERVICE_NAME], check=False)
            return
        print(f"DNS filter refresh returned HTTP {e.code}", file=sys.stderr)
    except urllib.error.URLError:
        # Service may not be started yet (e.g., initial Ansible provisioning).
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Update 280blocker DNS filter list")
    parser.add_argument(
        "--init",
        action="store_true",
        help="Ensure target file exists even if download fails; skip API refresh.",
    )
    parser.add_argument("--output", default=TARGET_PATH, help="Output filter file path")
    args = parser.parse_args()

    url, data = fetch_latest_filter()
    if data is None:
        if args.init:
            if not os.path.exists(args.output):
                write_atomic(args.output, b"! Initial placeholder: 280blocker fetch failed\n")
            print("Warning: could not fetch 280blocker filter during init", file=sys.stderr)
            return 0
        print("Error: failed to fetch 280blocker filter for current and previous month", file=sys.stderr)
        return 1

    old_hash = file_sha256(args.output)
    new_hash = hashlib.sha256(data).hexdigest()
    if old_hash == new_hash:
        return 0

    write_atomic(args.output, data)
    print(f"Updated {args.output} from {url}")
    if not args.init:
        refresh_dnsfilter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
