"""Download progress on the Windows taskbar button (ITaskbarList3), via plain ctypes COM.

On other platforms, or if COM fails, every call is a no-op.
"""

from __future__ import annotations

import ctypes
import sys
import uuid

TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_CLSID_TASKBARLIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_ITASKBARLIST4 = "{C43DC798-95D1-4BEA-9030-BB99E2983A1A}"  # extends ITaskbarList3
_CLSCTX_INPROC_SERVER = 0x1


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def from_str(cls, s: str) -> "_GUID":
        return cls.from_buffer_copy(uuid.UUID(s).bytes_le)


class TaskbarProgress:
    """Wraps ITaskbarList4 (ITaskbarList3 methods) for one window handle (``int(widget.winId())``)."""

    def __init__(self) -> None:
        self._ptr = ctypes.c_void_p()
        self._ok = False
        self._last: tuple[int, int] | None = None
        if sys.platform != "win32":
            return
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)
            clsid, iid = _GUID.from_str(_CLSID_TASKBARLIST), _GUID.from_str(_IID_ITASKBARLIST4)
            hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, _CLSCTX_INPROC_SERVER, ctypes.byref(iid),
                                        ctypes.byref(self._ptr))
            if hr != 0 or not self._ptr:
                return
            self._ok = self._call(3, ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)) == 0  # HrInit
        except Exception:
            self._ok = False

    def _call(self, index: int, proto, *args) -> int:
        vtable = ctypes.cast(ctypes.cast(self._ptr, ctypes.POINTER(ctypes.c_void_p))[0],
                             ctypes.POINTER(ctypes.c_void_p))
        return proto(vtable[index])(self._ptr, *args)

    def update(self, hwnd: int, state: int, fraction: float | None = None) -> None:
        """Show ``fraction`` (0..1) with a TBPF_* state on the window's taskbar button."""
        if not self._ok or not hwnd:
            return
        value = int(max(0.0, min(1.0, fraction or 0.0)) * 1000)
        if self._last == (state, value):
            return
        self._last = (state, value)
        try:
            set_state = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)
            self._call(10, set_state, ctypes.c_void_p(hwnd), state)  # SetProgressState
            if state in (TBPF_NORMAL, TBPF_PAUSED, TBPF_ERROR):
                set_value = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_ulonglong, ctypes.c_ulonglong)
                self._call(9, set_value, ctypes.c_void_p(hwnd), value, 1000)  # SetProgressValue
        except Exception:
            self._ok = False


def overall(snaps) -> tuple[int, float | None]:
    """Combine all unfinished downloads into one taskbar state and fraction."""
    running = [s for s in snaps if s.status.is_running]
    if running:
        sized = [s for s in running if s.size]
        if not sized:
            return TBPF_INDETERMINATE, None
        total = sum(s.size for s in sized)
        return TBPF_NORMAL, sum(min(s.downloaded, s.size) for s in sized) / total
    return TBPF_NOPROGRESS, None
