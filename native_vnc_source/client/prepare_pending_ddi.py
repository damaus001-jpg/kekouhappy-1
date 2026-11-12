import asyncio
import json
import os
from pathlib import Path
import sys

DATA=Path(__file__).resolve().parent
DEVICES={'04':'00008030-001E301922D8402E','07':'00008030-001838463A78802E','14':'00008030-000315A00EB9402E',
         '17':'00008030-001259D42209802E','18':'00008030-0011504E1132402E'}


async def mount(number,udid):
    env=os.environ.copy()
    env.update(PYMOBILEDEVICE3_UDID=udid,PYTHONUTF8='1')
    process=await asyncio.create_subprocess_exec(sys.executable,str(DATA/'vnc_av_continuous.py'),
        '-v','mounter','auto-mount',env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
        creationflags=0x08000000)
    print('Mounting cached DDI for device '+number,flush=True)
    try:
        out,err=await asyncio.wait_for(process.communicate(),240)
        log=out.decode('utf-8',errors='replace')+'\n'+err.decode('utf-8',errors='replace')
        result={'number':number,'udid':udid,'ok':process.returncode==0,'exit_code':process.returncode}
    except TimeoutError:
        process.kill()
        out,err=await process.communicate()
        log=err.decode('utf-8',errors='replace')
        result={'number':number,'udid':udid,'ok':False,'error':'镜像挂载超时'}
    (DATA/'logs'/f'prepare-ddi-{number}.log').write_text(log,encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return result


async def main():
    chosen=set(sys.argv[1:] or ('04','07','14'))
    results=await asyncio.gather(*(mount(n,u) for n,u in DEVICES.items() if n in chosen))
    (DATA/'diagnostics/prepare-pending-ddi-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


asyncio.run(main())
