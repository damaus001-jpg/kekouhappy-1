import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock, Mock

from native_ui_scan import scan, ScanResult, Direction
from native_workspace import verified_list, unread_records, compose_toolbar, list_page, open_phone_conversation
from native_message_page import classify_footer, read_message_footer


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
        elif direction==Direction.Previous:self.index=(self.index-1)%len(self.items)
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
    async def test_compose_toolbar_skips_thousands_of_message_rows(self):
        captions=['Edit, Button','Messages, Header']+['Conversation '+str(i) for i in range(2000)]+[
            'Search, Search Field','Dictate, Button','Compose, Button']
        items=[SimpleNamespace(platform_identifier=str(i),caption=c) for i,c in enumerate(captions)]
        inspector=Inspector(items)
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x), \
                patch('native_workspace.raw_page',new=AsyncMock(side_effect=AssertionError('must not walk message list'))):
            result=await list_page(inspector,None,toolbar_only=True)
        self.assertEqual([r['caption'] for r in result],['Compose, Button','Dictate, Button','Search, Search Field'])
        self.assertFalse(result.complete)
        self.assertEqual(result.reason,'compose_toolbar_verified')
        self.assertEqual(inspector.advances,0)
        self.assertFalse(inspector.monitoring)

    async def test_compose_alone_is_not_enough_to_identify_messages_list(self):
        items=[SimpleNamespace(platform_identifier=str(i),caption=c) for i,c in enumerate([
            'Inbox','Compose, Button'])]
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            self.assertIsNone(await compose_toolbar(Inspector(items)))

    def test_page_type_uses_search_or_plus_without_needing_top_header(self):
        for caption,kind in [('Search, Search Field','message_list'),('Search, Button','message_list'),
                             ('add, Button','conversation'),('+, Button','conversation')]:
            with self.subTest(caption=caption):
                result=classify_footer([{'caption':caption}])
                self.assertEqual(result['page_type'],kind)
                self.assertFalse(result['compose_available'])
                self.assertFalse(result['send_available'])
                self.assertEqual(result['input_state'],'unknown')

    async def test_conversation_detection_stops_at_plus_without_reading_bubbles(self):
        captions=['Header']+['Your Message, history '+str(i) for i in range(2000)]+[
            'add, Button','Message, hello','Send, Button, Send using Text messaging']
        items=[SimpleNamespace(platform_identifier=str(i),caption=c) for i,c in enumerate(captions)]
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            result=await read_message_footer(Inspector(items))
        self.assertEqual(result['page_type'],'conversation')
        self.assertEqual(result['elements_checked'],3)
        self.assertEqual(result['input_state'],'draft')
        self.assertTrue(result['send_available'])

    def test_empty_conversation_and_conflicting_or_incomplete_footer(self):
        result=classify_footer([{'caption':c} for c in ['Record audio, Button','Message, Text Message, SMS','add, Button']])
        self.assertEqual(result['page_type'],'conversation')
        self.assertEqual(result['input_state'],'empty')
        self.assertFalse(result['send_available'])
        for captions in [['Search, Search Field','add, Button'],['Compose, Button'],['Message, text','Send, Button']]:
            self.assertEqual(classify_footer([{'caption':c} for c in captions])['page_type'],'unknown')

    def test_disabled_send_button_is_not_actionable(self):
        result=classify_footer([{'caption':c} for c in ['add, Button','Message, hi','Send, Button, Disabled']])
        self.assertEqual(result['page_type'],'conversation')
        self.assertFalse(result['send_available'])
        result=classify_footer([{'caption':c} for c in ['add, Button','Send, Button']])
        self.assertEqual(result['page_type'],'conversation')
        self.assertFalse(result['send_available'])

    async def test_followup_open_uses_toolbar_and_verifies_recipient(self):
        phone=SimpleNamespace(chord=AsyncMock(),paste=AsyncMock(),keys=AsyncMock())
        number='+12025550191'
        pages=[page(['New Message, Show Conversation Details, Button','To:','Message']),
               page(['To:, '+number])]
        with patch('native_workspace.list_page',new_callable=AsyncMock) as navigation, \
                patch('native_workspace.raw_page',new=AsyncMock(side_effect=pages)), \
                patch('native_workspace.read',new=AsyncMock(return_value={'phone_number':number})), \
                patch('native_workspace.asyncio.sleep',new_callable=AsyncMock):
            self.assertEqual((await open_phone_conversation(None,phone,number))['phone_number'],number)
        navigation.assert_awaited_once_with(None,phone,toolbar_only=True)
        phone.paste.assert_awaited_once_with(number)
        phone.chord.assert_awaited_once_with(0x11)

    async def test_fast_navigation_still_preserves_existing_phone_draft(self):
        phone=SimpleNamespace(request=Mock())
        draft=page(['+12025550191, Show Conversation Details, Button','Message, draft','Send, Button'])
        with patch('native_workspace.compose_toolbar',new=AsyncMock(return_value=None)), \
                patch('native_workspace.raw_page',new=AsyncMock(return_value=draft)), \
                patch('native_workspace.context',return_value={}):
            with self.assertRaisesRegex(ValueError,'草稿'):
                await list_page(None,phone,toolbar_only=True)
        phone.request.assert_not_called()

    async def test_header_identity_can_stop_before_blocked_image_without_claiming_history(self):
        items=[SimpleNamespace(platform_identifier=str(i),caption=c) for i,c in enumerate(
            ['Back, Button','+12345678901, Show Conversation Details, Button','Includes picture'])]
        inspector=Inspector(items,drop=2)
        with patch('native_ui_scan.deserialize_object',side_effect=lambda x:x):
            result=await scan(inspector,limit=20,seconds=4,settle=0,
                              stop_when=lambda i:'Show Conversation Details' in i.caption)
        self.assertEqual(len(result),2)
        self.assertEqual(inspector.advances,1)
        self.assertFalse(result.complete)
        self.assertEqual(result.reason,'target_found')
        self.assertFalse(inspector.monitoring)

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
