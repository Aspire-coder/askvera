"""Upload generated policy section files to a test S3 prefix."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _require_file(path: Path, message: str) -> None:
    if not path.exists():
        raise FileNotFoundError(message)


def _count_files(package_dir: Path) -> tuple[int, int]:
    text_files = list(package_dir.glob("*.txt"))
    metadata_files = list(package_dir.glob("*.txt.metadata.json"))
    return len(text_files), len(metadata_files)


def _s3_uri(bucket: str, prefix: str) -> str:
    clean_prefix = prefix.strip("/")
    return f"s3://{bucket}/{clean_prefix}/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--profile", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_dir = args.package_dir.resolve()

    if not package_dir.is_dir():
        raise NotADirectoryError(f"Package folder not found: {package_dir}")

    _require_file(
        package_dir / "manifest.csv",
        f"manifest.csv was not found in {package_dir}. Run extract_policy_sections.py first.",
    )

    text_count, metadata_count = _count_files(package_dir)
    if text_count == 0:
        raise RuntimeError(f"No section .txt files found in {package_dir}.")
    if text_count != metadata_count:
        raise RuntimeError(
            f"Section file count ({text_count}) does not match metadata file count ({metadata_count})."
        )

    target = _s3_uri(args.bucket, args.prefix)
    base_command = ["aws"]
    if args.profile:
        base_command.extend(["--profile", args.profile])

    clean_command = [*base_command, "s3", "rm", target, "--recursive"]
    sync_command = [
        *base_command,
        "s3",
        "sync",
        str(package_dir),
        target,
        "--exclude",
        "*",
        "--include",
        "*.txt",
        "--include",
        "*.txt.metadata.json",
    ]
    if args.dry_run:
        clean_command.append("--dryrun")
        sync_command.append("--dryrun")

    print("Policy section package upload")
    print("-----------------------------")
    print(f"Package: {package_dir}")
    print(f"Text files: {text_count}")
    print(f"Metadata files: {metadata_count}")
    print(f"Target: {target}")
    print("")
    print("Cleaning target prefix:")
    print(" ".join(clean_command))
    print("")
    print("Uploading only searchable section files and metadata:")
    print(" ".join(sync_command))
    print("")

    subprocess.run(clean_command, check=True)
    subprocess.run(sync_command, check=True)

    print("")
    print("Upload complete.")
    print("Next: create a separate Bedrock Knowledge Base test data source that points to this S3 prefix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
