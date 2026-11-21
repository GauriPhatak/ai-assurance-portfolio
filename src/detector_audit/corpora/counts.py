"""Essay counts by English learner status, disability status, prompt and grade.

Usage (from the repo root)::

    make counts

which runs ``python -m detector_audit.corpora.counts --manifest <data_sources.yaml>
--out <results prefix>``.

Writes ``<out>.csv`` (one row per cell of the full cross-tabulation), ``<out>_summary.md``
(marginal counts per corpus) and ``<out>.meta.json`` (source commits and checksums).

Only identifier and demographic columns are read into memory; essay text columns are
never stored or printed. Corpora marked ``in_main_analysis: false`` are skipped.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from detector_audit.corpora.manifest import Corpus, Manifest, load_manifest

DIMENSIONS = ("prompt", "grade", "ell_status", "disability_status")
MISSING = "Missing"

# Long essays exceed the csv module's default 128 KiB field limit.
csv.field_size_limit(2**31 - 1)


class CountsError(ValueError):
    """Raised when the data are inconsistent with the counts specification."""


def _normalise(value: str | None, value_map: dict[str, str] | None, where: str) -> str:
    value = (value or "").strip()
    if not value:
        return MISSING
    if value_map is None:
        return value
    if value not in value_map:
        raise CountsError(f"{where}: unexpected value {value!r}; add it to value_maps")
    return value_map[value]


def essay_attributes(
    rows: Iterable[dict[str, str]], corpus: Corpus, source: str
) -> dict[str, dict[str, str]]:
    """Collapse rows to one record per essay, holding only the count dimensions.

    PERSUADE has one row per discourse element, so an essay appears many times. Its
    essay-level fields must agree across those rows; any disagreement is an error.

    Parameters
    ----------
    rows : iterable of dict
        CSV rows as produced by :class:`csv.DictReader`.
    corpus : Corpus
        Corpus with a ``counts`` specification.
    source : str
        Label used in error messages (for example, the file name).

    Returns
    -------
    dict
        Maps essay ID to ``{dimension: value}`` for every dimension in ``DIMENSIONS``.

    Raises
    ------
    CountsError
        On a missing essay ID, an unmapped value, or conflicting essay-level fields.
    """
    spec = corpus.counts
    if spec is None:
        raise CountsError(f"{corpus.key}: no counts specification")
    covered = set(spec.columns) | set(spec.constants)
    if covered != set(DIMENSIONS):
        raise CountsError(f"{corpus.key}: counts must cover exactly {DIMENSIONS}")
    essays: dict[str, dict[str, str]] = {}
    for line_no, row in enumerate(rows, start=2):
        where = f"{source} line {line_no}"
        essay_id = (row.get(spec.essay_id) or "").strip()
        if not essay_id:
            raise CountsError(f"{where}: empty essay id")
        attrs = dict(spec.constants)
        for dim, col in spec.columns.items():
            if col not in row:
                raise CountsError(f"{where}: column {col!r} not found")
            attrs[dim] = _normalise(row[col], spec.value_maps.get(dim), f"{where} {col}")
        previous = essays.setdefault(essay_id, attrs)
        if previous != attrs:
            diff = sorted(k for k in attrs if attrs[k] != previous[k])
            raise CountsError(f"{where}: essay {essay_id} has conflicting values for {diff}")
    return essays


def _read_split(manifest: Manifest, corpus: Corpus, filename: str) -> dict[str, dict[str, str]]:
    path = manifest.data_root / corpus.folder / filename
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; run `make data` first")
    with open(path, encoding="utf-8", newline="") as fh:
        return essay_attributes(csv.DictReader(fh), corpus, path.name)


def count_corpus(manifest: Manifest, corpus: Corpus) -> Counter[tuple[str, ...]]:
    """Count essays per (corpus, split, prompt, grade, ell_status, disability_status) cell.

    Raises
    ------
    CountsError
        If an essay ID appears in more than one split.
    """
    counts: Counter[tuple[str, ...]] = Counter()
    seen: dict[str, str] = {}
    for f in corpus.files:
        essays = _read_split(manifest, corpus, f.data_filename)
        for essay_id, attrs in essays.items():
            if essay_id in seen:
                raise CountsError(
                    f"{corpus.key}: essay {essay_id} is in both {seen[essay_id]} and {f.split}"
                )
            seen[essay_id] = f.split
            counts[(corpus.key, f.split, *(attrs[d] for d in DIMENSIONS))] += 1
    return counts


def _sort_key(cell: tuple[str, ...]) -> tuple:
    # Numeric grades sort numerically; "Missing" sorts last.
    def part(v: str) -> tuple:
        return (2, 0, v) if v == MISSING else (0, int(v), v) if v.isdigit() else (1, 0, v)

    return tuple(part(v) for v in cell)


COMPLEMENTARY = "suppressed"

# A published quantity is either a cell of the cross-tabulation, keyed by its cell tuple,
# or a total in the summary, keyed by ("split_total", corpus, split),
# ("corpus_total", corpus) or (dimension, corpus, value).
Key = tuple[str, ...]


def published_values(counts: Counter[Key]) -> dict[Key, int]:
    """Every cell and summary total that the outputs publish, with its true value."""
    values: dict[Key, int] = dict(counts)
    for cell, n in counts.items():
        for key in [
            ("split_total", cell[0], cell[1]),
            ("corpus_total", cell[0]),
            *((dim, cell[0], cell[i]) for i, dim in enumerate(DIMENSIONS, start=2)),
        ]:
            values[key] = values.get(key, 0) + n
    return values


def published_relations(counts: Counter[Key]) -> list[tuple[list[Key], Key]]:
    """Additive identities ``sum(parts) == whole`` that hold among published values.

    Anyone holding the outputs can use these to recover a hidden value by subtraction.
    """
    relations: dict[Key, list[Key]] = {}
    for cell in counts:
        # Cells add up to each total that contains them.
        relations.setdefault(("split_total", cell[0], cell[1]), []).append(cell)
        for i, dim in enumerate(DIMENSIONS, start=2):
            relations.setdefault((dim, cell[0], cell[i]), []).append(cell)
    out: list[tuple[list[Key], Key]] = [(parts, whole) for whole, parts in relations.items()]
    # Split totals, and each dimension's marginals, add up to the corpus total.
    for corpus in sorted({c[0] for c in counts}):
        splits = sorted({("split_total", corpus, c[1]) for c in counts if c[0] == corpus})
        out.append((splits, ("corpus_total", corpus)))
        for i, dim in enumerate(DIMENSIONS, start=2):
            levels = sorted({(dim, corpus, c[i]) for c in counts if c[0] == corpus})
            out.append((levels, ("corpus_total", corpus)))
    return out


def suppress_small_cells(counts: Counter[Key], min_cell_count: int) -> dict[Key, int | str]:
    """Display values for every published cell and total, with small-cell suppression.

    Primary suppression: any value below ``min_cell_count`` is shown as
    ``"<{min_cell_count}"``. Complementary suppression: if an identity from
    :func:`published_relations` has exactly one hidden term, that term could be recovered
    by subtraction, so one more term is hidden and shown as ``"suppressed"``: the
    smallest visible part if there is one, otherwise the whole. This repeats until no
    identity has exactly one hidden term.

    This blocks recovery by chains of single subtractions. It does not guarantee that
    every hidden value's feasible range (from solving all identities jointly) is wide.

    Parameters
    ----------
    counts : Counter
        Essay counts keyed by cell.
    min_cell_count : int
        Smallest count that may be shown.

    Returns
    -------
    dict
        Maps each key from :func:`published_values` to an ``int`` (shown) or a ``str``
        marker (hidden).
    """
    true = published_values(counts)
    shown: dict[Key, int | str] = {
        k: n if n >= min_cell_count else f"<{min_cell_count}" for k, n in true.items()
    }
    relations = published_relations(counts)

    def hidden(k: Key) -> bool:
        return isinstance(shown[k], str)

    changed = True
    while changed:
        changed = False
        for parts, whole in relations:
            terms = [*parts, whole]
            if sum(hidden(k) for k in terms) != 1:
                continue
            visible_parts = [k for k in parts if not hidden(k)]
            target = (
                min(visible_parts, key=lambda k: (true[k], _sort_key(k)))
                if visible_parts
                else whole
            )
            shown[target] = COMPLEMENTARY
            changed = True
    return shown


def write_counts_csv(
    counts: Counter[Key], path: Path, shown: dict[Key, int | str] | None = None
) -> None:
    """Write the full cross-tabulation as a long-format CSV.

    ``shown`` gives display values from :func:`suppress_small_cells`; without it, true
    counts are written.
    """
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["corpus", "split", *DIMENSIONS, "n_essays"])
        for cell in sorted(counts, key=_sort_key):
            w.writerow([*cell, shown[cell] if shown else counts[cell]])


def summary_markdown(
    counts: Counter[Key],
    manifest: Manifest,
    shown: dict[Key, int | str] | None = None,
    min_cell_count: int | None = None,
) -> str:
    """Marginal counts per corpus, as Markdown tables (both splits combined).

    ``shown`` and ``min_cell_count`` come from :func:`suppress_small_cells`; without
    them, true totals are written.
    """
    values = shown if shown else published_values(counts)

    def fmt(key: Key) -> str:
        return str(values[key])

    lines = [
        "# Essay counts by corpus",
        "",
        "Generated by `make counts` from the files listed in `configs/data_sources.yaml`.",
        "Train and test splits are combined. The full cross-tabulation, by split, is in",
        "`corpus_essay_counts.csv`. Do not edit by hand.",
    ]
    if shown and min_cell_count:
        n_primary = sum(1 for c in counts if shown[c] == f"<{min_cell_count}")
        n_comp = sum(1 for c in counts if shown[c] == COMPLEMENTARY)
        lines += [
            "",
            f"**Small-cell suppression.** Any count below {min_cell_count} essays, in the "
            f"cross-tabulation or in the totals below, is shown as `<{min_cell_count}`. "
            "Where a suppressed count could still be recovered by subtracting other "
            "published counts, one more count is hidden and shown as "
            f"`{COMPLEMENTARY}` (its true value is {min_cell_count} or more). Cells with "
            f"zero essays are not listed. In this release, {n_primary} of {len(counts)} "
            f"cross-tabulation cells are shown as `<{min_cell_count}` and {n_comp} as "
            f"`{COMPLEMENTARY}`.",
        ]
    for key in sorted({c[0] for c in counts}):
        corpus = manifest.corpora[key]
        splits = sorted({c[1] for c in counts if c[0] == key})
        lines += ["", f"## {corpus.title}", "", f"Total essays: {fmt(('corpus_total', key))}"]
        lines.append("(" + ", ".join(f"{s}: {fmt(('split_total', key, s))}" for s in splits) + ")")
        for i, dim in enumerate(DIMENSIONS, start=2):
            levels = sorted({c[i] for c in counts if c[0] == key}, key=lambda v: _sort_key((v,)))
            lines += ["", f"| {dim} | n_essays |", "|---|---:|"]
            lines += [f"| {v} | {fmt((dim, key, v))} |" for v in levels]
    return "\n".join(lines) + "\n"


def provenance(manifest: Manifest, corpora: Sequence[Corpus], manifest_path: str) -> dict:
    """Source commits, licenses and file checksums for the results metadata file."""
    return {
        "manifest": manifest_path,
        "corpora": {
            c.key: {
                "title": c.title,
                "license": c.license,
                "source_url": c.source_url,
                "source_commit": c.source_commit,
                "files": [
                    {
                        "filename": f.data_filename,
                        "split": f.split,
                        "sha256": f.extract.sha256 if f.extract else f.sha256,
                    }
                    for f in c.files
                ],
            }
            for c in corpora
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", required=True, help="path to data_sources.yaml")
    p.add_argument("--out", required=True, help="output path prefix (no extension)")
    p.add_argument(
        "--min-cell-count",
        type=int,
        required=True,
        help="suppress cells with fewer essays than this (0 disables suppression)",
    )
    args = p.parse_args(argv)
    if args.min_cell_count < 0:
        p.error("--min-cell-count must be 0 or more")

    manifest = load_manifest(args.manifest)
    corpora = [c for c in manifest.corpora.values() if c.in_main_analysis and c.counts]
    try:
        counts: Counter[tuple[str, ...]] = Counter()
        for corpus in corpora:
            counts += count_corpus(manifest, corpus)
    except (CountsError, FileNotFoundError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    mcc = args.min_cell_count
    shown = suppress_small_cells(counts, mcc) if mcc else None
    write_counts_csv(counts, out.with_suffix(".csv"), shown)
    out.with_name(out.name + "_summary.md").write_text(
        summary_markdown(counts, manifest, shown, mcc), encoding="utf-8", newline="\n"
    )
    meta = provenance(manifest, corpora, Path(args.manifest).as_posix())
    meta["min_cell_count"] = args.min_cell_count
    out.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {out}.csv, {out.name}_summary.md, {out.name}.meta.json ({len(counts)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
