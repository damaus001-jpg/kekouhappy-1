"""JSON/stdin-only CLI used by Pikachu's main process; never a desktop entry."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys

from backend_control import Backend
from host_access import (AuthorizationError, InstallationError, PROJECT,
                         authorized_operation, host_only, read_proof)


class BusyError(RuntimeError):
    pass


@contextmanager
def operation_lock(root):
    import msvcrt
    folder = Path(root) / 'iphone_batch/.device-data/logs/host-control'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'operation.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BusyError('后台正在执行其他启停操作') from None
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def check_install(root):
    root = Path(root)
    if not host_only(root) or not all((root / name).is_file() for name in (
            'runtime/python.exe', 'runtime/node.exe', 'VERSION',
            'iphone_batch/host_control.py', 'iphone_batch/dashboard.py',
            'iphone_batch/tunneld_entry.py')):
        raise InstallationError()


def execute(action, proof, *, root=PROJECT, backend_factory=Backend):
    result = {'protocol': 1, 'ok': False, 'action': action, 'state': 'unknown'}
    try:
        if action not in ('status', 'start', 'stop'):
            raise AuthorizationError()
        check_install(root)
        with authorized_operation(action, proof, root), operation_lock(root):
            backend = backend_factory()
            # Keep stdout a single JSON record even if an imported operation prints.
            with redirect_stdout(io.StringIO()):
                message = getattr(backend, action)() if action != 'status' else ''
                processes = backend.processes()
            state = ('running' if any(entry == 'dashboard.py' for _, entry in processes)
                     else 'residual' if processes else 'stopped')
            if action == 'stop' and processes:
                raise RuntimeError('仍有相关进程未退出，请再次点击彻底关闭')
            if action == 'start' and state != 'running':
                raise RuntimeError('后台启动失败，请查看后台日志')
            result.update(ok=True, state=state, process_count=len(processes),
                          version=(Path(root) / 'VERSION').read_text(encoding='utf-8-sig').strip(),
                          message=message or {'running': '后台运行中', 'residual': '主服务已停止，仍有相关进程',
                                              'stopped': '后台已关闭'}[state])
        return result, 0
    except InstallationError:
        result.update(code='MISSING_FILES', message='安装文件缺失'); return result, 2
    except AuthorizationError:
        result.update(code='AUTH_REQUIRED', message='请通过皮卡丘操作8070后台'); return result, 3
    except BusyError as error:
        result.update(code='BUSY', message=str(error)); return result, 4
    except Exception as error:
        result.update(code='OPERATION_FAILED', message=str(error)); return result, 1


def main():
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    try:
        proof = read_proof()
    except AuthorizationError:
        proof = None
    result, code = execute(action, proof)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
