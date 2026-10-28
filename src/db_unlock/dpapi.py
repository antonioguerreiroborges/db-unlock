"""Windows DPAPI helpers to encrypt secrets for the current Windows user.

Data encrypted here can only be decrypted by the same Windows user on the
same machine, so the password never sits in plain text on disk.
"""

import base64
import ctypes
from ctypes import wintypes

_ENTROPY = b"db-unlock"
_CRYPTPROTECT_UI_FORBIDDEN = 0x01


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _to_blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: _DataBlob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def protect(plain_text: str) -> str:
    """Encrypt a string and return it as base64."""
    data_in = _to_blob(plain_text.encode("utf-8"))
    entropy = _to_blob(_ENTROPY)
    data_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(data_in), "db-unlock", ctypes.byref(entropy),
        None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(data_out),
    )
    if not ok:
        raise ctypes.WinError()
    return base64.b64encode(_from_blob(data_out)).decode("ascii")


def unprotect(encrypted: str) -> str:
    """Decrypt a base64 string produced by protect()."""
    data_in = _to_blob(base64.b64decode(encrypted))
    entropy = _to_blob(_ENTROPY)
    data_out = _DataBlob()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(data_in), None, ctypes.byref(entropy),
        None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(data_out),
    )
    if not ok:
        raise ctypes.WinError()
    return _from_blob(data_out).decode("utf-8")
