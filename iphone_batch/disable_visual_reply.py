from pathlib import Path
p=Path('iphone_batch/reply_phone.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("    def __init__(self, manager='http://127.0.0.1:8070'):\n", "    def __init__(self, manager='http://127.0.0.1:8070'):\n        raise RuntimeError('用户要求禁止截屏定位；此视觉驱动已禁用，请使用系统界面元素驱动')\n")
p.write_text(s,encoding='utf-8')
