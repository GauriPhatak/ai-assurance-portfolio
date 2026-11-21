"""Tests for download verification, password lookup and zip extraction (no network)."""

import hashlib
import subprocess
import zipfile

import pytest

from detector_audit.corpora import download as dl
from detector_audit.corpora.manifest import ZipMember


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_sha256_file_matches_hashlib(tmp_path):
    p = tmp_path / "f.bin"
    data = b"x" * (3 * (1 << 20) + 7)  # spans several read chunks
    p.write_bytes(data)
    assert dl.sha256_file(p) == _sha(data)


def test_git_blob_sha1_matches_git(tmp_path):
    p = tmp_path / "f.csv"
    p.write_bytes(b"a,b\r\n1,2\r\n")  # CRLF must not be normalised
    expected = subprocess.run(
        ["git", "hash-object", "--no-filters", str(p)], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert dl.git_blob_sha1(p) == expected


def test_verify_file_accepts_match(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    dl.verify_file(p, 3, _sha(b"abc"))


@pytest.mark.parametrize(
    ("size", "digest", "msg"),
    [(4, _sha(b"abc"), "size"), (3, _sha(b"abd"), "sha256")],
)
def test_verify_file_rejects_mismatch(tmp_path, size, digest, msg):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    with pytest.raises(dl.ChecksumError, match=msg):
        dl.verify_file(p, size, digest)


def test_verify_file_rejects_missing(tmp_path):
    with pytest.raises(dl.ChecksumError, match="not found"):
        dl.verify_file(tmp_path / "nope", 1, "0" * 64)


def _member(**kw) -> ZipMember:
    base = dict(
        member="x.csv",
        size_bytes=0,
        sha256="0" * 64,
        password_env="TOY_ZIP_PASSWORD",
        password_source="https://example.org/readme",
    )
    return ZipMember(**{**base, **kw})


def test_password_from_environment_wins(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("TOY_ZIP_PASSWORD=from_file\n")
    monkeypatch.setenv("TOY_ZIP_PASSWORD", "from_env")
    assert dl.get_zip_password(_member(), f) == b"from_env"


def test_password_from_file_with_comments_and_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("TOY_ZIP_PASSWORD", raising=False)
    f = tmp_path / ".env"
    f.write_text('# comment\n\nOTHER=1\nTOY_ZIP_PASSWORD = "quoted value"\n')
    assert dl.get_zip_password(_member(), f) == b"quoted value"


def test_missing_password_names_variable_and_source(tmp_path, monkeypatch):
    monkeypatch.delenv("TOY_ZIP_PASSWORD", raising=False)
    with pytest.raises(dl.PasswordNotFoundError) as err:
        dl.get_zip_password(_member(), tmp_path / "absent.env")
    assert "TOY_ZIP_PASSWORD" in str(err.value)
    assert "https://example.org/readme" in str(err.value)


def _zip_with(tmp_path, name: str, data: bytes):
    # The stdlib cannot write encrypted zips, so extraction is tested on a plain one;
    # zipfile ignores the password for unencrypted members.
    zp = tmp_path / "a.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr(name, data)
    return zp


def test_extract_member_writes_verified_file(tmp_path):
    data = b"id,score\n1,3\n"
    zp = _zip_with(tmp_path, "inner/x.csv", data)
    out = tmp_path / "out"
    out.mkdir()
    m = _member(member="inner/x.csv", size_bytes=len(data), sha256=_sha(data))
    path = dl.extract_member(zp, m, b"pw", out)
    assert path == out / "x.csv"  # base name only: archive paths cannot escape out/
    assert path.read_bytes() == data
    assert not (out / "x.csv.part").exists()


def test_extract_member_bad_checksum_leaves_nothing(tmp_path):
    zp = _zip_with(tmp_path, "x.csv", b"abc")
    m = _member(size_bytes=3, sha256=_sha(b"different"))
    with pytest.raises(dl.ChecksumError):
        dl.extract_member(zp, m, b"pw", tmp_path)
    assert not (tmp_path / "x.csv").exists()
    assert not (tmp_path / "x.csv.part").exists()
