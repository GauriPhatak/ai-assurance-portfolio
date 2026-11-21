"""Download, verify and extract the project 1 corpora.

Usage (from the repo root)::

    make data          # download, verify, extract
    make data-verify   # manual-download fallback: verify files already in place, then extract

These run ``python -m detector_audit.corpora.download --manifest <data_sources.yaml>``.

Every file is checked against the SHA-256 recorded in the manifest. Downloads go to a
``.part`` file first and are renamed only after the checksum matches, so an interrupted
or corrupted download never looks complete. Files already present with the right
checksum are skipped, so the command is safe to rerun.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path

from detector_audit.corpora.manifest import Corpus, Manifest, SourceFile, ZipMember, load_manifest

_CHUNK = 1 << 20


class ChecksumError(RuntimeError):
    """Raised when a file's size or SHA-256 does not match the manifest."""


class PasswordNotFoundError(RuntimeError):
    """Raised when a zip password is in neither the environment nor the password file."""


def sha256_file(path: str | Path) -> str:
    """Return the hex SHA-256 digest of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1(path: str | Path) -> str:
    """Return the git blob SHA-1 of a file, as GitHub reports it (no line-ending filters)."""
    path = Path(path)
    h = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_file(path: str | Path, size_bytes: int, sha256: str) -> None:
    """Check a file's size and SHA-256 against expected values.

    Parameters
    ----------
    path : str or Path
        File to check.
    size_bytes : int
        Expected size. Checked first because it is cheap.
    sha256 : str
        Expected hex SHA-256 digest.

    Raises
    ------
    ChecksumError
        If the file is missing, or its size or digest differs.
    """
    path = Path(path)
    if not path.is_file():
        raise ChecksumError(f"{path}: file not found")
    actual_size = path.stat().st_size
    if actual_size != size_bytes:
        raise ChecksumError(f"{path}: size {actual_size} bytes, expected {size_bytes}")
    actual = sha256_file(path)
    if actual != sha256:
        raise ChecksumError(f"{path}: sha256 {actual}, expected {sha256}")


def _is_verified(path: Path, size_bytes: int, sha256: str) -> bool:
    try:
        verify_file(path, size_bytes, sha256)
    except ChecksumError:
        return False
    return True


def read_password_file(path: str | Path) -> dict[str, str]:
    """Parse a ``KEY=value`` file (blank lines and ``#`` comments ignored).

    Values may be wrapped in single or double quotes. A missing file gives an empty dict.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def get_zip_password(member: ZipMember, password_file: str | Path) -> bytes:
    """Look up a zip password: environment variable first, then the password file.

    Parameters
    ----------
    member : ZipMember
        Gives the variable name (``password_env``) and where the password is published.
    password_file : str or Path
        Untracked ``KEY=value`` file, used when the variable is not set.

    Returns
    -------
    bytes
        The password, UTF-8 encoded.

    Raises
    ------
    PasswordNotFoundError
        If neither source has a non-empty value.
    """
    value = os.environ.get(member.password_env) or read_password_file(password_file).get(
        member.password_env
    )
    if not value:
        raise PasswordNotFoundError(
            f"Zip password for {member.member} not found. Set {member.password_env} in the "
            f"environment or in {password_file} (see .env.example). The password is "
            f"published at {member.password_source}"
        )
    return value.encode("utf-8")


def _fetch_url(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out, _CHUNK)


def _fetch_gdrive(file_id: str, dest: Path) -> None:
    import gdown  # imported lazily: only needed for actual downloads

    gdown.download(id=file_id, output=str(dest), quiet=False)


def download_file(corpus: Corpus, f: SourceFile, dest_dir: Path) -> Path:
    """Download one file to ``dest_dir`` and verify it, skipping if already present.

    Returns
    -------
    Path
        Path of the verified file.

    Raises
    ------
    ChecksumError
        If the downloaded bytes do not match the manifest. The partial file is removed.
    """
    dest = dest_dir / f.filename
    if _is_verified(dest, f.size_bytes, f.sha256):
        print(f"  ok (already present): {dest}")
        return dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    url = corpus.url_for(f)
    print(f"  downloading {f.filename} from {url}")
    try:
        if f.host == "gdrive":
            _fetch_gdrive(f.gdrive_id or "", part)
        else:
            _fetch_url(url, part)
        verify_file(part, f.size_bytes, f.sha256)
        if f.git_blob_sha1 and git_blob_sha1(part) != f.git_blob_sha1:
            raise ChecksumError(f"{part}: git blob SHA-1 does not match GitHub's")
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    print(f"  ok (sha256 verified): {dest}")
    return dest


def extract_member(zip_path: Path, member: ZipMember, password: bytes, dest_dir: Path) -> Path:
    """Extract one named member from a password-protected zip and verify it.

    Only the member named in the manifest is extracted, and it is written under its
    base name, so paths stored inside the archive cannot escape ``dest_dir``.
    """
    dest = dest_dir / Path(member.member).name
    if _is_verified(dest, member.size_bytes, member.sha256):
        print(f"  ok (already extracted): {dest}")
        return dest
    part = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(zip_path) as zf, zf.open(member.member, pwd=password) as src:
            with open(part, "wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
        verify_file(part, member.size_bytes, member.sha256)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    part.replace(dest)
    print(f"  ok (extracted, sha256 verified): {dest}")
    return dest


def manual_download_hint(corpus: Corpus, f: SourceFile, dest_dir: Path) -> str:
    """Explain where to get a file by hand and where to put it."""
    if f.host == "gdrive":
        url = f"https://drive.google.com/file/d/{f.gdrive_id}/view"
    else:
        url = corpus.url_for(f)
    return f"Download {url} and save it as {dest_dir / f.filename}"


def fetch_corpus(
    manifest: Manifest, corpus: Corpus, *, verify_only: bool = False, extract: bool = True
) -> None:
    """Download (or, with ``verify_only``, just check) and extract every file of a corpus."""
    dest_dir = manifest.data_root / corpus.folder
    note = "" if corpus.in_main_analysis else "  [excluded from main analysis]"
    print(f"{corpus.title} ({corpus.license}){note}")
    for f in corpus.files:
        if verify_only:
            path = dest_dir / f.filename
            try:
                verify_file(path, f.size_bytes, f.sha256)
            except ChecksumError as err:
                hint = manual_download_hint(corpus, f, dest_dir)
                raise ChecksumError(f"{err}\n  {hint}") from err
            print(f"  ok (sha256 verified): {path}")
        else:
            path = download_file(corpus, f, dest_dir)
        if extract and f.extract:
            password = get_zip_password(f.extract, manifest.password_file)
            extract_member(path, f.extract, password, dest_dir)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--manifest", required=True, help="path to data_sources.yaml")
    p.add_argument("--corpus", action="append", help="corpus key (repeatable); default all")
    p.add_argument(
        "--verify-only",
        action="store_true",
        help="do not download; check files already in place (manual download fallback)",
    )
    p.add_argument("--no-extract", action="store_true", help="skip zip extraction")
    args = p.parse_args(argv)

    manifest = load_manifest(args.manifest)
    keys = args.corpus or list(manifest.corpora)
    unknown = sorted(set(keys) - set(manifest.corpora))
    if unknown:
        p.error(f"unknown corpus key(s): {', '.join(unknown)}")
    try:
        for key in keys:
            fetch_corpus(
                manifest,
                manifest.corpora[key],
                verify_only=args.verify_only,
                extract=not args.no_extract,
            )
    except (ChecksumError, PasswordNotFoundError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
