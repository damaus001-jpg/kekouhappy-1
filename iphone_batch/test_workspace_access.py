import unittest
from workspace_access import AccessVerifier, signed_header

KEY=bytes.fromhex('01'*32)
URL='http://127.0.0.1:8070/api/state?device=13'

class SignatureTests(unittest.TestCase):
    def header(self, **kwargs):
        return signed_header('GET',URL,key=KEY,timestamp=1700000000,nonce='a'*32,**kwargs)

    def test_valid_request_and_replay_rejected(self):
        gate=AccessVerifier(KEY)
        self.assertTrue(gate.verify('GET',8070,'/api/state?device=13',self.header(),now=1700000000))
        self.assertFalse(gate.verify('GET',8070,'/api/state?device=13',self.header(),now=1700000000))

    def test_method_port_query_and_path_are_bound(self):
        for method,port,path in [('POST',8070,'/api/state?device=13'),('GET',8080,'/api/state?device=13'),('GET',8070,'/api/state?device=14'),('GET',8070,'/')]:
            self.assertFalse(AccessVerifier(KEY).verify(method,port,path,self.header(),now=1700000000))

    def test_expired_and_future_signatures_are_rejected(self):
        for now in [1699999969,1700000031]:
            self.assertFalse(AccessVerifier(KEY).verify('GET',8070,'/api/state?device=13',self.header(),now=now))

    def test_missing_forged_and_other_key_are_rejected(self):
        for header in [None,'','Chrome','v1:bad:bad:bad',self.header().replace('v1:','v2:')]:
            self.assertFalse(AccessVerifier(KEY).verify('GET',8070,'/api/state?device=13',header,now=1700000000))
        self.assertFalse(AccessVerifier(b'x'*32).verify('GET',8070,'/api/state?device=13',self.header(),now=1700000000))

    def test_header_contains_no_shared_secret(self):
        self.assertNotIn(KEY.hex(),self.header())

    def test_translator_node_signature_vector_matches_python(self):
        self.assertEqual(self.header(),'v1:1700000000:'+'a'*32+':bffd05e27095c2137b3634ec56f7f7d0d583571c64ed9a7ea45339d4848ae011')

if __name__=='__main__':unittest.main()
