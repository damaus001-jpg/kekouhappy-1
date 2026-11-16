import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from message_notifications import parse_notification, open_notification, discover, is_center, verified_center_page, probe_surface
from native_ui_scan import ScanResult
import tempfile
from workspace_service import WorkspaceService
from notification_touch import locate,locate_open


def item(caption, identifier='element-one'):
    return SimpleNamespace(caption=caption, platform_identifier=identifier)


def center_items(*extra):
    return [item('Notification Center, Header', 'center-header'),
            item('Flashlight, Off, Button', 'flashlight'), item('Camera, Button', 'camera'), *extra]


class ParseTests(unittest.TestCase):
    def test_open_is_located_beside_only_the_expected_notification(self):
        def line(text,x,y,w=250):return {'text':text,'words':[{'text':text,'x':x,'y':y,'w':w,'h':28}]}
        expected={'phone_number':'+19562154700','time':'now','preview':'good morning'}
        lines=[line('+1 (956) 215-4700',350,1103),line('good morning',350,1139),
            line('Open',82,1123,71),line('+1 (956) 215-4700',150,1346),line('Open',82,1360,71)]
        point=locate_open(lines,expected,832,1808)
        self.assertAlmostEqual(point['x'],117.5/832)
        self.assertAlmostEqual(point['y'],1137/1808)
        with self.assertRaises(ValueError):locate_open(lines+[line('Open',710,1123,71)],expected,832,1808)

    def test_local_geometry_rejects_ambiguous_numbers_and_times(self):
        def line(text,y):return {'text':text,'words':[{'x':150,'y':y,'w':300,'h':25}]}
        expected={'phone_number':'+19562154700','time':'13 minutes ago'}
        lines=[line('+1 (956) 215-4700',1230),line('13m ago',1230),
               line('+1 (956) 215-4700',1390),line('14m ago',1390)]
        point=locate(lines,expected,832,1808)
        self.assertLess(point['y'],.75)
        with self.assertRaises(ValueError):locate(lines+[line('13m ago',1390)],expected,832,1808)

    def test_only_messages_source_is_accepted(self):
        for app in ('SIGNAL','CHATGPT','WeChat','MESSAGES PLUS'):
            self.assertIsNone(parse_notification(app+', now, +1 (956) 215-4700, Messages test, Button','x','one'))
        row=parse_notification('MESSAGES, Grouped, now, +1 (956) 215-4700, ❤️❤️❤️, Button, Activate to expand','x','one')
        self.assertEqual(row['phone_number'],'+19562154700')
        self.assertEqual(row['preview'],'❤️❤️❤️')
        self.assertTrue(row['grouped'])

    def test_time_change_is_not_a_new_notification_but_distinct_elements_are(self):
        one=parse_notification('MESSAGES, now, +19562154700, Okay, Button','x','one')
        later=parse_notification('MESSAGES, 1 minute ago, +19562154700, Okay, Button','x','one')
        second=parse_notification('MESSAGES, now, +19562154700, Okay, Button','y','one')
        self.assertEqual(one['id'],later['id'])
        self.assertNotEqual(one['id'],second['id'])
        self.assertNotEqual(one['id'],parse_notification('MESSAGES, now, +19562154700, Okay, Button','x','two')['id'])

    def test_name_only_requires_review_and_body_keeps_commas(self):
        row=parse_notification('MESSAGES, Yesterday, 19:10, John, Hello, friend, Button','x','one')
        self.assertFalse(row['clickable'])
        self.assertEqual(row['sender'],'John')
        self.assertEqual(row['preview'],'Hello, friend')


class OpenTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        probe = patch('message_notifications.probe_surface', AsyncMock(return_value=center_items()))
        probe.start()
        self.addCleanup(probe.stop)

    async def test_single_notification_can_require_a_second_open_tap(self):
        notification=item('MESSAGES, now, +19562154700, Hello, Button')
        center=center_items(notification)
        expected=parse_notification(notification.caption,notification.platform_identifier,'one')
        conversation=[item('+19562154700, Show Conversation Details, Button')]
        with patch('message_notifications.elements',AsyncMock(side_effect=[center,center,center,center,conversation])), \
             patch('message_notifications.activate',AsyncMock()), \
             patch('notification_touch.tap_notification',AsyncMock()) as touch:
            result=await open_notification(None,None,'one',expected,lambda records:{'phone_number':'+19562154700'})
        self.assertEqual(touch.await_count,2)
        self.assertEqual(result['phone_number'],'+19562154700')

    async def test_group_expands_then_opens_verified_recipient(self):
        group=item('MESSAGES, Grouped, now, +19562154700, Hello, Button, Activate to expand')
        single=item('MESSAGES, now, +19562154700, Hello, Button','expanded')
        header=item('Notification Center, Header')
        conversation=[item('+19562154700, Show Conversation Details, Button')]
        expected=parse_notification(group.caption,group.platform_identifier,'one')
        with patch('message_notifications.elements',AsyncMock(side_effect=[center_items(group),center_items(single),conversation])), patch('message_notifications.activate',AsyncMock()) as activate:
            result=await open_notification(None,None,'one',expected,lambda records:{'phone_number':'+19562154700'})
        self.assertEqual(activate.await_count,2)
        self.assertEqual(result['phone_number'],'+19562154700')

    async def test_changed_notification_never_clicked(self):
        old=item('MESSAGES, now, +19562154700, Hello, Button')
        expected=parse_notification(old.caption,old.platform_identifier,'one')
        changed=item('MESSAGES, now, +19562154700, Different, Button')
        with patch('message_notifications.elements',AsyncMock(return_value=center_items(changed))), patch('message_notifications.activate',AsyncMock()) as activate:
            with self.assertRaises(ValueError):await open_notification(None,None,'one',expected,lambda r:{})
        activate.assert_not_awaited()

    async def test_wrong_recipient_after_click_is_rejected(self):
        notification=item('MESSAGES, now, +19562154700, Hello, Button')
        expected=parse_notification(notification.caption,notification.platform_identifier,'one')
        with patch('message_notifications.elements',AsyncMock(side_effect=[center_items(notification),
             [item('+19999999999, Show Conversation Details, Button')]])), patch('message_notifications.activate',AsyncMock()):
            with self.assertRaises(ValueError):
                await open_notification(None,None,'one',expected,lambda r:{'phone_number':'+19999999999'})

    async def test_draft_stops_notification_center_gesture(self):
        with patch('message_notifications.probe_surface',AsyncMock(return_value=[item('Message, Draft'),item('Send, Button')])), patch('message_notifications.swipe',AsyncMock()) as swipe:
            with self.assertRaises(ValueError):await discover(None,None,'one')
        swipe.assert_not_awaited()


class SurfaceTests(unittest.IsolatedAsyncioTestCase):
    def test_title_alone_or_either_corner_button_is_not_success(self):
        for entries in ([item('Notification Center, Header')], [item('Show Notifications, Button')],
                        [item('Flashlight, Off, Button', 'f')], [item('Camera, Button', 'c')],
                        [item('Flashlight, Off, Button', 'same'), item('Camera, Button', 'same')]):
            self.assertFalse(is_center(entries))
        self.assertTrue(is_center(center_items()))
        self.assertTrue(is_center([item('手电筒, 关闭, 按钮', 'f'), item('相机, 按钮', 'c')]))

    async def test_failed_swipe_never_full_scans_the_messages_list(self):
        page = [item('Messages, Header')]
        with patch('message_notifications.probe_surface', AsyncMock(side_effect=[page, page])), \
                patch('message_notifications.swipe', AsyncMock()) as swipe, \
                patch('message_notifications.elements', AsyncMock()) as full, \
                patch('message_notifications.parse_notification') as parse:
            with self.assertRaisesRegex(ValueError, '下拉后未确认通知中心'):
                await discover(None, None, 'one')
        full.assert_not_awaited()
        parse.assert_not_called()
        swipe.assert_awaited_once_with(None, .002, .82)

    async def test_header_without_both_buttons_never_enters_full_scan(self):
        page = [item('Messages, Header')]
        unconfirmed = [item('Notification Center, Header')]
        with patch('message_notifications.probe_surface', AsyncMock(side_effect=[page, unconfirmed, unconfirmed])), \
                patch('message_notifications.swipe', AsyncMock()), \
                patch('message_notifications.elements', AsyncMock()) as full:
            with self.assertRaises(ValueError):
                await discover(None, None, 'one')
        full.assert_not_awaited()

    async def test_confirmed_pair_allows_collection_and_safe_close(self):
        notification = item('MESSAGES, now, +19562154700, Hello, Button')
        with patch('message_notifications.probe_surface', AsyncMock(side_effect=[
                [item('Messages, Header')], center_items(), center_items()])), \
                patch('message_notifications.elements', AsyncMock(return_value=center_items(notification))) as full, \
                patch('message_notifications.swipe', AsyncMock()) as swipe:
            result = await discover(None, None, 'one')
        self.assertEqual(len(result['items']), 1)
        self.assertTrue(result['complete'])
        full.assert_awaited_once_with(None, center_only=True)
        self.assertEqual(swipe.await_count, 2)

    async def test_surface_change_during_scan_stops_before_retry(self):
        changed = ScanResult([item('Messages, Header')])
        changed.reason, changed.complete = 'target_found', False
        with patch('message_notifications.scan', AsyncMock(return_value=changed)) as scan:
            with self.assertRaisesRegex(ValueError, '页面已离开通知中心'):
                await verified_center_page(None)
        self.assertEqual(scan.await_count, 1)

    async def test_probe_timeout_prevents_gesture_and_full_scan(self):
        partial = ScanResult([item('Unknown, Header')])
        partial.reason = 'event_timeout'
        with patch('message_notifications.scan', AsyncMock(return_value=partial)), \
                patch('message_notifications.elements', AsyncMock()) as full, \
                patch('message_notifications.swipe', AsyncMock()) as swipe:
            with self.assertRaisesRegex(ValueError, '未执行完整遍历'):
                await discover(None, None, 'one')
        full.assert_not_awaited()
        swipe.assert_not_awaited()

    async def test_cleanup_does_not_swipe_a_different_page(self):
        with patch('message_notifications.probe_surface', AsyncMock(side_effect=[
                [item('Messages, Header')], center_items(), [item('Messages, Header')]])), \
                patch('message_notifications.elements', AsyncMock(return_value=center_items())), \
                patch('message_notifications.swipe', AsyncMock()) as swipe:
            await discover(None, None, 'one')
        swipe.assert_awaited_once_with(None, .002, .82)


