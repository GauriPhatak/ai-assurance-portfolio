"""Tests for the essay counts table, on synthetic data."""

import csv
import random
from collections import Counter

import pytest

from detector_audit.corpora import counts as ct
from detector_audit.corpora.manifest import parse_manifest

H64 = "a" * 64


def _manifest(tmp_path, counts_spec, files):
    return parse_manifest(
        {
            "data_root": str(tmp_path),
            "corpora": {
                "toy": {
                    "title": "Toy",
                    "license": "CC BY 4.0",
                    "license_url": "u",
                    "source_url": "https://github.com/o/r",
                    "source_commit": "c" * 40,
                    "folder": "toy",
                    "in_main_analysis": True,
                    "files": [
                        {
                            "filename": f,
                            "split": s,
                            "host": "github",
                            "size_bytes": 1,
                            "sha256": H64,
                        }
                        for f, s in files
                    ],
                    "counts": counts_spec,
                }
            },
        }
    )


SPEC = {
    "essay_id": "eid",
    "columns": {"prompt": "p", "grade": "g", "ell_status": "ell"},
    "constants": {"disability_status": "Not recorded"},
    "value_maps": {"ell_status": {"Y": "Yes", "N": "No"}},
}


def _write(tmp_path, name, rows):
    d = tmp_path / "toy"
    d.mkdir(exist_ok=True)
    with open(d / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["eid", "p", "g", "ell", "full_text"])
        w.writeheader()
        w.writerows(rows)


def _row(eid, p="A", g="8", ell="Y"):
    return {"eid": eid, "p": p, "g": g, "ell": ell, "full_text": "SECRET ESSAY TEXT"}


def test_rows_collapse_to_essays_and_missing_is_labelled(tmp_path):
    # Essay 1 has three discourse rows; essay 3 has blank grade and whitespace ELL.
    _write(tmp_path, "train.csv", [_row("1"), _row("1"), _row("1"), _row("2", ell="N")])
    _write(tmp_path, "test.csv", [_row("3", g="", ell=" ")])
    m = _manifest(tmp_path, SPEC, [("train.csv", "train"), ("test.csv", "test")])
    counts = ct.count_corpus(m, m.corpora["toy"])
    assert counts == {
        ("toy", "train", "A", "8", "Yes", "Not recorded"): 1,
        ("toy", "train", "A", "8", "No", "Not recorded"): 1,
        ("toy", "test", "A", "Missing", "Missing", "Not recorded"): 1,
    }


def test_conflicting_essay_level_values_raise(tmp_path):
    _write(tmp_path, "train.csv", [_row("1", g="8"), _row("1", g="9")])
    m = _manifest(tmp_path, SPEC, [("train.csv", "train")])
    with pytest.raises(ct.CountsError, match="conflicting values for \\['grade'\\]"):
        ct.count_corpus(m, m.corpora["toy"])


def test_essay_in_two_splits_raises(tmp_path):
    _write(tmp_path, "train.csv", [_row("1")])
    _write(tmp_path, "test.csv", [_row("1")])
    m = _manifest(tmp_path, SPEC, [("train.csv", "train"), ("test.csv", "test")])
    with pytest.raises(ct.CountsError, match="both train and test"):
        ct.count_corpus(m, m.corpora["toy"])


def test_unmapped_value_raises(tmp_path):
    _write(tmp_path, "train.csv", [_row("1", ell="Maybe")])
    m = _manifest(tmp_path, SPEC, [("train.csv", "train")])
    with pytest.raises(ct.CountsError, match="unexpected value 'Maybe'"):
        ct.count_corpus(m, m.corpora["toy"])


def test_spec_must_cover_every_dimension(tmp_path):
    spec = {**SPEC, "constants": {}}
    _write(tmp_path, "train.csv", [_row("1")])
    m = _manifest(tmp_path, spec, [("train.csv", "train")])
    with pytest.raises(ct.CountsError, match="exactly"):
        ct.count_corpus(m, m.corpora["toy"])


