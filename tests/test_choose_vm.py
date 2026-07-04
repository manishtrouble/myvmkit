import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "choose-vm.py"
_SPEC = importlib.util.spec_from_file_location("choose_vm", _MODULE_PATH)
choose_vm = importlib.util.module_from_spec(_SPEC)
assert _SPEC is not None and _SPEC.loader is not None
sys.modules[_SPEC.name] = choose_vm
_SPEC.loader.exec_module(choose_vm)


def server_type(
    name,
    *,
    cores=2,
    memory=4,
    architecture="x86",
    cpu_type="shared",
    deprecation=None,
    prices=None,
    locations=None,
):
    return {
        "name": name,
        "cores": cores,
        "memory": memory,
        "architecture": architecture,
        "cpu_type": cpu_type,
        "deprecation": deprecation,
        "prices": [
            {
                "location": location,
                "price_monthly": {"gross": str(gross), "net": str(gross)},
            }
            for location, gross in (prices or {}).items()
        ],
        "locations": [
            {"name": location, **metadata}
            for location, metadata in (locations or {}).items()
        ],
    }


def args(**overrides):
    values = {
        "locations": "fsn1,nbg1,hel1",
        "preferred_locations": "",
        "preferred_families": "",
        "min_cpu": 2,
        "min_ram": "4",
        "max_eur": "8",
        "architecture": "x86",
        "cpu_type": "shared",
        "skip_deprecated": True,
        "price_kind": "gross",
        "dry_run": False,
        "output": "terraform.auto.tfvars.json",
        "name": "test-vm",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ChooseVmTests(unittest.TestCase):
    def test_cheapest_candidate_that_satisfies_resource_price_and_architecture_filters_wins(self):
        payload = {
            "server_types": [
                server_type("too-small", cores=1, memory=8, prices={"fsn1": "1.00"}),
                server_type("wrong-arch", architecture="arm", prices={"fsn1": "1.50"}),
                server_type("over-budget", prices={"fsn1": "9.00"}),
                server_type("valid-expensive", prices={"fsn1": "7.00"}),
                server_type("valid-cheapest", prices={"nbg1": "4.25"}),
            ]
        }

        selected = choose_vm.choose_candidate(payload, args())

        self.assertEqual("valid-cheapest", selected.server_type)
        self.assertEqual("nbg1", selected.location)
        self.assertEqual(choose_vm.Decimal("4.25"), selected.monthly_eur)

    def test_unavailable_and_deprecated_locations_are_skipped(self):
        payload = {
            "server_types": [
                server_type(
                    "cx22",
                    prices={"fsn1": "2.00", "nbg1": "3.00", "hel1": "4.00"},
                    locations={
                        "fsn1": {"available": False},
                        "nbg1": {"deprecation": {"announced": "2024-01-01"}},
                        "hel1": {"available": True},
                    },
                )
            ]
        }

        selected = choose_vm.choose_candidate(payload, args())

        self.assertEqual("cx22", selected.server_type)
        self.assertEqual("hel1", selected.location)
        self.assertEqual(choose_vm.Decimal("4.00"), selected.monthly_eur)

    def test_writes_tfvars_json_with_selected_type_location_and_name(self):
        candidate = choose_vm.Candidate(
            server_type="cx22",
            location="fsn1",
            monthly_eur=choose_vm.Decimal("4.00"),
            cores=2,
            memory_gb=choose_vm.Decimal("4"),
            architecture="x86",
            cpu_type="shared",
            recommended=False,
            family_rank=0,
            location_rank=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "nested" / "terraform.auto.tfvars.json"
            written = choose_vm.write_tfvars(
                candidate,
                args(output=str(output), name="chosen-by-test", dry_run=False),
            )

            self.assertEqual(
                {"server_type": "cx22", "location": "fsn1", "name": "chosen-by-test"},
                written,
            )
            self.assertEqual(written, json.loads(output.read_text(encoding="utf-8")))

    def test_dry_run_returns_tfvars_content_without_writing_output_file(self):
        candidate = choose_vm.Candidate(
            server_type="cpx31",
            location="hel1",
            monthly_eur=choose_vm.Decimal("7.25"),
            cores=4,
            memory_gb=choose_vm.Decimal("8"),
            architecture="x86",
            cpu_type="shared",
            recommended=True,
            family_rank=0,
            location_rank=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "terraform.auto.tfvars.json"
            rendered = choose_vm.write_tfvars(
                candidate,
                args(output=str(output), name="dry-run-vm", dry_run=True),
            )

            self.assertEqual(
                {"server_type": "cpx31", "location": "hel1", "name": "dry-run-vm"},
                rendered,
            )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
