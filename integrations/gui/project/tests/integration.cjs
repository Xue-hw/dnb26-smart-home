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
  let disconnected=false, posted=false,polls=0,faceCommand='c1',lightMode='manual';let savedSettings={temperature_on:30,temperature_off:28,door_open_seconds:30,bulb_linkage:false,retention_days:7};const calls=[],errors=[],streamHandlers=new Map(),settingsReadGates=[],settingsSaveGates=[];let holdSettingsReads=false,holdSettingsSave=false;const extraState={color:'#223344',led_count:4,speed:25};const hasExtras=scenario.startsWith('dual-uno-extras');
  let boardNow=scenario==='history-clock-skew'?new Date(Date.parse(now)-130*86400000).toISOString():now;
  const historyPoint=new Date(Date.parse(boardNow)-1800000).toISOString();
  const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!/canvas|Not implemented|navigation/i.test(e.message))errors.push(e.message)});
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost'+route,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole:vc});
  const w=dom.window;w.TextEncoder=TextEncoder;w.TextDecoder=TextDecoder;w.ResizeObserver=class{observe(){} disconnect(){}};
  w.EventSource=class{addEventListener(type,callback){streamHandlers.set(type,callback)}removeEventListener(type){streamHandlers.delete(type)}close(){}};
  w.URL.createObjectURL=()=> 'blob:mock';w.URL.revokeObjectURL=()=>{};
  w.HTMLCanvasElement.prototype.getContext=function(){return new Proxy({measureText:t=>({width:String(t).length*8}),canvas:this},{get:(o,k)=>k in o?o[k]:()=>{}})};
  const timer=w.setTimeout.bind(w);w.setTimeout=(f,ms,...args)=>timer(f,Math.min(ms,30),...args);
  const device={device_id:'light_01',kind:'light',name:'客厅灯',status:'online',state:{power:true,brightness:68},updated_at:now};
  w.fetch=async(url,init={})=>{
   const u=new URL(url,'http://localhost');calls.push([u.pathname,u.search,init.method,typeof init.body==='string'?JSON.parse(init.body):null]);
   if(disconnected)throw Error('测试断网');
   let data={};
   if(u.pathname==='/api/system/status')data={mode:'http',version:'test',backend:'online',hardware:'online',hardware_mode:scenario==='hardware-mock'?'mock':'serial',camera:'online',database:'online',model:'test',server_time:boardNow,message:''};
   if(u.pathname==='/api/dashboard/snapshot')data={freshness:scenario==='snapshot-mock'?'mock':'live',server_time:boardNow,sensors:[],devices:[device],recent_events:[]};
   if(scenario.startsWith('dual-uno')){
    if(u.pathname==='/api/system/status')data={...data,hardware:'offline',hardware_mode:'gateway',hardware_boards:{uno1:{status:scenario.endsWith('offline')?'offline':'online',message:'环境板已连接',capabilities:['temperature','humidity','light']},uno2:{status:hasExtras?'online':'offline',message:'门禁板未连接',capabilities:['door']}}};
   if(u.pathname==='/api/dashboard/snapshot')data={...data,devices:[
     {device_id:'door_01',kind:'door',name:'测试入户门',status:'online',board_id:'uno2',capabilities:hasExtras?['position','pin']:['position'],state:{position:'closed',state_basis:'actuator',...(hasExtras?{pin:'9876'}:{})},updated_at:now},
     {device_id:'garage_door',kind:'door',name:'测试车库门',status:'online',board_id:'uno1',capabilities:hasExtras?['position','pin']:['position'],state:{position:'moving',state_basis:'actuator'},updated_at:now},
     {...device,board_id:'uno1',capabilities:hasExtras?['power','mode','color','led_count']:scenario==='dual-uno-brightness'?['power','mode','brightness']:['power','mode'],state:{power:scenario!=='dual-uno-light-off',mode:lightMode,...(scenario==='dual-uno-brightness'?{brightness:68}:{}),...(hasExtras?{color:extraState.color,led_count:extraState.led_count}:{})}},
     {device_id:'fan_01',kind:'fan',name:'测试风扇',status:'online',board_id:'uno1',capabilities:hasExtras?['power','mode','speed']:['power','mode'],state:{power:false,mode:'auto',...(hasExtras?{speed:extraState.speed}:{})},updated_at:now}
    ]};
   }
   if(u.pathname.endsWith('/commands')){posted=true;const mock=['hardware-mock','snapshot-mock','command-source-mock'].includes(scenario);data={command_id:'cmd1',status:mock?'acked':scenario==='pending-acked'?'pending':scenario,source:mock?'mock':'serial',device_id:'light_01',requested_at:now};if(scenario==='acked'||mock)device.state.power=false;}
   if(scenario.startsWith('dual-uno')&&u.pathname.endsWith('/commands')){data={command_id:'cmd1',status:scenario.endsWith('pending')?'pending':scenario==='dual-uno-extras-pin-fail'?'failed':'acked',device_id:'light_01',source:'serial',error_message:scenario==='dual-uno-extras-pin-fail'?'controller rejected secret 1357':undefined};if(init.body){const params=JSON.parse(init.body).params;if(params.mode==='auto')lightMode='auto';for(const key of ['color','led_count','speed'])if(key in params)extraState[key]=params[key];}}
   if(scenario.endsWith('pending')&&scenario.startsWith('dual-uno')&&u.pathname==='/api/commands/cmd1')return new Promise(()=>{});
   if(u.pathname==='/api/commands/cmd1'){polls++;data={command_id:'cmd1',status:'acked'};device.state.power=false;}
   if(u.pathname==='/api/sensors/history')data=[{metric:'temperature',unit:'°C',points:[{ts:now,value:24}],aggregated:false}];
   if(u.pathname==='/api/devices/events')data={items:[{event_id:'e'+u.search,device_name:'灯',device_id:'light_01',occurred_at:now,action:'set',state:{power:true},source:'test'}],total:45,page:Number(u.searchParams.get('page')),page_size:20};
   if(u.pathname==='/api/recognition/events')data={items:[],total:0,page:1,page_size:20};
   if(scenario==='history-clock-skew'){
    const inRange=Date.parse(u.searchParams.get('start'))<=Date.parse(historyPoint)&&Date.parse(u.searchParams.get('end'))>=Date.parse(historyPoint);
    if(u.pathname==='/api/sensors/history')data=[{metric:'temperature',unit:'°C',points:inRange?[{ts:historyPoint,value:24}]:[],aggregated:false}];
    if(u.pathname==='/api/devices/events')data={items:inRange?[{event_id:'board-event',device_name:'板端历史设备',device_id:'light_01',occurred_at:historyPoint,action:'set',state:{power:true},source:'test'}]:[],total:inRange?1:0,page:1,page_size:20};
   }
   if(u.pathname==='/api/camera/snapshot')data={camera_id:'cam1',image_url:'/demo/camera-preview.svg',captured_at:now,status:'online',message:'测试照片'};
   if(u.pathname==='/api/vision/live'){
    const serverNow=scenario==='clock-skew'?new Date(Date.parse(now)-130*86400000).toISOString():now;
    data={server_time:scenario==='server-time-missing'?undefined:serverNow,frame_id:8,captured_at:scenario==='live-stale'?'2000-01-01T00:00:00Z':serverNow,face_captured_at:['face-stale','live-stale'].includes(scenario)?'2000-01-01T00:00:00Z':scenario==='face-missing'?null:serverNow,objects:[],faces:[{user_id:'p1',user_name:'授权测试',identity_matched:true,liveness_status:'passed',access_granted:true,command_id:['receipt-swap','live-mock-receipt'].includes(scenario)?faceCommand:null}],width:640,height:480,camera_status:'online'};
   }
   if(u.pathname==='/api/commands/c1')data={command_id:'c1',status:'acked',source:scenario==='live-mock-receipt'?'mock':'serial'};
   if(u.pathname==='/api/commands/c2')return new Promise(()=>{});
   if(u.pathname==='/api/alerts')data={items:[{id:'a1',code:'camera_offline',severity:'warning',message:'测试摄像头离线',active:true,acknowledged:false,created_at:now}]};
   if(u.pathname==='/api/settings'){if(init.method==='PUT'){if(holdSettingsSave)await new Promise(resolve=>settingsSaveGates.push(resolve));savedSettings=JSON.parse(init.body);}data={...savedSettings};if(init.method!=='PUT'&&holdSettingsReads)await new Promise(resolve=>settingsReadGates.push(resolve));}
   if(u.pathname==='/api/models')data={items:[{name:'custom-yolo',status:'ready',classes:['drone','fire_extinguisher','bulb']}]};
   if(u.pathname==='/api/auth/status')data={write_access:scenario.startsWith('temperature-')||(route!=='/system'&&!scenario.endsWith('readonly')),authentication_required:true};
   if(scenario.startsWith('temperature-')&&u.pathname==='/api/system/status')data={...data,hardware_mode:'gateway',hardware_boards:{uno1:{status:scenario==='temperature-offline'?'offline':'online',message:'环境板',capabilities:['temperature'],temperature_on:scenario==='temperature-mismatch'?29:30,temperature_off:28,temperature_config_synced:scenario!=='temperature-unconfirmed'}}};
   if(u.pathname==='/api/person/list')data=[{user_id:'P1',name:'测试人员',avatar_url:null,created_at:now,feature_version:'v1'}];
   return {ok:true,headers:{get:()=> 'application/json'},json:async()=>data};
  };
  w.eval(code);
  const text=()=>w.document.body.textContent;
  const button=name=>Array.from(w.document.querySelectorAll('button')).find(b=>b.textContent===name);
  await until(()=>!text().includes('正在加载页面模块')&&w.document.querySelector('h1'),'initial');
  await delay(100);
  return {dom,w,text,button,calls,errors,holdSettingsReads:()=>holdSettingsReads=true,releaseSettingsRead:()=>settingsReadGates.shift()?.(),get waitingSettingsReads(){return settingsReadGates.length},holdSettingsSave:()=>holdSettingsSave=true,releaseSettingsSave:()=>settingsSaveGates.shift()?.(),get waitingSettingsSaves(){return settingsSaveGates.length},disconnect:()=>disconnected=true,advanceFaceCommand:()=>faceCommand='c2',advanceDeviceClock:()=>{boardNow=new Date(Date.parse(boardNow)+60000).toISOString();streamHandlers.get('system.status.changed')?.({data:JSON.stringify({type:'system.status.changed'})})},get boardNow(){return boardNow},get polls(){return polls},get posted(){return posted}};
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
 const boardHistory=await start('/history','history-clock-skew');
 await until(()=>boardHistory.text().includes('板端历史设备'),'board history visible despite clock offset');
 assert(boardHistory.text().includes('设备时间与浏览器有偏差'));
 function assertBoardRange(hours){
  const query=boardHistory.calls.filter(([p])=>p==='/api/sensors/history').at(-1)[1];const params=new URLSearchParams(query);const end=Date.parse(params.get('end')),start=Date.parse(params.get('start'));
  assert(Math.abs(end-Date.parse(boardHistory.boardNow))<3000,'history end must follow board time');assert.equal(end-start,hours*3600000);
  for(const endpoint of ['/api/devices/events','/api/recognition/events']){const other=new URLSearchParams(boardHistory.calls.filter(([p])=>p===endpoint).at(-1)[1]);assert.equal(other.get('start'),params.get('start'));assert.equal(other.get('end'),params.get('end'));}
 }
 assertBoardRange(24);
 const historyInput=(id,value)=>{const input=boardHistory.w.document.querySelector(id);Object.getOwnPropertyDescriptor(boardHistory.w.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new boardHistory.w.Event('input',{bubbles:true}));input.dispatchEvent(new boardHistory.w.Event('change',{bubbles:true}));};
 historyInput('#history-start','2020-01-01T00:00');historyInput('#history-end','2020-01-02T00:00');await delay(30);
 const statusCalls=boardHistory.calls.filter(([p])=>p==='/api/system/status').length;boardHistory.advanceDeviceClock();await until(()=>boardHistory.calls.filter(([p])=>p==='/api/system/status').length>statusCalls,'clock resync');await delay(30);assert.equal(boardHistory.w.document.querySelector('#history-start').value,'2020-01-01T00:00');assert.equal(boardHistory.w.document.querySelector('#history-end').value,'2020-01-02T00:00');
 boardHistory.button('查询').click();await until(()=>boardHistory.text().includes('该区间没有设备事件'),'manual historical range');
 const manual=new URLSearchParams(boardHistory.calls.filter(([p])=>p==='/api/devices/events').at(-1)[1]);assert.equal(manual.get('start'),new Date('2020-01-01T00:00').toISOString());assert.equal(manual.get('end'),new Date('2020-01-02T00:00').toISOString());
 for(const [button,hours] of [['最近1小时',1],['最近24小时',24],['最近7天',168]]){const count=boardHistory.calls.length;boardHistory.button(button).click();await until(()=>boardHistory.calls.length>count,'quick range sent '+hours);await delay(50);await until(()=>!boardHistory.button(button).disabled,'quick range completed '+hours);assertBoardRange(hours);}
 boardHistory.button('重置').click();await delay(30);boardHistory.button('查询').click();await delay(40);assertBoardRange(24);boardHistory.dom.window.close();results.push('130-day board clock drives initial reset and all quick history ranges without changing manual input');
 const p=await start('/personnel');await until(()=>p.text().includes('测试人员'),'personnel');assert(p.text().includes('待后端确认'));assert(!p.text().includes('有效（演示）'));p.button('新增授权人员').click();await delay(30);assert(p.w.document.querySelector('[role=dialog]'));p.w.document.dispatchEvent(new p.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await delay(30);assert(!p.w.document.querySelector('[role=dialog]'));results.push('personnel state and dialog Escape');p.dom.window.close();
 const m=await start('/monitor');assert(!m.text().includes('Mock 推理'));assert(m.text().includes('照片仅供身份核对'));assert(!m.w.document.querySelector('.verification-result').textContent.includes('验证通过，门状态以设备反馈为准'));m.button('摄像头照片').click();await until(()=>m.text().includes('保存状态：待接入保存回执'),'camera receipt');assert(!m.text().includes('后端确认已保存'));results.push('monitor real-mode, pending access and archive receipts');m.dom.window.close();
 const live=await start('/monitor','live-valid');await until(()=>live.text().includes('验证通过，门状态以设备反馈为准'),'live pass');live.disconnect();await until(()=>live.text().includes('人脸输入异常或结果已过期，不保留通过提示'),'live disconnect clears pass');assert(!live.text().includes('验证通过，门状态以设备反馈为准'));live.dom.window.close();results.push('live verification cleared after input failure');
 const stale=await start('/monitor','live-stale');assert(!stale.text().includes('验证通过，门状态以设备反馈为准'));assert(stale.text().includes('画面不可用或已过期'));stale.dom.window.close();results.push('stale live frame cannot show access grant');
 for(const scenario of ['face-stale','face-missing']){const face=await start('/monitor',scenario);assert(face.text().includes('实时输入'));assert(!face.text().includes('验证通过，门状态以设备反馈为准'));assert(face.text().includes('人脸输入异常或结果已过期，不保留通过提示'));face.dom.window.close();results.push(scenario+' cannot show access grant with fresh object frames');}
 const hardware=await start('/','dual-uno');
 const row=name=>Array.from(hardware.w.document.querySelectorAll('.control-row')).find(item=>item.textContent.includes(name));
 assert(row('测试车库门').textContent.includes('移动中'));assert(row('测试车库门').querySelector('button').disabled);
 assert(row('测试入户门').querySelector('button').disabled,'offline board must disable even stale-online device');
 assert(row('客厅灯').textContent.includes('手动模式'));assert(row('测试风扇').textContent.includes('自动模式'));
 assert(!hardware.w.document.querySelector('[aria-label="目标灯光亮度"]'),'unsupported brightness must be hidden');
 const model=hardware.w.document.querySelector('.house-model');assert(model);assert(model.textContent.includes('灯开启'));assert(!model.querySelector('.scene-status').textContent.includes('0%'));hardware.button('俯视').click();await delay(20);assert.equal(hardware.button('俯视').getAttribute('aria-pressed'),'true');hardware.w.document.querySelector('[aria-label="复位模型视角"]').click();await delay(20);assert.equal(hardware.button('立体').getAttribute('aria-pressed'),'true');assert.equal(hardware.w.document.querySelector('.hero-stats strong').textContent,'3 / 4');
 assert(!hardware.text().includes('窗户：'));assert(hardware.text().includes('装饰窗未接设备'));
 assert(hardware.text().includes('执行器反馈，未验证物理位置'));assert(!hardware.text().includes('门已关闭'));
 assert(!row('客厅灯').querySelector('button[aria-label]').disabled);assert(row('测试风扇').querySelector('button[aria-label]').disabled);assert.deepEqual(hardware.errors,[]);hardware.dom.window.close();
 const boards=await start('/system','dual-uno');const boardRows=Array.from(boards.w.document.querySelectorAll('.service-list > div'));
 assert(boardRows.some(item=>item.textContent.includes('UNO1')&&item.textContent.includes('在线')));assert(boardRows.some(item=>item.textContent.includes('UNO2')&&item.textContent.includes('离线')));boards.dom.window.close();
 const hardwareOff=await start('/','dual-uno-light-off');const offModel=hardwareOff.w.document.querySelector('.house-model');assert(offModel.textContent.includes('灯关闭'));hardwareOff.dom.window.close();
 const metrics=await start('/history','dual-uno');const options=Array.from(metrics.w.document.querySelectorAll('#history-metric option')).map(item=>item.value);assert(options.includes('light'));assert(!options.includes('smoke'));assert(!options.includes('rain'));metrics.dom.window.close();results.push('dual UNO status, actuator basis, garage movement, unsupported controls and sensors');
 const auto=await start('/','dual-uno-auto');auto.w.document.querySelector('[aria-label="客厅灯恢复自动"]').click();await until(()=>auto.text().includes('设备已确认执行'),'restore auto ACK');const autoPost=auto.calls.find(([p,,method])=>p.endsWith('/commands')&&method==='POST');assert.deepEqual(autoPost[3],{action:'set',params:{mode:'auto'}});const autoRow=Array.from(auto.w.document.querySelectorAll('.control-row')).find(item=>item.textContent.includes('客厅灯'));assert(autoRow.textContent.includes('自动模式'));assert(auto.w.document.querySelector('[aria-label="客厅灯恢复自动"]').disabled);auto.dom.window.close();results.push('restore auto sends only mode and waits for reported mode');
 for(const scenario of ['dual-uno-readonly','dual-uno-offline','dual-uno-pending']){
  const control=await start('/',scenario);const autoButton=control.w.document.querySelector('[aria-label="客厅灯恢复自动"]');assert(autoButton);
  if(scenario==='dual-uno-pending'){autoButton.click();await until(()=>control.posted,'pending auto posted');await delay(20);assert(autoButton.disabled);const lightRow=Array.from(control.w.document.querySelectorAll('.control-row')).find(item=>item.textContent.includes('客厅灯'));assert(lightRow.querySelector('button').disabled);assert(!control.text().includes('设备已确认执行'));}
  else{assert(autoButton.disabled);autoButton.click();await delay(20);assert(!control.posted);}
  control.dom.window.close();
 }results.push('restore auto disabled for readonly offline and pending commands');
 const manualControl=await start('/','dual-uno-manual');manualControl.button('关灯').click();await until(()=>manualControl.posted,'manual power posted');assert.deepEqual(manualControl.calls.find(([p,,method])=>p.endsWith('/commands')&&method==='POST')[3],{action:'toggle',params:{}});manualControl.dom.window.close();
 const brightness=await start('/','dual-uno-brightness');const slider=brightness.w.document.querySelector('[aria-label="目标灯光亮度"]');Object.getOwnPropertyDescriptor(brightness.w.HTMLInputElement.prototype,'value').set.call(slider,'42');slider.dispatchEvent(new brightness.w.Event('input',{bubbles:true}));slider.dispatchEvent(new brightness.w.Event('change',{bubbles:true}));await delay(20);brightness.button('应用亮度').click();await until(()=>brightness.posted,'brightness posted');assert.deepEqual(brightness.calls.find(([p,,method])=>p.endsWith('/commands')&&method==='POST')[3],{action:'set',params:{brightness:42}});brightness.dom.window.close();results.push('manual power and brightness requests do not inject mode');
 for(const scenario of ['temperature-synced','temperature-mismatch','temperature-offline','temperature-unconfirmed']){
  const temp=await start('/system',scenario);const sync=temp.w.document.querySelector('[aria-label="UNO1 温控同步状态"]');assert(sync);assert.equal(sync.textContent.includes('温控阈值已同步'),scenario==='temperature-synced');assert.equal(temp.w.document.querySelector('#temperature_on').step,'0.1');assert.equal(temp.w.document.querySelector('#door_open_seconds').step,'1');
  if(scenario==='temperature-synced'){
   const input=temp.w.document.querySelector('#temperature_on');Object.getOwnPropertyDescriptor(temp.w.HTMLInputElement.prototype,'value').set.call(input,'30.1');input.dispatchEvent(new temp.w.Event('input',{bubbles:true}));input.dispatchEvent(new temp.w.Event('change',{bubbles:true}));await delay(20);assert(sync.textContent.includes('温控阈值已同步'),'unsaved draft must not replace backend desired settings');temp.button('保存后端配置').click();await until(()=>temp.text().includes('配置已保存在后端，等待硬件确认'),'settings saved awaiting hardware');assert(temp.w.document.querySelector('[aria-label="UNO1 温控同步状态"]').textContent.includes('温控阈值待同步'));assert.equal(temp.calls.find(([p,,method])=>p==='/api/settings'&&method==='PUT')[3].temperature_on,30.1);
  }
  temp.dom.window.close();
 }results.push('temperature sync requires online UNO actual values and confirmation; save only changes desired values');
 const configRace=await start('/system','temperature-synced');configRace.holdSettingsReads();configRace.button('检查服务').click();await until(()=>configRace.waitingSettingsReads===1,'old settings GET blocked');
 const configInput=configRace.w.document.querySelector('#temperature_on');Object.getOwnPropertyDescriptor(configRace.w.HTMLInputElement.prototype,'value').set.call(configInput,'30.1');configInput.dispatchEvent(new configRace.w.Event('input',{bubbles:true}));configInput.dispatchEvent(new configRace.w.Event('change',{bubbles:true}));await delay(20);configRace.button('保存后端配置').click();await until(()=>configRace.text().includes('配置已保存在后端，等待硬件确认'),'new PUT saved before old GET');configRace.releaseSettingsRead();await delay(60);assert.equal(configRace.w.document.querySelector('#temperature_on').value,'30.1','old GET must not overwrite newer saved draft');assert(configRace.w.document.querySelector('[aria-label="UNO1 温控同步状态"]').textContent.includes('温控阈值待同步'));configRace.dom.window.close();results.push('old settings GET cannot overwrite newer PUT or claim hardware sync');
 const configDuringSave=await start('/system','temperature-synced');configDuringSave.holdSettingsSave();configDuringSave.button('保存后端配置').click();await until(()=>configDuringSave.waitingSettingsSaves===1,'PUT blocked');const beforeRefresh=configDuringSave.calls.filter(([p])=>p==='/api/settings').length;assert(configDuringSave.button('检查服务').disabled);configDuringSave.button('检查服务').click();await delay(40);assert.equal(configDuringSave.calls.filter(([p])=>p==='/api/settings').length,beforeRefresh,'refresh cannot fetch old settings during PUT');configDuringSave.releaseSettingsSave();await until(()=>configDuringSave.text().includes('配置已保存在后端，等待硬件确认'),'PUT completed');assert(!configDuringSave.button('检查服务').disabled);configDuringSave.dom.window.close();results.push('settings refresh is blocked while PUT is pending');
 const extras=await start('/','dual-uno-extras');
 function editField(app,id,value){const input=app.w.document.querySelector(id);Object.getOwnPropertyDescriptor(app.w.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new app.w.Event('input',{bubbles:true}));input.dispatchEvent(new app.w.Event('change',{bubbles:true}));}
 async function submitExtra(app,label,id,value,expected){const before=app.calls.filter(([p,,method])=>p.endsWith('/commands')&&method==='POST').length;editField(app,id,value);await delay(20);app.button(label).click();await until(()=>app.calls.filter(([p,,method])=>p.endsWith('/commands')&&method==='POST').length>before,label+' posted');await until(()=>!app.button(label).disabled||app.w.document.querySelector(id).value===String(value),label+' acknowledged');await delay(30);const request=app.calls.filter(([p,,method])=>p.endsWith('/commands')&&method==='POST').at(-1);assert.deepEqual(request[3],{action:'set',params:expected});return request;}
 assert(extras.w.document.querySelector('#light_01-color'));assert(extras.w.document.querySelector('#light_01-led-count'));assert(extras.w.document.querySelector('#fan_01-speed'));assert(!extras.text().includes('9876'),'PIN accidentally returned in state must not be rendered');
 await submitExtra(extras,'应用颜色','#light_01-color','#ff0000',{color:'#ff0000'});
 for(const value of ['0','9','1.5']){editField(extras,'#light_01-led-count',value);await delay(20);assert(extras.button('应用灯珠数').disabled);}
 await submitExtra(extras,'应用灯珠数','#light_01-led-count','8',{led_count:8});
 for(const value of ['-1','101','2.5']){editField(extras,'#fan_01-speed',value);await delay(20);assert(extras.button('应用风速').disabled);}
 await submitExtra(extras,'应用风速','#fan_01-speed','0',{speed:0});
 for(const deviceId of ['door_01','garage_door']){const input=extras.w.document.querySelector(`#${deviceId}-pin`);assert.equal(input.type,'password');assert.equal(input.maxLength,4);editField(extras,`#${deviceId}-pin`,'12a4');await delay(20);assert(input.closest('form').querySelector('button').disabled);editField(extras,`#${deviceId}-pin`,'2468');await delay(20);const count=extras.calls.length;input.closest('form').querySelector('button').click();await until(()=>input.value==='','PIN cleared after ACK');assert(extras.calls.length>count);const request=extras.calls.filter(([p,,method])=>p.endsWith('/commands')&&method==='POST').at(-1);assert.equal(request[0],`/api/devices/${deviceId}/commands`);assert.deepEqual(request[3],{action:'set',params:{pin:'2468'}});assert(!extras.text().includes('2468'));}
 extras.dom.window.close();results.push('capability controls validate color count speed and masked door PIN, send one parameter and clear PIN on ACK');
 for(const scenario of ['dual-uno-extras-readonly','dual-uno-extras-offline','dual-uno-extras-pending']){const blocked=await start('/',scenario);if(scenario.endsWith('pending')){editField(blocked,'#light_01-color','#ff0000');await delay(20);blocked.button('应用颜色').click();await until(()=>blocked.posted,'extra command pending');await delay(20);}const inputs=['#light_01-color','#light_01-led-count',...(scenario.endsWith('pending')?[]:['#fan_01-speed'])];for(const id of inputs)assert(blocked.w.document.querySelector(id).disabled);if(scenario.endsWith('readonly'))for(const id of ['door_01','garage_door'])assert(blocked.w.document.querySelector(`#${id}-pin`).disabled);blocked.dom.window.close();}results.push('extended controls obey readonly board-offline and per-device pending protection');
 const pinFailure=await start('/','dual-uno-extras-pin-fail');editField(pinFailure,'#door_01-pin','1357');await delay(20);pinFailure.w.document.querySelector('#door_01-pin').closest('form').querySelector('button').click();await until(()=>pinFailure.text().includes('修改设备 PIN 失败'),'safe PIN failure');assert(!pinFailure.text().includes('1357'));assert(!pinFailure.text().includes('controller rejected secret'));pinFailure.dom.window.close();results.push('PIN controller errors cannot echo secret into GUI');
 const sys=await start('/system');await until(()=>sys.text().includes('custom-yolo'),'system models');assert(sys.text().includes('测试摄像头离线'));assert(sys.button('保存后端配置').disabled);assert.equal(sys.w.document.querySelector('#admin-token').type,'password');sys.dom.window.close();results.push('system models alerts and read-only settings');
 for(const scenario of ['hardware-mock','snapshot-mock']){
  const a=await start('/',scenario);assert(a.text().includes('硬件模拟：Arduino 尚未接入'));assert(a.text().includes('可用模拟设备'));assert(!a.text().includes('报告在线的设备'));
  a.button('关灯').click();await until(()=>a.text().includes('模拟回执已确认'),'mock command acknowledged');assert(!a.text().includes('设备已确认执行'));a.dom.window.close();
  const s=await start('/system',scenario);assert(s.text().includes('未接入 · 模拟回执'));const hardware=Array.from(s.w.document.querySelectorAll('.service-list > div')).find(row=>row.textContent.includes('Arduino'));assert(!hardware.textContent.includes('在线'));s.dom.window.close();
  results.push(scenario+' stays explicit across dashboard command and Arduino status');
 }
 const bySource=await start('/','command-source-mock');bySource.button('关灯').click();await until(()=>bySource.text().includes('模拟回执已确认'),'source-labelled mock ack');assert(!bySource.text().includes('设备已确认执行'));bySource.dom.window.close();results.push('command source mock cannot claim physical execution');
 const skew=await start('/monitor','clock-skew');assert(skew.text().includes('验证通过，门状态以设备反馈为准'));skew.dom.window.close();results.push('fresh board frames tolerate 130 day client/server clock difference');
 const missingClock=await start('/monitor','server-time-missing');assert(!missingClock.text().includes('验证通过，门状态以设备反馈为准'));missingClock.dom.window.close();results.push('missing server clock cannot show access grant');
 const receipt=await start('/monitor','receipt-swap');await until(()=>receipt.text().includes('关联命令：c1')&&receipt.text().includes('控制器已确认执行'),'first face command ACK');receipt.advanceFaceCommand();await until(()=>receipt.text().includes('关联命令：c2'),'next face command pending');assert(!receipt.text().includes('控制器已确认执行'));assert(receipt.text().includes('正在查询执行回执'));receipt.dom.window.close();results.push('new face command never inherits previous command ACK');
 const mockReceipt=await start('/monitor','live-mock-receipt');await until(()=>mockReceipt.text().includes('模拟回执已确认；Arduino 尚未接入'),'live mock receipt');assert(!mockReceipt.text().includes('控制器已确认执行'));mockReceipt.dom.window.close();results.push('live command receipt labels mock source');
 console.log(JSON.stringify({passed:true,results},null,2));
})().catch(e=>{console.error(e);process.exit(1)});
