import json
from pathlib import Path
from PIL import Image
from reply_phone import PhoneDriver
from reply_assistant import ReplyStore, ReplyAssistant

root=Path(__file__).resolve().parent
image=Image.open(root/'.device-data/diagnostics/unread-list-current.png')
driver=PhoneDriver()
lines=driver.lines(image)
print(json.dumps({'ocr_lines':len(lines),'unread_rows':driver.unread_rows(image,lines)},ensure_ascii=True))

