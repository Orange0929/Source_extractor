(() => {
  const panel=document.getElementById('sttControl');
  if(!panel)return;
  const find=id=>document.getElementById(id);
  const dialog=find('appSettings');
  let latest=null, hardware=null;
  const deviceValue=settings=>settings.device==='cuda'?'cuda:'+(settings.gpu_index||0):settings.device;
  function devices() {
    const select=find('sttDevice'), selected=editing?select.value:(latest?deviceValue(latest.settings):'auto');
    const options=[new Option('자동 (권장)','auto'),new Option('CPU: '+(hardware?.cpu.name||'확인 중'),'cpu')];
    for(const gpu of hardware?.gpus||[]) {
      const option=new Option(`GPU ${gpu.index}: ${gpu.name} · ${gpu.ready?'런타임 확인됨':'추가 구성 필요'}`,'cuda:'+gpu.index);
      option.disabled=!gpu.ready;options.push(option);
    }
    if(selected.startsWith('cuda:')&&!options.some(o=>o.value===selected))options.push(new Option('지정한 GPU · 감지되지 않음',selected));
    select.replaceChildren(...options);select.value=selected;
  }
  function threadHelp() {
    const manual=find('sttThreadMode').value==='manual';
    find('sttThreadManual').hidden=!manual;
    const count=hardware?.cpu.logical_threads||null;
    if(count)find('sttThreads').max=String(count);
    const threads=count?Math.max(1,Math.floor(count/({eco:4,balanced:2,maximum:1}[find('sttPerformance').value]||2))):null;
    find('sttThreadHelp').textContent=manual
      ?`CPU 분석에 배정할 스레드 수${count?' (1~'+count+')':''}입니다. 높이면 다른 작업이 버벅일 수 있습니다. GPU 사용률 제한은 아닙니다.`
      :`자동 배정${threads?' · 현재 성능 모드: '+threads+' / '+count+'스레드':''}. 다른 작업을 함께 하면 절전 또는 균형을 권장합니다.`;
  }
  async function detect() {
    find('sttHardwareStatus').textContent='CPU·GPU와 실행 구성을 확인하는 중…';
    try {
      hardware=await request('/api/stt/hardware');devices();threadHelp();if(latest)render(latest);
      find('sttHardwareStatus').textContent=`CPU: ${hardware.cpu.name} (${hardware.cpu.logical_threads}스레드) · ${hardware.gpus.map(g=>g.name+': '+g.reason).join(' · ')||hardware.message||'NVIDIA GPU 감지 안 됨'}`;
    }catch(e){find('sttHardwareStatus').textContent='장치 확인 실패: '+e.message;}
  }
  find('btnAppSettings').onclick=async()=>{
    editing=false;find('sttSettingsNotice').textContent='';
    if(latest)render(latest);
    dialog.showModal();
    try{await refresh();}catch(e){find('sttSettingsNotice').textContent=e.message;}
    await detect();
  };
  find('sttSettingsClose').onclick=()=>dialog.close();
  dialog.addEventListener('keydown',e=>e.stopPropagation());
  dialog.addEventListener('close',()=>{editing=false;if(latest)render(latest);});
  let editing=false;
  async function request(path,body) {
    const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok)throw new Error(data.detail||data.error||'요청 실패');
    return data;
  }
  function render(data) {
    latest=data;
    panel.hidden=!data.running && data.waiting===0;
    const actualName=data.actual.device==='cpu'?(hardware?.cpu.name||'CPU'):data.actual.device==='cuda'?(hardware?.gpus.find(g=>g.index===(data.actual.gpu_index||0))?.name||'NVIDIA GPU'):'미정';
    find('sttDeviceStatus').textContent=`실제 장치: ${actualName} · ${data.actual.message||''}`;
    if(!editing){
      devices();
      find('sttPerformance').value=data.settings.performance;
      find('sttThreadMode').value=data.settings.threads===0?'auto':'manual';
      find('sttThreads').value=data.settings.threads||1;
    }
    threadHelp();
    find('sttStatus').textContent=`${data.paused?(data.running?'현재 파일 완료 후 일시정지 예정':'일시정지됨'):(data.running?'분석 중':'대기 중')} · 대기 ${data.waiting}개 ${data.counts?`· 완료 ${data.counts.done} / 실패 ${data.counts.error} / 중단 ${data.counts.cancelled}`:''} · ${data.filename||''}`;
    find('sttResume').disabled=!data.paused;
    find('sttPause').disabled=data.paused;
  }
  async function refresh(){render(await request('/api/stt/control'));}
  dialog.querySelectorAll('select,input').forEach(el=>el.addEventListener('input',()=>{editing=true;threadHelp();}));
  find('sttSave').onclick=async()=>{
    try {render(await request('/api/stt/settings',{device:find('sttDevice').value.startsWith('cuda:')?'cuda':find('sttDevice').value,gpu_index:find('sttDevice').value.startsWith('cuda:')?Number(find('sttDevice').value.split(':')[1]):(latest?.settings.gpu_index||0),performance:find('sttPerformance').value,threads:find('sttThreadMode').value==='auto'?0:Number(find('sttThreads').value)}));editing=false;
      find('sttSettingsNotice').textContent='설정 저장됨. 현재 파일이 끝난 뒤 다음 분석부터 적용합니다.';await refresh();
    }catch(e){find('sttSettingsNotice').textContent=e.message;}
  };
  for(const [id,action] of [['sttPause','pause'],['sttResume','resume'],['sttStop','stop']])find(id).onclick=async()=>{
    if(action==='stop'&&!confirm('현재 분석과 대기 중인 분석을 중단할까요? 완료된 대사는 보존됩니다. 다시 분석하려면 실패·미완료 음성 재분석을 사용하세요.'))return;
    try {render(await request('/api/stt/control/'+action,{}));find('sttNotice').textContent=action==='stop'?'중단 요청됨. 업로드는 별도이며 계속될 수 있습니다.':'';}
    catch(e){find('sttNotice').textContent=e.message;}
  };
  async function poll(){try{await refresh();}catch(e){find('sttStatus').textContent='분석 상태 확인 실패: '+e.message;}finally{setTimeout(poll,2000);}}
  poll();
})();
