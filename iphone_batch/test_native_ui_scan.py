import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

from native_ui_scan import scan, ScanResult, Direction
from native_workspace import verified_list, unread_records


class Inspector:
    def __init__(self, items, drop=None):
        self.items=items;self.index=0;self.drop=drop
        self._event_queue=asyncio.Queue();self.advances=0;self.monitoring=False
    async def set_app_monitoring_enabled(self,value):self.monitoring=value
    async def set_monitored_event_type(self):pass
    def _extract_event_payload(self,args):return args
    async def move_focus(self,direction):
        if direction==Direction.Last:self.index=len(self.items)-1
        elif direction==Direction.First:self.index=0
        else:self.index=(self.index+1)%len(self.items)
        self._event_queue.put_nowait(('hostInspectorCurrentElementChanged:',self.items[self.index]))
    async def move_focus_next(self):
        self.advances+=1
        if self.drop==self.advances:return
        await self.move_focus(Direction.Next)


def page(captions,complete=True):
    result=ScanResult({'caption':c} for c in captions)
    result.complete=complete;result.reason='cycle_verified' if complete else 'time_limit';result.elapsed=1
    return result


class ScannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_name_and_preview_do_not_hide_distinct_contacts(self):
        rows=unread_records([{'caption':'Messages, Header'},
            {'caption':'John, Unread, Hi','platform_identifier':'a'},
            {'caption':'John, Unread, Hi','platform_identifier':'b'}])
        self.assertEqual(len(rows),2)

    async def test_recycled_identifier_does_not_skip_different_contact(self):
        items=[SimpleNamespace(platform_identifier='reused',caption=c) for c in ['Messages, Header','John, Unread, Hi','Mary, Unread, Hey']]
        inspector=Inspector(items)
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            result=await scan(inspector,limit=20,seconds=4,settle=0)
        self.assertTrue(result.complete);self.assertEqual(result,items)
        self.assertFalse(inspector.monitoring)

    async def test_silent_next_is_not_repeated_or_claimed_complete(self):
        items=[SimpleNamespace(platform_identifier=str(i),caption=str(i)) for i in range(3)]
        inspector=Inspector(items,drop=1)
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            result=await scan(inspector,limit=20,seconds=.4,settle=0)
        self.assertFalse(result.complete);self.assertEqual(inspector.advances,1)
        self.assertEqual(len(result),1);self.assertFalse(inspector.monitoring)

    async def test_limit_is_never_full_result(self):
        items=[SimpleNamespace(platform_identifier=str(i),caption=str(i)) for i in range(5)]
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            result=await scan(Inspector(items),limit=3,seconds=4,settle=0)
        self.assertFalse(result.complete);self.assertEqual(result.reason,'limit')

    async def test_changing_list_preserves_observed_unreads_but_is_incomplete(self):
        first=page(['Messages, Header','John, Unread, Hi'])
        second=page(['Messages, Header','Mary, Unread, Hey'])
        with patch('native_workspace.raw_page',new=AsyncMock(return_value=second)):
            result=await verified_list(None,first)
        self.assertFalse(result['complete']);self.assertEqual(result['reason'],'list_changed')
        self.assertEqual({i['name'] for i in result['items']},{'John','Mary'})

    async def test_stable_full_passes_are_complete(self):
        first=page(['Messages, Header','John, Unread, Hi'])
        with patch('native_workspace.raw_page',new=AsyncMock(return_value=first)):
            result=await verified_list(None,first)
        self.assertTrue(result['complete']);self.assertEqual(len(result['items']),1)

    async def test_identifiers_changing_between_passes_do_not_double_count(self):
        first=page(['Messages, Header','John, Unread, Hi','John, Unread, Hi'])
        second=page(['Messages, Header','John, Unread, Hi','John, Unread, Hi'])
        for index,row in enumerate(first):row['platform_identifier']='first'+str(index)
        for index,row in enumerate(second):row['platform_identifier']='second'+str(index)
        with patch('native_workspace.raw_page',new=AsyncMock(return_value=second)):
            result=await verified_list(None,first)
        self.assertTrue(result['complete']);self.assertEqual(len(result['items']),2)


if __name__=='__main__':unittest.main()
