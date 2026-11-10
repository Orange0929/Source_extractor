(() => {
  const panel=document.getElementById('sttControl');
  if(!panel)return;
  const find=id=>document.getElementById(id);
  const dialog=find('appSettings');
  let latest=null;
  find('btnAppSettings').onclick=async()=>{
    editing=false;find('sttSettingsNotice').textContent='';
    if(latest)render(latest);
    dialog.showModal();
    try{await refresh();}catch(e){find('sttSettingsNotice').textContent=e.message;}
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
    find('sttDeviceStatus').textContent=`실제 장치: ${data.actual.device||'미정'} · ${data.actual.message||''}`;
    if(!editing){
      find('sttDevice').value=data.settings.device;
      find('sttPerformance').value=data.settings.performance;
      find('sttThreads').value=data.settings.threads;
    }
    find('sttStatus').textContent=`${data.paused?(data.running?'현재 파일 완료 후 일시정지 예정':'일시정지됨'):(data.running?'분석 중':'대기 중')} · 대기 ${data.waiting}개 ${data.counts?`· 완료 ${data.counts.done} / 실패 ${data.counts.error} / 중단 ${data.counts.cancelled}`:''} · ${data.filename||''}`;
    find('sttResume').disabled=!data.paused;
    find('sttPause').disabled=data.paused;
  }
  async function refresh(){render(await request('/api/stt/control'));}
  dialog.querySelectorAll('select,input').forEach(el=>el.addEventListener('input',()=>{editing=true;}));
  find('sttSave').onclick=async()=>{
    try {render(await request('/api/stt/settings',{device:find('sttDevice').value,performance:find('sttPerformance').value,threads:Number(find('sttThreads').value)}));editing=false;
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
