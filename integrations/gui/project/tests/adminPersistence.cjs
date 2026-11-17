const {build}=require('esbuild');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
const result=await build({entryPoints:[path.resolve(__dirname,'../src/services/connection.ts')],bundle:true,write:false,format:'cjs',platform:'browser',define:{'import.meta.env.VITE_API_BASE_URL':'""','import.meta.env.VITE_DATA_MODE':'"http"'},plugins:[{name:'native-test',setup(b){b.onResolve({filter:/^@capacitor\/core$/},()=>({path:'core',namespace:'test'}));b.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export const Capacitor={isNativePlatform:()=>globalThis.native}; export const registerPlugin=()=>globalThis.vault;'}));}}]});
const persistent=new Map(),session=new Map(),calls=[];let saved=null,failVault=false;
const storage=map=>({getItem:key=>map.get(key)||null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key)});
const vault={async get({backend}){if(failVault)throw Error('vault unavailable');return {token:saved?.backend===backend?saved.token:''};},async set(value){if(failVault)throw Error('vault unavailable');saved=value;},async clear(){if(failVault)throw Error('vault unavailable');saved=null;}};
function load(native){const module={exports:{}};const context={module,exports:module.exports,URL,AbortSignal,native,vault,window:{location:{origin:'http://board:8080'},localStorage:storage(persistent),sessionStorage:storage(session)},fetch:async(url,options={})=>{calls.push({url,options});return {ok:true,json:async()=>({write_access:true,persistent_admin:true})};}};vm.runInNewContext(result.outputFiles[0].text,context);return module.exports;}
let connection=load(true);
session.set('dnb26_admin_token','legacy-unbound-token');
assert.equal(connection.adminToken(),'');session.clear();
await connection.saveConnection('http://board:8080','http','fake-admin',true);
assert.equal(saved.token,'fake-admin');assert(![...persistent.values()].includes('fake-admin'));
session.clear();persistent.delete('dnb26_admin_remember_backend');connection=load(true);await connection.restoreAdminSession();assert.equal(connection.adminToken(),'fake-admin');
assert.equal(connection.rememberAdmin(),'http://board:8080');
await connection.saveConnection('http://other:8080','http','',false);assert.equal(connection.adminToken(),'');assert.equal(saved,null);
await connection.saveConnection('http://board:8080','http','fake-admin',true);
await connection.clearAdminAccess();session.clear();await connection.restoreAdminSession();assert.equal(connection.adminToken(),'');assert.equal(saved,null);
failVault=true;await assert.rejects(connection.saveConnection('http://board:8080','http','fake-admin',true));assert.equal(connection.adminToken(),'');failVault=false;
await connection.saveConnection('http://board:8080','http','temporary-admin',false);await connection.restoreAdminSession();assert.equal(connection.adminToken(),'temporary-admin');await connection.clearAdminAccess();
connection=load(false);await connection.saveConnection('http://board:8080','http','fake-admin',true);
assert.equal(calls.at(-1).options.method,'POST');assert.equal(calls.at(-1).options.headers.Authorization,'Bearer fake-admin');assert.equal(connection.adminToken(),'');assert(![...persistent.values(),...session.values()].includes('fake-admin'));
await assert.rejects(connection.saveConnection('http://other:8080','http','fake-admin',true),/同源/);
await connection.clearAdminAccess();assert.equal(calls.at(-1).options.method,'DELETE');
await connection.saveConnection('http://board:8080','http','fake-admin',false);assert.equal(connection.adminToken(),'fake-admin');assert.equal(connection.rememberAdmin(),'');
console.log('PASS: native encrypted-vault restore, endpoint isolation, explicit clear, storage failures, browser HttpOnly session, no persistent plaintext token');
})().catch(error=>{console.error(error);process.exitCode=1;});
