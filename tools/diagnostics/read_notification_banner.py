"""Time read-only persistent notification banner reads, with no UI activation."""
import asyncio,json,struct,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'iphone_batch'))
from native_workspace import ROOT
from pairing_patch import open_paired_usb
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
from pymobiledevice3.services.os_trace import OsTraceService
from pymobiledevice3.services.accessibilityaudit import deserialize_object


async def read(service,springboard):
    started=time.perf_counter();stages={}
    await service._ensure_ready()
    await service.set_app_monitoring_enabled(False)
    await service.set_monitored_event_type()
    original=deserialize_object(await asyncio.wait_for(service._invoke('deviceFetchSpecialElement:',0),1.5))
    token=getattr(original,'identifier',None)
    original_pid=struct.unpack('<I',token[:4])[0] if token and len(token)>=4 else 0
    try:
        await service._invoke('deviceSetAuditTargetPid:',springboard,expects_reply=False)
        banner=deserialize_object(await asyncio.wait_for(service._invoke('deviceFetchSpecialElement:',1),1.5))
        stages['target_and_fetch_seconds']=round(time.perf_counter()-started,4)
        if (getattr(banner,'_fields',{}).get('AccessibilityIdentifier_v1')!='NotificationShortLookView'):
            return {'found':False,'seconds':round(time.perf_counter()-started,4)}
        token=banner.identifier
        while not service._event_queue.empty():service._event_queue.get_nowait()
        await service._invoke('deviceInspectorFocusOnElement:',service._serialize_element(token),expects_reply=False)
        label=await asyncio.wait_for(service.element_attribute(token,'Label'),1.5)
        if not isinstance(label,str) or not label.strip():
            await asyncio.sleep(.05)
            label=await asyncio.wait_for(service.element_attribute(token,'Label'),1.5)
        if not isinstance(label,str) or not label.strip():raise RuntimeError('Banner Label not readable')
        stages['read_seconds']=round(time.perf_counter()-started,4)
        result={'found':True,'caption':label,**stages}
    finally:
        await service._invoke('deviceSetAuditTargetPid:',original_pid,expects_reply=False)
        await service.set_app_monitoring_enabled(False)
    result['including_restore_seconds']=round(time.perf_counter()-started,4)
    return result


async def main(device):
    all_started=time.perf_counter();times=[]
    for session in range(2):
        started=time.perf_counter()
        lockdown=await open_paired_usb(device,ROOT)
        try:
            async with OsTraceService(lockdown) as trace:processes=(await trace.get_pid_list())['Payload']
            springboard=next(int(pid) for pid,value in processes.items() if value.get('ProcessName')=='SpringBoard')
            async with AccessibilityAudit(lockdown) as service:
                connected=time.perf_counter()
                result=await read(service,springboard)
                result.update(mode='new_connection',session=session+1,
                              connection_seconds=round(connected-started,4),
                              total_seconds=round(time.perf_counter()-started,4))
                times.append(result);print(json.dumps(result,ensure_ascii=True),flush=True)
                if session==1:
                    for repeat in range(3):
                        await asyncio.sleep(.15)
                        result=await read(service,springboard)
                        result.update(mode='reuse_connection',repeat=repeat+1)
                        times.append(result);print(json.dumps(result,ensure_ascii=True),flush=True)
        finally:await lockdown.close()
    (ROOT/'diagnostics').mkdir(parents=True,exist_ok=True)
    (ROOT/'diagnostics/notification-banner-timings.json').write_text(json.dumps(times,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'total_test_seconds':round(time.perf_counter()-all_started,3)}),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Read-only timing of a visible persistent Messages banner; never activates UI.')
    parser.add_argument('--device',required=True,help='Exact USB UDID of the intended device')
    args=parser.parse_args()
    asyncio.run(main(args.device))
