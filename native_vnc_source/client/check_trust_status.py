import asyncio
from pathlib import Path
import sys

DATA = Path(__file__).resolve().parent
sys.path.insert(0, str(DATA.parent))
from pairing_patch import install
install()

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.usbmux import list_devices


async def check(device):
    try:
        client = await create_using_usbmux(serial=device.serial, autopair=False,
            connection_type='USB', pairing_records_cache_folder=DATA,
            usbmux_address='127.0.0.1:27015')
        try:
            state = "TRUSTED" if client.paired else "NO_VALID_TRUST"
            print(f"{device.serial}\t{state}")
        finally:
            await client.close()
    except Exception as exc:
        print(f"{device.serial}\tCHECK_FAILED\t{type(exc).__name__}: {exc}")


async def main():
    devices = await list_devices()
    print(f"USB devices: {len(devices)}")
    await asyncio.gather(*(check(device) for device in devices))


asyncio.run(main())
