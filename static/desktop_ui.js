// The desktop bridge is absent in a normal browser; keep the existing page usable.
(() => {
  const panel = document.getElementById('desktopUpdates');
  const check = document.getElementById('btnCheckUpdate');
  const install = document.getElementById('btnInstallUpdate');
  const restart = document.getElementById('btnRestartUpdate');
  const status = document.getElementById('desktopUpdateStatus');
  const saveLogs = document.getElementById('btnSaveLogs');
  const openCmd = document.getElementById('btnOpenDebugCmd');
  let api = null, timer = null, ready = false;
  function render(state) {
    status.textContent = state.error || state.message || '';
    const working = ['checking','downloading'].includes(state.phase);
    check.disabled = working;
    install.hidden = state.phase !== 'available';
    restart.hidden = state.phase !== 'ready';
    if (working && !timer) timer = setInterval(poll, 1000);
    if (!working && timer) { clearInterval(timer); timer = null; }
  }
  async function poll() {
    try { render(await api.update_status()); }
    catch (e) { render({phase:'error',message:String(e)}); }
  }
  async function call(method) {
    try { render(await api[method]()); }
    catch (e) { render({phase:'error',message:String(e)}); }
  }
  async function connect() {
    if (ready || !window.pywebview?.api) return;
    ready = true; api = window.pywebview.api;
    panel.hidden = false;
    try {
      const info = await api.desktop_info();
      document.getElementById('desktopVersion').textContent = `앱 ${info.version} · GitHub main`;
      await api.ui_ready();
      await poll();
    } catch (e) { status.textContent = '앱 연결 실패: '+e; }
  }
  check.addEventListener('click', () => { render({phase:'checking',message:'GitHub 새 버전 확인 중…'}); call('check_update'); });
  install.addEventListener('click', () => { render({phase:'downloading',message:'업데이트 준비 중…'}); call('start_update'); });
  restart.addEventListener('click', async () => {
    restart.disabled = true;
    try {
      const result = await api.restart_app();
      if (result.error) status.textContent = result.error;
    } catch (e) { status.textContent = String(e); }
    finally { restart.disabled = false; }
  });
  saveLogs.addEventListener('click', async () => {
    saveLogs.disabled = true;
    try {
      const result = await api.save_diagnostic_log();
      status.textContent = result.message || result.error || '';
    } catch (e) { status.textContent = String(e); }
    finally { saveLogs.disabled = false; }
  });
  openCmd.addEventListener('click', async () => {
    openCmd.disabled = true;
    try {
      const result = await api.open_debug_cmd();
      status.textContent = result.message || result.error || '';
    } catch (e) { status.textContent = String(e); }
    finally { openCmd.disabled = false; }
  });
  window.addEventListener('pywebviewready', connect);
  connect();
})();
