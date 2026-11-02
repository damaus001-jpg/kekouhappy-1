"""Idle HID state verification and bounded recovery; never replay user input."""
import asyncio
import logging
import time


async def ensure_input_services(instance):
    """Close half-open services on errors/cancellation, before caching them."""
    from pymobiledevice3.remote.core_device.hid_service import UniversalHIDServiceService, IndigoHIDService
    async with instance._hid_lock:
        for name, factory in (('_uhs', UniversalHIDServiceService), ('_indigo', IndigoHIDService)):
            if getattr(instance, name) is None:
                service = factory(instance._rsd)
                instance._batch_connect_stage = name
                started = time.monotonic()
                try:
                    await service.connect()
                except BaseException:
                    try:
                        await asyncio.wait_for(service.close(), .4)
                    except BaseException:
                        pass
                    raise
                setattr(instance, name, service)
                logging.getLogger(__name__).info('HID connected: port=%s service=%s elapsed=%.3fs',
                    getattr(instance, '_http_port', None), name, time.monotonic() - started)
        if instance._hid_worker_task is None or instance._hid_worker_task.done():
            instance._hid_worker_task = asyncio.create_task(instance._hid_worker())


async def refresh_service_catalog(instance):
    """Read service discovery again over the same tunnel and same identity.

    No lockdown pairing, new host identity, or media restart is performed.
    Update only after confirming the exact same device; retain active streams.
    """
    from pymobiledevice3.remote.remotexpc import RemoteXPCConnection
    rsd = instance._rsd
    connection = RemoteXPCConnection(rsd.service.address, open_connection=rsd.open_connection)
    try:
        await connection.connect()
        await connection.send_device_handshake(rsd.handshake_uuid)
        peer = await connection.receive_response()
        if peer.get('Properties', {}).get('UniqueDeviceID') != rsd.udid:
            raise ConnectionError('Service discovery returned a different device')
        if not isinstance(peer.get('Services'), dict):
            raise ConnectionError('Service discovery omitted services')
        rsd.peer_info = peer
    finally:
        try:
            await asyncio.wait_for(connection.close(), .4)
        except Exception:
            pass


async def clear_input(instance):
    instance._batch_input_generation = getattr(instance, '_batch_input_generation', 0) + 1
    instance._batch_contact = None
    instance._batch_keys_down = False
    try:
        await asyncio.wait_for(instance._stop_hid(), .4)
    except Exception:
        # Timed-out teardown must not leave dead objects eligible for reuse.
        instance._uhs = None
        instance._indigo = None
        instance._kb_service_id = None


def record_input(instance, kind, data):
    instance._batch_last_input = time.monotonic()
    if kind == '_handle_touch':
        instance._batch_contact = data if data['type'] == 'contact' else None
    elif kind == '_handle_key':
        instance._batch_keys_down = bool(data.get('usages'))


async def _check_input(instance, lock, is_active):
    """Caller holds no input lock. A repair invalidates already queued input."""
    if not is_active():
        return {'ok': False, 'state': 'inactive'}
    if lock.locked():
        return {'ok': False, 'state': 'busy'}
    async with lock:
        if not is_active():
            return {'ok': False, 'state': 'inactive'}
        if (getattr(instance, '_batch_contact', None)
                or getattr(instance, '_batch_keys_down', False)
                or time.monotonic() - getattr(instance, '_batch_last_input', 0) < 2):
            return {'ok': False, 'state': 'busy'}

        stage = None
        async def probe():
            nonlocal stage
            stage = 'connect'
            await instance._ensure_hid()
            # Verify the same service used by real input. connectedServices
            # proved unreliable on the test phone and must not be a heartbeat.
            # Only reached when idle; never send a pressed key or touch event.
            stage = 'keyboard_registration'
            await instance._ensure_keyboard()
            stage = 'idle_keyboard_state'
            await instance._uhs.send_keyboard(instance._kb_service_id, [])

        try:
            for attempt in range(1):
                try:
                    await asyncio.wait_for(probe(), 4)
                    return {'ok': True, 'state': 'ready', 'recovered': bool(attempt),
                            'probe': 'idle-keyboard'}
                except Exception as error:
                    logging.getLogger(__name__).warning('Input health failed: port=%s stage=%s error=%s attempt=%s',
                        getattr(instance, '_http_port', None), stage, type(error).__name__, attempt + 1)
                    instance._batch_recovering = True
                    await clear_input(instance)
                    if not is_active():
                        return {'ok': False, 'state': 'inactive'}
            return {'ok': False, 'state': 'unavailable', 'error': '控制连接恢复失败，请点击刷新重试',
                    'stage': stage}
        finally:
            instance._batch_recovering = False


async def check_input(instance, lock, is_active):
    if getattr(instance, '_batch_catalog_refreshing', False):
        return {'ok': False, 'state': 'busy'}
    result = await _check_input(instance, lock, is_active)
    if result.get('state') != 'unavailable' or not is_active():
        return result
    refreshed = False
    if (result.get('stage') in ('connect', 'keyboard_registration') and hasattr(instance, '_rsd')
            and time.monotonic() - getattr(instance, '_batch_catalog_refresh_at', 0) >= 30):
        instance._batch_catalog_refresh_at = time.monotonic()
        instance._batch_catalog_refreshing = instance._batch_recovering = True
        try:
            # Do not hold the input lock here: switching phones remains possible.
            await asyncio.wait_for(refresh_service_catalog(instance), 3)
            refreshed = True
            logging.getLogger(__name__).warning('Input service catalog refreshed: port=%s', getattr(instance, '_http_port', None))
        except Exception as error:
            logging.getLogger(__name__).warning('Input service catalog refresh failed: port=%s error=%s',
                getattr(instance, '_http_port', None), type(error).__name__)
        finally:
            instance._batch_catalog_refreshing = instance._batch_recovering = False
    if not is_active():
        return {'ok': False, 'state': 'inactive'}
    result = await _check_input(instance, lock, is_active)
    if result.get('ok'):
        result.update(recovered=True, discovery_refreshed=refreshed)
    return result
