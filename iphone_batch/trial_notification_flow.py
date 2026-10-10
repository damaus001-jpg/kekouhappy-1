"""Validate the known test notification; never invoke send or translation."""
import json
from workspace_service import WorkspaceService

device='00008030-001119CE0A93402E'
base='http://127.0.0.1:8080'
service=WorkspaceService()
result=service.notifications(device,base)
print(json.dumps({'discovered':len(result['items']),
                  'notifications':[{'sender':r['sender'],'preview':r['preview'],'grouped':r['grouped']}
                                   for r in result['items']]},ensure_ascii=True),flush=True)
matches=[r for r in result['items'] if r['phone_number']=='+19562154700' and r['preview']=='❤️❤️❤️']
if len(matches)!=1:
    raise ValueError('未唯一找到用户刚发送的测试通知，未点击')
row=matches[0]
current=service.native(device,'open_notification',base,record=service.notification_path(row['id']))
path=service.root/'diagnostics'/'notification-open-trial.json'
service.write(path,current)
print(json.dumps({'opened_phone':current['phone_number'], 'message_count':len(current['messages']),
                  'test_message_present':any(m['text']=='❤️❤️❤️' and m['side']=='incoming' for m in current['messages'])}),flush=True)
