import plistlib
import unittest
from pasteboard_text import archive_text, attributed_text, install, ATTRIBUTED_UTI


def archive(objects, root=1):
    return plistlib.dumps({'$archiver':'NSKeyedArchiver','$version':100000,
        '$top':{'root':plistlib.UID(root)},'$objects':objects},fmt=plistlib.FMT_BINARY)

class AttributedTextTests(unittest.TestCase):
    def test_message_body_only_unicode_and_newlines(self):
        value='\u4e2d\u6587\nSMS \U0001f600'
        raw=archive(['$null',{'NSString':plistlib.UID(2),'NSAttributes':plistlib.UID(3)},
            value,{'font':'not message text','url':'not copied body'}])
        self.assertEqual(archive_text(raw),value)

    def test_wrapped_string_and_snapshot(self):
        raw=archive(['$null',{'NSString':plistlib.UID(2)}, {'NS.string':plistlib.UID(3)},'body'])
        snapshot={'pasteboard':{'items':[{'data':{ATTRIBUTED_UTI:{'data':raw}}}]}}
        self.assertEqual(attributed_text(snapshot),'body')

    def test_cycles_and_unrecognised_formats_are_not_text(self):
        for raw in [b'invalid',archive(['$null',{'NSString':plistlib.UID(1)}]),
                    archive(['$null',{'attributes':'must not extract'}])]:
            self.assertIsNone(archive_text(raw))

    def test_plain_text_preferred_and_patch_idempotent(self):
        install();install()
        from pymobiledevice3.remote.core_device.pasteboard_service import snapshot_text
        raw=archive(['$null',{'NSString':plistlib.UID(2)},'rich body'])
        item={'data':{'public.utf8-plain-text':{'data':b'plain body'},ATTRIBUTED_UTI:{'data':raw}}}
        self.assertEqual(snapshot_text({'items':[item]}),'plain body')
        del item['data']['public.utf8-plain-text']
        self.assertEqual(snapshot_text({'items':[item]}),'rich body')

if __name__=='__main__':unittest.main()
