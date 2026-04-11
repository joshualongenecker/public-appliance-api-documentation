#!/usr/bin/env python3
"""
generate_writable_erds.py

Reads appliance_api.json and appliance_api_erd_definitions.json, identifies
every ERD that:
  1. Appears in appliance_api.json (i.e. is part of the public API surface), and
  2. Has "write" listed in its operations in the ERD definitions.

For each match the script records whether a paired Status ERD and/or a paired
Request ERD exists, which is useful for evaluating how "safe" it is to write to
that ERD.

The output is written to docs/writable_erds.md.

Usage:
    python3 generate_writable_erds.py
"""

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
API_FILE = SCRIPT_DIR / "appliance_api.json"
ERD_DEFINITIONS_FILE = SCRIPT_DIR / "appliance_api_erd_definitions.json"
OUTPUT_FILE = SCRIPT_DIR / "docs" / "writable_erds.md"


def collect_api_erd_ids(api_data: dict) -> set[str]:
    """Return the lowercase set of all ERD ids mentioned in appliance_api.json."""
    ids: set[str] = set()

    def add_features(version: dict) -> None:
        for feature in version.get("features", []):
            for erd in feature.get("required", []):
                ids.add(erd["erd"].lower())
            for erd in feature.get("optional", []):
                ids.add(erd["erd"].lower())

    for version in api_data["common"]["versions"].values():
        add_features(version)

    for feature_api in api_data["featureApis"].values():
        for version in feature_api["versions"].values():
            add_features(version)

    return ids


def base_name(name: str) -> str:
    """Strip trailing 'Status' or 'Request' suffix and normalise."""
    n = name.strip()
    n = re.sub(r"\s+Status$", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+Request$", "", n, flags=re.IGNORECASE)
    return n.lower().strip()


def build_paired_maps(erds: list) -> tuple[dict, dict]:
    """
    Return two mappings:
      request_to_status: erd_id -> list of paired status ERD ids
      status_to_request: erd_id -> list of paired request ERD ids
    A pair is defined as two ERDs whose names share the same base and end with
    'Request' and 'Status' respectively.
    """
    by_base: dict[str, list] = {}
    for e in erds:
        b = base_name(e["name"])
        by_base.setdefault(b, []).append(e)

    request_to_status: dict[str, list[str]] = {}
    status_to_request: dict[str, list[str]] = {}

    for group in by_base.values():
        request_erds = [e for e in group if e["name"].lower().endswith("request")]
        status_erds = [e for e in group if e["name"].lower().endswith("status")]
        if request_erds and status_erds:
            for req in request_erds:
                request_to_status[req["id"]] = [s["id"] for s in status_erds]
            for sta in status_erds:
                status_to_request[sta["id"]] = [r["id"] for r in request_erds]

    return request_to_status, status_to_request


def clean_description(desc: str) -> str:
    """Collapse newlines/whitespace and escape pipe characters for markdown tables."""
    cleaned = re.sub(r"\s*\n\s*", " ", desc.strip())
    cleaned = cleaned.replace("|", "\\|")
    return cleaned


def build_rows(
    erds: list,
    api_ids: set[str],
    request_to_status: dict,
    status_to_request: dict,
) -> list[dict]:
    """Build table row data for every writable ERD that appears in the API."""
    rows = []
    for e in erds:
        if "write" not in e.get("operations", []):
            continue
        if e["id"].lower() not in api_ids:
            continue

        status_ids = ", ".join(request_to_status.get(e["id"], []))
        request_ids = ", ".join(status_to_request.get(e["id"], []))

        rows.append(
            {
                "name": e["name"],
                "erd_id": e["id"],
                "has_status_erd": "Yes" if status_ids else "No",
                "status_ids": status_ids,
                "has_request_erd": "Yes" if request_ids else "No",
                "request_ids": request_ids,
                "ha_domain": e.get("ha_domain", ""),
                "description": clean_description(e.get("description", "")),
            }
        )

    rows.sort(key=lambda r: int(r["erd_id"], 16))
    return rows


def write_markdown(rows: list[dict], output_path: Path) -> None:
    """Write the writable ERDs markdown table to output_path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Writable ERDs",
        "",
        "Every ERD that appears in the public Appliance API (`appliance_api.json`) and "
        "supports **write** operations according to the ERD definitions. "
        "The *Has Status ERD* and *Has Request ERD* columns indicate whether a "
        "complementary paired ERD exists, which can help identify how safe it is to write "
        "to that ERD.",
        "",
        "| Name | ERD | Has Status ERD | Status ERD(s) | Has Request ERD | Request ERD(s) | HA Domain | Description |",
        "| ---- | --- | -------------- | ------------- | --------------- | -------------- | --------- | ----------- |",
    ]

    for r in rows:
        lines.append(
            f"| {r['name']} | {r['erd_id']} | {r['has_status_erd']} | {r['status_ids']} "
            f"| {r['has_request_erd']} | {r['request_ids']} | {r['ha_domain']} | {r['description']} |"
        )

    lines += [
        "",
        f"*Total: {len(rows)} writable ERDs*",
        "",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written {len(rows)} rows to {output_path}")


def main() -> None:
    for path in (API_FILE, ERD_DEFINITIONS_FILE):
        if not path.exists():
            print(f"ERROR: {path} not found", file=sys.stderr)
            sys.exit(1)

    with API_FILE.open(encoding="utf-8") as f:
        api_data = json.load(f)

    with ERD_DEFINITIONS_FILE.open(encoding="utf-8") as f:
        defs_data = json.load(f)

    erds = defs_data["erds"]
    api_ids = collect_api_erd_ids(api_data)
    request_to_status, status_to_request = build_paired_maps(erds)
    rows = build_rows(erds, api_ids, request_to_status, status_to_request)
    write_markdown(rows, OUTPUT_FILE)


if __name__ == "__main__":
    main()
