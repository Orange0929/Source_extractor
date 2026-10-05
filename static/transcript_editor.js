/* Edit persisted transcript without changing audio or clip boundaries. */
window.editClipTranscript = function (clip) {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog');
    dialog.style.cssText = 'width:min(620px,90vw);background:#20232b;color:#eee;border:1px solid #687080;border-radius:12px;padding:24px';
    dialog.innerHTML = `<h2>대사 수정</h2>
      <p>들리는 대사를 입력하세요. 모든 검색 모드에 반영됩니다. 오디오와 시간 구간은 유지됩니다.</p>
      <label>대사<textarea rows="5" maxlength="20000" style="display:block;width:100%;box-sizing:border-box;margin:12px 0"></textarea></label>
      <details><summary>처음 저장된 대사</summary><p class="original" style="white-space:pre-wrap"></p><button type="button" class="restore">원문을 입력창에 복원</button></details>
      <p role="status" class="status" style="color:#ffbf87"></p>
      <p>수정 후 현재 검색어와 일치하지 않으면 목록에서 사라질 수 있어요.</p>
      <div style="display:flex;justify-content:flex-end;gap:12px"><button type="button" class="cancel">취소</button><button type="button" class="save">저장</button></div>`;
    const input = dialog.querySelector('textarea');
    const save = dialog.querySelector('.save');
    const cancel = dialog.querySelector('.cancel');
    const status = dialog.querySelector('.status');
    const original = clip.original_transcript ?? clip.transcript ?? '';
    const expected = clip.transcript || '';
    input.value = expected;
    dialog.querySelector('.original').textContent = original;
    dialog.querySelector('.restore').onclick = () => { input.value = original; input.focus(); };
    let busy = false;
    let saved = false;
    dialog.addEventListener('keydown', e => e.stopPropagation());
    dialog.addEventListener('cancel', e => { if (busy) e.preventDefault(); });
    dialog.addEventListener('close', () => { dialog.remove(); resolve(saved); }, {once:true});
    cancel.onclick = () => dialog.close();
    save.onclick = async () => {
      if (busy) return;
      if (!input.value.trim()) { status.textContent = '대사를 입력하세요.'; input.focus(); return; }
      busy = true; save.disabled = cancel.disabled = input.disabled = true;
      dialog.querySelector('.restore').disabled = true;
      status.textContent = '저장 중…';
      try {
        const response = await fetch(`/api/clips/${encodeURIComponent(clip.id)}/transcript`, {
          method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({transcript:input.value, expected_transcript:expected})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || '대사를 저장하지 못했어요.');
        Object.assign(clip, data.clip);
        saved = true;
        dialog.close();
      } catch (e) { status.textContent = e.message; }
      finally {
        busy = false; save.disabled = cancel.disabled = input.disabled = false;
        dialog.querySelector('.restore').disabled = false;
      }
    };
    document.body.appendChild(dialog);
    dialog.showModal();
    input.focus();
  });
};
