// Original-level moves preserve all connected clips and analysis caches.
(() => {
  const dialog = document.createElement('dialog');
  dialog.style.cssText = 'width:min(850px,90vw);background:#17191f;color:#fff;border:1px solid #666;border-radius:12px;padding:20px';
  dialog.innerHTML = `<h2>원본 관리 · 프로필 이동</h2>
    <p class="hint">파일명·등록 시각·업로드 묶음으로 찾은 뒤 여러 개 선택하세요. 연결된 대사도 함께 이동합니다. 대상 프로필의 기존 파일과 자동 병합하지 않습니다.</p>
    <p id="moveSource"></p><input id="moveFilter" placeholder="파일명 / 날짜 / 업로드 묶음 검색" style="width:95%">
    <select id="moveFiles" multiple size="14" style="width:100%;margin:10px 0"></select>
    <div class="row"><button id="moveAll">표시된 파일 전체 선택</button><button id="moveNone">선택 해제</button><span id="moveCount"></span></div>
    <div class="row"><label>이동할 프로필 <select id="moveTarget"></select></label><button id="moveSubmit">선택 원본 이동</button><button id="moveClose">닫기</button></div><p id="moveMessage" role="status"></p>`;
  document.body.appendChild(dialog);
  const get = id => dialog.querySelector('#'+id);
  let source = '', sourceName = '', audios = [];
  const selected = new Set();
  function count() { get('moveCount').textContent = `${selected.size}개 선택 / 원본 ${audios.length}개`; }
  function render() {
    const q = get('moveFilter').value.trim().toLowerCase();
    get('moveFiles').replaceChildren();
    for (const a of audios) {
      const label = `${a.orig_filename || a.path} | ${a.created_at || '등록 시각 없음'} | ${a.stt_status || '구버전 상태 미기록'} | 묶음 ${a.upload_batch_id || '미기록'}`;
      if (q && !label.toLowerCase().includes(q)) continue;
      const opt = new Option(label, a.id); opt.selected = selected.has(a.id); get('moveFiles').append(opt);
    }
    count();
  }
  get('moveFilter').oninput = render;
  get('moveFiles').onchange = () => { for (const o of get('moveFiles').options) o.selected ? selected.add(o.value) : selected.delete(o.value); count(); };
  get('moveAll').onclick = () => { for (const o of get('moveFiles').options) selected.add(o.value); render(); };
  get('moveNone').onclick = () => { selected.clear(); render(); };
  get('moveClose').onclick = () => dialog.close();
  document.getElementById('btnManageAudios').onclick = async () => {
    if (elAudioFile.disabled) return alert('현재 업로드가 끝난 뒤 원본 관리를 열어 주세요.');
    source = currentProfileId(); if (!source) return alert('프로필을 선택하세요.');
    sourceName = elProfileSelect.selectedOptions[0].textContent;
    try {
      const [files, ps] = await Promise.all([apiGet(`/api/audios?profile_id=${encodeURIComponent(source)}`), apiGet('/api/profiles')]);
      audios = files.audios; selected.clear(); get('moveFilter').value = ''; get('moveMessage').textContent = '';
      get('moveSource').textContent = `현재 소속: ${sourceName}`;
      get('moveTarget').replaceChildren();
      for (const p of ps.profiles) if (p.id !== source) get('moveTarget').append(new Option(p.name,p.id));
      render(); dialog.showModal();
    } catch (e) { alert(e.message); }
  };
  get('moveSubmit').onclick = async () => {
    const target = get('moveTarget').value;
    if (!target || !selected.size) return alert('이동할 파일과 대상 프로필을 선택하세요.');
    if (!confirm(`${sourceName} → ${get('moveTarget').selectedOptions[0].textContent}\n원본 ${selected.size}개와 연결된 모든 대사를 이동할까요?`)) return;
    get('moveSubmit').disabled = true;
    try {
      const r = await apiPostJson('/api/audios/move', {source_profile_id:source,target_profile_id:target,audio_ids:[...selected]});
      audios = audios.filter(a=>!selected.has(a.id)); selected.clear(); render();
      get('moveMessage').textContent = `원본 ${r.audios}개 · 대사 ${r.clips}개 이동 완료`;
      resetPlayer(); await refreshAudios(); await doSearch();
    } catch (e) { get('moveMessage').textContent = e.message; }
    finally { get('moveSubmit').disabled = false; }
  };
})();
