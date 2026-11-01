import io
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from visual_composer import composer_rect, input_point, send_point, send_point_in_frame, frame


def screen(width=588,height=1280,dark=False,send=False):
    image=np.full((height,width,3),24 if dark else 255,dtype=np.uint8)
    x,y,w,h=round(.19*width),round(.915*height),round(.74*width),round(.048*height)
    cv2.rectangle(image,(x,y),(x+w,y+h),(100,100,100) if dark else (230,230,230),1)
    if send:
        cv2.circle(image,(x+w-round(.07*width),y+h//2),round(.03*width),(40,210,50),-1)
    return image


class VisualComposerTests(unittest.TestCase):
    def test_live_size_and_theme_change_do_not_require_fixed_device_coordinates(self):
        for width,height,dark in [(588,1280,False),(720,1560,True),(390,844,False)]:
            with self.subTest(width=width,dark=dark),patch('visual_composer.frame',return_value=screen(width,height,dark)):
                point=input_point(None)
                self.assertTrue(.3<point['x']<.6)
                self.assertTrue(.9<point['y']<.98)

    def test_empty_screen_never_guesses_input_location(self):
        with self.assertRaises(ValueError):composer_rect(np.full((1280,588,3),255,dtype=np.uint8))

    def test_colored_message_bubble_is_not_mistaken_for_input(self):
        image=screen()
        cv2.rectangle(image,(110,800),(548,870),(40,210,50),-1)
        self.assertGreater(composer_rect(image)[1],1100)

    def test_only_enabled_send_circle_inside_composer_is_used(self):
        image=screen(send=True)
        point=send_point_in_frame(image)
        self.assertTrue(.8<point['x']<.93)
        self.assertTrue(.9<point['y']<.98)
        with self.assertRaises(ValueError):send_point_in_frame(screen())

    def test_cached_pre_paste_frame_is_skipped_until_send_is_visible(self):
        def updates():
            yield screen()
            yield screen(send=True)
        with patch('visual_composer.frames',side_effect=lambda phone:updates()):
            point=send_point(None)
        self.assertTrue(.8<point['x']<.93)

    def test_truncated_video_is_never_used_for_touch(self):
        response=io.BytesIO(struct.pack('>I',1000)+b'bad')
        phone=SimpleNamespace(base='http://127.0.0.1:8080',opener=SimpleNamespace(open=lambda *a,**k:response))
        with self.assertRaisesRegex(ValueError,'连接中断'):frame(phone)


if __name__=='__main__':unittest.main()
