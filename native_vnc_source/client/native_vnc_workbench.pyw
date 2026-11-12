"""Native Windows phone workbench. Tk widgets and embedded native VNC windows."""
import concurrent.futures
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import uuid

import psutil
from native_process_owner import ProcessOwner, terminate_tree


def locate_data():
    start = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
    for parent in start.parents:
        if (parent / 'iphone_batch/dashboard.py').is_file():
            return parent / 'iphone_batch/.device-data'
    raise RuntimeError('未找到项目运行目录')


DATA = locate_data()
ROOT = DATA.parents[1]
PYTHON = ROOT / 'runtime/python.exe'
if not PYTHON.is_file():
    PYTHON = ROOT / '.venv/Scripts/python.exe'
SOURCE = DATA / 'upstream-pymobiledevice3-v11.51.0'
VIEWER = SOURCE / 'TightVNC/PFiles/TightVNC/tvnviewer.exe'
WORKER = DATA / 'native_vnc_worker.py'
LOGS = DATA / 'logs'
STATE = DATA / 'native-vnc-desktop-state.json'
INITIAL = [
    '00008030-001275241E8B802E', '00008030-001225443E33C02E',
    '00008030-000315A00EB9402E', '00008030-001515510132402E',
    '00008030-001268E626C0C02E', '00008030-000E60161E79402E',
    '00008030-001944362185402E', '00008030-001838463A78802E',
    '00008030-001D25540A91802E', '00008030-001619C136F2802E',
    '00008030-001E301922D8402E', '00008030-001C481A3C32802E',
    '00008030-00040DD23E42402E', '00008030-00044C540285402E',
    '00008030-000518813442402E', '00008030-000A046E2E9B402E',
    '00008030-0011504E1132402E',
]
PROFILE_FIELDS = ('姓名', '年龄', '工作', '地区', '婚否', '兴趣爱好', '其他信息', '资料依据', '待确认')
U = ctypes.windll.user32
U.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
U.SetParent.restype = wintypes.HWND
U.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
U.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
U.GetWindowLongPtrW.restype = ctypes.c_ssize_t
U.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
U.SetWindowLongPtrW.restype = ctypes.c_ssize_t
U.IsWindow.argtypes = [wintypes.HWND]
U.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
U.EnableWindow.argtypes = [wintypes.HWND,wintypes.BOOL]
U.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
U.SetProcessDPIAware()


def ready(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.4) as sock:
            return sock.recv(12).startswith(b'RFB ')
    except OSError:
        return False


