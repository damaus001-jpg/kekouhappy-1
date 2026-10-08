"""Read-only native hit testing with app target and raw event capture."""
import asyncio,json,sys
from pathlib import Path
from bpylist2 import archiver
from pymobiledevice3 import common
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit
ROOT=Path(__file__).resolve().parent/'.device-data';common._HOMEFOLDER=ROOT
class NativePoint:
    def __init__(self,x,y):self.x=x;self.y=y
    def encode_archive(self,a):
        a._archive_obj['NS.special']=1;a.encode('NS.pointval','{'+str(self.x)+', '+str(self.y)+'}')
archiver.ARCHIVE_CLASS_MAP[NativePoint]='NSValue'
def safe(v):
    if isinstance(v,bytes):return {'hex':v.hex()}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [safe(x) for x in v]
    return v if v is None or isinstance(v,(str,int,float,bool)) else repr(v)
async def events(s,timeout=.6):
    out=[]
    while True:
        try:
            name,args=await asyncio.wait_for(s._event_queue.get(),timeout)
            out.append({'event':name,'args':safe(args)})
        except asyncio.TimeoutError:break
    return out
async def main():
    ld=await create_using_usbmux(serial='00008030-001C481A3C32802E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    out=[]
    try:
        async with AccessibilityAudit(ld) as s:
            it=s.iter_elements();i=None
            try:
                async with asyncio.timeout(15):
                    async for item in it:
                        if ', Unread, ' in (item.caption or ''):i=item;break
            finally:await it.aclose()
            if i is None:return
            pid=int.from_bytes(i.element.identifier[:4],'little')
            print(json.dumps({'native_element_pid':pid,'caption':i.caption}),flush=True)
            for sel,args in [('deviceSetAuditTargetPid:',(pid,)),('deviceSetAuditUIPid:',(pid,)),('deviceInspectorEnable:',(True,)),('deviceDidGetTargeted',()),('deviceInspectorAutodrillIntoElements:',(True,))]:
                try:print(json.dumps({'setup':sel,'reply':safe(await s._invoke(sel,*args))}),flush=True)
                except Exception as e:print(json.dumps({'setup':sel,'error':str(e)}),flush=True)
            await s.set_app_monitoring_enabled(True)
            for typ in (0,1,2):
                await s.set_monitored_event_type(typ);await events(s,.1)
                for x,y in ((.5,.25),(.5,.4)):
                    try:
                        r=await s._invoke('deviceFetchElementAtNormalizedDeviceCoordinate:',NativePoint(x,y))
                        data={'type':typ,'point':[x,y],'reply':safe(r),'events':await events(s)}
                    except Exception as e:data={'type':typ,'error':str(e)}
                    out.append(data);print(json.dumps(data),flush=True)
            await s.set_monitored_event_type();await s.set_app_monitoring_enabled(False)
    finally:
        (ROOT/'diagnostics'/'native-targeted-hit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
        await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
