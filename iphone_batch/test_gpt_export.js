const assert=require('node:assert/strict');
const {buildGptProfileExport}=require('./web/gpt_export');
const incoming={side:'incoming',kind:'text',text:'I live in Dallas.',time:'12:00'};
const value=buildGptProfileExport({phone_number:'+15550000001',messages:[
 {side:'outgoing',kind:'text',text:'I am a doctor.'},incoming,{...incoming},
 {side:'incoming',kind:'attachment',text:'image.jpg'},
 {side:'incoming',kind:'audio',text:'audio-file'},
 {side:'unknown',kind:'text',text:'unconfirmed speaker'}
]});
assert.equal(value.message_count,3);
assert(value.text.includes('[1] 我方'));
assert(value.text.includes('[2] 对方'));
assert.equal(value.text.split('I live in Dallas.').length-1,2);
assert(!value.text.includes('image.jpg'));assert(!value.text.includes('audio-file'));
assert(!value.text.includes('unconfirmed speaker'));
assert(value.text.includes('+15550000001'));
const long='A'.repeat(50000)+'\n终点';
assert(buildGptProfileExport({messages:[{side:'incoming',text:long}]}).text.includes(long));
assert.throws(()=>buildGptProfileExport({messages:[]}));
console.log('GPT export passed: both speakers, original text, repeated messages, attachments excluded and no truncation');
