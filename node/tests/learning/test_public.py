from pathlib import Path

import pytest

from mia.learning.public import licence_verdict, load_public


@pytest.mark.parametrize(
    ("licence", "verdict"),
    [
        # ========== ALLOWED: Permissive licences ==========
        ("CC-BY-4.0", "allowed"),
        ("CC BY 4.0", "allowed"),
        ("CC BY-4.0", "allowed"),
        ("CC-BY-3.0", "allowed"),
        ("CC BY 3.0", "allowed"),
        ("MIT", "allowed"),
        ("Apache-2.0", "allowed"),
        ("Apache 2.0", "allowed"),
        ("Apache License 2.0", "allowed"),
        ("CC0-1.0", "allowed"),
        ("CC0", "allowed"),
        ("BSD-2-Clause", "allowed"),
        ("BSD 2-Clause", "allowed"),
        ("BSD-3-Clause", "allowed"),
        ("BSD 3-Clause", "allowed"),
        ("MPL-2.0", "allowed"),
        # ========== NEEDS_APPROVAL: Share-alike/copyleft/custom ==========
        ("CC-BY-SA-4.0", "needs_approval"),
        ("GPL-3.0", "needs_approval"),
        ("ODbL", "needs_approval"),
        ("custom", "needs_approval"),
        # ========== NEVER: Non-commercial variants ==========
        ("CC-BY-NC-4.0", "never"),
        ("CC-BY-NC-ND-4.0", "never"),
        ("CC-BY-NC-SA-4.0", "never"),
        ("CC BY-NC", "never"),
        ("cc by-nc 4.0", "never"),
        ("CC BY NC SA", "never"),
        ("cc-by-nc-4.0", "never"),
        ("Non-commercial", "never"),
        ("NonCommercial", "never"),
        ("noncommercial", "never"),
        ("cc_by_nc_4.0", "never"),
        ("CC-BY-NC4.0", "never"),
        ("(NC)", "never"),
        ("CC-BY-NC,research", "never"),
        ("https://creativecommons.org/licenses/by-nc/4.0/", "never"),
        # ========== NEVER: Other unrecognised/restricted ==========
        ("unknown", "never"),
        ("unknown license", "never"),
        ("proprietary", "never"),
        ("other", "never"),
        ("n/a", "never"),
        ("none", "never"),
        ("unspecified", "never"),
        ("tbd", "never"),
        # ========== NEVER: Empty/whitespace ==========
        ("", "never"),
        ("   ", "never"),
    ],
)
def test_licence_rules(licence: str, verdict: str) -> None:
    assert licence_verdict(licence) == verdict


def test_load_refuses_non_commercial_and_unapproved_share_alike(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text(
        "datasets:\n- {name: nllb, source: hf, version: '1', licence: CC-BY-NC-4.0, use: train}\n"
    )
    with pytest.raises(ValueError, match="never"):
        load_public(path)
    path.write_text(
        "datasets:\n- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other}\n"
    )
    with pytest.raises(ValueError, match="approval"):
        load_public(path)
    path.write_text(
        "datasets:\n- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other, approved_by: Allan}\n"
    )
    assert load_public(path).datasets[0].name == "sgd"


def test_load_empty_yaml_returns_empty_spec(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text("")
    spec = load_public(path)
    assert spec.datasets == []
    assert spec.rejected == []


def test_load_empty_file_with_datasets_field(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text("datasets: []\n")
    spec = load_public(path)
    assert spec.datasets == []
    assert spec.rejected == []


def test_rejected_list_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text(
        "datasets:\n"
        "- {name: sgd, source: hf, version: '1', licence: CC-BY-4.0, use: train}\n"
        "rejected:\n"
        "- {name: rejected1, reason: 'unknown license'}\n"
        "- {name: rejected2, reason: 'commercial use only'}\n"
    )
    spec = load_public(path)
    assert len(spec.rejected) == 2
    assert spec.rejected[0]["name"] == "rejected1"
    assert spec.rejected[0]["reason"] == "unknown license"
    assert spec.rejected[1]["name"] == "rejected2"
    assert spec.rejected[1]["reason"] == "commercial use only"


def test_load_with_multiple_datasets_and_mixed_verdicts(tmp_path: Path) -> None:
    path = tmp_path / "public.yaml"
    path.write_text(
        "datasets:\n"
        "- {name: mit_data, source: hf, version: '1', licence: MIT, use: train}\n"
        "- {name: custom_data, source: hf, version: '2', licence: custom, use: other, approved_by: Bob}\n"
    )
    spec = load_public(path)
    assert len(spec.datasets) == 2
    assert spec.datasets[0].name == "mit_data"
    assert spec.datasets[1].name == "custom_data"
    assert spec.datasets[1].approved_by == "Bob"


def test_nc_licence_with_approved_by_still_raises(tmp_path: Path) -> None:
    """NC licence is never allowed even with approval."""
    path = tmp_path / "public.yaml"
    path.write_text(
        "datasets:\n"
        "- {name: nllb, source: hf, version: '1', licence: CC-BY-NC-4.0, use: train, approved_by: Admin}\n"
    )
    with pytest.raises(ValueError, match="never"):
        load_public(path)


def test_blank_approved_by_raises_approval_error(tmp_path: Path) -> None:
    """Blank/whitespace approved_by is treated as missing for needs_approval."""
    path = tmp_path / "public.yaml"
    path.write_text(
        "datasets:\n"
        "- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other, approved_by: ''}\n"
    )
    with pytest.raises(ValueError, match="approval"):
        load_public(path)
    path.write_text(
        "datasets:\n"
        "- {name: sgd, source: hf, version: '1', licence: CC-BY-SA-4.0, use: other, approved_by: '   '}\n"
    )
    with pytest.raises(ValueError, match="approval"):
        load_public(path)