def viewer_handle(pid):
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        U.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and U.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(512)
            U.GetWindowTextW(hwnd, title, 512)
            if 'iPhone screen' in title.value or title.value.startswith('VNC '):
                found.append(hwnd)
        return True
    U.EnumWindows(visit, 0)
    return found[0] if found else None


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('手机群控 · 开发版 · 原生 VNC 短信工作台' if os.environ.get('NATIVE_VNC_DEV') == '1' else '手机群控 · 独立 VNC 短信工作台')
        self.root.geometry('1540x920')
        self.root.state('zoomed')
        self.root.minsize(1100, 700)
        self.events = queue.Queue()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        self.launch_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.process_owner = ProcessOwner()
        self.meta = json.loads(STATE.read_text(encoding='utf-8')) if STATE.is_file() else {}
        device_map = DATA / 'workspace/device-map.json'
        if device_map.is_file():
            for item in json.loads(device_map.read_text(encoding='utf-8')):
                self.meta.setdefault('labels', {}).setdefault(item['udid'], '设备 ' + item['number'])
        self.devices = {}
        self.cells = {}
        self.viewers = {}
        self.servers = {}
        self.connecting = set()
        self.closing = False
        self.active = None
        self.conversations = []
        self.current = None
        self.scan_enabled = False
        self.scanning = False
        self.message_busy = False
        self.drafts = {}
        self.resource_samples = []
        self.baseline = psutil.virtual_memory()._asdict()
        self.selected_text = tk.StringVar(value='尚未选择手机')
        self.status = tk.StringVar(value='正在检查 USB 手机…')
        self.resources = tk.StringVar()
        self.followup = tk.BooleanVar()
        self.focus_fps = tk.StringVar(value=str(self.meta.get('focus_fps',5)))
        self.gpu_var=tk.BooleanVar(value=bool(self.meta.get('gpu_accel',False)))
        self.memory_var=tk.BooleanVar(value=bool(self.meta.get('memory_optimization',True)))
        self.decoder_status=tk.StringVar(value='解码状态：未选择手机')
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TButton', padding=(6, 4))
        style.configure('TNotebook.Tab', padding=(16, 8))
        self.build()
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.pump)
        self.root.after(1000, self.sample_resources)
        self.root.after(300, self.refresh_devices)
        self.root.after(1500, self.relayout)
        self.root.after(15000, self.auto_capture)

    def build(self):
        header = ttk.Frame(self.root, padding=8)
        header.pack(fill='x')
        ttk.Label(header, text='手机群控', font=('Microsoft YaHei UI', 16, 'bold')).pack(side='left', padx=(0, 16))
        ttk.Button(header, text='刷新 USB 设备', command=self.refresh_devices).pack(side='left')
        ttk.Button(header, text='接入全部画面', command=self.connect_all).pack(side='left', padx=6)
        ttk.Button(header, text='两排监看', command=self.monitor).pack(side='left')
        ttk.Button(header, text='全屏', command=self.fullscreen).pack(side='left', padx=6)
        ttk.Label(header,text='大屏帧率').pack(side='left',padx=(12,4))
        fps_box=ttk.Combobox(header,textvariable=self.focus_fps,values=('5','10','15','29'),state='readonly',width=4)
        fps_box.pack(side='left')
        fps_box.bind('<<ComboboxSelected>>',lambda _:self.change_fps())
        ttk.Checkbutton(header,text='内存优化',variable=self.memory_var,command=self.save_acceleration).pack(side='left',padx=(10,2))
        ttk.Checkbutton(header,text='GPU 硬解',variable=self.gpu_var,command=self.save_acceleration).pack(side='left',padx=2)
        ttk.Button(header,text='应用到所选',command=self.apply_acceleration).pack(side='left',padx=4)
        ttk.Label(header, textvariable=self.resources).pack(side='right')
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill='both', expand=True)
        self.grid_tab = ttk.Frame(self.tabs, padding=4)
        self.work_tab = ttk.Frame(self.tabs, padding=6)
        self.tabs.add(self.grid_tab, text='全局监看 · 两排 × 十台 · 每秒刷新 1 次')
        self.tabs.add(self.work_tab, text='短信工作台')
        self.tabs.bind('<<NotebookTabChanged>>', lambda _: self.root.after(30, self.relayout))
        for col in range(10):
            self.grid_tab.columnconfigure(col, weight=1, uniform='phones')
        for row in range(2):
            self.grid_tab.rowconfigure(row, weight=1, uniform='rows')
        for i in range(20):
            cell = ttk.Frame(self.grid_tab, relief='solid', borderwidth=1)
            cell.grid(row=i // 10, column=i % 10, sticky='nsew', padx=2, pady=2)
            cell.grid_propagate(False)
            bar = ttk.Frame(cell)
            bar.pack(fill='x')
            label = ttk.Label(bar, text=f'{i+1:02d} 空位', anchor='w')
            label.pack(side='left', fill='x', expand=True)
            button = ttk.Button(bar, text='大屏', width=4, command=lambda i=i: self.pick_index(i))
            button.pack(side='right')
            ttk.Button(bar,text='⋯',width=2,command=lambda i=i:self.device_menu(i)).pack(side='right')
            label.bind('<Button-3>',lambda event,i=i:self.device_menu(i,event))
            screen = tk.Frame(cell, bg='#111714')
            screen.pack(fill='both', expand=True)
            placeholder = tk.Label(screen, text='未连接', fg='#bac6bd', bg='#111714', wraplength=125)
            placeholder.place(relx=.5, rely=.5, anchor='center')
            state = ttk.Label(cell, text='', anchor='center', font=('Microsoft YaHei UI', 8))
            state.pack(fill='x')
            for widget in (label, screen, placeholder):
                widget.bind('<Double-Button-1>', lambda _, i=i: self.pick_index(i))
            screen.bind('<Configure>', lambda _: self.debounce_layout())
            self.cells[i] = {'screen': screen, 'label': label, 'state': state, 'placeholder': placeholder}
        panes = ttk.Panedwindow(self.work_tab, orient='horizontal')
        panes.pack(fill='both', expand=True)
        left = ttk.Frame(panes, width=170)
        phone = ttk.Frame(panes, width=330)
        reading = ttk.Frame(panes, width=700)
        panes.add(left, weight=0)
        panes.add(phone, weight=1)
        panes.add(reading, weight=3)
        ttk.Label(left, text='设备列表', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w')
        self.device_list = tk.Listbox(left, exportselection=False, width=23)
        self.device_list.pack(fill='both', expand=True)
        self.device_list.bind('<<ListboxSelect>>', self.device_pick)
        ttk.Button(left, text='编辑设备编号', command=self.edit_label).pack(fill='x', pady=3)
        ttk.Button(left, text='建立所选手机信任', command=self.trust_selected).pack(fill='x', pady=3)
        ttk.Button(left, text='重连所选画面', command=self.reconnect).pack(fill='x', pady=3)
        ttk.Button(left,text='断开此台（画面和操作）',command=lambda:self.set_device_enabled(self.active,False)).pack(fill='x',pady=3)
        ttk.Button(left,text='接入此台',command=lambda:self.set_device_enabled(self.active,True)).pack(fill='x',pady=3)
        ttk.Button(left,text='仅监看 / 允许操作',command=lambda:self.toggle_readonly(self.active)).pack(fill='x',pady=3)
        self.scan_var = tk.BooleanVar()
        ttk.Checkbutton(left, text='自动遍历当前气泡', variable=self.scan_var, command=self.toggle_scan).pack(anchor='w', pady=5)
        ttk.Label(left, text='仅界面结构读取\n有回复草稿时暂停', wraplength=160).pack(anchor='w')
        version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        ttk.Label(left, text=version + ' · VNC 独立客户端').pack(anchor='w', pady=8)
        ttk.Label(phone, textvariable=self.selected_text, wraplength=320).pack(fill='x')
        ttk.Label(phone,textvariable=self.decoder_status,wraplength=320).pack(fill='x')
        controls = ttk.Frame(phone)
        controls.pack(fill='x', pady=5)
        ttk.Button(controls, text='手机主页', command=lambda: self.action('home')).pack(side='left')
        ttk.Button(controls, text='回到两排', command=self.monitor).pack(side='left', padx=5)
        self.focus_screen = tk.Frame(phone, bg='#111714')
        self.focus_screen.pack(fill='both', expand=True)
        self.focus_screen.bind('<Configure>', lambda _: self.debounce_layout())
        commands = ttk.Frame(reading)
        commands.pack(fill='x')
        for text, action in [('读取当前气泡', 'capture'), ('同步完整历史', 'history'), ('刷新已保存记录', 'saved')]:
            ttk.Button(commands, text=text, command=lambda a=action: self.action(a)).pack(side='left', padx=3)
        self.conversation_box = ttk.Combobox(reading, state='readonly')
        self.conversation_box.pack(fill='x', pady=6)
        self.conversation_box.bind('<<ComboboxSelected>>', lambda _: self.show_conversation())
        self.content_tabs = ttk.Notebook(reading)
        self.content_tabs.pack(fill='both', expand=True)
        message_tab = ttk.Frame(self.content_tabs)
        profile_tab = ttk.Frame(self.content_tabs, padding=8)
        self.content_tabs.add(message_tab, text='短信原文')
        self.content_tabs.add(profile_tab, text='联系人资料')
        self.messages = tk.Text(message_tab, wrap='word', state='disabled', font=('Microsoft YaHei UI', 11), padx=12, pady=10)
        self.messages.pack(fill='both', expand=True)
        self.messages.tag_configure('incoming', foreground='#182a37', background='#edf2f5', spacing1=6, spacing3=9)
        self.messages.tag_configure('outgoing', foreground='#16472b', background='#e1f3e8', spacing1=6, spacing3=9)
        self.profile_vars = {}
        for field in PROFILE_FIELDS:
            row = ttk.Frame(profile_tab)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=field, width=9).pack(side='left')
            var = tk.StringVar()
            self.profile_vars[field] = var
            ttk.Entry(row, textvariable=var).pack(side='left', fill='x', expand=True)
        buttons = ttk.Frame(profile_tab)
        buttons.pack(fill='x', pady=8)
        ttk.Button(buttons, text='保存资料', command=self.save_profile).pack(side='left')
        ttk.Button(buttons, text='粘贴汇总 JSON', command=self.import_profile).pack(side='left', padx=5)
        ttk.Button(buttons, text='复制会话汇总', command=self.copy_summary).pack(side='left')
        row = ttk.Frame(reading)
        row.pack(fill='x', pady=4)
        ttk.Checkbutton(row, text='此联系人待跟进', variable=self.followup, command=self.save_followup).pack(side='left')
        ttk.Button(row, text='导出原文', command=self.export_messages).pack(side='right')
        self.draft = tk.Text(reading, height=4, wrap='word', font=('Microsoft YaHei UI', 11))
        self.draft.pack(fill='x', pady=4)
        ttk.Label(reading,text='先点击所选手机中的输入框；粘贴按钮只填入正文，不自动发送。').pack(anchor='w')
        row = ttk.Frame(reading)
        row.pack(fill='x')
        ttk.Button(row, text='表情', command=self.emoji).pack(side='left')
        ttk.Button(row, text='粘贴到手机当前输入框', command=lambda: self.action('paste')).pack(side='right', padx=5)
        ttk.Button(row, text='确认发送手机已填正文', command=self.send).pack(side='right')
        ttk.Label(self.root, textvariable=self.status, padding=6, anchor='w').pack(fill='x')
        self.root.bind('<Escape>', lambda _: self.root.attributes('-fullscreen', False))

    def submit(self, fn, callback=None):
        def job():
            try:
                result = fn()
                self.events.put(('callback', callback, result, None))
            except Exception as exc:
                self.events.put(('callback', callback, None, str(exc)))
        self.pool.submit(job)

    def worker(self, body):
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'
        process = self.process_owner.spawn(lambda:subprocess.Popen([str(PYTHON),str(WORKER)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            encoding='utf-8',env=env,creationflags=subprocess.CREATE_NO_WINDOW|0x00000004),suspended=True,
            tag=body.get('device'),ticket=body.get('_ticket'))
        try:
            stdout,stderr=process.communicate(json.dumps(body),timeout=650 if body['action'] in ('history','prepare') else 150)
        except subprocess.TimeoutExpired:
            terminate_tree(process.pid)
            process.communicate()
            raise ValueError('手机操作超时，未自动重试')
        finally:
            self.process_owner.forget(process.pid)
        try:
            value = json.loads(stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise ValueError((stderr or '服务未返回有效结果')[-400:])
        if process.returncode or value.get('error'):
            raise ValueError(value.get('error', '服务调用失败'))
        return value

    def refresh_devices(self):
        self.status.set('正在检测 USB 和信任状态…')
        self.submit(lambda: self.worker({'action': 'probe'}), self.on_devices)

    def on_devices(self, result):
        if not hasattr(self, 'device_order'):
            # Preserve this computer's saved numbering; a clean installation
            # assigns slots to its own phones rather than the developer's UDIDs.
            self.device_order = list(self.meta.get('device_order', []))
            if not self.device_order and STATE.is_file():
                self.device_order = list(INITIAL)
        for d in result['devices']:
            if d['udid'] not in self.device_order:
                self.device_order.append(d['udid'])
        if len(self.device_order) > 20:
            online = {d['udid'] for d in result['devices']}
            self.device_order = [u for u in self.device_order if u in online][:20]
        self.meta['device_order'] = self.device_order
        result['devices'] = [d for d in result['devices'] if d['udid'] in self.device_order]
        for d in result['devices']:
            d.update(index=self.device_order.index(d['udid']), port=5901+self.device_order.index(d['udid']))
        self.devices = {d['udid']: d for d in result['devices']}
        self.device_list.delete(0, 'end')
        self.list_ids = sorted(self.devices, key=lambda k: self.devices[k]['index'])
        for udid in self.list_ids:
            d = self.devices[udid]
            cell = self.cells.get(d['index'])
            label = self.label(udid)
            self.device_list.insert('end', label + (' 需信任' if not d['trusted'] else ''))
            if cell:
                cell['label'].configure(text=label)
                cell['placeholder'].configure(text='等待接入' if d['trusted'] else '请解锁手机\n确认信任此电脑')
                cell['state'].configure(text=udid[-8:])
        self.status.set(f"USB {len(self.devices)} 台；配对有效 {sum(d['trusted'] for d in self.devices.values())} 台")
        self.write_device_controls()
        for udid in self.devices:
            if not self.device_enabled(udid):self.show_device_off(udid)
        self.connect_all()

    def trust_selected(self):
        if not self.active:
            self.status.set('请先在列表选中手机')
            return
        self.status.set('请解锁所选手机，确认手机上的“信任此电脑”提示')
        udid = self.active
        self.submit(lambda: self.worker({'action': 'trust', 'device': udid}),
                    lambda _: self.refresh_devices())

    def device_enabled(self,udid):
        return not self.meta.get('disabled_devices',{}).get(udid,False)

    def write_device_controls(self):
        data={'ports':{str(d['port']):{'device':u,'enabled':self.device_enabled(u),
            'control_enabled':self.device_enabled(u) and not self.meta.get('readonly_devices',{}).get(u,False)}
            for u,d in self.devices.items()}}
        target=DATA/'native-vnc-device-controls.json'
        temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(data),encoding='utf-8')
        temp.replace(target)

    def show_device_off(self,udid):
        if udid not in self.devices:return
        cell=self.cells[self.devices[udid]['index']]
        cell['placeholder'].configure(text='已手动断开\n画面与操作均已关闭')
        cell['placeholder'].place(relx=.5,rely=.5,anchor='center')
        cell['state'].configure(text='手动断开 · 可单独接入')

    def set_device_enabled(self,udid,enabled):
        if not udid:return
        self.meta.setdefault('disabled_devices',{})[udid]=not enabled
        self.save_meta()
        self.write_device_controls()
        if not enabled:
            self.process_owner.stop_tag(udid)
            self.viewers.pop(udid,None)
            self.servers.pop(udid,None)
            self.connecting.discard(udid)
            self.show_device_off(udid)
            self.status.set(self.label(udid)+' 已断开，停止该台画面、解码和操作')
        else:
            self.process_owner.resume_tag(udid)
            self.connecting.discard(udid)
            self.connect_all()
            self.status.set(self.label(udid)+' 正在重新接入')

    def toggle_readonly(self,udid):
        if not udid:return
        values=self.meta.setdefault('readonly_devices',{})
        values[udid]=not values.get(udid,False)
        self.save_meta()
        self.write_device_controls()
        item=self.viewers.get(udid)
        if item:U.EnableWindow(item['hwnd'],not values[udid])
        if udid in self.devices and udid in self.viewers:
            self.cells[self.devices[udid]['index']]['state'].configure(text=('仅监看 · ' if values[udid] else '已连接 · ')+udid[-8:])
        self.status.set(self.label(udid)+(' 仅监看，鼠标、键盘和粘贴已锁定' if values[udid] else ' 已允许鼠标、键盘和粘贴操作'))

    def device_menu(self,index,event=None):
        udid=next((u for u,d in self.devices.items() if d['index']==index),None)
        if udid is None:return
        menu=tk.Menu(self.root,tearoff=False)
        if self.device_enabled(udid):
            menu.add_command(label='断开此台：停止画面和操作',command=lambda:self.set_device_enabled(udid,False))
        else:
            menu.add_command(label='接入此台',command=lambda:self.set_device_enabled(udid,True))
        locked=self.meta.get('readonly_devices',{}).get(udid,False)
        menu.add_command(label='允许操作' if locked else '仅监看：锁定鼠标和键盘',command=lambda:self.toggle_readonly(udid))
        try:menu.tk_popup(event.x_root if event else self.root.winfo_pointerx(),event.y_root if event else self.root.winfo_pointery())
        finally:menu.grab_release()

    def label(self, udid):
        index = self.device_order.index(udid)
        return self.meta.get('labels', {}).get(udid, f'设备 {index+1:02d}')

    def connect_all(self):
        limit = int(os.environ.get('NATIVE_VNC_MAX_DEVICES', '20'))
        trusted = [(u,d) for u,d in self.devices.items() if d['trusted']]
        for udid, d in sorted(trusted, key=lambda item: item[1]['index'])[:limit]:
            if self.device_enabled(udid) and d['trusted'] and udid not in self.viewers and udid not in self.connecting:
                self.connecting.add(udid)
                self.launch_pool.submit(self.connect,dict(d,_ticket=self.process_owner.ticket(udid)))

    def connect(self, d):
        udid, port = d['udid'], d['port']
        ticket=d.get('_ticket',self.process_owner.ticket(udid))
        try:
            if self.closing or not self.device_enabled(udid) or ticket!=self.process_owner.ticket(udid):return
            deadline=time.monotonic()+90
            while psutil.cpu_percent(interval=.3)>75:
                if self.closing or not self.device_enabled(udid) or ticket!=self.process_owner.ticket(udid):return
                self.events.put(('state',udid,'等待 CPU 余量，逐台接入'))
                if time.monotonic()>deadline:raise ValueError('CPU 持续繁忙，请稍后接入此设备')
                time.sleep(.7)
            self.events.put(('state', udid, '启动中'))
            if not ready(port):
                self.events.put(('state',udid,'检查开发者模式与镜像'))
                self.worker({'action':'prepare','device':udid,'_ticket':ticket})
                env = os.environ.copy()
                options=self.meta.get('device_acceleration',{}).get(udid,{
                    'gpu_accel':self.meta.get('gpu_accel',False),
                    'memory_optimization':self.meta.get('memory_optimization',True)})
                env.update(PYMOBILEDEVICE3_UDID=udid, PYTHONUTF8='1', VNC_PREVIEW_WIDTH='0',
                           VNC_PRESENT_FPS='1', VNC_DECODE_THREADS='1',
                           VNC_GPU_ACCEL='1' if options['gpu_accel'] else '0',
                           VNC_MEMORY_OPT='1' if options['memory_optimization'] else '0')
                LOGS.mkdir(exist_ok=True)
                with (LOGS / f'native-vnc-{port}.out.log').open('w', encoding='utf-8') as out, (LOGS / f'native-vnc-{port}.err.log').open('w', encoding='utf-8') as err:
                    server = self.process_owner.spawn(lambda:subprocess.Popen([str(PYTHON), str(DATA/'vnc_av_continuous.py'), '-v',
                        'developer', 'core-device', 'display', 'serve-vnc', '--port', str(port),
                        '--decoder', 'av', '--userspace', '--share-clipboard'], env=env,
                        stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW|0x00000004),suspended=True,tag=udid,ticket=ticket)
                self.servers[udid] = server
                for _ in range(80):
                    if self.closing:
                        return
                    if ready(port):
                        break
                    if server.poll() is not None:
                        raise ValueError('手机投屏服务启动失败')
                    time.sleep(.35)
                else:
                    raise ValueError('投屏启动超时')
            existing = None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if (proc.info['name'] or '').lower() == 'tvnviewer.exe' and f'-port={port}' in (proc.info['cmdline'] or []):
                    existing = proc.pid
                    break
            if existing is None:
                existing = self.process_owner.spawn(lambda:subprocess.Popen([str(VIEWER), '-host=127.0.0.1', f'-port={port}',
                    '-password=isolated', '-scale=auto', '-fullscreen=no', '-showcontrols=no',
                    '-viewonly=no', '-useclipboard=no'], cwd=VIEWER.parent,
                    creationflags=0x00000004),suspended=True,tag=udid,ticket=ticket).pid
            else:
                self.process_owner.adopt(existing,tag=udid,ticket=ticket)
            for _ in range(70):
                if self.closing:
                    return
                hwnd = viewer_handle(existing)
                if hwnd:
                    self.events.put(('attach', udid, hwnd, existing))
                    return
                time.sleep(.2)
            raise ValueError('未找到 VNC 画面窗口')
        except Exception as exc:
            if self.closing or not self.device_enabled(udid) or ticket!=self.process_owner.ticket(udid):return
            self.events.put(('failed', udid, str(exc)))

    def attach(self, udid, hwnd, pid):
        if not self.device_enabled(udid) or not U.IsWindow(hwnd):return
        self.connecting.discard(udid)
        cell = self.cells[self.devices[udid]['index']]
        U.SetWindowPos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, 0x0013)
        U.ShowWindow(hwnd, 9)
        style = U.GetWindowLongPtrW(hwnd, -16)
        style = (style & ~(0x80000000 | 0x00c00000 | 0x00040000 | 0x00080000 | 0x00030000)) | 0x40000000
        U.SetWindowLongPtrW(hwnd, -16, style)
        self.viewers[udid] = {'hwnd': hwnd, 'pid': pid, 'parent': None}
        U.EnableWindow(hwnd,not self.meta.get('readonly_devices',{}).get(udid,False))
        cell['placeholder'].place_forget()
        cell['state'].configure(text=('仅监看 · ' if self.meta.get('readonly_devices',{}).get(udid,False) else '已连接 · ') + udid[-8:])
        self.relayout()

    def relayout(self):
        if self.closing:
            return
        work = self.tabs.select() == str(self.work_tab)
        mode = {'focus_port': self.devices[self.active]['port'] if work and self.active else None,
                'grid_fps': 1, 'focus_fps': int(self.focus_fps.get())}
        mode_text = json.dumps(mode)
        if mode_text != getattr(self, '_last_mode', None):
            (DATA/'native-vnc-display-mode.json').write_text(mode_text,encoding='utf-8')
            self._last_mode = mode_text
        for udid, item in self.viewers.items():
            hwnd = item['hwnd']
            if not U.IsWindow(hwnd):
                continue
            parent = self.focus_screen if work and udid == self.active else self.cells[self.devices[udid]['index']]['screen']
            handle = parent.winfo_id()
            if item['parent'] != handle:
                U.SetParent(hwnd, handle)
                item['parent'] = handle
            U.SetWindowPos(hwnd, None, 0, 0, max(1,parent.winfo_width()), max(1,parent.winfo_height()), 0x0074)

    def debounce_layout(self):
        old = getattr(self, '_layout_timer', None)
        if old:
            self.root.after_cancel(old)
        self._layout_timer = self.root.after(60, self.relayout)

    def change_fps(self):
        self.meta['focus_fps']=int(self.focus_fps.get())
        self.save_meta()
        self.relayout()
        self.status.set(f'全局监看 1 帧/秒，单台大屏最多 {self.focus_fps.get()} 帧/秒')

    def save_acceleration(self):
        self.meta['gpu_accel']=self.gpu_var.get()
        self.meta['memory_optimization']=self.memory_var.get()
        self.save_meta()
        self.status.set('加速设置已保存；点击“应用到所选”重连接入生效，新接入设备使用此设置')

    def apply_acceleration(self):
        self.save_acceleration()
        if self.message_busy:
            self.status.set('当前有手机操作正在执行，操作结束后再应用解码设置')
            return
        if self.active:
            self.meta.setdefault('device_acceleration',{})[self.active]={
                'gpu_accel':self.gpu_var.get(),'memory_optimization':self.memory_var.get()}
            self.save_meta()
        self.reconnect()

    def pick_index(self, index):
        d = next((d for d in self.devices.values() if d['index'] == index), None)
        if d:
            self.pick(d['udid'])

    def device_pick(self, _):
        chosen = self.device_list.curselection()
        if chosen:
            self.pick(self.list_ids[chosen[0]])

    def pick(self, udid):
        if self.active:
            self.drafts[self.active] = self.draft.get('1.0', 'end-1c')
        self.active = udid
        options=self.meta.get('device_acceleration',{}).get(udid,self.meta)
        self.gpu_var.set(bool(options.get('gpu_accel',False)))
        self.memory_var.set(bool(options.get('memory_optimization',True)))
        self.selected_text.set(self.label(udid) + ' · ' + udid[-12:])
        self.draft.delete('1.0', 'end')
        self.draft.insert('1.0', self.drafts.get(udid, ''))
        self.tabs.select(self.work_tab)
        self.relayout()
        self.action('saved')

    def monitor(self):
        self.tabs.select(self.grid_tab)
        self.relayout()

    def fullscreen(self):
        self.monitor()
        self.root.attributes('-fullscreen', not bool(self.root.attributes('-fullscreen')))

    def action(self, action, extra=None):
        if not self.active:
            self.status.set('请先选择一台手机')
            return
        if action in ('paste','home','send') and (not self.device_enabled(self.active) or self.meta.get('readonly_devices',{}).get(self.active,False)):
            self.status.set('此设备已断开或仅监看，请先接入并允许操作')
            return
        if self.message_busy:
            self.status.set('正在处理上一项操作，请稍候')
            return
        udid = self.active
        if action in ('send','history','profile','save_profile') and not self.current:
            self.status.set('请先读取并选择会话')
            return
        body = {'action': action, 'device': udid, 'port': self.devices[udid]['port'],
                'conversation_id': (self.current or {}).get('id'), 'text': self.draft.get('1.0','end-1c')}
        body.update(extra or {})
        self.message_busy = True
        self.status.set('正在从下往上慢速遍历，遇到图片继续；读到会话完整手机号后停止，最长约 2 分钟' if action in ('capture','capture_visible') else '正在处理：' + action)
        def done(value):
            self.message_busy = False
            if udid != self.active:
                return
            if action == 'saved':
                self.load_saved(value)
            elif action in ('capture', 'capture_visible', 'history', 'send'):
                preferred = value.get('conversation_id')
                if action == 'send':
                    self.draft.delete('1.0','end')
                self.submit(lambda: self.worker({'action':'saved','device':udid}),
                    lambda result: self.load_saved(result, preferred) if self.active == udid else None)
                self.status.set(value.get('message', f"已读取 {value.get('message_count',0)} 条"))
            else:
                self.status.set(value.get('message', '操作完成'))
        self.submit(lambda: self.worker(body), done)

    def load_saved(self, value, preferred=None):
        self.conversations = value.get('conversations', [])
        self.conversation_box['values'] = [f"{c.get('contact')} · {len(c['messages'])} 条 · {c.get('created','')}" for c in self.conversations]
        if self.conversations:
            index = next((i for i,c in enumerate(self.conversations) if c['id']==preferred),0)
            self.conversation_box.current(index)
        else:
            self.conversation_box.set('暂无已保存记录')
        self.show_conversation()

    def show_conversation(self):
        index = self.conversation_box.current()
        self.current = self.conversations[index] if 0 <= index < len(self.conversations) else None
        self.messages.configure(state='normal')
        self.messages.delete('1.0','end')
        for m in (self.current or {}).get('messages', []):
            side = '我方' if m.get('side')=='outgoing' else '对方'
            date=m.get('date') or m.get('date_label') or '日期未知'
            self.messages.insert('end', f"{side} · {date} {m.get('time') or '时间未知'}\n{m.get('text') or '[附件]'}\n\n", m.get('side','incoming'))
        self.messages.configure(state='disabled')
        self.messages.see('end')
        for var in self.profile_vars.values():
            var.set('')
        self.followup.set(self.meta.get('followup', {}).get(self.contact_key(),False))
        if self.current:
            udid, identifier = self.active, self.current['id']
            self.submit(lambda: self.worker({'action':'profile','device':udid,'conversation_id':identifier}),
                lambda result: self.load_profile(result) if self.active==udid and self.current and self.current['id']==identifier else None)

    def load_profile(self, result):
        for name,var in self.profile_vars.items():
            var.set(result.get('fields',{}).get(name,''))

    def save_profile(self):
        self.action('save_profile', {'fields': {k:v.get() for k,v in self.profile_vars.items()}})

    def import_profile(self):
        try:
            raw = simpledialog.askstring('填入联系人资料', '粘贴 JSON：', parent=self.root)
            if raw:
                value = json.loads(raw)
                self.load_profile({'fields': value.get('fields',value)})
        except (ValueError, AttributeError):
            self.status.set('JSON 格式无效')

    def contact_key(self):
        return str(self.active) + ':' + str((self.current or {}).get('phone_number') or (self.current or {}).get('contact'))

    def save_meta(self):
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(STATE)

    def save_followup(self):
        if self.current:
            self.meta.setdefault('followup',{})[self.contact_key()] = self.followup.get()
            self.save_meta()

    def edit_label(self):
        if self.active:
            value = simpledialog.askstring('设备编号','输入设备编号：',initialvalue=self.label(self.active),parent=self.root)
            if value:
                self.meta.setdefault('labels',{})[self.active]=value[:16]
                self.save_meta()
                self.cells[self.devices[self.active]['index']]['label'].configure(text=value[:16])
                self.selected_text.set(value[:16]+' · '+self.active[-12:])

    def export_text(self):
        c=self.current or {}
        lines=[f"设备：{self.label(self.active)}",f"联系人：{c.get('phone_number') or c.get('contact')}"]
        for m in c.get('messages',[]):
            lines.append(f"{'我方' if m.get('side')=='outgoing' else '对方'} · {m.get('date') or m.get('date_label') or '日期未知'} {m.get('time') or ''}\n{m.get('text') or '[附件]'}")
        return '\n\n'.join(lines)

    def export_messages(self):
        if not self.current:
            return
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.txt',filetypes=[('文本','*.txt')])
        if path:
            Path(path).write_text(self.export_text(),encoding='utf-8')
            self.status.set('短信原文已导出')

    def copy_summary(self):
        if self.current:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.export_text())
            self.status.set('已复制会话原文，可粘贴到汇总工具')

    def emoji(self):
        top=tk.Toplevel(self.root)
        top.title('选择表情')
        for i,text in enumerate(['🙂','😊','😂','😍','🙏','👍','❤️','🌹','☀️','🌙','🎉','✅']):
            ttk.Button(top,text=text,command=lambda t=text:self.draft.insert('insert',t)).grid(row=i//6,column=i%6,padx=4,pady=4)

    def send(self):
        if not self.current:
            self.status.set('请先读取会话')
            return
        if messagebox.askyesno('确认发送',f"设备：{self.label(self.active)}\n号码：{self.current.get('phone_number')}\n\n仅发送手机输入框中已核验一致的正文，发送后不自动重试。",parent=self.root):
            self.action('send',{'confirm':True,'token':uuid.uuid4().hex})

    def toggle_scan(self):
        self.scan_enabled=self.scan_var.get()
        self.status.set('自动遍历已开启：仅读取原生界面结构' if self.scan_enabled else '自动遍历已关闭')

    def auto_capture(self):
        if self.closing:
            return
        if self.scan_enabled and not self.message_busy and self.active and self.device_enabled(self.active) and not self.draft.get('1.0','end-1c').strip():
            self.action('capture_visible')
        self.root.after(15000,self.auto_capture)

    def reconnect(self):
        if not self.active or self.active in self.connecting:
            return
        udid=self.active
        self.set_device_enabled(udid,False)
        self.set_device_enabled(udid,True)

    def sample_resources(self):
        if self.closing:
            return
        memory=psutil.virtual_memory()
        cpu=psutil.cpu_percent()
        live=sum(U.IsWindow(v['hwnd'])!=0 for v in self.viewers.values())
        self.resources.set(f'{live} 台画面   CPU {cpu:.0f}%   内存 {memory.percent:.0f}% / 可用 {memory.available/1024**3:.1f} GB')
        if self.active in self.devices and self.active in self.viewers:
            try:
                mode=json.loads((DATA/'diagnostics'/f"accel-{self.devices[self.active]['port']}.json").read_text(encoding='utf-8'))
                names={'gpu-initializing':'GPU 初始化中','gpu-d3d11va':'GPU 硬件解码',
                       'cpu':'CPU 软件解码','cpu-fallback':'GPU 未启用，已回退 CPU','cpu-restarting':'GPU 失败，正在重新接入 CPU'}
                self.decoder_status.set(names.get(mode['decoder'],mode['decoder'])+
                    (' · 缓冲复用开启' if mode.get('memory_optimized') else ' · 缓冲复用关闭')+
                    ('\n'+mode['reason'][:120] if mode.get('reason') else ''))
            except (OSError,ValueError,KeyError):self.decoder_status.set('解码状态：等待当前设备上报')
        else:self.decoder_status.set('解码状态：未接入所选手机')
        self.resource_samples.append({'time':time.time(),'cpu':cpu,'memory_percent':memory.percent,'available':memory.available,'windows':live})
        if len(self.resource_samples)%5==0:
            (DATA/'native-vnc-resource-samples.json').write_text(json.dumps(self.resource_samples[-180:],indent=2),encoding='utf-8')
        self.root.after(2000,self.sample_resources)

    def pump(self):
        while True:
            try:item=self.events.get_nowait()
            except queue.Empty:break
            kind=item[0]
            if kind=='callback':
                _,callback,value,error=item
                if error:
                    self.message_busy=False
                    self.status.set(error)
                elif callback:
                    callback(value)
            elif kind=='attach':
                self.attach(*item[1:])
            elif kind in ('state','failed'):
                _,udid,text=item
                cell=self.cells.get(self.devices[udid]['index'])
                if cell:
                    cell['state'].configure(text=text)
                    if kind=='failed':cell['placeholder'].configure(text=text+'\n可选中后重连')
                if kind=='failed':self.connecting.discard(udid)
        if not self.closing:
            self.root.after(100,self.pump)

    def close(self):
        self.closing=True
        self.save_meta()
        self.process_owner.close()
        self.pool.shutdown(wait=False,cancel_futures=True)
        self.launch_pool.shutdown(wait=False,cancel_futures=True)
        self.root.destroy()


if __name__=='__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--check-install':
        check = subprocess.run([str(PYTHON), str(DATA / 'check_native_install.py')],
            capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW)
        Path(sys.argv[2]).write_text(check.stdout or check.stderr, encoding='utf-8')
        sys.exit(check.returncode)
    try:
        App().root.mainloop()
    except Exception:
        import traceback
        (DATA/'native-vnc-client-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        raise
