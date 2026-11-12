import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import native_ui_scan
from pymobiledevice3.services.accessibilityaudit import Direction
from native_reverse_reader import capture_reverse,recipient_number


class FakeService:
    def __init__(self,captions):
        self.nodes=[SimpleNamespace(caption=c,platform_identifier=str(i)) for i,c in enumerate(captions)]
        self._event_queue=asyncio.Queue()
        self.index=0
        self.moves=[]
    async def set_app_monitoring_enabled(self,_):pass
    async def set_monitored_event_type(self):pass
    def _extract_event_payload(self,args):return args
    async def move_focus_next(self):await self.move_focus(Direction.Next)
    async def move_focus(self,direction):
        self.moves.append(direction)
        if direction==Direction.First:self.index=0
        elif direction==Direction.Last:self.index=len(self.nodes)-1
        elif direction==Direction.Previous:self.index=(self.index-1)%len(self.nodes)
        else:self.index=(self.index+1)%len(self.nodes)
        self._event_queue.put_nowait(('hostInspectorCurrentElementChanged:',[self.nodes[self.index]]))


class ReverseTests(unittest.IsolatedAsyncioTestCase):
    async def capture(self,captions):
        service=FakeService(captions)
        async def fast_scan(*args,**kwargs):
            self.assertTrue(kwargs['reverse'])
            self.assertEqual(kwargs['settle'],.20)
            kwargs['settle']=0
            return await native_ui_scan.scan(*args,**kwargs)
        with patch('native_ui_scan.deserialize_object',side_effect=lambda value:value),patch('native_reverse_reader.scan',side_effect=fast_scan):
            result=await capture_reverse(service)
        return result,service

    async def test_picture_does_not_stop_reverse_traversal(self):
        result,service=await self.capture(['+12025550123, Show Conversation Details, Button',
            'Mon, Oct 12 at 13:04','+12025550123, first, 13:04',
            '+12025550123, Includes picture','Your Message, last, 13:05','Message, Text Field'])
        self.assertEqual(result['phone_number'],'+12025550123')
        self.assertEqual([m['kind'] for m in result['messages']],['text','attachment','text'])
        self.assertEqual(result['messages'][0]['date'],'10-12')
        self.assertIn(Direction.Previous,service.moves)
        self.assertFalse(result['history_complete'])

    async def test_body_number_is_not_a_stop_condition(self):
        self.assertIsNone(recipient_number('Your Message, call +12025550123, 13:04'))
        with self.assertRaisesRegex(ValueError,'未读到会话顶部的完整手机号'):
            await self.capture(['Morgan, Show Conversation Details, Button',
                'Your Message, call +12025550123, 13:04','Your Message, Includes picture'])


if __name__=='__main__':unittest.main()
