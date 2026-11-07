"""Locate Messages controls in a live frame; never stores phone images."""
import struct
import time

import cv2
import numpy as np


def frames(phone, seconds=6):
    def exact(response, size):
        data = bytearray()
        while len(data) < size:
            chunk = response.read(size-len(data))
            if not chunk:
                raise ValueError('视频连接中断，未点击手机')
            data.extend(chunk)
        return bytes(data)
    with phone.opener.open(phone.base+'/jpeg.bin', timeout=10) as response:
        deadline = time.monotonic()+seconds
        while time.monotonic() < deadline:
            size = struct.unpack('>I', exact(response, 4))[0]
            if not 100 < size <= 8*1024*1024:
                raise ValueError('视频帧无效，未点击手机')
            result = cv2.imdecode(np.frombuffer(exact(response, size), dtype=np.uint8), cv2.IMREAD_COLOR)
            if result is None or result.shape[0] <= result.shape[1]:
                raise ValueError('请使用手机竖屏短信界面，未点击手机')
            yield result


def frame(phone):
    stream = frames(phone)
    try:return next(stream)
    finally:stream.close()


def composer_rect(image):
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    contours, _ = cv2.findContours(cv2.Canny(gray, 8, 24), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if not (.08*width < x < .45*width and x+w > .85*width and w > .45*width
                and .02*height < h < .18*height and y > .45*height and w > 2.5*h):
            continue
        inside = image[y+max(2,h//6):y+h-max(2,h//6), x+w//8:x+7*w//8]
        if not inside.size or float(np.median(inside.max(axis=2).astype(float)-inside.min(axis=2))) > 25:
            continue
        candidates.append((x,y,w,h))
    if not candidates:
        raise ValueError('未定位到短信输入框，请保持当前会话完整显示，未输入或发送')
    # The bottommost wide neutral rounded field is the composer. Consolidate
    # inner/outer edges of that field; never guess between nearby distinct fields.
    best = max(candidates, key=lambda r:r[1]+r[3]/2)
    bx,by,bw,bh = best
    for x,y,w,h in candidates:
        intersection = max(0,min(x+w,bx+bw)-max(x,bx))*max(0,min(y+h,by+bh)-max(y,by))
        union = w*h+bw*bh-intersection
        if abs(y+h/2-(by+bh/2)) < .08*height and intersection/max(1,union) < .7:
            raise ValueError('短信输入框位置不唯一，未点击手机')
    return best


def input_point(phone, *, fresh=False):
    if fresh:
        # Skip the hub's cached first frame after keyboard registration, which
        # may still show the composer above the old software keyboard.
        stream = frames(phone)
        try:
            next(stream)
            image = next(stream)
        finally:
            stream.close()
    else:
        image = frame(phone)
    x,y,w,h = composer_rect(image)
    return {'x':(x+.32*w)/image.shape[1], 'y':(y+.5*h)/image.shape[0]}


def send_point_in_frame(image):
    x,y,w,h = composer_rect(image)
    height,width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([30,85,65]), np.array([135,255,255]))
    candidates = []
    contours,_ = cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        cx,cy,cw,ch = cv2.boundingRect(contour)
        # Messages also renders Send as a short horizontal capsule. Require
        # a rounded, compact shape inside the composer, including that layout.
        perimeter = cv2.arcLength(contour, True)
        rounded = len(cv2.approxPolyDP(contour, .025*perimeter, True)) >= 6
        if (.025*width < cw < .15*width and .7 < cw/ch < 1.8 and rounded
                and .35*h < ch < 1.3*h
                and cx+cw/2 > x+.75*w and abs(cy+ch/2-(y+h/2)) < .6*h
                and cx+cw/2 < x+w+.02*width and cv2.contourArea(contour) > .55*cw*ch):
            candidates.append((cx,cy,cw,ch))
    if len(candidates) != 1:
        raise ValueError('未定位到唯一可用的手机发送按钮，未执行发送')
    x,y,w,h = candidates[0]
    return {'x':(x+w/2)/width, 'y':(y+h/2)/height}


def send_point(phone):
    # The hub's first JPEG may predate the paste. Keep the stream subscribed
    # until the enabled Send button is actually visible instead of reopening
    # and consuming the same cached first frame on every attempt.
    stream = frames(phone)
    failure = None
    try:
        for image in stream:
            try:return send_point_in_frame(image)
            except ValueError as exc:failure = exc
    finally:
        stream.close()
    raise ValueError(str(failure) if failure else '视频未提供发送按钮画面，未执行发送')
