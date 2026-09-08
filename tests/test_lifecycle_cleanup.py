"""Cleanup behavior for the real lifecycle audit's private temporary copy."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "verify_research_lifecycle",
    Path(__file__).parents[1] / "scripts" / "verify_research_lifecycle.py",
)
assert SPEC is not None and SPEC.loader is not None
lifecycle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lifecycle)


def sharing_violation(winerror=32) -> OSError:
    error = OSError(winerror, "The process cannot access the file")
    error.winerror = winerror
    return error


def audit_paths(tmp_path):
    source = tmp_path / "source-data"
    work_root = tmp_path / "audit-work"
    target = work_root / "audit-private-copy"
    source.mkdir()
    target.mkdir(parents=True)
    (target / "marker.txt").write_text("private audit copy", encoding="utf-8")
    return source, work_root, target


@pytest.mark.parametrize("winerror", [32, 33])
def test_cleanup_retries_a_temporary_sharing_violation_and_removes_copy(
    tmp_path, monkeypatch, winerror
):
    source, work_root, target = audit_paths(tmp_path)
    remove_calls = []
    waits = []
    real_rmtree = shutil.rmtree

    def remove(path):
        remove_calls.append(path)
        if len(remove_calls) == 1:
            raise sharing_violation(winerror)
        real_rmtree(path)

    monkeypatch.setattr(lifecycle.shutil, "rmtree", remove)
    monkeypatch.setattr(lifecycle, "sleep", waits.append)

    lifecycle.remove_temporary_data_copy(target, source, work_root)

    assert not target.exists()
    assert remove_calls == [target, target]
    assert waits == [0.1]


def test_cleanup_raises_after_all_sharing_violation_retries(tmp_path, monkeypatch):
    source, work_root, target = audit_paths(tmp_path)
    remove_calls = []
    waits = []

    def remove(path):
        remove_calls.append(path)
        raise sharing_violation()

    monkeypatch.setattr(lifecycle.shutil, "rmtree", remove)
    monkeypatch.setattr(lifecycle, "sleep", waits.append)

    with pytest.raises(OSError, match="cannot access"):
        lifecycle.remove_temporary_data_copy(target, source, work_root)

    assert target.exists()
    assert remove_calls == [target] * 4
    assert waits == [0.1, 0.2, 0.4]


def test_cleanup_does_not_retry_an_unrelated_os_error(tmp_path, monkeypatch):
    source, work_root, target = audit_paths(tmp_path)
    remove_calls = []
    waits = []
    error = OSError(5, "Access denied")
    error.winerror = 5

    def remove(path):
        remove_calls.append(path)
        raise error

    monkeypatch.setattr(lifecycle.shutil, "rmtree", remove)
    monkeypatch.setattr(lifecycle, "sleep", waits.append)

    with pytest.raises(OSError, match="Access denied"):
        lifecycle.remove_temporary_data_copy(target, source, work_root)

    assert remove_calls == [target]
    assert waits == []


def test_cleanup_reraises_an_os_error_without_winerror(tmp_path, monkeypatch):
    source, work_root, target = audit_paths(tmp_path)
    remove_calls = []
    waits = []
    error = OSError(5, "POSIX access denied")

    def remove(path):
        remove_calls.append(path)
        raise error

    monkeypatch.setattr(lifecycle.shutil, "rmtree", remove)
    monkeypatch.setattr(lifecycle, "sleep", waits.append)

    with pytest.raises(OSError) as raised:
        lifecycle.remove_temporary_data_copy(target, source, work_root)

    assert raised.value is error
    assert remove_calls == [target]
    assert waits == []


def test_cleanup_rejects_target_outside_work_root_before_removal(tmp_path, monkeypatch):
    source, work_root, _ = audit_paths(tmp_path)
    unsafe_target = tmp_path / "elsewhere" / "audit-outside"
    unsafe_target.mkdir(parents=True)
    remove_calls = []

    monkeypatch.setattr(lifecycle.shutil, "rmtree", lambda path: remove_calls.append(path))

    with pytest.raises(AssertionError, match="Unsafe cleanup"):
        lifecycle.remove_temporary_data_copy(unsafe_target, source, work_root)

    assert remove_calls == []


def test_cleanup_rejects_source_and_its_ancestor_before_removal(tmp_path, monkeypatch):
    _, work_root, _ = audit_paths(tmp_path)
    source_target = work_root / "audit-source"
    source_target.mkdir()
    ancestor_target = work_root / "audit-ancestor"
    source_inside_ancestor = ancestor_target / "source-data"
    source_inside_ancestor.mkdir(parents=True)
    remove_calls = []

    monkeypatch.setattr(lifecycle.shutil, "rmtree", lambda path: remove_calls.append(path))

    with pytest.raises(AssertionError, match="Cannot remove live data"):
        lifecycle.remove_temporary_data_copy(source_target, source_target, work_root)
    with pytest.raises(AssertionError, match="Cannot remove live data"):
        lifecycle.remove_temporary_data_copy(ancestor_target, source_inside_ancestor, work_root)

    assert remove_calls == []
