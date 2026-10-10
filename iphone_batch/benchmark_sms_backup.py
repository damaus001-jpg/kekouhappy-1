import asyncio,json,sys,time
from pathlib import Path
from native_workspace import ROOT
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.mobilebackup2 import Mobilebackup2Service,BackupSelection
async def main():
    device='00008030-001119CE0A93402E';started=time.monotonic();last=[0]
    ld=await create_using_usbmux(serial=device,connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    folder=ROOT/'sms-backup';folder.mkdir(exist_ok=True)
    def progress(value):
        now=time.monotonic()
        if now-last[0]>=10 or value>=100:
            last[0]=now;print(json.dumps({'progress':value,'elapsed_seconds':round(now-started,2)}),flush=True)
    try:
        async with Mobilebackup2Service(ld) as service:
            callback=service.selection_filter_callback(BackupSelection.SMS.rules())
            try:
                async with asyncio.timeout(180):
                    await service.backup(full=False,backup_directory=folder,filter_callback=callback,progress_callback=progress)
                print(json.dumps({'status':'backup_completed','seconds':round(time.monotonic()-started,2),'directory':str(folder/device)}),flush=True)
            except Exception as e:
                print(json.dumps({'status':'backup_not_completed','seconds':round(time.monotonic()-started,2),'error_type':type(e).__name__,'error':str(e)},ensure_ascii=True),flush=True)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
