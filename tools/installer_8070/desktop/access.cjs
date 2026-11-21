const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const HEADER='X-Pikachu-Workspace-Auth';
let key;
function target(value){try{const u=new URL(value),p=Number(u.port);return u.protocol==='http:'&&u.hostname==='127.0.0.1'&&!u.username&&!u.password&&(p===8070||p>=8080&&p<=65535);}catch{return false;}}
function loadKey(){
 if(key)return key;
 if(!process.env.LOCALAPPDATA)throw Error('缺少本机用户数据目录');
 const directory=path.join(process.env.LOCALAPPDATA,'PikachuSmsBridge'),file=path.join(directory,'workspace-access.key');
 fs.mkdirSync(directory,{recursive:true});
 try{fs.writeFileSync(file,crypto.randomBytes(32).toString('hex'),{flag:'wx',encoding:'ascii',mode:0o600});}catch(error){if(error.code!=='EEXIST')throw error;}
 const raw=fs.readFileSync(file,'ascii').trim();if(!/^[0-9a-f]{64}$/.test(raw))throw Error('本机工作台访问凭据无效');
 return key=Buffer.from(raw,'hex');
}
function headers(method,value,previous={}){
 const result=Object.fromEntries(Object.entries(previous).filter(([name])=>name.toLowerCase()!==HEADER.toLowerCase()));
 if(target(value)){
  const u=new URL(value),stamp=String(Math.floor(Date.now()/1000)),nonce=crypto.randomBytes(16).toString('hex');
  const payload=`v1\n${method.toUpperCase()}\n${u.port}\n${u.pathname}${u.search}\n${stamp}\n${nonce}`;
  result[HEADER]=`v1:${stamp}:${nonce}:${crypto.createHmac('sha256',loadKey()).update(payload).digest('hex')}`;
 }
 return result;
}
module.exports={headers,target};