def test_outputs_never_contain_essay_text(tmp_path):
    _write(tmp_path, "train.csv", [_row("1"), _row("2", g="10")])
    m = _manifest(tmp_path, SPEC, [("train.csv", "train")])
    counts = ct.count_corpus(m, m.corpora["toy"])
    out = tmp_path / "c.csv"
    ct.write_counts_csv(counts, out)
    summary = ct.summary_markdown(counts, m)
    assert "SECRET" not in out.read_text() and "SECRET" not in summary
    # Grades sort numerically, so 8 comes before 10.
    lines = out.read_text().splitlines()
    assert lines[0] == "corpus,split,prompt,grade,ell_status,disability_status,n_essays"
    assert [ln.split(",")[3] for ln in lines[1:]] == ["8", "10"]


def _cell(split, prompt, grade, ell="Yes"):
    return ("toy", split, prompt, grade, ell, "Not recorded")


def _attack(counts, shown):
    """Recover hidden values by repeated single subtraction; return what was recovered."""
    true = ct.published_values(counts)
    known = {k for k, v in shown.items() if not isinstance(v, str)}
    recovered = set()
    changed = True
    while changed:
        changed = False
        for parts, whole in ct.published_relations(counts):
            unknown = [k for k in [*parts, whole] if k not in known]
            if len(unknown) == 1:
                known.add(unknown[0])
                recovered.add(unknown[0])
                changed = True
    return {k: true[k] for k in recovered}


def test_relations_are_true_identities():
    rng = random.Random(1)
    counts = Counter(
        {_cell(s, p, g): rng.randint(1, 40) for s in "ab" for p in "XYZ" for g in ("8", "9")}
    )
    true = ct.published_values(counts)
    for parts, whole in ct.published_relations(counts):
        assert sum(true[k] for k in parts) == true[whole]


def test_small_cells_are_shown_as_threshold():
    counts = Counter({_cell("train", "A", "8"): 50, _cell("train", "A", "9"): 3})
    shown = ct.suppress_small_cells(counts, 11)
    assert shown[_cell("train", "A", "9")] == "<11"


def test_hidden_marginal_when_cell_has_no_visible_partner():
    # Grade 10 has a single cell, so hiding that cell is useless while the grade-10
    # marginal is published; the marginal itself must be hidden.
    counts = Counter(
        {
            _cell("train", "A", "8"): 50,
            _cell("train", "A", "9"): 3,
            _cell("train", "A", "10"): 17,
        }
    )
    shown = ct.suppress_small_cells(counts, 11)
    assert shown[_cell("train", "A", "9")] == "<11"
    assert shown[_cell("train", "A", "10")] == ct.COMPLEMENTARY
    assert shown[("grade", "toy", "10")] == ct.COMPLEMENTARY
    assert shown[_cell("train", "A", "8")] == 50
    assert _attack(counts, shown) == {}


@pytest.mark.parametrize("seed", range(200))
def test_no_small_value_is_recoverable_by_subtraction(seed):
    rng = random.Random(seed)
    counts = Counter()
    for s in ("train", "test"):
        for p in "ABCD"[: rng.randint(1, 4)]:
            for g in ("8", "9", "10")[: rng.randint(1, 3)]:
                for ell in ("Yes", "No"):
                    n = rng.choice([0, 0, rng.randint(1, 10), rng.randint(1, 60)])
                    if n:
                        counts[_cell(s, p, g, ell)] = n
    if not counts:
        return
    shown = ct.suppress_small_cells(counts, 11)
    leaked = {k: v for k, v in _attack(counts, shown).items() if v < 11}
    assert leaked == {}
    # Every value below the threshold is hidden, and shown ints are true values.
    true = ct.published_values(counts)
    for k, v in shown.items():
        if true[k] < 11:
            assert v == "<11"
        elif not isinstance(v, str):
            assert v == true[k]


def test_no_suppression_without_display_values(tmp_path):
    counts = Counter({_cell("train", "A", "8"): 2})
    out = tmp_path / "c.csv"
    ct.write_counts_csv(counts, out)
    assert out.read_text().splitlines()[1].endswith(",2")


def test_summary_states_rule_and_uses_suppressed_values(tmp_path):
    m = _manifest(tmp_path, SPEC, [("train.csv", "train")])
    counts = Counter({_cell("train", "A", "8"): 40, _cell("train", "B", "8"): 4})
    shown = ct.suppress_small_cells(counts, 11)
    text = ct.summary_markdown(counts, m, shown, 11)
    assert "below 11 essays" in text
    assert "| B | <11 |" in text
    assert "| 4 |" not in text
