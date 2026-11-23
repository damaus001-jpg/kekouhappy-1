"""One bounded, serial, read-only banner worker per USB device.

Keep Python imports warm; open/restore/close the native session for every read.
No HID, screenshots, clipboard, database backup or sending is exposed here.
"""
import asyncio
import json
import os
import queue
import sys
import threading

MAX_LINE = 256 * 1024
IDLE_SECONDS = 30


def serve_banner(args, execute, *, input_stream=None, output_stream=None, idle_seconds=IDLE_SECONDS):
    if args.action not in ('banner','badge'):
        raise ValueError('Persistent workers may only perform read-only notification checks')
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    requests = queue.Queue(maxsize=1)
    def read_requests():
        if input_stream is sys.stdin:
            # An idle daemon must not hold stdin's BufferedReader lock during
            # interpreter shutdown. Raw reads also let parent EOF end cleanly.
            pending = b''
            while True:
                block = os.read(input_stream.fileno(), 4096)
                if not block:
                    requests.put(None)
                    return
                pending += block
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    if len(line) > 4096:
                        requests.put(None)
                        return
                    try:
                        requests.put(line.decode('ascii'))
                    except UnicodeDecodeError:
                        requests.put(None)
                        return
                if len(pending) > 4096:
                    requests.put(None)
                    return
        while True:
            line = input_stream.readline(4097)
            if not line or len(line) > 4096:
                requests.put(None)
                return
            requests.put(line)
    threading.Thread(target=read_requests, name='banner-worker-input', daemon=True).start()
    while True:
        try:
            line = requests.get(timeout=idle_seconds)
        except queue.Empty:
            return
        if line is None:
            return
        try:
            request = json.loads(line)
            identifier = request['request_id']
            if (set(request) != {'request_id'} or not isinstance(identifier, str)
                    or len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier)):
                return
        except (KeyError, TypeError, ValueError):
            return
        try:
            # Each request gets a fresh loop/session, preserving the old cleanup
            # and audit-target restoration behavior without import/process churn.
            result = asyncio.run(execute(args))
        except Exception as error:
            result = {'error': str(error)}
        output = json.dumps({'request_id': identifier, 'result': result}, ensure_ascii=True)
        if len(output) > MAX_LINE - 1:
            output = json.dumps({'request_id': identifier, 'result': {'error': '横幅读取结果过大'}})
        print(output, file=output_stream, flush=True)
