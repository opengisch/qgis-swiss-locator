"""
Data files used by the plugin, run from the repository root:

  python -m scripts build                generate them into the plugin sources,
                                         to test the plugin locally
  python -m scripts build --site _site   generate the GitHub Pages site (CI)
  python -m scripts fetch                download the published ones into the
                                         plugin sources (packaging)
  python -m scripts fetch --site _site   download the published ones into the
                                         GitHub Pages site, to publish them
                                         again with the documentation (CI)

In the plugin sources, they go to swiss_locator/remote_data/bundled/, which is
git-ignored. The plugin uses them when they are fresher than its cache.
"""

import argparse
import logging
import os
import sys

from scripts.build import build_files
from scripts.datasets import DATASETS
from scripts.published import download
from swiss_locator.remote_data import spec


class _GitHubActionsFormatter(logging.Formatter):
    """Turn warnings and errors into GitHub Actions annotations."""

    def format(self, record):
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            return f"::error::{message}"
        if record.levelno >= logging.WARNING:
            return f"::warning::{message}"
        return message


def _setup_logging():
    handler = logging.StreamHandler()
    if os.environ.get("GITHUB_ACTIONS"):
        handler.setFormatter(_GitHubActionsFormatter("%(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build_parser = commands.add_parser("build", help="generate the data files")
    build_parser.add_argument(
        "--site",
        help="generate the GitHub Pages site in this folder, keeping the "
        "published version of a dataset that cannot be generated",
    )
    build_parser.add_argument(
        "--only",
        action="append",
        choices=[dataset.file_name for dataset in DATASETS],
        metavar="FILE_NAME",
        help="generate only this file, can be repeated",
    )

    fetch_parser = commands.add_parser(
        "fetch", help="download the published data files"
    )
    fetch_parser.add_argument(
        "--site",
        help="download them, with the manifest, into the GitHub Pages site "
        "in this folder",
    )

    args = parser.parse_args(argv)
    _setup_logging()

    if args.command == "fetch":
        if args.site:
            destination = os.path.join(args.site, spec.DATA_PATH)
            complete = download(destination, spec.DATA_FILES + (spec.MANIFEST,))
        else:
            complete = download(spec.BUNDLED_DIR)
        return 0 if complete else 1
    if args.site:
        output_dir = os.path.join(args.site, spec.DATA_PATH)
        report = build_files(output_dir, publish=True, only=args.only)
    else:
        output_dir = spec.BUNDLED_DIR
        report = build_files(output_dir, only=args.only)
    _print_summary(report, output_dir)
    failed = any(entry["status"] == "failed" for entry in report.values())
    return 1 if failed else 0


def _print_summary(report: dict[str, dict], output_dir: str):
    """Print the outcome of each file, also as GitHub Actions job summary."""
    lines = []
    for file_name, entry in report.items():
        if entry["status"] == "failed":
            lines.append(f"✗ {file_name}: FAILED, {entry['error']}")
        else:
            symbol = "✓" if entry["status"] == "updated" else "!"
            lines.append(
                f"{symbol} {file_name}: {entry['status']}, {entry['count']} items"
            )
        lines.extend(f"    {note}" for note in entry["notes"])
    lines.append(f"Written to {os.path.abspath(output_dir)}")

    print("\nSummary\n" + "\n".join(f"  {line}" for line in lines))
    job_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if job_summary:
        with open(job_summary, "a", encoding="utf-8") as f:
            f.write("### Data files\n\n```\n" + "\n".join(lines) + "\n```\n")


if __name__ == "__main__":
    sys.exit(main())