class StoreTests(unittest.TestCase):
    def test_incomplete_check_preserves_saved_notification(self):
        with tempfile.TemporaryDirectory() as root:
            row = parse_notification('MESSAGES, now, +19562154700, Hello, Button', 'x', 'one')
            service = WorkspaceService(root, native=lambda *args, **kwargs: {'items': [], 'complete': False})
            path = service.notification_path(row['id'])
            service.write(path, row)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, '已保留上次通知结果'):
                service.notifications('one', 'unused')
            self.assertEqual(path.read_bytes(), before)

    def test_notification_open_archives_live_context_and_marks_handled_after_success(self):
        with tempfile.TemporaryDirectory() as root:
            row=parse_notification('MESSAGES, now, +19562154700, Hello, Button','x','one')
            calls=[]
            def native(device,action,base,**kwargs):
                calls.append(action)
                return {'device':device,'contact':row['phone_number'],'phone_number':row['phone_number'],
                        'messages':[{'side':'incoming','text':'Hello','time':'10:00','kind':'text'}],
                        'source':'native-current','context_fingerprint':'current'}
            def translator(path):
                output=path.with_name(path.stem+'-translated.json')
                output.write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
                return {'output':str(output),'messages':1}
            service=WorkspaceService(root,native=native,translator=translator)
            service.write(service.notification_path(row['id']),row)
            with patch('workspace_service.read_snapshot',return_value=None):
                result=service.dispatch('one',{'action':'open_notification','notification_id':row['id']},'unused')
            self.assertEqual(calls,['open_notification'])
            self.assertEqual(service.conversation('one',result['conversation_id'])['context_fingerprint'],'current')
            with self.assertRaises(ValueError):service.dispatch('one',{'action':'open_notification','notification_id':row['id']},'unused')
            self.assertEqual(calls,['open_notification'])

    def test_notification_for_other_device_is_never_clicked(self):
        with tempfile.TemporaryDirectory() as root:
            row=parse_notification('MESSAGES, now, +19562154700, Hello, Button','x','one')
            called=[]
            service=WorkspaceService(root,native=lambda *args,**kwargs:called.append(args))
            service.write(service.notification_path(row['id']),row)
            with self.assertRaises(ValueError):service.dispatch('two',{'action':'open_notification','notification_id':row['id']},'unused')
            self.assertEqual(called,[])

    def test_card_count_uses_current_visible_cards_regardless_of_old_open_state(self):
        with tempfile.TemporaryDirectory() as root:
            row=parse_notification('MESSAGES, now, +19562154700, Hello, Button','x','one')
            wrong={**row,'device':'two'}
            other={**row,'app':'Signal'}
            service=WorkspaceService(root,native=lambda *args,**kwargs:{'items':[dict(row),wrong,other],'complete':True})
            first=service.notifications('one','unused')
            self.assertEqual(len(first['items']),1)
            self.assertEqual(first['items'][0]['status'],'pending')
            service.write(service.notification_path(row['id']),{**row,'status':'opened'})
            self.assertEqual(len(service.notifications('one','unused')['items']),1)
            service.native=lambda *args,**kwargs:{'items':[], 'complete':True}
            self.assertEqual(service.notifications('one','unused')['items'],[])

    def test_missing_notification_id_cannot_fall_back_to_capture(self):
        with tempfile.TemporaryDirectory() as root:
            called=[]
            service=WorkspaceService(root,native=lambda *args,**kwargs:called.append(args))
            with self.assertRaises(ValueError):service.dispatch('one',{'action':'open_notification'},'unused')
            self.assertEqual(called,[])


if __name__=='__main__':unittest.main()
