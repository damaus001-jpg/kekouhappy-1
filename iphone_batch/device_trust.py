"""Trust repair for explicit page actions; background viewer retries never pair."""
import argparse
import asyncio
import json
from pathlib import Path
import uuid

async def repair(udid, cache, factory=None):
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.exceptions import MuxException
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    factory = factory or create_using_usbmux
    client = await factory(serial=udid, connection_type='USB', autopair=False,
                           pairing_records_cache_folder=cache, usbmux_address='127.0.0.1:27015')
    try:
        if client.paired:
            return {'ok': True, 'message': '已有信任连接验证通过'}
        record = client.pair_record or {}
        key = record.get('HostPrivateKey')
        private_key = load_pem_private_key(key, password=None) if key else None
        previous = cache / (udid + '.plist')
        if previous.exists():
            backup = cache / 'trust-backups' / (udid + '-' + uuid.uuid4().hex + '.plist')
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(previous.read_bytes())
        try:
            await client.pair(timeout=60, private_key=private_key)
        except MuxException:
            # Pair() saves the local identity before writing Apple's usbmux
            # cache. That second write can fail after phone-side trust already
            # succeeded. Accept it only when the new identity starts a session.
            if not await client.validate_pairing():
                raise
            return {'ok': True, 'message': '信任连接已建立（本地配对身份已验证）',
                    'system_record_saved': False}
        if not await client.validate_pairing():
            raise ValueError('手机尚未接受配对身份，请解锁并完成信任确认')
        return {'ok': True, 'message': '信任连接已建立'}
    finally:
        await client.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True)
    args = parser.parse_args()
    from pairing_patch import install
    install()
    try:
        result = asyncio.run(asyncio.wait_for(repair(args.device, Path(__file__).parent / '.device-data'), 80))
    except Exception as error:
        messages = {'UserDeniedPairingError': '手机已拒绝信任，请重新点击并在手机上允许',
                    'PairingDialogResponsePendingError': '等待信任确认超时，请解锁手机、点击信任并输入密码',
                    'PasswordRequiredError': '请先解锁手机并输入密码，再重试',
                    'TimeoutError': '建立信任超时，请保持手机解锁及 USB 连接后重试'}
        result = {'ok': False, 'error': messages.get(type(error).__name__,
                  str(error) if isinstance(error, ValueError) else '建立信任失败（' + type(error).__name__ + '），请检查手机连接后重试')}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 1

if __name__ == '__main__':
    raise SystemExit(main())
