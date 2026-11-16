"""Reserve a .part file at its final size without writing zeros to disk.

On NTFS a plain truncate() zero-fills the whole file, which for a multi-GB
download takes seconds to minutes. Marking the file sparse first makes the
size change instant, and later writes at any offset stay fast.
"""

from __future__ import annotations

import sys
from typing import BinaryIO

_FSCTL_SET_SPARSE = 0x000900C4


def _windows_sparse(fh: BinaryIO, size: int) -> bool:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    k.DeviceIoControl.restype = wintypes.BOOL
    k.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.c_void_p, wintypes.DWORD]
    k.SetFilePointerEx.restype = wintypes.BOOL
    k.SetEndOfFile.argtypes = [wintypes.HANDLE]
    k.SetEndOfFile.restype = wintypes.BOOL

    fh.flush()
    handle = msvcrt.get_osfhandle(fh.fileno())
    returned = wintypes.DWORD()
    if not k.DeviceIoControl(handle, _FSCTL_SET_SPARSE, None, 0, None, 0, ctypes.byref(returned), None):
        return False  # e.g. FAT32/exFAT: no sparse support
    return bool(k.SetFilePointerEx(handle, size, None, 0) and k.SetEndOfFile(handle))


def preallocate(fh: BinaryIO, size: int) -> None:
    if sys.platform == "win32":
        try:
            if _windows_sparse(fh, size):
                return
        except OSError:
            pass
    fh.truncate(size)
