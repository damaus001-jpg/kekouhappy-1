"""Whole-system CPU utility for Windows 10 Task Manager compatibility."""
import ctypes
import math
import os


class CounterValue(ctypes.Structure):
    _fields_ = [('status', ctypes.c_uint32), ('value', ctypes.c_double)]


class WindowsCpuUtility:
    def __init__(self, library=None):
        self.library = library if library is not None else ctypes.WinDLL('pdh.dll')
        handle = ctypes.c_void_p
        signatures = {
            'PdhOpenQueryW': [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(handle)],
            'PdhAddEnglishCounterW': [handle, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(handle)],
            'PdhCollectQueryData': [handle],
            'PdhGetFormattedCounterValue': [handle, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(CounterValue)],
            'PdhCloseQuery': [handle],
        }
        for name, arguments in signatures.items():
            function = getattr(self.library, name)
            function.argtypes = arguments
            function.restype = ctypes.c_uint32
        self.query = handle()
        self.counter = handle()
        self.primed = False

    @staticmethod
    def check(status):
        if status:
            raise OSError(f'CPU performance counter unavailable: 0x{status:08x}')

    def __call__(self):
        try:
            if not self.query.value:
                self.check(self.library.PdhOpenQueryW(None, 0, ctypes.byref(self.query)))
                # English paths are localized by PDH, including on Chinese Windows.
                self.check(self.library.PdhAddEnglishCounterW(
                    self.query, r'\Processor Information(_Total)\% Processor Utility',
                    0, ctypes.byref(self.counter)))
            self.check(self.library.PdhCollectQueryData(self.query))
            if not self.primed:
                self.primed = True
                return 0.0  # Baseline only; CpuUsage discards this sample.
            result = CounterValue()
            self.check(self.library.PdhGetFormattedCounterValue(self.counter, 0x200, None, ctypes.byref(result)))
            if result.status not in (0, 1) or not math.isfinite(result.value):
                raise OSError('CPU performance counter returned invalid data')
            return max(0.0, min(100.0, result.value))
        except Exception:
            self.close()
            raise

    def close(self):
        if self.query.value:
            self.library.PdhCloseQuery(self.query)
        self.query = ctypes.c_void_p()
        self.counter = ctypes.c_void_p()
        self.primed = False


def create_cpu_reader():
    if os.name == 'nt':
        return WindowsCpuUtility()
    import psutil
    return lambda: psutil.cpu_percent(interval=None)
