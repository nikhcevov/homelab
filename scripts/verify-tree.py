#!/usr/bin/env python3
"""Read-only rsync gate: exit 0 only when contents and metadata match."""

import argparse
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--source-host", help="Optional SSH source host; destination stays local"
    )
    parser.add_argument(
        "--ssh-command", default="ssh -o BatchMode=yes -o StrictHostKeyChecking=yes"
    )
    args = parser.parse_args()
    if not args.destination.is_dir():
        parser.error(f"Not an existing directory: {args.destination}")
    destination = args.destination.resolve()
    if args.source_host:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", args.source_host):
            parser.error(
                "Use an SSH hostname or IPv4 address, optionally prefixed by user@"
            )
        if not PurePosixPath(args.source).is_absolute() or not re.fullmatch(
            r"/[A-Za-z0-9_./-]*", args.source
        ):
            parser.error(
                "Remote source must be an absolute path without shell metacharacters"
            )
        source = args.source_host + ":" + args.source.rstrip("/") + "/"
    else:
        source_path = Path(args.source)
        if not source_path.is_dir():
            parser.error(f"Not an existing directory: {source_path}")
        source_path = source_path.resolve()
        if (
            source_path == destination
            or source_path in destination.parents
            or destination in source_path.parents
        ):
            parser.error(
                "Source and destination must be distinct, non-overlapping directories"
            )
        source = str(source_path) + "/"
    command = [
        "rsync",
        "--archive",
        "--hard-links",
        "--acls",
        "--xattrs",
        "--numeric-ids",
        "--dry-run",
        "--checksum",
        "--delete",
        "--itemize-changes",
        "--out-format=%i %n%L",
    ]
    if args.source_host:
        command += ["--rsh", args.ssh_command]
    result = subprocess.run(
        command + ["--", source, str(destination) + "/"],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        print(result.stderr, end="", file=sys.stderr)
        return 2
    if result.stdout:
        changes = result.stdout.splitlines()
        print(
            f"FAIL: {len(changes)} differences; no files were changed", file=sys.stderr
        )
        print("\n".join(changes[:50]), file=sys.stderr)
        if len(changes) > 50:
            print("Further differences omitted", file=sys.stderr)
        return 1
    print(
        f"PASS: {source} matches {destination} (contents, metadata, hardlinks, extra files)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
