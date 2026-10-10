"""Per-device touch profiles; normal sends inspect video dimensions, never save images."""
import asyncio
import base64
import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent / '.device-data' / 'coordinates'


def load_profile(device):
    if not re.fullmatch(r'[A-Za-z0-9-]{8,64}', device):
        raise ValueError('设备编号无效')
    path = ROOT / (device + '.json')
    if not path.exists():
        return None
    profile = json.loads(path.read_text(encoding='utf-8-sig'))
    if profile.get('device') != device or not profile.get('input_verified'):
        raise ValueError('当前手机坐标未校准')
    for role in ('input', 'send'):
        point = profile[role]
        if not all(isinstance(point[k], (int, float)) and 0 < point[k] < 1 for k in ('x', 'y')):
            raise ValueError('手机点击坐标无效')
    return profile


def video_size(phone):
    import av
    info = phone.request(phone.base, '/codec')
    decoder = av.CodecContext.create('hevc', 'r')
    decoder.extradata = base64.b64decode(info['description'])
    def exact(response, size):
        data = bytearray()
        while len(data) < size:
            chunk = response.read(size - len(data))
            if not chunk:
                raise ValueError('视频连接中断，未点击手机')
            data.extend(chunk)
        return bytes(data)
    with phone.opener.open(phone.base + '/stream.bin', timeout=10) as response:
        for _ in range(120):
            length = struct.unpack('>I', exact(response, 4))[0]
            if not 1 < length <= 20000000:
                raise ValueError('视频帧无效，未点击手机')
            for frame in decoder.decode(av.Packet(exact(response, length)[1:])):
                return frame.width, frame.height
    raise ValueError('未确认屏幕方向，未点击手机')


async def check_layout(phone, profile, captions):
    if any('Keyboard Key' in c and not c.startswith('Dictate,') for c in captions):
        raise ValueError('屏幕键盘布局与坐标校准不一致，请收起屏幕键盘')
    width, height = await asyncio.to_thread(video_size, phone)
    expected = profile['screen']
    if width >= height or abs(width / height - expected['width'] / expected['height']) > .02:
        raise ValueError('屏幕方向或比例已变化，请重新校准手机坐标')


async def tap(phone, point):
    coords = {key: round(point[key] * 65535) for key in ('x', 'y')}
    try:
        phone.request(phone.base, '/touch', {'type': 'contact', **coords})
        await asyncio.sleep(.08)
    finally:
        phone.request(phone.base, '/touch', {'type': 'release', **coords})
    await asyncio.sleep(.3)
