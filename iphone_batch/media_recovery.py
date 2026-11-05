"""Release stale on-device observation state without injecting user input."""
import asyncio
import json
from pymobiledevice3.cli.cli_common import RSDServiceProviderDep, async_command

async def reset_media_session(rsd, stop=None, session=None):
    from pymobiledevice3.remote.core_device.display_service import DisplayService
    from pymobiledevice3.remote.core_device.hid_service import touch_session
    stop = stop or DisplayService.stop_all_streams
    session = session or touch_session
    # Every stop uses the SDK's fresh-connection implementation. Reusing the
    # stream-start connection can crash the phone's display daemon.
    await stop(rsd)
    async with session(rsd):
        # Opening this context establishes media-gated HID authorization and
        # waits for surface matching. Do not send a click, key, or test swipe.
        pass
    # touch_session's teardown is best-effort. Require a final acknowledged
    # cleanup before the workbench creates its permanent video/HID session.
    await stop(rsd)
    return {'ok':True,'remote_session_reset':True,'input_events_sent':False}

async def reset_workspace_session(service_provider: RSDServiceProviderDep):
    try:
        result=await asyncio.wait_for(reset_media_session(service_provider),18)
    except Exception as error:
        raise RuntimeError('手机端媒体/触控会话清理未完成（'+type(error).__name__+'）') from None
    print(json.dumps(result))

def install_cli():
    from pymobiledevice3.cli.developer.core_device import display_cli
    if getattr(display_cli,'_workspace_reset_installed',False):return
    display_cli.command('reset-workspace-session')(async_command(reset_workspace_session))
    display_cli._workspace_reset_installed=True
