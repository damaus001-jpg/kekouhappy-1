"""Explicitly retry only the six currently unvalidated phone identities."""
import asyncio
import json
import os
from pathlib import Path
import sys

DATA = Path(__file__).resolve().parent
DEVICES = {
    '06':'00008030-00040DD23E42402E', '09':'00008030-00044C540285402E',
    '13':'00008030-000518813442402E', '15':'00008030-000A046E2E9B402E',
    '17':'00008030-001259D42209802E', '18':'00008030-0011504E1132402E',
}


async def repair(number, udid):
    env = os.environ.copy()
    env['PYTHONUTF8']='1'
    process = await asyncio.create_subprocess_exec(sys.executable, str(DATA.parent/'device_trust.py'),
        '--device', udid, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env, creationflags=0x08000000)
    print(f'Device {number}: pairing requested; unlock and accept trust if prompted', flush=True)
    try:
        out, err = await asyncio.wait_for(process.communicate(),95)
        try:
            result = json.loads(out.decode('utf-8').strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {'ok':False, 'error':'配对未返回有效结果'}
    except TimeoutError:
        process.kill()
        await process.communicate()
        result = {'ok':False, 'error':'等待信任确认超时'}
    result.update(number=number,udid=udid)
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return result


async def main():
    results = await asyncio.gather(*(repair(n,u) for n,u in DEVICES.items()))
    (DATA/'diagnostics/trust-reestablish-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


asyncio.run(main())
