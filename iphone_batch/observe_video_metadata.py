"""Bounded, read-only localhost video telemetry; never starts capture or input."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from workspace_access import signed_opener


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--number',default='01')
    parser.add_argument('--seconds',type=int,default=90)
    args=parser.parse_args()
    if not 2<=args.seconds<=120:parser.error('seconds must be between 2 and 120')
    if not args.number.isdigit() or len(args.number)>2:parser.error('invalid device number')
    opener=signed_opener()
    state=json.load(opener.open('http://127.0.0.1:8070/api/state',timeout=8))
    device=next((row for row in state['devices'] if int(row['number'])==int(args.number)),None)
    if not device or not device.get('enabled') or not device.get('ready'):
        raise RuntimeError('Only an already enabled and ready device may be observed')
    number=device['number']
    port=device['port']
    if type(port) is not int or not 8080<=port<8100:raise ValueError('invalid viewer port')
    output=Path(__file__).resolve().parent/'.device-data'/'diagnostics'/('video-sync-'+number+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    samples=[]
    start=time.monotonic()
    while True:
        elapsed=round(time.monotonic()-start,2)
        try:
            health=json.load(opener.open(f'http://127.0.0.1:{port}/video-health',timeout=2))
            forwards=[row for row in health.get('forwards',[]) if not row['ended']]
            row={'elapsed_s':elapsed,'utc':datetime.now(timezone.utc).isoformat(),
                'server_at':health['at'],'au_age_ms':health['last_au_age_ms'],
                'input_age_ms':health.get('last_input_age_ms'),
                'forward_age_ms':round(1000*(health['at']-forwards[-1]['last_drain_at'])) if forwards else None,
                'browser':health.get('browser',[])}
        except Exception as error:
            row={'elapsed_s':elapsed,'error':type(error).__name__}
        samples.append(row)
        if len(samples)>61:samples.pop(0)
        temp=output.with_suffix('.tmp')
        temp.write_text(json.dumps({'device_number':number,'scope':'numeric telemetry only',
                                    'samples':samples},ensure_ascii=True),encoding='utf-8')
        temp.replace(output)
        if len(samples)%10==1:print(json.dumps(row,ensure_ascii=True),flush=True)
        if time.monotonic()-start>=args.seconds:break
        time.sleep(2)
    print(json.dumps({'device_number':number,'elapsed_s':round(time.monotonic()-start,2),
                      'samples':len(samples),'output':str(output)},ensure_ascii=True),flush=True)


if __name__=='__main__':main()
