# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "packaging",
#     "pyyaml",
# ]
# ///

import argparse
import json
from typing import Any, Optional

import yaml
from packaging.version import Version

CI_TARGETS_YAML = "ci-targets.yaml"
CI_EXTRA_SKIP_LABELS = ["documentation"]


def meets_conditional_version(version: str, min_version: str) -> bool:
    return Version(version) >= Version(min_version)


def parse_labels(labels: Optional[str]) -> dict[str, set[str]]:
    """Parse labels into a dict of category filters."""
    if not labels:
        return {}

    result: dict[str, set[str]] = {
        "platform": set(),
        "python": set(),
        "build": set(),
        "arch": set(),
        "libc": set(),
        "directives": set(),
    }

    for label in labels.split(","):
        label = label.strip()

        # Handle special labels
        if label in CI_EXTRA_SKIP_LABELS:
            result["directives"].add("skip")
            continue

        if not label or ":" not in label:
            continue

        category, value = label.split(":", 1)

        if category == "ci":
            category = "directives"

        if category in result:
            result[category].add(value)

    return result


def should_include_entry(entry: dict[str, str], filters: dict[str, set[str]]) -> bool:
    """Check if an entry satisfies the label filters."""
    if filters.get("directives") and "skip" in filters["directives"]:
        return False

    if filters.get("platform") and entry["platform"] not in filters["platform"]:
        return False

    if filters.get("python") and entry["python"] not in filters["python"]:
        return False

    if filters.get("arch") and entry["arch"] not in filters["arch"]:
        return False

    if (
        filters.get("libc")
        and entry.get("libc")
        and entry["libc"] not in filters["libc"]
    ):
        return False

    if filters.get("build"):
        build_options = set(entry.get("build_options", "").split("+"))
        if not all(f in build_options for f in filters["build"]):
            return False

    return True


def generate_matrix_entries(
    config: dict[str, Any],
    platform_filter: Optional[str] = None,
    label_filters: Optional[dict[str, set[str]]] = None,
) -> list[dict[str, str]]:
    matrix_entries = []

    for platform, platform_config in config.items():
        if platform_filter and platform != platform_filter:
            continue

        for target_triple, target_config in platform_config.items():
            add_matrix_entries_for_config(
                matrix_entries,
                target_triple,
                target_config,
                platform,
                label_filters.get("directives", set()),
            )

    # Apply label filters if present
    if label_filters:
        matrix_entries = [
            entry
            for entry in matrix_entries
            if should_include_entry(entry, label_filters)
        ]

    return matrix_entries


def add_matrix_entries_for_config(
    matrix_entries: list[dict[str, str]],
    target_triple: str,
    config: dict[str, Any],
    platform: str,
    directives: set[str],
) -> None:
    python_versions = config["python_versions"]
    build_options = config["build_options"]
    arch = config["arch"]

    # Create base entry that will be used for all variants
    base_entry = {
        "arch": arch,
        "target_triple": target_triple,
        "platform": platform,
    }

    # Add optional fields if they exist
    if "arch_variant" in config:
        base_entry["arch_variant"] = config["arch_variant"]
    if "libc" in config:
        base_entry["libc"] = config["libc"]
    if "vcvars" in config:
        base_entry["vcvars"] = config["vcvars"]
    if "run" in config:
        base_entry["run"] = str(config["run"]).lower()

    if "dry-run" in directives:
        base_entry["dry-run"] = "true"

    # Process regular build options
    for python_version in python_versions:
        for build_option in build_options:
            entry = base_entry.copy()
            entry.update(
                {
                    "python": python_version,
                    "build_options": build_option,
                }
            )
            matrix_entries.append(entry)

    # Process conditional build options (e.g., freethreaded)
    for conditional in config.get("build_options_conditional", []):
        min_version = conditional["minimum-python-version"]
        for python_version in python_versions:
            if not meets_conditional_version(python_version, min_version):
                continue

            for build_option in conditional["options"]:
                entry = base_entry.copy()
                entry.update(
                    {
                        "python": python_version,
                        "build_options": build_option,
                    }
                )
                matrix_entries.append(entry)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a JSON matrix for building distributions in CI"
    )
    parser.add_argument(
        "--platform",
        choices=["darwin", "linux", "windows"],
        help="Filter matrix entries by platform",
    )
    parser.add_argument(
        "--labels",
        help="Comma-separated list of labels to filter by (e.g., 'platform:darwin,python:3.13,build:debug'), all must match.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    labels = parse_labels(args.labels)

    with open(CI_TARGETS_YAML, "r") as f:
        config = yaml.safe_load(f)

    matrix = {
        "include": generate_matrix_entries(
            config,
            args.platform,
            labels,
        )
    }

    print(json.dumps(matrix))


if __name__ == "__main__":
    main()
