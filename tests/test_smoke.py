"""Smoke test: both packages install and import."""

import aiassure
import detector_audit


def test_packages_import_and_have_version():
    assert isinstance(aiassure.__version__, str)
    assert isinstance(detector_audit.__version__, str)
