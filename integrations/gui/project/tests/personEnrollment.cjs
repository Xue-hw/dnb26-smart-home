const {build}=require('esbuild');
const {JSDOM}=require('jsdom');
const assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const wait=()=>new Promise(resolve=>setTimeout(resolve,20));
async function until(check){for(let i=0;i<80;i++){if(check())return;await wait();}throw Error('Enrollment UI timeout');}
(async()=>{
 const bundle=await build({stdin:{contents:`import {createRoot} from 'react-dom/client';import PersonnelPage from './src/pages/PersonnelPage';
 const root=createRoot(document.getElementById('root'));root.render(<PersonnelPage/>);window.__unmount=()=>root.unmount();`,loader:'tsx',resolveDir:root},
 bundle:true,write:false,format:'iife',tsconfig:path.join(root,'tsconfig.json'),plugins:[{name:'context',setup(b){
 b.onResolve({filter:/context\/AppDataContext$/},()=>({path:'context',namespace:'fixture'}));
 b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const useAppData=()=>window.__context;'}));}}]});
 async function runCase(personId){
 const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost',runScripts:'outside-only'}),w=dom.window;
 let checks=0,fail=false,hold=false,release;
 let persons=[{user_id:personId,name:'test',avatar_url:null,created_at:new Date().toISOString(),feature_version:'v1'}];
 w.__context={mode:'http',source:{getPersons:async()=>[...persons],deletePerson:async()=>{persons=[];},addPerson:async input=>{persons=[{...input,feature_version:'v2',created_at:new Date().toISOString()}];},
 getPersonEnrollment:async user_id=>{checks++;if(fail)throw new w.Error('后端暂时不可用');const result={user_id,status:'ready',active:true,loaded:true,feature_status:'valid',model_status:'online',feature_version:persons[0].feature_version,checked_at:new Date().toISOString(),message:'人脸特征有效，已载入识别服务'};if(hold)return new Promise(resolve=>{release=()=>resolve(result);});return result;}}};
 w.eval(bundle.outputFiles[0].text);await until(()=>w.document.body.textContent.includes('test'));
 const button=()=>Array.from(w.document.querySelectorAll('button')).find(b=>b.textContent.includes('确认录入状态'));
 assert.ok(button(),'person card must offer explicit backend confirmation');
 assert.ok(!w.document.body.textContent.includes('后端接入后展示'));
 button().click();await until(()=>w.document.body.textContent.includes('已录入（后端确认）'));
 assert.equal(checks,1);
 fail=true;button().click();await until(()=>w.document.body.textContent.includes('后端暂时不可用'));
 assert.ok(!w.document.body.textContent.includes('已录入（后端确认）'),'failed recheck cannot retain prior success');
 fail=false;button().click();await until(()=>w.document.body.textContent.includes('已录入（后端确认）'));
 const click=text=>Array.from(w.document.querySelectorAll('button')).find(b=>b.textContent.trim()===text).click();
 async function removeAndRecreate(){
  click('删除');await wait();click('确认删除');await until(()=>w.document.body.textContent.includes('暂无授权人员'));
  click('新增授权人员');await wait();
  const input=(id,value)=>{const e=w.document.getElementById(id);Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new w.Event('input',{bubbles:true}));};
  input('person-name','replacement');input('person-id',personId);await wait();click('确认新增');await until(()=>w.document.body.textContent.includes('replacement'));
 }
 await removeAndRecreate();
 assert.ok(!w.document.body.textContent.includes('已录入（后端确认）'),'replacement record cannot inherit old confirmation');
 hold=true;button().click();await until(()=>release);
 await removeAndRecreate();release();await wait();await wait();
 assert.ok(!w.document.body.textContent.includes('已录入（后端确认）'),'delayed response cannot confirm a replaced person');
 w.__unmount();dom.window.close();
 console.log('PASS: enrollment confirmation, failed recheck, deletion/recreation and stale response: '+personId);
 }
 for(const personId of ['P1','constructor','toString','__proto__'])await runCase(personId);
})().catch(error=>{console.error(error);process.exit(1);});
