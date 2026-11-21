"""Load and validate the data source manifest (``configs/data_sources.yaml``)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")


class ManifestError(ValueError):
    """Raised when the manifest is malformed."""


@dataclass(frozen=True)
class ZipMember:
    """A single file to extract from a password-protected zip archive."""

    member: str
    size_bytes: int
    sha256: str
    password_env: str
    password_source: str


@dataclass(frozen=True)
class SourceFile:
    """One downloadable file belonging to a corpus."""

    filename: str
    split: str
    host: str
    size_bytes: int
    sha256: str
    gdrive_id: str | None = None
    git_blob_sha1: str | None = None
    extract: ZipMember | None = None

    @property
    def data_filename(self) -> str:
        """Name of the CSV that holds the data (the zip member if zipped)."""
        return self.extract.member if self.extract else self.filename


@dataclass(frozen=True)
class CountsSpec:
    """How to map a corpus's columns onto the shared counts table."""

    essay_id: str
    columns: dict[str, str] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    value_maps: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Corpus:
    """A corpus and its source files."""

    key: str
    title: str
    license: str
    license_url: str
    source_url: str
    source_commit: str
    folder: str
    in_main_analysis: bool
    files: tuple[SourceFile, ...]
    counts: CountsSpec | None = None

    def url_for(self, f: SourceFile) -> str:
        """Return the pinned download URL for one of this corpus's files."""
        if f.host == "gdrive":
            return f"https://drive.google.com/uc?id={f.gdrive_id}"
        if f.host == "github":
            repo = self.source_url.removeprefix("https://github.com/")
            return f"https://raw.githubusercontent.com/{repo}/{self.source_commit}/{f.filename}"
        raise ManifestError(f"unknown host {f.host!r} for {f.filename}")


@dataclass(frozen=True)
class Manifest:
    """The full data source manifest."""

    data_root: Path
    password_file: Path
    corpora: dict[str, Corpus]


def _require(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ManifestError(f"{where}: missing required key {key!r}")
    return d[key]


def _check_hash(value: str, pattern: re.Pattern[str], where: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise ManifestError(f"{where}: malformed hash {value!r}")
    return value


def _parse_file(d: dict[str, Any], where: str) -> SourceFile:
    host = _require(d, "host", where)
    if host == "gdrive" and not d.get("gdrive_id"):
        raise ManifestError(f"{where}: gdrive files need gdrive_id")
    extract = None
    if "extract" in d:
        e = d["extract"]
        ew = f"{where}.extract"
        extract = ZipMember(
            member=_require(e, "member", ew),
            size_bytes=int(_require(e, "size_bytes", ew)),
            sha256=_check_hash(_require(e, "sha256", ew), _SHA256, ew),
            password_env=_require(e, "password_env", ew),
            password_source=_require(e, "password_source", ew),
        )
    blob = d.get("git_blob_sha1")
    return SourceFile(
        filename=_require(d, "filename", where),
        split=_require(d, "split", where),
        host=host,
        size_bytes=int(_require(d, "size_bytes", where)),
        sha256=_check_hash(_require(d, "sha256", where), _SHA256, where),
        gdrive_id=d.get("gdrive_id"),
        git_blob_sha1=_check_hash(blob, _SHA1, where) if blob is not None else None,
        extract=extract,
    )


def parse_manifest(raw: dict[str, Any]) -> Manifest:
    """Build a :class:`Manifest` from an already-parsed YAML mapping.

    Parameters
    ----------
    raw : dict
        Mapping as returned by ``yaml.safe_load``.

    Returns
    -------
    Manifest
        Validated manifest.

    Raises
    ------
    ManifestError
        If required keys are missing or hashes are malformed.
    """
    corpora: dict[str, Corpus] = {}
    for key, c in _require(raw, "corpora", "manifest").items():
        where = f"corpora.{key}"
        files = tuple(
            _parse_file(f, f"{where}.files[{i}]") for i, f in enumerate(_require(c, "files", where))
        )
        counts = None
        if "counts" in c:
            cs = c["counts"]
            counts = CountsSpec(
                essay_id=_require(cs, "essay_id", f"{where}.counts"),
                columns=dict(cs.get("columns", {})),
                constants={k: str(v) for k, v in cs.get("constants", {}).items()},
                value_maps={k: dict(v) for k, v in cs.get("value_maps", {}).items()},
            )
        corpora[key] = Corpus(
            key=key,
            title=_require(c, "title", where),
            license=_require(c, "license", where),
            license_url=_require(c, "license_url", where),
            source_url=_require(c, "source_url", where),
            source_commit=_require(c, "source_commit", where),
            folder=_require(c, "folder", where),
            in_main_analysis=bool(_require(c, "in_main_analysis", where)),
            files=files,
            counts=counts,
        )
    return Manifest(
        data_root=Path(_require(raw, "data_root", "manifest")),
        password_file=Path(raw.get("password_file", ".env")),
        corpora=corpora,
    )


def load_manifest(path: str | Path) -> Manifest:
    """Read and validate the manifest YAML at ``path``.

    Parameters
    ----------
    path : str or Path
        Path to ``data_sources.yaml``.

    Returns
    -------
    Manifest
        Validated manifest.
    """
    with open(path, encoding="utf-8") as fh:
        return parse_manifest(yaml.safe_load(fh))
