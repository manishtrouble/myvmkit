#!/usr/bin/env python3
"""Select a Hetzner Cloud server type/location and write Terraform tfvars.

The script deliberately runs before Terraform so `terraform plan` stays deterministic.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

DEFAULT_API_URL = "https://api.hetzner.cloud/v1/server_types"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "terraform" / "terraform.auto.tfvars.json"


@dataclass(frozen=True)
class Candidate:
    server_type: str
    location: str
    monthly_eur: Decimal
    cores: int
    memory_gb: Decimal
    architecture: str
    cpu_type: str
    recommended: bool
    family_rank: int
    location_rank: int

    def sort_key(self) -> tuple[Decimal, int, int, int, str, str]:
        return (
            self.monthly_eur,
            0 if self.recommended else 1,
            self.location_rank,
            self.family_rank,
            self.server_type,
            self.location,
        )


def parse_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"invalid decimal for {field}: {value!r}") from exc


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def fetch_json(api_url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        api_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "myvmkit-choose-vm/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Hetzner API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"failed to call Hetzner API: {exc.reason}") from exc


def load_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.fixture:
        return json.loads(Path(args.fixture).read_text(encoding="utf-8"))

    token = args.token or os.environ.get("HCLOUD_TOKEN")
    if not token:
        raise SystemExit("HCLOUD_TOKEN is required unless --fixture is used")

    return fetch_json(args.api_url, token)


def price_for_location(server_type: dict[str, Any], location: str, price_kind: str) -> Decimal | None:
    for price in server_type.get("prices", []):
        if price.get("location") != location:
            continue
        monthly = price.get("price_monthly") or {}
        if price_kind not in monthly:
            return None
        return parse_decimal(monthly[price_kind], f"{server_type.get('name')}.{location}.price_monthly.{price_kind}")
    return None


def location_metadata(server_type: dict[str, Any], location: str) -> dict[str, Any] | None:
    for item in server_type.get("locations", []) or []:
        if item.get("name") == location:
            return item
    return None


def family_rank(name: str, preferred_families: list[str]) -> int:
    if not preferred_families:
        return 0
    for idx, family in enumerate(preferred_families):
        if name.startswith(family):
            return idx
    return len(preferred_families)


def location_rank(location: str, preferred_locations: list[str], allowed_locations: list[str]) -> int:
    ordering = preferred_locations or allowed_locations
    try:
        return ordering.index(location)
    except ValueError:
        return len(ordering)


def iter_candidates(payload: dict[str, Any], args: argparse.Namespace) -> Iterable[Candidate]:
    allowed_locations = split_csv(args.locations)
    preferred_locations = split_csv(args.preferred_locations)
    preferred_families = split_csv(args.preferred_families)
    min_ram = parse_decimal(args.min_ram, "--min-ram")
    max_eur = parse_decimal(args.max_eur, "--max-eur")

    for server_type in payload.get("server_types", []):
        name = server_type.get("name")
        if not name:
            continue

        if preferred_families and not any(name.startswith(family) for family in preferred_families):
            continue

        cores = int(server_type.get("cores") or 0)
        memory = parse_decimal(server_type.get("memory") or 0, f"{name}.memory")
        architecture = server_type.get("architecture") or ""
        cpu_type = server_type.get("cpu_type") or ""

        if cores < args.min_cpu:
            continue
        if memory < min_ram:
            continue
        if args.architecture and architecture != args.architecture:
            continue
        if args.cpu_type and cpu_type != args.cpu_type:
            continue
        if args.skip_deprecated and server_type.get("deprecation"):
            continue

        for location in allowed_locations:
            metadata = location_metadata(server_type, location)
            if metadata is not None:
                if metadata.get("available") is False:
                    continue
                if args.skip_deprecated and metadata.get("deprecation"):
                    continue

            monthly = price_for_location(server_type, location, args.price_kind)
            if monthly is None or monthly > max_eur:
                continue

            yield Candidate(
                server_type=name,
                location=location,
                monthly_eur=monthly,
                cores=cores,
                memory_gb=memory,
                architecture=architecture,
                cpu_type=cpu_type,
                recommended=bool(metadata.get("recommended")) if metadata else False,
                family_rank=family_rank(name, preferred_families),
                location_rank=location_rank(location, preferred_locations, allowed_locations),
            )


def choose_candidate(payload: dict[str, Any], args: argparse.Namespace) -> Candidate:
    candidates = sorted(iter_candidates(payload, args), key=Candidate.sort_key)
    if not candidates:
        raise SystemExit(
            "no matching Hetzner server type/location found; relax min CPU/RAM, max EUR, architecture, or locations"
        )
    return candidates[0]


def write_tfvars(candidate: Candidate, args: argparse.Namespace) -> dict[str, str]:
    content = {
        "server_type": candidate.server_type,
        "location": candidate.location,
        "name": args.name,
    }

    if args.dry_run:
        return content

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return content


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Hetzner server_types API URL")
    parser.add_argument("--token", default=None, help="Hetzner API token; defaults to HCLOUD_TOKEN")
    parser.add_argument("--fixture", help="Read a saved API JSON response instead of calling Hetzner")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output terraform.auto.tfvars.json path")
    parser.add_argument("--dry-run", action="store_true", help="Print selection without writing tfvars")

    parser.add_argument("--name", default=f"devbox-{date.today().isoformat()}", help="Terraform var.name to write")
    parser.add_argument("--min-cpu", type=int, default=2, help="Minimum vCPU count")
    parser.add_argument("--min-ram", default="4", help="Minimum RAM in GB")
    parser.add_argument("--max-eur", default="8", help="Maximum monthly EUR price")
    parser.add_argument("--locations", default="fsn1,nbg1,hel1", help="Allowed Hetzner locations, comma-separated")
    parser.add_argument("--preferred-locations", default="", help="Tie-breaker location order, comma-separated")
    parser.add_argument("--preferred-families", default="", help="Allowed/preferred server type prefixes, e.g. cx,cpx")
    parser.add_argument("--architecture", default="x86", help="Architecture filter, e.g. x86 or arm")
    parser.add_argument("--cpu-type", default="", help="Optional CPU type filter, e.g. shared or dedicated")
    parser.add_argument("--price-kind", choices=("gross", "net"), default="gross", help="Use gross or net monthly price")
    parser.add_argument("--include-deprecated", dest="skip_deprecated", action="store_false", help="Allow deprecated types/locations")
    parser.set_defaults(skip_deprecated=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    payload = load_payload(args)
    candidate = choose_candidate(payload, args)
    tfvars = write_tfvars(candidate, args)

    print(
        "Selected: "
        f"type={candidate.server_type} "
        f"location={candidate.location} "
        f"monthly_{args.price_kind}_eur={candidate.monthly_eur} "
        f"cores={candidate.cores} "
        f"ram_gb={candidate.memory_gb} "
        f"arch={candidate.architecture} "
        f"cpu_type={candidate.cpu_type} "
        f"recommended={str(candidate.recommended).lower()}"
    )
    print(json.dumps(tfvars, indent=2, sort_keys=True))

    if args.dry_run:
        print("Dry run: did not write terraform.auto.tfvars.json")
    else:
        print(f"Wrote {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
