from fixed_coordinates import load_profile, video_size
from native_conversation import NativeConversation

phone = NativeConversation()
phone.base = 'http://127.0.0.1:8080'
print({'video_size': video_size(phone),
       'input_verified': load_profile('00008030-001119CE0A93402E')['input_verified']})
