import json
from pathlib import Path
import tempfile
import unittest

from contact_profiles import read_profile, save_profile, validate_fields
from workspace_service import WorkspaceService


class ContactProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contact = {'id':'first-window', 'phone_number':'+15550000001', 'contact':'Alice'}

    def test_same_contact_new_window_keeps_profile_and_normalizes_number(self):
        fields = {'姓名':'Alice', '年龄':'65', '工作':'已退休', '婚否':'未提及'}
        saved = save_profile(self.root,'phone1',self.contact,fields)
        second = {**self.contact,'id':'second-window','phone_number':'5550000001'}
        self.assertEqual(read_profile(self.root,'phone1',second), saved)
        self.assertEqual(read_profile(self.root,'phone1',second)['fields']['工作'],'已退休')

    def test_device_and_contact_isolation(self):
        save_profile(self.root,'phone1',self.contact,{'姓名':'Alice'})
        self.assertEqual(read_profile(self.root,'phone2',self.contact)['fields'],{})
        self.assertEqual(read_profile(self.root,'phone1',{**self.contact,'phone_number':'+15550000002'})['fields'],{})

    def test_unknown_number_does_not_merge_same_display_name(self):
        unknown = {**self.contact,'phone_number':None}
        save_profile(self.root,'phone1',unknown,{'姓名':'Alice'})
        self.assertEqual(read_profile(self.root,'phone1',{**unknown,'id':'other-person'})['fields'],{})

    def test_empty_fields_can_be_saved_to_remove_incorrect_information(self):
        save_profile(self.root,'phone1',self.contact,{'姓名':'Alice'})
        save_profile(self.root,'phone1',self.contact,{'姓名':''})
        self.assertEqual(read_profile(self.root,'phone1',self.contact)['fields']['姓名'],'')

    def test_invalid_data_rejected_before_writing(self):
        for fields in [None,[],{'姓名':{'value':'Alice'}},{'姓名':'a'*1001},{'api_key':'invalid'}]:
            with self.assertRaises(ValueError):validate_fields(fields)
        self.assertFalse((self.root/'workspace').exists())

    def test_service_checks_conversation_device_without_calling_model_or_phone(self):
        folder=self.root/'diagnostics';folder.mkdir()
        (folder/'sample-translated.json').write_text(json.dumps({'device':'phone1','contact':'Alice','phone_number':'+15550000001','messages':[]}),encoding='utf-8')
        def forbidden(*args,**kwargs):raise AssertionError('Profile editing must not call a model or phone')
        service=WorkspaceService(self.root,requester=forbidden,native=forbidden,translator=forbidden)
        service.contact_profile('phone1','sample-translated',{'姓名':'Alice'})
        self.assertEqual(service.contact_profile('phone1','sample-translated')['fields']['姓名'],'Alice')
        with self.assertRaises(ValueError):service.contact_profile('phone2','sample-translated',{'姓名':'wrong'})


if __name__=='__main__':unittest.main()
