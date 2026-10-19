"""Only upstream's psutil surface, backed by Android/OS measurements.

CPU process accounting is restricted on Android; report it as unsupported.
"""
import os
import shutil
from types import SimpleNamespace

Error = OSError
IOPRIO_CLASS_IDLE = 3


def cpu_percent(interval=0):
    raise NotImplementedError('Android restricts system CPU accounting')


def virtual_memory():
    from java import jclass
    from com.chaquo.python import Python
    context = Python.getPlatform().getApplication()
    info = jclass('android.app.ActivityManager$MemoryInfo')()
    context.getSystemService('activity').getMemoryInfo(info)
    return SimpleNamespace(available=info.availMem, total=info.totalMem,
                           percent=round(100 * (1 - info.availMem / info.totalMem), 1))


def disk_usage(path):
    total, used, free = shutil.disk_usage(os.environ['HOME'] if path == '/' else path)
    return SimpleNamespace(total=total, used=used, free=free, percent=round(100 * used / total, 1))


def net_if_addrs():
    raise NotImplementedError('Use Android ConnectivityManager')


class Process:
    def __init__(self, pid):
        self.pid = pid

    def nice(self, priority):
        os.setpriority(os.PRIO_PROCESS, self.pid, priority)

    def ionice(self, priority):
        raise NotImplementedError('Android does not expose ioprio')
