from pathlib import Path
p=Path('probe_native_geometry.py')
s=p.read_text(encoding='utf-8-sig')
s=s.replace('AccessibilityAudit,deserialize_object','AccessibilityAudit,deserialize_object,SERIALIZABLE_OBJECTS,SerializedObject')
s=s.replace("ROOT=Path", "SERIALIZABLE_OBJECTS['AXAuditNode_v1']=SerializedObject\nROOT=Path")
p.write_text(s,encoding='utf-8')
