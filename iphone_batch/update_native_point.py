from pathlib import Path
p=Path('iphone_batch/probe_native_hit.py');s=p.read_text(encoding='utf-8-sig')
s=s.replace("def passthrough(value):", "from bpylist2 import archiver\nclass NativePoint:\n    def __init__(self,x,y):self.x=x;self.y=y\n    def encode_archive(self,archive):\n        archive._archive_obj['NS.special']=1\n        archive.encode('NS.pointval','{'+str(self.x)+', '+str(self.y)+'}')\narchiver.ARCHIVE_CLASS_MAP[NativePoint]='NSValue'\n\ndef passthrough(value):")
start=s.index('            formats=');end=s.index('\n            for name,point',start)
s=s[:start]+"            formats=[('native_point',NativePoint(.5,.3))]"+s[end:]
p.write_text(s,encoding='utf-8')
