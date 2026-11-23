"""Read the Messages icon's SpringBoard AX label from the Dock upward only."""
import asyncio
import re
from datetime import datetime, timezone

from pymobiledevice3.services.accessibilityaudit import Direction, deserialize_object


MESSAGES = re.compile(r'^(?:Messages|信息|短信)(?:,|$)', re.IGNORECASE)
UNREAD = re.compile(r'(\d+)\s+unread\s+messages?\b', re.IGNORECASE)
MAX_STEPS = 6


async def observe(service, lockdown, device):
    from pymobiledevice3.services.os_trace import OsTraceService
    async with OsTraceService(lockdown) as trace:
        payload=(await asyncio.wait_for(trace.get_pid_list(),3))['Payload']
    pid=next((int(key) for key,row in payload.items() if row.get('ProcessName')=='SpringBoard'),None)
    if pid is None:raise ValueError('无法定位主屏幕无障碍元素')
    await service._ensure_ready()
    original=deserialize_object(await asyncio.wait_for(service._invoke('deviceFetchSpecialElement:',0),2))
    token=getattr(original,'identifier',None)
    if not isinstance(token,bytes) or len(token)<4:
        raise ValueError('无法核验元素读取恢复目标')
    original_pid=int.from_bytes(token[:4],'little')
    observed=[]
    try:
        await service._invoke('deviceSetAuditTargetPid:',pid,expects_reply=False)
        # Read-only AX focus movement; suppress the on-screen inspector overlay.
        if hasattr(service, 'set_show_visuals'):
            await service.set_show_visuals(False)
        await service.set_app_monitoring_enabled(True)
        await service.set_monitored_event_type()
        await asyncio.sleep(.08)
        while not service._event_queue.empty():service._event_queue.get_nowait()
        for direction in (Direction.Last,*([Direction.Previous]*(MAX_STEPS-1))):
            while not service._event_queue.empty():service._event_queue.get_nowait()
            await service.move_focus(direction)
            deadline=asyncio.get_running_loop().time()+1.25
            item=None
            while asyncio.get_running_loop().time()<deadline:
                try:
                    name,args=await asyncio.wait_for(service._event_queue.get(),
                        max(.02,deadline-asyncio.get_running_loop().time()))
                except asyncio.TimeoutError:break
                if name!='hostInspectorCurrentElementChanged:':continue
                data=deserialize_object(service._extract_event_payload(args))
                rows=data if isinstance(data,list) else [data]
                if rows:item=rows[0];break
            if item is None:break
            caption=(getattr(item,'caption',None) or '').strip()
            observed.append(caption)
            if not MESSAGES.match(caption):continue
            match=UNREAD.search(caption)
            return {'device':device,'source':'app_icon_badge','state':'read',
                    'unread_count':int(match.group(1)) if match else 0,
                    'caption':caption,'steps':len(observed),
                    'observed_at':datetime.now(timezone.utc).isoformat()}
        raise ValueError('从主屏幕底部有限读取中未找到信息图标：'+', '.join(observed[-3:]))
    finally:
        await service.set_app_monitoring_enabled(False)
        await service._invoke('deviceSetAuditTargetPid:',original_pid,expects_reply=False)
