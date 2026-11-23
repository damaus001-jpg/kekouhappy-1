"""Durable scheduler for explicitly submitted bulk SMS tasks.

The scheduler never retries a unit after its sender has persisted send_requested:
the phone may have accepted the message even when the host did not get a receipt.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import json
import random
import re
import threading
import time
import uuid
from pathlib import Path

from send_policy import validate_send_text


TASK_ID = re.compile(r"^[a-f0-9]{32}$")
PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")
TERMINAL = {"completed", "completed_with_errors", "failed", "uncertain", "cancelled"}
MAX_IN_FLIGHT = 3


class SmsTaskWait(RuntimeError):
    """The task is valid but the assigned device is temporarily unavailable."""


def _iso_now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def _epoch(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.timestamp() if parsed.tzinfo is not None else 0
    except (TypeError, ValueError):
        return 0


def _scheduled_epoch(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("定时开始时间无效")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("定时开始时间无效") from None
    if dt.tzinfo is None:
        raise ValueError("定时开始时间必须包含时区")
    epoch = dt.timestamp()
    if epoch <= time.time():
        raise ValueError("请选择未来的定时开始时间")
    return epoch


class SmsTaskRunner:
    def __init__(self, root, device_lookup, deliver, stopping, *, max_workers=20, device_activity=None):
        self.root = Path(root) / "workspace" / "sms-tasks"
        self.root.mkdir(parents=True, exist_ok=True)
        self.device_lookup = device_lookup
        self.deliver = deliver
        self.stopping = stopping
        self.device_activity = device_activity or (lambda device, busy: None)
        self.max_workers = max(1, min(int(max_workers), MAX_IN_FLIGHT))
        self.slots = threading.BoundedSemaphore(self.max_workers)
        self.lock = threading.RLock()
        self.jobs = {}
        self.active_id = None
        self.halt = threading.Event()
        self._load()

    def _path(self, identifier):
        if not isinstance(identifier, str) or not TASK_ID.fullmatch(identifier):
            raise ValueError("短信任务编号无效")
        return self.root / (identifier + ".json")

    def _unit_path(self, identifier, index):
        if type(index) is not int or not 0 <= index < 10000:
            raise ValueError("短信任务号码序号无效")
        return self.root / identifier / "items" / (f"{index:05d}.json")

    def _write_unit(self, identifier, item, *, status="ready", error=None):
        path = self._unit_path(identifier, item["index"])
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {"version": 1, "task_id": identifier, "index": item["index"],
                 "device": item["device"], "number": item["number"], "text": item["text"],
                 "status": status, "updated_at": _iso_now(), "error": error}
        value['next_delay_seconds'] = item.get('next_delay_seconds')
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return path

    @staticmethod
    def write_unit_status(path, value, status, *, error=None, sent_at=None):
        value.update(status=status, updated_at=_iso_now(), error=error)
        if sent_at:
            value["sent_at"] = sent_at
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
        return value

    def unit_path(self, identifier, index):
        return self._unit_path(identifier, index)

    @staticmethod
    def _read_unit(path):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, job):
        job["updated_at"] = _iso_now()
        path = self._path(job["id"])
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    def _load(self):
        for path in self.root.glob("[0-9a-f]" * 32 + ".json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(job, dict) or job.get("id") != path.stem:
                    continue
                job['concurrency'] = min(MAX_IN_FLIGHT, job.get('concurrency', 1))
                if job.get("status") == "running":
                    for item in job.get("items", []):
                        unit = self._read_unit(self._unit_path(job["id"], item.get("index")))
                        if unit.get("status") == "sent_verified":
                            item["status"] = "sent_verified"
                            item["last_send_at"] = unit.get("sent_at")
                            continue
                        if unit.get("status") == "send_requested" or item.get("status") in ("send_requested", "uncertain"):
                            item["status"] = "uncertain"
                            item["send_requested"] = True
                            item["error"] = "工作台在发送期间关闭；请核对手机，系统不会自动重发"
                        elif item.get("status") == "sending":
                            item["status"] = "queued"
                            item["error"] = None
                    uncertain = any(item.get("status") == "uncertain" for item in job.get("items", []))
                    job["status"] = "uncertain" if uncertain else "queued"
                    job["error"] = ("存在发送结果不明的号码，需人工核对；未自动重试"
                                    if uncertain else None)
                    if job.get('navigation_failed') and not uncertain:
                        job['status'] = 'failed'
                        job['error'] = '已发送，返回短信列表失败；任务已停止，不会重发'
                    self._save(job)
                self.jobs[job["id"]] = job
            except (OSError, ValueError, TypeError):
                continue

    def create(self, body):
        if not isinstance(body, dict):
            raise ValueError("短信任务格式无效")
        if set(body) - {"name", "numbers", "texts", "devices", "concurrency", "startMode", "startAt", "timezone"}:
            raise ValueError("短信任务包含不支持的字段")
        name = body.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise ValueError("任务名称须为 1–80 个字符")
        numbers = body.get("numbers")
        if not isinstance(numbers, list) or not numbers or len(numbers) > 10000:
            raise ValueError("号码数量须为 1–10000")
        normalized = []
        seen = set()
        for number in numbers:
            if not isinstance(number, str) or not PHONE.fullmatch(number):
                raise ValueError("号码必须是已规范化的国际号码")
            if number in seen:
                raise ValueError("号码列表存在重复号码，请重新导入")
            seen.add(number)
            normalized.append(number)
        texts = body.get("texts")
        if not isinstance(texts, list) or not texts or len(texts) > 1000:
            raise ValueError("短信正文至少一条，最多 1000 条")
        texts = [validate_send_text(text) for text in texts]
        if sum(len(text.encode("utf-8")) for text in texts) > 2 * 1024 * 1024:
            raise ValueError("短信正文总量超过 2 MB")
        devices = body.get("devices")
        if not isinstance(devices, dict) or not devices or len(devices) > 20:
            raise ValueError("请至少选择一台、最多 20 台设备")
        selected = []
        current = self.device_lookup()
        for udid, interval in devices.items():
            if not isinstance(udid, str) or udid not in current:
                raise ValueError("所选设备已不存在，请刷新后重试")
            if not isinstance(interval, dict) or set(interval) - {"min", "max"}:
                raise ValueError("设备发送间隔无效")
            low, high = interval.get("min"), interval.get("max")
            if (type(low) is not int or type(high) is not int or low < 1 or high < low or high > 86400):
                raise ValueError("设备发送间隔须为 1–86400 秒，最大值不能小于最小值")
            selected.append({"udid": udid, "min": low, "max": high})
        if len({row["udid"] for row in selected}) != len(selected):
            raise ValueError("设备列表存在重复项")
        concurrency = body.get("concurrency")
        if type(concurrency) is not int or not 1 <= concurrency <= min(MAX_IN_FLIGHT, len(selected)):
            raise ValueError("在途自动发送同时最多 3 台，且不能超过所选设备数")
        mode = body.get("startMode")
        if mode not in ("immediate", "scheduled"):
            raise ValueError("执行时间模式无效")
        start_at = None
        due_at = time.time()
        if mode == "scheduled":
            start_at = body.get("startAt")
            due_at = _scheduled_epoch(start_at)
        elif body.get("startAt") is not None:
            raise ValueError("立即发送任务不应包含定时时间")
        zone = body.get("timezone")
        if zone is not None and (not isinstance(zone, str) or len(zone) > 100):
            raise ValueError("本地时区标识无效")

        identifier = uuid.uuid4().hex
        items = []
        for index, number in enumerate(normalized):
            owner = selected[index % len(selected)]
            items.append({"index": index, "number": number, "text": texts[index % len(texts)],
                          "task_id": identifier, "device": owner["udid"], "status": "queued", "attempts": 0,
                          "last_send_at": None, "error": None})
        now = _iso_now()
        job = {"version": 1, "id": identifier, "name": name.strip(), "created_at": now,
               "updated_at": now, "start_mode": mode, "start_at": start_at, "due_at": due_at,
               "timezone": zone,
               "concurrency": concurrency, "devices": selected, "texts": texts,
               "status": "queued" if mode == "immediate" else "scheduled",
               "items": items, "cancel_requested": False, "error": None}
        with self.lock:
            self._save(job)
            self.jobs[identifier] = job
        return self.snapshot(identifier)

    def snapshot(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job:
                raise ValueError("短信任务不存在")
            return self._public(job)

    def list(self, limit=20):
        with self.lock:
            jobs = sorted(self.jobs.values(), key=lambda row: row.get("created_at", ""), reverse=True)
            return [self._public(job) for job in jobs[:max(1, min(int(limit), 100))]]

    def daily_summary(self, day=None):
        with self.lock:
            jobs=[job for job in self.jobs.values() if
                  (job.get('created_at','')[:10] == day if day else True)]
            rows=[]
            for job in jobs:
                items=job.get('items',[])
                sent=[item for item in items if item.get('status')=='sent_verified']
                failed=[item for item in items if item.get('status') in ('failed','uncertain') or item.get('phase')=='return_failed']
                detailed=sum(bool(item.get('had_existing_conversation')) for item in sent)
                rows.append({'id':job['id'],'name':job.get('name',''),'date':job.get('created_at','')[:10],
                    'status':job.get('status'),'created_at':job.get('created_at'),
                    'due_at':job.get('due_at'),'total':len(items),'sent':len(sent),'failed':len(failed),
                    'detailed':detailed,'new':len(sent)-detailed,
                    'failed_numbers':[{'number':i.get('number'),'device':i.get('device'),'error':i.get('error')} for i in failed]})
        priority={'running':0,'waiting_for_device':0,'queued':0,'scheduled':1}
        rows.sort(key=lambda row:(priority.get(row['status'],2),-(_epoch(row.get('due_at')) if row['status']=='scheduled' else _epoch(row.get('created_at')))))
        return rows

    @staticmethod
    def _public(job):
        counts = {}
        for item in job.get("items", []):
            counts[item.get("status", "unknown")] = counts.get(item.get("status", "unknown"), 0) + 1
        device_rows=[]
        for device in job.get('devices', []):
            assigned=[item for item in job.get('items', []) if item.get('device')==device.get('udid')]
            device_rows.append({'udid':device['udid'], 'total':len(assigned),
                'sent':sum(item.get('status')=='sent_verified' for item in assigned),
                'remaining':sum(item.get('status') not in ('sent_verified','cancelled') for item in assigned),
                'failed':sum(item.get('status') in ('failed','uncertain') or item.get('phase')=='return_failed' for item in assigned),
                'failure':next((item.get('error') for item in assigned if item.get('error')),None)})
        return {key: value for key, value in job.items() if key not in ("texts", "items")} | {
            "total": len(job.get("items", [])), "counts": counts, "device_progress":device_rows,
            'in_flight': len({item['device'] for item in job.get('items', []) if item.get('status') == 'sending'}),
            'waiting_next_compose': len({item['device'] for item in job.get('items', [])
                if item.get('status') == 'queued' and item.get('phase') == 'waiting_next_compose'}),
            "items": [{key: item.get(key) for key in
                       ("index", "number", "device", "status", "phase", "last_send_at", "next_compose_at", "error")}
                      for item in job.get("items", [])]}

    def cancel(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job:
                raise ValueError("短信任务不存在")
            if job.get("status") in TERMINAL:
                return self._public(job)
            job["cancel_requested"] = True
            if job.get("status") != "running":
                job["status"] = "cancelled"
                for item in job.get("items", []):
                    if item.get("status") == "queued":
                        item["status"] = "cancelled"
            self._save(job)
            self.halt.set()
            return self._public(job)

    def resume_unsent(self, identifier):
        """Explicit recovery only; preserve receipts and reject any uncertain send."""
        with self.lock:
            original = self.jobs.get(identifier)
            if not original or original.get('status') != 'failed':
                raise ValueError('只能继续已停止的失败任务')
            if self.active_id is not None:
                raise ValueError('请等待当前发送任务停止后再继续')
            job = deepcopy(original)
            for item in job['items']:
                path = self._unit_path(identifier, item['index'])
                unit = self._read_unit(path)
                if path.exists() and (not unit or any(unit.get(key) != item.get(key)
                        for key in ('task_id', 'index', 'device', 'number', 'text'))):
                    raise ValueError('任务发送记录不匹配，不能继续')
                if unit.get('status') == 'sent_verified':
                    item.update(status='sent_verified', phase='finished',
                                last_send_at=unit.get('sent_at'), error=None)
                    continue
                if (unit.get('send_requested_at') or unit.get('status') == 'send_requested'
                        or item.get('status') in ('sent_verified', 'sending', 'uncertain', 'send_requested')):
                    raise ValueError('存在发送结果未确认的号码，禁止自动重发')
                if item.get('status') not in ('failed', 'queued') or unit.get('status') not in (None, 'ready'):
                    raise ValueError('任务中存在不能自动继续的号码')
                item.update(status='queued', phase='waiting_slot', error=None)
            job.update(status='queued', due_at=time.time(), retry_at=0,
                       cancel_requested=False, navigation_failed=False, error=None)
            self._save(job)
            self.jobs[identifier] = job
            return self._public(job)

    def run(self):
        while not self.stopping.wait(.5):
            with self.lock:
                if self.active_id is not None:
                    continue
                due = next((job for job in sorted(self.jobs.values(), key=lambda row: row.get("created_at", ""))
                            if job.get("status") in ("queued", "scheduled", "waiting_for_device") and
                            job.get("due_at", 0) <= time.time() and job.get("retry_at", 0) <= time.time()), None)
                if due is None:
                    continue
                self.active_id = due["id"]
                self.halt.clear()
                due["status"] = "running"
                self._save(due)
            try:
                self._run_job(due["id"])
            finally:
                with self.lock:
                    self.active_id = None

    def _get(self, identifier):
        with self.lock:
            return self.jobs[identifier]

    def _update_item(self, identifier, index, **changes):
        with self.lock:
            job = self.jobs[identifier]
            item = job["items"][index]
            item.update(changes)
            self._save(job)

    def _wait_interval(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.halt.is_set() and not self.stopping.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            self.halt.wait(min(.5, remaining))
        return False

    def _run_device(self, identifier, device):
        self._run_device_queue(identifier, device)

    def _next_compose_at(self, identifier, device):
        """Persisted send-action clock; receipt and return navigation consume the gap."""
        job = self._get(identifier)
        interval = next(row for row in job['devices'] if row['udid'] == device)
        # One device's assigned queue is sequential. Only its latest known send
        # can constrain the next compose; avoid rereading every old unit file.
        for item in reversed(job['items']):
            if item['device'] != device or item.get('status') != 'sent_verified':
                continue
            unit = self._read_unit(self._unit_path(identifier, item['index']))
            anchor = _epoch(unit.get('send_requested_at')) or _epoch(unit.get('sent_at')) or _epoch(item.get('last_send_at'))
            delay = unit.get('next_delay_seconds') or item.get('next_delay_seconds') or interval['max']
            return max(item.get('next_compose_at', 0), anchor + delay if anchor else 0)
        return 0

    def _run_device_queue(self, identifier, device):
        job = self._get(identifier)
        interval = next(row for row in job["devices"] if row["udid"] == device)
        indices = [item["index"] for item in job["items"] if item["device"] == device]
        for index in indices:
            if self.stopping.is_set() or self.halt.is_set():
                return
            job = self._get(identifier)
            if job.get("cancel_requested"):
                return
            item = job["items"][index]
            if item.get("status") != "queued":
                if item.get("status") in ("uncertain", "failed"):
                    self.halt.set()
                continue
            due = self._next_compose_at(identifier, device)
            if due > time.time():
                self._update_item(identifier, index, phase='waiting_next_compose', next_compose_at=due)
                if not self._wait_interval(due - time.time()):
                    return
            self._update_item(identifier, index, phase='waiting_slot')
            while not self.slots.acquire(timeout=.2):
                if self.stopping.is_set() or self.halt.is_set():
                    return
            if self.stopping.is_set() or self.halt.is_set():
                self.slots.release()
                return
            try:
                self.device_activity(device, True)
                delay = random.randint(interval['min'], interval['max'])
                self._update_item(identifier, index, status='sending', attempts=1, error=None,
                                  next_delay_seconds=delay, phase='in_flight')
                unit_path = self._write_unit(identifier, self._get(identifier)['items'][index])
                try:
                    result = self.deliver(device, self._get(identifier),
                                          self._get(identifier)['items'][index], unit_path)
                    unit = self._read_unit(unit_path)
                    if result != 'sent_verified' or unit.get('status') != 'sent_verified':
                        raise RuntimeError('手机未确认发送结果')
                except SmsTaskWait as exc:
                    self._update_item(identifier, index, status='queued', phase='waiting_device', error=None)
                    with self.lock:
                        job = self.jobs[identifier]
                        job.update(status='waiting_for_device', retry_at=time.time() + 5, error=str(exc)[:300])
                        self._save(job)
                    self.halt.set()
                    return
                except Exception as exc:
                    unit = self._read_unit(unit_path)
                    if unit.get('status') == 'sent_verified':
                        self._update_item(identifier, index, status='sent_verified', phase='return_failed',
                            last_send_at=unit.get('sent_at'), error='已发送，返回短信列表失败：' + str(exc)[:300])
                        with self.lock:
                            job = self.jobs[identifier]
                            job['navigation_failed'] = True
                            job['error'] = '已发送，返回短信列表失败；任务已停止，不会重发'
                            self._save(job)
                        self.halt.set()
                        return
                    requested = unit.get('status') == 'send_requested'
                    self._update_item(identifier, index, status='uncertain' if requested else 'failed',
                        phase='uncertain' if requested else 'failed',
                        error='发送结果不明，请核对手机；禁止自动重发' if requested else str(exc)[:500])
                    self.halt.set()
                    return
                sent_at = unit.get('sent_at') or _iso_now()
                anchor = _epoch(unit.get('send_requested_at')) or _epoch(sent_at)
                self._update_item(identifier, index, status='sent_verified', last_send_at=sent_at,
                    send_requested=False, phase='finished', error=None, next_compose_at=anchor + delay)
            finally:
                try:
                    self.device_activity(device, False)
                finally:
                    self.slots.release()

    def _run_job(self, identifier):
        job = self._get(identifier)
        devices = list(dict.fromkeys(item["device"] for item in job["items"]))
        errors = []
        self.slots = threading.BoundedSemaphore(min(job['concurrency'], self.max_workers, MAX_IN_FLIGHT))
        # Waiting out a device's interval must not reserve an in-flight slot.
        with ThreadPoolExecutor(max_workers=len(devices),
                                thread_name_prefix="sms-device") as pool:
            futures = [pool.submit(self._run_device, identifier, device) for device in devices]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    errors.append(str(exc)[:500])
                    self.halt.set()
        with self.lock:
            job = self.jobs[identifier]
            states = {item.get("status") for item in job["items"]}
            if "uncertain" in states:
                job["status"] = "uncertain"
                job["error"] = "存在发送结果不明的号码；核对手机后再处理，系统不会自动重发"
            elif job.get('navigation_failed'):
                job['status'] = 'failed'
            elif "failed" in states:
                job["status"] = "failed"
                job["error"] = next((item.get("error") for item in job["items"] if item.get("status") == "failed"), None)
            elif job.get("cancel_requested"):
                for item in job["items"]:
                    if item.get("status") == "queued":
                        item["status"] = "cancelled"
                job["status"] = "cancelled"
            elif job.get("status") == "waiting_for_device":
                pass
            elif self.stopping.is_set() and any(item.get("status") == "queued" for item in job["items"]):
                job["status"] = "queued"
                job["error"] = None
            elif all(item.get("status") == "sent_verified" for item in job["items"]):
                job["status"] = "completed"
                job["error"] = None
            else:
                job["status"] = "failed"
                job["error"] = errors[0] if errors else "任务未完整执行"
            self._save(job)
