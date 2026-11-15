const esbuild=require('esbuild');
const {JSDOM,VirtualConsole}=require('jsdom');
const assert=require('node:assert/strict');
const path=require('node:path');
const root=path.resolve(__dirname, '..');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(f,label){for(let i=0;i<100;i++){if(f())return;await delay(20);}throw Error('Timed out: '+label)}
(async()=>{
 const build=await esbuild.build({entryPoints:[root+'/src/main.tsx'],bundle:true,write:false,format:'iife',loader:{'.css':'empty'},define:{'import.meta.env.PROD':'false','import.meta.env.VITE_DATA_MODE':'"http"','import.meta.env.VITE_API_BASE_URL':'""'},tsconfig:root+'/tsconfig.json'});
 const code=build.outputFiles[0].text;
 const now=new Date().toISOString();
 async function start(route='/', scenario='acked'){
  let disconnected=false, posted=false,polls=0;const calls=[],errors=[];
  const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/canvas|Not implemented|navigation/i.test(e.message))errors.push(e.message)});
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'+route,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
  const w=dom.window;w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.ResizeObserver=class{observe(){} disconnect(){}};
  w.EventSource=class{addEventListener(){}removeEventListener(){}close(){}};
  w.URL.createObjectURL=()=> 'blob:mock';w.URL.revokeObjectURL=()=>{};
  w.HTMLCanvasElement.prototype.getContext=function(){return new Proxy({measureText:t=>({width:String(t).length*8}),canvas:this},{get:(o,k)=>k in o?o[k]:()=>{}})};
  const timer=w.setTimeout.bind(w);w.setTimeout=(f,ms,...args)=>timer(f,Math.min(ms,30),...args);
  const device={device_id:'light_01',kind:'light',name:'客厅灯',status:'online',state:{power:true,brightness:68},updated_at:now};
  w.fetch=async(url,init={})=>{
   const u=new URL(url,'http://localhost');calls.push([u.pathname,u.search,init.method]);
   if(disconnected)throw Error('测试断网');
   let data={};
   if(u.pathname==='/api/system/status')data={mode:'http',version:'test',backend:'online',hardware:'online',camera:'online',database:'online',model:'test',server_time:now,message:''};
   if(u.pathname==='/api/dashboard/snapshot')data={freshness:'live',server_time:now,sensors:[],devices:[device],recent_events:[]};
   if(u.pathname.endsWith('/commands')){posted=true;data={command_id:'cmd1',status:scenario==='pending-acked'?'pending':scenario,device_id:'light_01',requested_at:now};if(scenario==='acked')device.state.power=false;}
   if(u.pathname==='/api/commands/cmd1'){polls++;data={command_id:'cmd1',status:'acked'};device.state.power=false;}
   if(u.pathname==='/api/sensors/history')data=[{metric:'temperature',unit:'°C',points:[{ts:now,value:24}],aggregated:false}];
   if(u.pathname==='/api/devices/events')data={items:[{event_id:'e'+u.search,device_name:'灯',device_id:'light_01',occurred_at:now,action:'set',state:{power:true},source:'test'}],total:45,page:Number(u.searchParams.get('page')),page_size:20};
   if(u.pathname==='/api/recognition/events')data={items:[],total:0,page:1,page_size:20};
   if(u.pathname==='/api/camera/snapshot')data={camera_id:'cam1',image_url:'/demo/camera-preview.svg',captured_at:now,status:'online',message:'测试照片'};
   if(u.pathname==='/api/person/list')data=[{user_id:'P1',name:'测试人员',avatar_url:null,created_at:now,feature_version:'v1'}];
   return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data};
  };
  w.eval(code);
  const text=()=>w.document.body.textContent;
  const button=name=>Array.from(w.document.querySelectorAll('button')).find(b=>b.textContent===name);
  await until(()=>!text().includes('正在加载页面模块')&&w.document.querySelector('h1'),'initial');
  await delay(100);
  return {dom,w,text,button,calls,errors,disconnect:()=>disconnected=true,get polls(){return polls},get posted(){return posted}};
 }
 const results=[];
 for(const scenario of ['acked','failed','timeout','pending-acked']){
  const a=await start('/',scenario);assert(a.text().includes('未接入'));assert(!a.text().includes('门已关闭'));assert(!a.text().includes('演示模式'));
  a.button('关灯').click();await until(()=>a.posted,'command posted');
  await until(()=>!a.text().includes('等待设备确认…'),'command finished');
  if(['acked','pending-acked'].includes(scenario)){assert(a.text().includes('设备已确认执行'));if(scenario==='pending-acked')assert(a.polls>0)}
  else assert(!a.text().includes('已确认执行'));
  if(scenario==='acked'){a.button('门窗').click();await delay(25);assert(a.text().includes('该分类暂无设备'));a.button('全部').click();await delay(25);a.button('手机使用').click();await delay(25);assert(a.text().includes('把家居面板放到主屏幕'));a.w.document.dispatchEvent(new a.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await delay(25);a.disconnect();a.button('刷新状态').click();await until(()=>a.text().includes('数据连接异常或已过期'),'offline');assert(a.text().includes('上次读数'));assert(a.button('开灯').disabled)}
  assert.deepEqual(a.errors,[]);results.push('command '+scenario+' + unknown state + mode labels');a.dom.window.close();
 }
 const h=await start('/history');await until(()=>h.text().includes('传感器历史曲线'),'history');
 const header=h.w.document.querySelector('.history-stack .panel-header p').textContent;
 const input=h.w.document.querySelector('#history-start');Object.getOwnPropertyDescriptor(h.w.HTMLInputElement.prototype,'value').set.call(input,'2020-01-01T00:00');input.dispatchEvent(new h.w.Event('input',{bubbles:true}));input.dispatchEvent(new h.w.Event('change',{bubbles:true}));
 assert.equal(h.w.document.querySelector('.history-stack .panel-header p').textContent,header);
 h.button('下一页').click();await until(()=>h.text().includes('第 2 / 3 页'),'page 2');assert(h.calls.some(([p,q])=>p==='/api/devices/events'&&q.includes('page=2')));results.push('history applied range and pagination');h.dom.window.close();
 const p=await start('/personnel');await until(()=>p.text().includes('测试人员'),'personnel');assert(p.text().includes('待后端确认'));assert(!p.text().includes('有效（演示）'));p.button('新增授权人员').click();await delay(30);assert(p.w.document.querySelector('[role=dialog]'));p.w.document.dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await delay(30);assert(!p.w.document.querySelector('[role=dialog]'));results.push('personnel state and dialog Escape');p.dom.window.close();
 const m=await start('/monitor');assert(!m.text().includes('Mock 推理'));assert(m.text().includes('门禁执行：待接入独立设备回执'));m.button('摄像头照片').click();await until(()=>m.text().includes('保存状态：待接入保存回执'),'camera receipt');assert(!m.text().includes('后端确认已保存'));results.push('monitor real-mode, pending access and archive receipts');m.dom.window.close();
 console.log(JSON.stringify({passed:true,results},null,2));
})().catch(e=>{console.error(e);process.exit(1)});
