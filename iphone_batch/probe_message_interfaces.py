"""Read-only checks; never send messages or modify device settings."""
import asyncio
import json
import sys
from native_workspace import ROOT
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.file_relay import FileRelayService
from pymobiledevice3.services.house_arrest import HouseArrestService
from pymobiledevice3.services.notification_proxy import NotificationProxyService


async def main():
    ld = await create_using_usbmux(
        serial='00008030-001119CE0A93402E', connection_type='USB',
        usbmux_address='127.0.0.1:27015',
        pairing_records_cache_folder=ROOT, autopair=False)
    results = {}
    try:
        results['ios_version'] = await ld.get_value(key='ProductVersion')
        for name, factory in [
            ('file_relay', lambda: FileRelayService(ld)),
            ('notification_proxy', lambda: NotificationProxyService(ld)),
        ]:
            try:
                async with asyncio.timeout(10):
                    async with factory():
                        results[name] = {'service_available': True}
            except Exception as exc:
                results[name] = {'error': type(exc).__name__, 'detail': str(exc)}
        try:
            async with asyncio.timeout(10):
                async with await HouseArrestService.create(ld, 'com.apple.MobileSMS'):
                    results['messages_container'] = {'container_available': True}
        except Exception as exc:
            results['messages_container'] = {'error': type(exc).__name__, 'detail': str(exc)}
    finally:
        await ld.close()
    destination = ROOT / 'diagnostics' / 'message-interface-probe.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
