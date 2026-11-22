import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
import struct
import threading
import unittest
from unittest.mock import AsyncMock, patch

from message_banner import observe, parse_banner
from notification_monitor import NotificationMonitor


class BannerTests(unittest.IsolatedAsyncioTestCase):
    async def check_read(self, fail=False):
        calls=[]
        root=SimpleNamespace(identifier=struct.pack('<I', 99)+b'root')
        banner=SimpleNamespace(identifier=b'live-banner',_fields={'AccessibilityIdentifier_v1':'NotificationShortLookView'})
        async def invoke(name, *args, **kwargs):
            calls.append((name,args))
            if name=='deviceFetchSpecialElement:':return root if args[0]==0 else banner
        service=SimpleNamespace(_ensure_ready=AsyncMock(),set_app_monitoring_enabled=AsyncMock(),
            set_monitored_event_type=AsyncMock(),_invoke=invoke,_serialize_element=lambda token:token,
            element_attribute=AsyncMock(side_effect=RuntimeError('unreadable') if fail else None,
                                       return_value='MESSAGES, now, +1 (202) 555-0123, Hi, there'))
        trace=SimpleNamespace(get_pid_list=AsyncMock(return_value={'Payload':{'42':{'ProcessName':'SpringBoard'}}}))
        context=AsyncMock();context.__aenter__.return_value=trace
        with patch('pymobiledevice3.services.os_trace.OsTraceService',return_value=context), patch(
                'pymobiledevice3.services.accessibilityaudit.deserialize_object',side_effect=lambda value:value):
            if fail:
                with self.assertRaises(RuntimeError):await observe(service,object(),'device')
                result=None
            else:result=await observe(service,object(),'device')
        self.assertEqual(calls[-1],('deviceSetAuditTargetPid:',(99,)))
        self.assertTrue(all(name in {'deviceFetchSpecialElement:','deviceSetAuditTargetPid:',
                                    'deviceInspectorFocusOnElement:'} for name,_ in calls))
        return result

    async def test_observation_never_activates_or_walks_and_restores_target(self):
        result=await self.check_read()
        self.assertEqual(result['items'][0]['preview'],'Hi, there')
        self.assertFalse(result['items'][0]['clickable'])
        self.assertFalse(result['complete'])

    async def test_read_error_also_restores_target(self):
        await self.check_read(fail=True)

    async def test_ignore_other_apps_and_deduplicate_changing_time_label(self):
        self.assertIsNone(parse_banner('MAIL, now, someone, hello',b'live','device'))
        a=parse_banner('MESSAGES, now, +12025550123, Hi',b'live','device')
        b=parse_banner('MESSAGES, 1 minute ago, +12025550123, Hi',b'live','device')
        self.assertEqual(a['id'],b['id'])


class BannerRetentionTests(unittest.TestCase):
    def test_disappeared_banner_is_not_acknowledged_as_read(self):
        monitor=NotificationMonitor([{'udid':'d'}],threading.RLock(),lambda _:nullcontext(),
            lambda *_:None,lambda _:True,threading.Event())
        monitor.record('d',{'source':'banner','items':[{'id':'one','sender':'a'}]})
        monitor.record('d',{'source':'banner','items':[]})
        self.assertEqual(monitor.snapshot('d')['card_count'],1)
        self.assertFalse(monitor.snapshot('d')['complete'])
        monitor.acknowledge('d','one')
        self.assertEqual(monitor.snapshot('d')['card_count'],0)


if __name__=='__main__':unittest.main()
