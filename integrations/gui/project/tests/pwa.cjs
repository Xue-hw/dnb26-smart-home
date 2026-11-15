const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');const root=path.resolve(__dirname,'..');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'public/manifest.webmanifest')));
assert.equal(manifest.display,'standalone');assert.equal(manifest.scope,'/');
for(const icon of manifest.icons)assert(fs.existsSync(path.join(root,'public',icon.src)));
const handlers={};let response;
vm.runInNewContext(fs.readFileSync(path.join(root,'public/sw.js'),'utf8'),{self:{location:{origin:'https://test.local'},addEventListener:(n,f)=>handlers[n]=f},URL,fetch:async()=>{throw Error('offline')},caches:{match:async()=> 'OFFLINE_PAGE'},Response:{error:()=> 'ERROR'}});
for(const p of ['/api/dashboard/snapshot','/uploads/person.png']){let intercepted=false;handlers.fetch({request:{url:'https://test.local'+p,mode:'navigate'},respondWith:()=>intercepted=true});assert.equal(intercepted,false)}
handlers.fetch({request:{url:'https://test.local/history',mode:'navigate'},respondWith:r=>response=r});
(async()=>{assert.equal(await response,'OFFLINE_PAGE');console.log('PASS: manifest, icon files, offline navigation, no API/photo interception')})();
