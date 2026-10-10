import asyncio,json,sys,time
from native_workspace import ROOT
from native_ui_scan import scan
from native_action import serialize
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.accessibilityaudit import AccessibilityAudit,deserialize_object,SERIALIZABLE_OBJECTS,SerializedObject
SERIALIZABLE_OBJECTS['AXAuditNode_v1']=SerializedObject

def safe(v):
    if hasattr(v,'_fields'):return {'type':type(v).__name__,'fields':safe(v._fields)}
    if isinstance(v,dict):return {str(k):safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [safe(x) for x in v]
    if isinstance(v,bytes):return {'hex':v.hex()}
    return v if v is None or isinstance(v,(str,int,float,bool)) else str(type(v))
async def main():
    ld=await create_using_usbmux(serial='00008030-001119CE0A93402E',connection_type='USB',usbmux_address='127.0.0.1:27015',pairing_records_cache_folder=ROOT,autopair=False)
    try:
        try:print(json.dumps({'backup_encrypted':await ld.get_value('com.apple.mobile.backup','WillEncrypt')}),flush=True)
        except Exception as e:print(json.dumps({'backup_encryption_status':'unknown','reason':type(e).__name__}),flush=True)
        async with AccessibilityAudit(ld) as s:
            items=await scan(s,limit=3,seconds=6,settle=0)
            target=next((i for i in items if ', Show Conversation Details' in (i.caption or '')),None)
            if target is None:print('No conversation header');return
            attrs=[a._fields for sec in target._fields.get('InspectorSectionsValue_v1',[]) for a in sec._fields.get('ElementAttributesValue_v1',[])]
            attr=next((a for a in attrs if a.get('AttributeNameValue_v1')=='_AXHierarchyElementsAttribute'),None)
            if attr is None:print(json.dumps({'attribute_names':[a.get('AttributeNameValue_v1') for a in attrs]}));return
            started=time.monotonic()
            response=await asyncio.wait_for(s._invoke('deviceElement:valueForAttribute:',serialize('AXAuditElement_v1',{'PlatformElementValue_v1':target.element.identifier}),serialize('AXAuditElementAttribute_v1',attr)),5)
            data=safe(deserialize_object(response))
            (ROOT/'diagnostics'/'message-hierarchy-fast.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'hierarchy_seconds':time.monotonic()-started,'hierarchy':data},ensure_ascii=True),flush=True)
    finally:await ld.close()
if sys.platform=='win32':asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
asyncio.run(main())
