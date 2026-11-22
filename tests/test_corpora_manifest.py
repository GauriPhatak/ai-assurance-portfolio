"""Tests for the data source manifest loader."""

import copy
from pathlib import Path

import pytest

from detector_audit.corpora.manifest import ManifestError, load_manifest, parse_manifest

REPO = Path(__file__).resolve().parents[1]
REAL_MANIFEST = REPO / "projects/01-ai-detector-audit/configs/data_sources.yaml"

H64 = "a" * 64
MINIMAL = {
    "data_root": "data/raw",
    "corpora": {
        "toy": {
            "title": "Toy",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "source_url": "https://github.com/owner/repo",
            "source_commit": "c" * 40,
            "folder": "toy",
            "in_main_analysis": True,
            "files": [
                {
                    "filename": "a.csv",
                    "split": "train",
                    "host": "github",
                    "size_bytes": 3,
                    "sha256": H64,
                }
            ],
        }
    },
}


def test_real_manifest_loads_and_is_complete():
    m = load_manifest(REAL_MANIFEST)
    assert set(m.corpora) == {"persuade_2_0", "ellipse", "ellipse_raw_rater_scores"}
    assert m.corpora["ellipse_raw_rater_scores"].in_main_analysis is False
    for c in m.corpora.values():
        assert c.license == "CC BY 4.0"
        for f in c.files:
            assert len(f.sha256) == 64
            if f.extract:
                assert f.extract.password_env.endswith("_ZIP_PASSWORD")


def test_real_manifest_contains_no_zip_passwords():
    text = REAL_MANIFEST.read_text(encoding="utf-8")
    for published in ("persuade_test", "ellipse_test", "ellipse_raw_data"):
        assert published not in text


def test_github_url_is_pinned_to_commit():
    m = parse_manifest(MINIMAL)
    c = m.corpora["toy"]
    assert c.url_for(c.files[0]) == (
        f"https://raw.githubusercontent.com/owner/repo/{'c' * 40}/a.csv"
    )


def test_gdrive_file_without_id_is_rejected():
    raw = copy.deepcopy(MINIMAL)
    raw["corpora"]["toy"]["files"][0]["host"] = "gdrive"
    with pytest.raises(ManifestError, match="gdrive_id"):
        parse_manifest(raw)


def test_malformed_sha256_is_rejected():
    raw = copy.deepcopy(MINIMAL)
    raw["corpora"]["toy"]["files"][0]["sha256"] = "not-a-hash"
    with pytest.raises(ManifestError, match="malformed hash"):
        parse_manifest(raw)


def test_missing_key_is_reported_with_location():
    raw = copy.deepcopy(MINIMAL)
    del raw["corpora"]["toy"]["license"]
    with pytest.raises(ManifestError, match=r"corpora\.toy: missing required key 'license'"):
        parse_manifest(raw)
