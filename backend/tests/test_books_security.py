"""Books file-path traversal tests (ISSUE-020).

``_confine_upload_path`` must reject absolute paths, ``..`` traversal, and
cross-user file reads, accepting only this user's uploaded files inside
UPLOAD_DIR.
"""

import os
import sys

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.api.v1.books import MAX_UPLOAD_BYTES, UPLOAD_DIR, _confine_upload_path  # noqa: E402
from app.utils.exceptions import NotFoundException  # noqa: E402


def _write(name: str, content: b"") -> str:
    """Create a file under UPLOAD_DIR and return its path string."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    p = UPLOAD_DIR / name
    p.write_bytes(content)
    return str(p)


def test_legit_user_file_accepted():
    p = _write("1_book.txt", b"hello")
    got = _confine_upload_path(p, 1)
    assert got.name == "1_book.txt"


def test_absolute_path_outside_rejected():
    # /etc/passwd on POSIX, a nonsense absolute path on Windows — either way
    # it must not live under UPLOAD_DIR.
    try:
        _confine_upload_path(os.path.join(os.sep, "etc", "passwd"), 1)
        raise AssertionError("absolute path should be rejected")
    except NotFoundException:
        pass


def test_traversal_rejected():
    _write("1_real.txt", b"x")
    try:
        _confine_upload_path(os.path.join("..", "..", "backend", ".env"), 1)
        raise AssertionError("traversal should be rejected")
    except NotFoundException:
        pass


def test_cross_user_rejected():
    # File exists under UPLOAD_DIR but carries user 2's prefix.
    p = _write("2_secret.txt", b"x")
    try:
        _confine_upload_path(p, 1)  # requester is user 1
        raise AssertionError("cross-user file should be rejected")
    except NotFoundException:
        pass


def test_missing_file_rejected():
    try:
        _confine_upload_path(str(UPLOAD_DIR / "1_nope.txt"), 1)
        raise AssertionError("missing file should be rejected")
    except NotFoundException:
        pass


def test_upload_size_cap_enforced():
    assert MAX_UPLOAD_BYTES > 0
    assert MAX_UPLOAD_BYTES == 50 * 1024 * 1024
