import av
import base64
import json
from pathlib import Path
import struct
import time
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open('http://127.0.0.1:8080/codec', timeout=15) as response:
    info = json.load(response)
codec = av.CodecContext.create('hevc', 'r')
codec.extradata = base64.b64decode(info['description'])
output = Path(__file__).resolve().parent / '.device-data' / 'diagnostics' / 'unread-list-current.png'

def read_exact(response, length):
    data = bytearray()
    while len(data) < length:
        chunk = response.read(length-len(data))
        if not chunk:
            raise EOFError('Video stream closed')
        data.extend(chunk)
    return bytes(data)

started = time.monotonic()
with opener.open('http://127.0.0.1:8080/stream.bin', timeout=15) as response:
    while time.monotonic()-started < 25:
        length = struct.unpack('>I', read_exact(response, 4))[0]
        if not 1 <= length <= 20000000:
            raise ValueError('Invalid frame length')
        frame_data = read_exact(response, length)
        frames = codec.decode(av.Packet(frame_data[1:]))
        if frames:
            frames[-1].to_image().save(output)
            if time.monotonic()-started >= 3:
                print(json.dumps({'image':str(output),'width':frames[-1].width,'height':frames[-1].height}))
                break
    else:
        raise TimeoutError('No decoded video frame')

