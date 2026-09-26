// ===== DOM =====
const elProfileName = document.getElementById("profileName");
const btnAddProfile = document.getElementById("btnAddProfile");
const elProfileSelect = document.getElementById("profileSelect");
const btnDeleteProfile = document.getElementById("btnDeleteProfile");

const btnExportProfile = document.getElementById("btnExportProfile");
const importZip = document.getElementById("importZip");

const uploadForm = document.getElementById("uploadForm");
const elAudioFile = document.getElementById("audioFile");

const elSearchMode = document.getElementById("searchMode");
const searchModeHelp = document.getElementById("searchModeHelp");
const elSearchInput = document.getElementById("searchInput");
const btnSearch = document.getElementById("btnSearch");
const btnReset = document.getElementById("btnReset");
const elResults = document.getElementById("results");

const btnSelectAll = document.getElementById("btnSelectAll");
const btnSelectNone = document.getElementById("btnSelectNone");
const btnDownloadSelected = document.getElementById("btnDownloadSelected");
const btnDeleteSelected = document.getElementById("btnDeleteSelected");
const btnLoadMore = document.getElementById("btnLoadMore");
const resultSummary = document.getElementById("resultSummary");
const profileLoading = document.getElementById("profileLoading");

const audioPlayer = document.getElementById("audioPlayer");
const playerTitle = document.getElementById("playerTitle");
const downloadLink = document.getElementById("downloadLink");

// manual waveform editor
const clipEditor = document.getElementById("clipEditor");
const editorClipTitle = document.getElementById("editorClipTitle");
const waveContextSeconds = document.getElementById("waveContextSeconds");
const waveContextSummary = document.getElementById("waveContextSummary");
const btnApplyWaveSettings = document.getElementById("btnApplyWaveSettings");
const sourceAudioSelect = document.getElementById("sourceAudioSelect");
const btnLoadWaveform = document.getElementById("btnLoadWaveform");
const waveformStatus = document.getElementById("waveformStatus");
const waveformViewport = document.getElementById("waveformViewport");
const waveformSurface = document.getElementById("waveformSurface");
const audioPlot = new AudioPlot(document.getElementById("waveformCanvas"), waveformViewport, waveformSurface);
const pitchStatus = document.getElementById("pitchStatus");
let analysisController = null;
let pitchRequest = 0;
async function analysisRequest(kind, token) {
  const url = new URL(`/api/audio_analysis/${encodeURIComponent(editorAudioId)}`, window.location.origin);
  url.searchParams.set("kind", kind);
  url.searchParams.set("start_s", editorViewStart.toFixed(6));
  url.searchParams.set("end_s", editorViewEnd.toFixed(6));
  const signal = analysisController.signal;
  for (let attempt = 0; attempt < 60; attempt++) {
    if (token !== editorLoadToken || signal.aborted) throw new Error("cancelled");
    const response = await fetch(url, {signal});
    if (response.status === 429 && attempt < 59) {
      await new Promise(resolve => setTimeout(resolve, 1000)); continue;
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "분석 실패");
    return data;
  }
}
async function loadPitch(token) {
  const request = ++pitchRequest;
  audioPlot.points = []; audioPlot.draw();
  if (editorViewEnd - editorViewStart > 90) {
    pitchStatus.textContent = "피치는 90초 이내 대사 구간에서 표시돼요. 대사를 클릭해 주세요."; return;
  }
  pitchStatus.textContent = "피치 불러오는 중… 저장된 결과가 없으면 분석합니다. 재생·구간 선택은 가능합니다.";
  try {
    const data = await analysisRequest("pitch", token);
    if (token !== editorLoadToken || request !== pitchRequest) return;
    audioPlot.setPoints(data.points);
    pitchStatus.textContent = data.points.some(p => p[1] != null)
      ? "노란 선: FCPE 피치 · C4 = 가운데 도 · 무성음/불확실한 구간은 끊어서 표시 · 배경음이 있으면 오차 가능"
      : "이 구간에서는 신뢰할 수 있는 피치를 찾지 못했어요.";
  } catch (e) {
    if (token === editorLoadToken && request === pitchRequest && e.name !== "AbortError") pitchStatus.textContent = e.message;
  }
}
document.getElementById("waveGain").addEventListener("input", ev => {
  audioPlot.gain = Number(ev.target.value);
  document.getElementById("waveGainValue").textContent = audioPlot.gain.toFixed(1) + "×";
  audioPlot.draw();
});
document.getElementById("btnPitch").addEventListener("click", () => {
  if (editorDuration > 0 && audioPlot.data) loadPitch(editorLoadToken);
});
const waveSelection = document.getElementById("waveSelection");
const wavePlayhead = document.getElementById("wavePlayhead");
audioPlot.attachBars(document.getElementById("timeScroll"), document.getElementById("pitchScroll"));
const btnExpandEditor = document.getElementById("btnExpandEditor");
let editorPlaceholder = null;
let previousBodyOverflow = "";
function expandEditor(expand) {
  if (expand === clipEditor.classList.contains("is-expanded")) return;
  const start = audioPlot.hStart, end = audioPlot.hEnd;
  if (expand) {
    editorPlaceholder = document.createComment("editor position");
    clipEditor.before(editorPlaceholder);
    document.body.appendChild(clipEditor);
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  } else {
    if (editorPlaceholder?.isConnected) editorPlaceholder.replaceWith(clipEditor);
    else document.querySelector("main").appendChild(clipEditor);
    editorPlaceholder = null;
    document.body.style.overflow = previousBodyOverflow;
  }
  clipEditor.classList.toggle("is-expanded", expand);
  btnExpandEditor.setAttribute("aria-expanded", String(expand));
  btnExpandEditor.textContent = expand ? "⛶ 원래 화면 (Esc)" : "⛶ 편집 화면 확대";
  audioPlot.horizontal(start, end);
  btnExpandEditor.focus({preventScroll:true});
}
btnExpandEditor.addEventListener("click", () => expandEditor(!clipEditor.classList.contains("is-expanded")));
document.addEventListener("keydown", ev => {
  if (ev.key === "Escape" && clipEditor.classList.contains("is-expanded")) {
    ev.preventDefault(); expandEditor(false);
  }
});
const sourceAudioPlayer = document.getElementById("sourceAudioPlayer");
const rangeStart = document.getElementById("rangeStart");
const rangeEnd = document.getElementById("rangeEnd");
const rangeDuration = document.getElementById("rangeDuration");
const btnPlaySelection = document.getElementById("btnPlaySelection");
const btnDownloadRange = document.getElementById("btnDownloadRange");
const loopSelection = document.getElementById("loopSelection");
const manualTranscript = document.getElementById("manualTranscript");
const btnSaveManualClip = document.getElementById("btnSaveManualClip");

// ✅ jobs UI
const jobsArea = document.getElementById("jobsArea");

// ✅ master UI
const masterBox = document.getElementById("masterBox");
const masterProgress = document.getElementById("masterProgress");
const masterPct = document.getElementById("masterPct");
const btnCancelAll = document.getElementById("btnCancelAll");
const btnClearJobs = document.getElementById("btnClearJobs");

let profiles = [];

// 검색 결과 캐시 + 선택 상태
let lastResults = [];
const selectedClipIds = new Set();
const PAGE_SIZE = 100;
let totalResults = 0;
let hasMoreResults = false;

let profileAudios = [];
let editorAudioId = "";
let editorDuration = 0;
let editorViewStart = 0;
let editorViewEnd = 0;
let selectionStart = 0;
let selectionEnd = 1;
let dragAnchorTime = null;
let editorLoadToken = 0;
let activeEditorRow = null;
let activeClipBounds = null;

const WAVE_CONTEXT_STORAGE_KEY = "sourceExtractor.waveContextSeconds";
const SEARCH_MODE_HELP = {
  basic: "표기 그대로 검색 · 띄어쓰기/기호는 무시하지만 발음 변화나 다른 문자 표기는 변환하지 않습니다.",
  ko_sound: "형태소 분석 기반 발음 검색 · 연음·동화·된소리·구개음화·ㅎ 변화·ㄴ 첨가·겹받침·7종성을 적용합니다. ㅔ/ㅐ는 함께 검색합니다. 사투리와 실제 발음 변형은 다를 수 있습니다.",
  jp_sound: "가나를 기준으로 검색 · 로마자나 한글 입력은 일본어 가나로 추정 변환합니다.",
  continuous: "음소열 검색 · u do / 우도 / ㅜ도 지원. ㅔ/ㅐ는 함께 검색합니다. 받침 연결은 ㄴ아 / ㄴ 아 / n a처럼 입력하세요. 원문에 ㄴ 받침 뒤 아가 이어진 구간만 찾으며, 단순 나는 제외합니다.",
};
function updateSearchModeHelp() {
  searchModeHelp.textContent = SEARCH_MODE_HELP[elSearchMode.value] || SEARCH_MODE_HELP.basic;
}
updateSearchModeHelp();
const savedWaveContextRaw = localStorage.getItem(WAVE_CONTEXT_STORAGE_KEY);
const savedWaveContext = Number(savedWaveContextRaw);
waveContextSeconds.value = savedWaveContextRaw !== null && Number.isFinite(savedWaveContext)
  ? String(Math.min(30, Math.max(0, savedWaveContext)))
  : "2";
waveContextSummary.textContent = `현재: 앞뒤 ${waveContextSeconds.value}초`;

// job poll timers
const jobTimers = new Map(); // jobId -> timer

// ✅ 전체 취소/전체 진행 계산용 상태
let cancelAllRequested = false;
let currentUploadXhr = null;        // 현재 업로드 중인 XHR
const knownJobIds = new Set();      // 실제 job_id들(업로드 완료된 것들)
const tempUploadingIds = new Set(); // uploading-... 임시 카드 id들

// ===== Helpers =====
function currentProfileId() {
  return elProfileSelect.value || "";
}

async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiPostForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiPostJson(url, obj) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj || {})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiDelete(url) {
  const res = await fetch(url, { method: "DELETE" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "삭제 실패");
  return data;
}

function resetPlayer() {
  audioPlayer.pause();
  audioPlayer.src = "";
  playerTitle.textContent = "재생할 항목을 선택하세요";
  downloadLink.href = "#";
  downloadLink.style.display = "none";
}

function updateBulkDeleteButton() {
  btnDownloadSelected.textContent = `선택 WAV 받기(${selectedClipIds.size})`;
  btnDownloadSelected.disabled = selectedClipIds.size === 0;
  btnDeleteSelected.textContent = `선택 삭제(${selectedClipIds.size})`;
  btnDeleteSelected.disabled = selectedClipIds.size === 0;
}

function buildSearchUrl(path, extra = {}) {
  const url = new URL(path, window.location.origin);
  url.searchParams.set("q", elSearchInput.value || "");
  url.searchParams.set("mode", elSearchMode.value || "basic");
  const pid = currentProfileId();
  if (pid) url.searchParams.set("profile_id", pid);
  for (const [key, value] of Object.entries(extra)) {
    url.searchParams.set(key, String(value));
  }
  return url;
}

async function refreshProfiles() {
  const data = await apiGet("/api/profiles");
  profiles = data.profiles || [];

  elProfileSelect.innerHTML = "";
  if (profiles.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "프로필을 먼저 추가하세요";
    elProfileSelect.appendChild(opt);
    btnDeleteProfile.disabled = true;
    btnExportProfile.disabled = true;
  } else {
    for (const p of profiles) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      opt.className = "notranslate";
      elProfileSelect.appendChild(opt);
    }
    btnDeleteProfile.disabled = false;
    btnExportProfile.disabled = false;
  }
}

async function refreshAudios(preferredAudioId = "") {
  const pid = currentProfileId();
  sourceAudioSelect.innerHTML = "";
  profileAudios = [];

  if (!pid) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "프로필을 먼저 선택하세요";
    sourceAudioSelect.appendChild(opt);
    btnLoadWaveform.disabled = true;
    return;
  }

  const url = new URL("/api/audios", window.location.origin);
  url.searchParams.set("profile_id", pid);
  const data = await apiGet(url.toString());
  profileAudios = data.audios || [];

  if (profileAudios.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "업로드된 원본 오디오가 없어요";
    sourceAudioSelect.appendChild(opt);
    btnLoadWaveform.disabled = true;
    return;
  }

  for (const audio of profileAudios) {
    const opt = document.createElement("option");
    opt.value = audio.id;
    const duration = Number(audio.duration || 0);
    opt.textContent = `${audio.orig_filename || audio.path || "audio"}${duration ? ` (${formatTime(duration)})` : ""}`;
    sourceAudioSelect.appendChild(opt);
  }

  if (preferredAudioId && profileAudios.some(a => a.id === preferredAudioId)) {
    sourceAudioSelect.value = preferredAudioId;
  }
  btnLoadWaveform.disabled = false;
}

// ===== master progress =====
function setMasterVisible(show) {
  if (!masterBox) return;
  masterBox.style.display = show ? "block" : "none";
}

function updateMasterFromCards() {
  if (!masterProgress || !masterPct) return;

  const cards = Array.from(jobsArea.querySelectorAll(".jobcard"));
  if (cards.length === 0) {
    masterProgress.value = 0;
    masterPct.textContent = "0%";
    setMasterVisible(false);
    return;
  }

  setMasterVisible(true);

  let sum = 0;
  let doneCount = 0;

  for (const c of cards) {
    const pr = c.querySelector(".jobprogress");
    const v = pr ? Number(pr.value || 0) : 0;
    sum += v;

    const st = (c.dataset.status || "").toLowerCase();
    if (st === "done" || st === "error" || st === "cancelled") doneCount += 1;
  }

  const avg = Math.floor(sum / cards.length);
  masterProgress.value = Math.max(0, Math.min(100, avg));
  masterPct.textContent = `${Math.max(0, Math.min(100, avg))}%`;

  // 전체 취소 버튼은 "작업이 존재할 때"만 켜두기
  if (btnCancelAll) btnCancelAll.disabled = (doneCount === cards.length);
}

function markAllCardsCancelledUI() {
  const cards = Array.from(jobsArea.querySelectorAll(".jobcard"));
  for (const card of cards) {
    const st = (card.dataset.status || "").toLowerCase();
    if (st === "done" || st === "error" || st === "cancelled") continue;

    // 강제로 취소 상태 표시
    card.dataset.status = "cancelled";
    card.classList.add("jobcancel");

    const jobText = card.querySelector(".jobtext");
    const btnCancel = card.querySelector(".btnCancel");
    if (jobText) jobText.textContent = "취소됨";
    if (btnCancel) btnCancel.disabled = true;
  }
}

async function cancelAll() {
  cancelAllRequested = true;

  // 1) 현재 업로드 중이면 업로드 중단
  try {
    if (currentUploadXhr) currentUploadXhr.abort();
  } catch (e) {}

  // 2) 이미 생성된 모든 job_id에 cancel 요청
  const ids = Array.from(knownJobIds);
  await Promise.all(ids.map(async (jobId) => {
    try { await apiPostJson(`/api/jobs/${jobId}/cancel`, {}); }
    catch (e) { /* 개별 실패는 무시 */ }
  }));

  // 3) 폴링 중지 + UI 취소 표시
  for (const jobId of ids) stopJobPolling(jobId);
  markAllCardsCancelledUI();
  updateMasterFromCards();
}

// ===== Results Rendering with checkboxes =====
function updateResultSummary() {
  resultSummary.textContent = `${lastResults.length}개 표시 / 전체 ${totalResults}개`;
  btnLoadMore.style.display = hasMoreResults ? "block" : "none";
  btnLoadMore.disabled = false;
  btnLoadMore.textContent = "더 보기";
}

function renderResults(items, append = false) {
  if (!append) {
    editorTransport.stop();
    expandEditor(false);
    clipEditor.remove();
    clipEditor.style.display = "none";
    activeEditorRow = null;
    lastResults = [];
    elResults.innerHTML = "";
  }

  const incoming = items || [];
  const known = new Set(lastResults.map(x => x.id));
  const newItems = incoming.filter(x => !known.has(x.id));
  lastResults.push(...newItems);
  updateBulkDeleteButton();

  if (!append && newItems.length === 0) {
    const empty = document.createElement("div");
    empty.className = "hint notranslate";
    empty.textContent = "검색 결과가 없어요.";
    elResults.appendChild(empty);
    return;
  }

  for (const c of newItems) {
    const row = document.createElement("div");
    row.className = "result";
    row.style.display = "grid";
    row.style.gridTemplateColumns = "28px 1fr";
    row.style.columnGap = "10px";
    row.style.alignItems = "start";

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = selectedClipIds.has(c.id);
    cb.style.marginTop = "10px";
    cb.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (cb.checked) selectedClipIds.add(c.id);
      else selectedClipIds.delete(c.id);
      updateBulkDeleteButton();
    });

    const card = document.createElement("div");

    const t = document.createElement("div");
    t.className = "t notranslate";
    t.setAttribute("translate", "no");
    t.textContent = c.transcript || "(텍스트 없음)";

    const m = document.createElement("div");
    m.className = "m notranslate";
    m.setAttribute("translate", "no");

    const left = document.createElement("span");
    const dur =
      (c.end_s != null && c.start_s != null)
        ? ` ${(c.end_s - c.start_s).toFixed(2)}s`
        : "";
    left.textContent = `clip${dur}`;

    const rightBox = document.createElement("span");
    rightBox.style.display = "flex";
    rightBox.style.gap = "8px";
    rightBox.style.alignItems = "center";

    const right = document.createElement("span");
    right.textContent = c.created_at || "";

    const delBtn = document.createElement("button");
    delBtn.textContent = "삭제";
    delBtn.className = "ghost notranslate";
    delBtn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm("이 클립을 삭제할까요?")) return;

      try {
        await apiDelete(`/api/clips/${c.id}`);
        selectedClipIds.delete(c.id);
        updateBulkDeleteButton();

        if ((downloadLink.href || "").includes(`/api/clip_audio/${c.id}`)) {
          resetPlayer();
        }
        await doSearch(false);
      } catch (e) {
        alert(e.message);
      }
    });

    rightBox.appendChild(right);
    rightBox.appendChild(delBtn);

    m.appendChild(left);
    m.appendChild(rightBox);

    card.appendChild(t);
    card.appendChild(m);

    row.appendChild(cb);
    row.appendChild(card);

    row.addEventListener("click", async () => {
      const url = `/api/clip_audio/${c.id}`;
      playerTitle.textContent = c.transcript || "재생";
      audioPlayer.src = url;
      audioPlayer.play().catch(() => {});
      downloadLink.href = url;
      downloadLink.style.display = "inline";
      try {
        await openClipInEditor(c, row);
      } catch (e) {
        if (e.message !== "cancelled") alert(e.message);
      }
    });

    elResults.appendChild(row);
  }
}

async function doSearch(append = false) {
  const offset = append ? lastResults.length : 0;
  const url = buildSearchUrl("/api/search", { limit: PAGE_SIZE, offset });
  const data = await apiGet(url.toString());
  totalResults = Number(data.total || 0);
  hasMoreResults = Boolean(data.has_more);
  renderResults(data.results || [], append);
  updateResultSummary();
}

// ===== Manual waveform range editor =====
function formatTime(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  const minutes = Math.floor(value / 60);
  const secs = value - minutes * 60;
  return `${minutes}:${secs.toFixed(3).padStart(6, "0")}`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function updateSelectionUI(scrollIntoView = false) {
  const viewDuration = editorViewEnd - editorViewStart;
  if (editorDuration <= 0 || viewDuration <= 0) return;

  selectionStart = clamp(selectionStart, editorViewStart, editorViewEnd);
  selectionEnd = clamp(selectionEnd, editorViewStart, editorViewEnd);
  if (selectionEnd < selectionStart) {
    [selectionStart, selectionEnd] = [selectionEnd, selectionStart];
  }
  if (selectionEnd - selectionStart < 0.01) {
    selectionEnd = Math.min(editorViewEnd, selectionStart + 0.01);
    if (selectionEnd - selectionStart < 0.01) {
      selectionStart = Math.max(editorViewStart, selectionEnd - 0.01);
    }
  }

  const leftPct = ((selectionStart - editorViewStart) / viewDuration) * 100;
  const widthPct = ((selectionEnd - selectionStart) / viewDuration) * 100;
  waveSelection.style.left = `${leftPct}%`;
  waveSelection.style.width = `${widthPct}%`;

  rangeStart.value = selectionStart.toFixed(3);
  rangeEnd.value = selectionEnd.toFixed(3);
  rangeDuration.value = `${(selectionEnd - selectionStart).toFixed(3)}초`;

  if (scrollIntoView) {
    requestAnimationFrame(() => {
      const leftPx = waveformSurface.offsetWidth * ((selectionStart - editorViewStart) / viewDuration);
      waveformViewport.scrollLeft = Math.max(0, leftPx - waveformViewport.clientWidth * 0.3);
    });
  }
}

function setSelection(start, end, scrollIntoView = false) {
  selectionStart = Number(start || 0);
  selectionEnd = Number(end || 0);
  updateSelectionUI(scrollIntoView);
}

function showEditorIndicator(time) {
  const duration = editorViewEnd - editorViewStart;
  wavePlayhead.style.display = duration > 0 ? "block" : "none";
  if (duration > 0) wavePlayhead.style.left = `${clamp((time-editorViewStart)/duration,0,1)*100}%`;
}
const editorTransport = new EditorTransport(sourceAudioPlayer, showEditorIndicator,
  () => loopSelection.checked, message => { waveformStatus.textContent = message; });
function loadSelectionPreview() {
  if (!editorAudioId || selectionEnd-selectionStart < .01) return;
  editorTransport.prepare(editorAudioId, selectionStart, selectionEnd, "selection");
}
function toggleCursorPlayback() {
  if (!editorAudioId || !audioPlot.data || editorViewEnd <= editorViewStart) return;
  if (editorTransport.active) { editorTransport.stop(); return; }
  editorTransport.playSelectionFromCursor(editorAudioId, selectionStart, selectionEnd);
}
document.addEventListener("keydown", ev => {
  if (ev.code !== "Space" || ev.ctrlKey || ev.altKey || ev.metaKey) return;
  const target = ev.target;
  if (target.closest('input, textarea, select, audio, [contenteditable]:not([contenteditable="false"]), [role="slider"]')) return;
  if (!clipEditor.isConnected || clipEditor.style.display === "none" || !audioPlot.data) return;
  // Buttons retain their keyboard behavior outside the focused editor.
  if (!clipEditor.classList.contains("is-expanded") && target.closest('button, a') && !clipEditor.contains(target)) return;
  ev.preventDefault();
  if (!ev.repeat) toggleCursorPlayback();
});

function waitForMediaMetadata(media, token) {
  return new Promise((resolve, reject) => {
    const done = () => {
      cleanup();
      if (token !== editorLoadToken) return reject(new Error("cancelled"));
      resolve();
    };
    const failed = () => {
      cleanup();
      reject(new Error("원본 오디오를 재생할 수 없어요."));
    };
    const cleanup = () => {
      media.removeEventListener("loadedmetadata", done);
      media.removeEventListener("error", failed);
    };
    media.addEventListener("loadedmetadata", done, { once: true });
    media.addEventListener("error", failed, { once: true });
  });
}

function waitForImage(image, token) {
  return new Promise((resolve, reject) => {
    const done = () => {
      cleanup();
      if (token !== editorLoadToken) return reject(new Error("cancelled"));
      resolve();
    };
    const failed = () => {
      cleanup();
      reject(new Error("파형 이미지를 만들 수 없어요."));
    };
    const cleanup = () => {
      image.removeEventListener("load", done);
      image.removeEventListener("error", failed);
    };
    image.addEventListener("load", done, { once: true });
    image.addEventListener("error", failed, { once: true });
  });
}

async function loadWaveform(audioId, preferredStart = null, preferredEnd = null, transcript = "") {
  if (!audioId) throw new Error("원본 오디오를 선택하세요.");

  editorTransport.stop();
  const token = ++editorLoadToken;
  if (analysisController) analysisController.abort();
  analysisController = new AbortController();
  audioPlot.clear();
  pitchStatus.textContent = "파형을 준비하는 중…";
  editorAudioId = audioId;
  editorDuration = 0;
  editorViewStart = 0;
  editorViewEnd = 0;
  sourceAudioPlayer.pause();
  waveformViewport.style.display = "none";
  waveformStatus.textContent = "정규화 시간축과 파형을 준비하는 중...";
  btnLoadWaveform.disabled = true;

  const mediaReady = waitForMediaMetadata(sourceAudioPlayer, token);
  sourceAudioPlayer.src = `/api/audio_source/${encodeURIComponent(audioId)}`;
  sourceAudioPlayer.load();

  try {
    await mediaReady;
    if (token !== editorLoadToken) return;

    editorDuration = Number(sourceAudioPlayer.duration || 0);
    if (!Number.isFinite(editorDuration) || editorDuration <= 0) {
      throw new Error("원본 길이를 읽지 못했어요.");
    }

    if (preferredStart != null && preferredEnd != null) {
      const start = clamp(Number(preferredStart), 0, editorDuration);
      const end = clamp(Number(preferredEnd), start + 0.01, editorDuration);
      const contextSeconds = clamp(Number(waveContextSeconds.value || 0), 0, 30);
      editorViewStart = Math.max(0, start - contextSeconds);
      editorViewEnd = Math.min(editorDuration, end + contextSeconds);
    } else {
      editorViewStart = 0;
      editorViewEnd = editorDuration;
    }

    const waveData = await analysisRequest("waveform", token);
    if (token !== editorLoadToken) return;
    audioPlot.data = waveData;
  } catch (e) {
    if (e.message !== "cancelled") waveformStatus.textContent = e.message;
    throw e;
  } finally {
    if (token === editorLoadToken) btnLoadWaveform.disabled = false;
  }

  if (token !== editorLoadToken) return;
  waveformViewport.style.display = "block";
  // Wait for display:block to have a real width before the first wheel gesture.
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  audioPlot.activate();
  const selectedLength = Math.max(0, Number(preferredEnd) - Number(preferredStart));
  const visibleLength = editorViewEnd - editorViewStart;
  waveformStatus.textContent = preferredStart == null
    ? `원본 전체 ${formatTime(editorDuration)} 표시 중`
    : `파형 ${visibleLength.toFixed(3)}초만 표시 중 · Whisper ${selectedLength.toFixed(3)}초 + 앞뒤 최대 ${Number(waveContextSeconds.value || 0)}초`;
  manualTranscript.value = transcript || "";
  audioPlot.horizontal(0, 1);

  const start = preferredStart == null ? 0 : Number(preferredStart);
  const end = preferredEnd == null ? Math.min(editorDuration, start + 1) : Number(preferredEnd);
  setSelection(start, end, true);
  editorTransport.place(start);
  loadSelectionPreview();
  audioPlot.draw();
  loadPitch(token);
}

async function openClipInEditor(clip, row) {
  if (activeEditorRow && activeEditorRow !== row) activeEditorRow.classList.remove("active");
  activeEditorRow = row;
  row.classList.add("active");
  row.appendChild(clipEditor);
  clipEditor.style.display = "block";
  editorClipTitle.textContent = clip.transcript || "(텍스트 없음)";
  activeClipBounds = {
    audioId: clip.audio_id,
    start: Number(clip.start_s),
    end: Number(clip.end_s),
    transcript: clip.transcript || ""
  };
  await refreshAudios(clip.audio_id);
  sourceAudioSelect.value = clip.audio_id;
  await loadWaveform(clip.audio_id, clip.start_s, clip.end_s, clip.transcript || "");
}

function pointerTime(ev) {
  const rect = waveformSurface.getBoundingClientRect();
  const viewDuration = editorViewEnd - editorViewStart;
  if (!rect.width || viewDuration <= 0) return editorViewStart;
  return clamp(
    editorViewStart + ((ev.clientX - rect.left) / rect.width) * viewDuration,
    editorViewStart,
    editorViewEnd
  );
}

let dragMode = "";
waveformSurface.addEventListener("pointerdown", (ev) => {
  if (editorDuration <= 0 || ev.button !== 0) return;
  ev.preventDefault();
  document.activeElement?.blur();
  if (ev.target.closest(".wave-ruler")) {
    editorTransport.place(pointerTime(ev));
    return;
  }
  editorTransport.stop();
  waveformSurface.setPointerCapture(ev.pointerId);
  const t = pointerTime(ev);
  if (ev.target.classList.contains("left")) {
    dragMode = "left";
    dragAnchorTime = selectionEnd;
  } else if (ev.target.classList.contains("right")) {
    dragMode = "right";
    dragAnchorTime = selectionStart;
  } else {
    dragMode = "new";
    dragAnchorTime = t;
    setSelection(t, Math.min(editorViewEnd, t + 0.01));
  }
});

waveformSurface.addEventListener("pointermove", (ev) => {
  if (!dragMode || dragAnchorTime == null) return;
  const t = pointerTime(ev);
  if (dragMode === "left") setSelection(Math.min(t, dragAnchorTime), Math.max(t, dragAnchorTime));
  else if (dragMode === "right") setSelection(Math.min(dragAnchorTime, t), Math.max(dragAnchorTime, t));
  else setSelection(Math.min(dragAnchorTime, t), Math.max(dragAnchorTime, t));
});

function finishWaveDrag(ev) {
  if (!dragMode) return;
  try { waveformSurface.releasePointerCapture(ev.pointerId); } catch (e) {}
  dragMode = "";
  dragAnchorTime = null;
  loadSelectionPreview();
}
waveformSurface.addEventListener("pointerup", finishWaveDrag);
waveformSurface.addEventListener("pointercancel", finishWaveDrag);

rangeStart.addEventListener("change", () => {
  setSelection(Number(rangeStart.value), selectionEnd);
  loadSelectionPreview();
});
rangeEnd.addEventListener("change", () => {
  setSelection(selectionStart, Number(rangeEnd.value));
  loadSelectionPreview();
});


btnLoadWaveform.addEventListener("click", async () => {
  try {
    activeClipBounds = null;
    editorClipTitle.textContent = "원본 전체에서 직접 추출";
    await loadWaveform(sourceAudioSelect.value);
  }
  catch (e) { if (e.message !== "cancelled") alert(e.message); }
});

btnApplyWaveSettings.addEventListener("click", async () => {
  const contextSeconds = clamp(Number(waveContextSeconds.value || 0), 0, 30);
  waveContextSeconds.value = String(contextSeconds);
  waveContextSummary.textContent = `현재: 앞뒤 ${contextSeconds}초`;
  localStorage.setItem(WAVE_CONTEXT_STORAGE_KEY, String(contextSeconds));
  if (!activeClipBounds) return;

  btnApplyWaveSettings.disabled = true;
  try {
    await loadWaveform(
      activeClipBounds.audioId,
      activeClipBounds.start,
      activeClipBounds.end,
      activeClipBounds.transcript
    );
  } catch (e) {
    if (e.message !== "cancelled") alert(e.message);
  } finally {
    btnApplyWaveSettings.disabled = false;
  }
});

btnPlaySelection.addEventListener("click", () => {
  if (!editorAudioId || editorDuration <= 0) return alert("파형을 먼저 불러오세요.");
  editorTransport.place(selectionStart);
  loadSelectionPreview();
  editorTransport.play();
});

btnDownloadRange.addEventListener("click", () => {
  if (!editorAudioId || editorDuration <= 0) return alert("파형을 먼저 불러오세요.");
  if (selectionEnd - selectionStart < 0.01) return alert("받을 구간을 드래그해서 선택하세요.");
  const url = new URL(`/api/audio_range/${encodeURIComponent(editorAudioId)}`, window.location.origin);
  url.searchParams.set("start_s", selectionStart.toFixed(6));
  url.searchParams.set("end_s", selectionEnd.toFixed(6));
  url.searchParams.set("filename", manualTranscript.value || "선택 구간");
  const link = document.createElement("a");
  link.href = url.toString();
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
});

clipEditor.addEventListener("click", (ev) => ev.stopPropagation());

btnSaveManualClip.addEventListener("click", async () => {
  const pid = currentProfileId();
  if (!pid || !editorAudioId) return alert("프로필과 원본 오디오를 선택하세요.");
  if (selectionEnd - selectionStart < 0.01) return alert("저장할 구간을 드래그해서 선택하세요.");

  btnSaveManualClip.disabled = true;
  try {
    const data = await apiPostJson("/api/clips/manual", {
      profile_id: pid,
      audio_id: editorAudioId,
      start_s: selectionStart,
      end_s: selectionEnd,
      transcript: manualTranscript.value || ""
    });
    await doSearch(false);
    alert(`새 클립으로 저장했어요: ${data.clip?.transcript || "수동 구간"}`);
  } catch (e) {
    alert(e.message);
  } finally {
    btnSaveManualClip.disabled = false;
  }
});

// ===== Job UI (multi) =====
function createJobCard(jobId, fileLabel) {
  const card = document.createElement("div");
  card.className = "jobcard";
  card.dataset.jobId = jobId;
  card.dataset.status = "running";

  card.innerHTML = `
    <div class="jobhead">
      <div class="jobtitle notranslate" translate="no">
        <b>STT</b> <span class="mono">${escapeHtml(fileLabel || "")}</span>
      </div>
      <button class="danger ghost notranslate btnCancel" type="button">취소</button>
    </div>
    <div class="jobrow">
      <div class="jobtext notranslate" translate="no">대기중...</div>
      <div class="jobpct notranslate" translate="no">0%</div>
    </div>
    <progress class="jobprogress" value="0" max="100"></progress>
  `;

  const btnCancel = card.querySelector(".btnCancel");
  btnCancel.addEventListener("click", async () => {
    try {
      const realId = card.dataset.jobId || jobId;
      if (realId && !String(realId).startsWith("uploading-")) {
        await apiPostJson(`/api/jobs/${realId}/cancel`, {});
      } else {
        // 업로드 중 임시 카드면 UI만 취소 표시
        card.dataset.status = "cancelled";
        card.classList.add("jobcancel");
        btnCancel.disabled = true;
        const jobText = card.querySelector(".jobtext");
        if (jobText) jobText.textContent = "취소됨(업로드 중단)";
      }
    } catch (e) {
      alert(e.message);
    } finally {
      updateMasterFromCards();
    }
  });

  jobsArea.prepend(card);
  updateMasterFromCards();
  return card;
}

function updateJobCard(card, job, prefixText) {
  const jobText = card.querySelector(".jobtext");
  const jobPct = card.querySelector(".jobpct");
  const jobProgress = card.querySelector(".jobprogress");
  const btnCancel = card.querySelector(".btnCancel");

  const p = Math.max(0, Math.min(100, Math.floor(job.progress ?? 0)));
  jobProgress.value = p;
  jobPct.textContent = `${p}%`;

  const msg = job.message || "";
  jobText.textContent = (prefixText ? `${prefixText} / ` : "") + msg;

  const st = (job.status || "").toLowerCase();
  if (st) card.dataset.status = st;

  if (st === "done") {
    btnCancel.disabled = true;
    card.classList.add("jobdone");
  } else if (st === "error") {
    btnCancel.disabled = true;
    card.classList.add("joberror");
  } else if (st === "cancelled") {
    btnCancel.disabled = true;
    card.classList.add("jobcancel");
  }

  updateMasterFromCards();
}

function startJobPolling(jobId, card, prefixText) {
  stopJobPolling(jobId);

  const tick = async () => {
    if (cancelAllRequested) return;

    try {
      const data = await apiGet(`/api/jobs/${jobId}`);
      const job = data.job;

      updateJobCard(card, job, prefixText);

      const st = (job.status || "").toLowerCase();
      if (st === "done" || st === "error" || st === "cancelled") {
        stopJobPolling(jobId);

        // 완료되면 검색 자동 갱신
        if (st === "done") {
          await doSearch().catch(() => {});
          await refreshAudios().catch(() => {});
        }
      }
    } catch (e) {
      // 서버 리로드 등 일시 에러는 무시하고 계속
    }
  };

  tick();
  const t = setInterval(tick, 700);
  jobTimers.set(jobId, t);
}

function stopJobPolling(jobId) {
  const t = jobTimers.get(jobId);
  if (t) {
    clearInterval(t);
    jobTimers.delete(jobId);
  }
}

// ===== Upload with upload-progress (XHR) =====
function uploadWithProgress(profileId, file, prefixText, onUploadProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    currentUploadXhr = xhr;

    xhr.open("POST", "/api/upload", true);

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onUploadProgress) {
        const pct = Math.floor((evt.loaded / evt.total) * 100);
        onUploadProgress(pct, prefixText);
      }
    };

    xhr.onload = () => {
      currentUploadXhr = null;
      try {
        const data = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || "업로드 실패"));
      } catch (e) {
        reject(new Error("서버 응답 파싱 실패"));
      }
    };

    xhr.onerror = () => {
      currentUploadXhr = null;
      reject(new Error("네트워크 오류"));
    };

    xhr.onabort = () => {
      currentUploadXhr = null;
      reject(new Error("업로드 취소됨"));
    };

    const fd = new FormData();
    fd.append("profile_id", profileId);
    fd.append("audio", file);
    xhr.send(fd);
  });
}

// ===== Events =====
btnAddProfile.addEventListener("click", async () => {
  try {
    const name = (elProfileName.value || "").trim();
    if (!name) return alert("프로필 이름을 입력하세요.");

    const fd = new FormData();
    fd.append("name", name);
    await apiPostForm("/api/profiles", fd);

    elProfileName.value = "";
    await refreshProfiles();
    await refreshAudios();
    await doSearch();
  } catch (e) {
    alert(e.message);
  }
});

btnDeleteProfile.addEventListener("click", async () => {
  const pid = currentProfileId();
  if (!pid) return alert("삭제할 프로필이 없어요.");

  const pname = elProfileSelect.options[elProfileSelect.selectedIndex]?.textContent || "";
  const ok = confirm(
    `프로필 '${pname}'을(를) 삭제할까요?\n` +
    `※ 해당 프로필의 클립/원본 업로드 파일/캐시까지 함께 삭제됩니다.`
  );
  if (!ok) return;

  try {
    await apiDelete(`/api/profiles/${pid}`);
    resetPlayer();
    selectedClipIds.clear();
    updateBulkDeleteButton();
    await refreshProfiles();
    await refreshAudios();
    await doSearch();
  } catch (e) {
    alert(e.message);
  }
});

// ✅ Export
btnExportProfile.addEventListener("click", () => {
  const pid = currentProfileId();
  if (!pid) return alert("프로필을 먼저 선택하세요.");
  window.location.href = `/api/export/profile/${pid}`;
});

// ✅ Import
importZip.addEventListener("change", async (ev) => {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;

  try {
    const fd = new FormData();
    fd.append("file", f);

    const res = await apiPostForm("/api/import", fd);

    await refreshProfiles();

    // ✅ import된 프로필로 자동 선택
    const importedId = res?.imported_profile?.id;
    if (importedId) {
      elProfileSelect.value = importedId;
    }

    await refreshAudios();
    await doSearch();
    alert(`가져오기 완료! (클립 ${res.clips ?? 0}개 / 오디오 ${res.audios ?? 0}개 / 피치 ${res.pitch_results ?? 0}구간)` + (res.pitch_warnings ? `\n피치 ${res.pitch_warnings}구간은 저장본을 사용할 수 없어 열 때 다시 분석합니다.` : ""));
  } catch (e) {
    alert(e.message);
  } finally {
    ev.target.value = "";
  }
});


// ✅ 전체 취소 버튼
if (btnCancelAll) {
  btnCancelAll.addEventListener("click", async () => {
    const ok = confirm("현재 업로드/STT 작업을 전부 취소할까요?");
    if (!ok) return;
    await cancelAll();
  });
}

// ✅ 작업 목록 지우기(UI만)
if (btnClearJobs) {
  btnClearJobs.addEventListener("click", () => {
    // 폴링 정리
    for (const [jobId, t] of jobTimers.entries()) {
      clearInterval(t);
    }
    jobTimers.clear();

    knownJobIds.clear();
    tempUploadingIds.clear();
    cancelAllRequested = false;
    currentUploadXhr = null;

    jobsArea.innerHTML = "";
    updateMasterFromCards(); // master 숨김 처리 포함
  });
}

// ✅ Multi upload:
// - 업로드는 순차(XHR로 진행률 표시)
// - 업로드 완료 즉시 job 폴링 시작 (STT는 서버에서 병렬로 동시에 돌아감)
uploadForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    const pid = currentProfileId();
    if (!pid) return alert("프로필을 먼저 선택/생성하세요.");

    const files = Array.from(elAudioFile.files || []);
    if (files.length === 0) return alert("오디오 파일을 선택하세요.");

    // 시작 시 상태 리셋
    cancelAllRequested = false;
    setMasterVisible(true);

    // 업로드 중에는 업로드만 잠깐 막기
    uploadForm.querySelector("button[type='submit']").disabled = true;
    elAudioFile.disabled = true;

    for (let i = 0; i < files.length; i++) {
      if (cancelAllRequested) break;

      const f = files[i];
      const prefix = `(${i + 1}/${files.length}) ${f.name}`;

      // job 카드 먼저 만들고 "업로드중"으로 표시
      const tempJobId = `uploading-${Date.now()}-${i}`;
      tempUploadingIds.add(tempJobId);

      const card = createJobCard(tempJobId, prefix);
      updateJobCard(card, { progress: 0, message: "업로드중...", status: "running" }, "");

      let res;
      try {
        res = await uploadWithProgress(
          pid,
          f,
          prefix,
          (pct) => {
            // 업로드는 0~20으로 매핑해서 보여줌
            const mapped = Math.min(20, Math.floor(pct * 0.2));
            updateJobCard(card, { progress: mapped, message: `업로드중... (${pct}%)`, status: "running" }, "");
          }
        );
      } catch (e) {
        // 전체 취소로 인한 abort 포함
        if (cancelAllRequested || String(e.message || "").includes("취소")) {
          card.dataset.status = "cancelled";
          card.classList.add("jobcancel");
          const btnCancel = card.querySelector(".btnCancel");
          if (btnCancel) btnCancel.disabled = true;
          const jobText = card.querySelector(".jobtext");
          if (jobText) jobText.textContent = "취소됨(업로드 중단)";
          updateMasterFromCards();
          break;
        } else {
          card.dataset.status = "error";
          card.classList.add("joberror");
          const btnCancel = card.querySelector(".btnCancel");
          if (btnCancel) btnCancel.disabled = true;
          const jobText = card.querySelector(".jobtext");
          if (jobText) jobText.textContent = `업로드 실패: ${e.message}`;
          updateMasterFromCards();
          continue;
        }
      } finally {
        currentUploadXhr = null;
      }

      if (cancelAllRequested) {
        // 업로드는 끝났는데 바로 전체취소 눌렀을 수도 있음
        const realJobId = res && res.job_id;
        if (realJobId) {
          try { await apiPostJson(`/api/jobs/${realJobId}/cancel`, {}); } catch (e) {}
        }
        card.dataset.status = "cancelled";
        card.classList.add("jobcancel");
        updateMasterFromCards();
        break;
      }

      // 임시 job 카드 -> 진짜 jobId로 교체
      const realJobId = res.job_id;
      knownJobIds.add(realJobId);

      card.dataset.jobId = realJobId;
      tempUploadingIds.delete(tempJobId);

      updateJobCard(card, { progress: 20, message: "STT 대기중...", status: "queued" }, "");

      // 취소 버튼도 실제 jobId로 동작하도록 재바인딩
      const btnCancel = card.querySelector(".btnCancel");
      btnCancel.disabled = false;
      btnCancel.onclick = async () => {
        try { await apiPostJson(`/api/jobs/${realJobId}/cancel`, {}); }
        catch (e) { alert(e.message); }
      };

      // ✅ 여기서부터 각 job 폴링을 "동시에" 시작
      startJobPolling(realJobId, card, prefix);
      await refreshAudios(res.audio?.id || "").catch(() => {});
    }

    elAudioFile.value = "";
    updateMasterFromCards();

  } catch (e) {
    alert(e.message);
  } finally {
    uploadForm.querySelector("button[type='submit']").disabled = false;
    elAudioFile.disabled = false;
  }
});

btnSearch.addEventListener("click", async () => {
  try { await doSearch(false); } catch (e) { alert(e.message); }
});

elSearchInput.addEventListener("keydown", async (ev) => {
  if (ev.key !== "Enter") return;
  ev.preventDefault();
  try { await doSearch(false); } catch (e) { alert(e.message); }
});

btnReset.addEventListener("click", async () => {
  elSearchInput.value = "";
  selectedClipIds.clear();
  updateBulkDeleteButton();
  try { await doSearch(false); } catch (e) { alert(e.message); }
});

elSearchMode.addEventListener("change", async () => {
  updateSearchModeHelp();
  selectedClipIds.clear();
  updateBulkDeleteButton();
  try { await doSearch(false); } catch (e) {}
});

elProfileSelect.addEventListener("change", async () => {
  profileLoading.hidden = false;
  elProfileSelect.disabled = true;
  elResults.setAttribute("aria-busy", "true");
  resultSummary.textContent = "프로필 불러오는 중…";
  // Let the progress bar paint before the first network/disk request starts.
  await new Promise(resolve => requestAnimationFrame(resolve));
  selectedClipIds.clear();
  updateBulkDeleteButton();
  resetPlayer();
  editorTransport.stop();
  sourceAudioPlayer.removeAttribute("src");
  waveformViewport.style.display = "none";
  waveformStatus.textContent = "원본 오디오를 선택하세요.";
  editorAudioId = "";
  editorDuration = 0;
  try {
    await refreshAudios();
    await doSearch(false);
  } catch (e) {
    alert(e.message);
  } finally {
    profileLoading.hidden = true;
    elProfileSelect.disabled = false;
    elResults.removeAttribute("aria-busy");
  }
});

btnLoadMore.addEventListener("click", async () => {
  btnLoadMore.disabled = true;
  btnLoadMore.textContent = "불러오는 중...";
  try { await doSearch(true); }
  catch (e) {
    btnLoadMore.disabled = false;
    btnLoadMore.textContent = "더 보기";
    alert(e.message);
  }
});

// ✅ bulk select controls
btnSelectAll.addEventListener("click", async () => {
  btnSelectAll.disabled = true;
  try {
    const data = await apiGet(buildSearchUrl("/api/search/ids").toString());
    for (const id of (data.ids || [])) selectedClipIds.add(id);
    for (const cb of elResults.querySelectorAll('input[type="checkbox"]')) cb.checked = true;
    updateBulkDeleteButton();
  } catch (e) {
    alert(e.message);
  } finally {
    btnSelectAll.disabled = false;
  }
});

btnSelectNone.addEventListener("click", async () => {
  selectedClipIds.clear();
  updateBulkDeleteButton();
  for (const cb of elResults.querySelectorAll('input[type="checkbox"]')) cb.checked = false;
});

btnDownloadSelected.addEventListener("click", async () => {
  if (selectedClipIds.size === 0) return;
  btnDownloadSelected.disabled = true;
  btnDownloadSelected.textContent = `WAV ${selectedClipIds.size}개 만드는 중...`;
  try {
    const data = await apiPostJson("/api/clips/bulk_download", {
      clip_ids: Array.from(selectedClipIds)
    });
    const a = document.createElement("a");
    a.href = data.download_url;
    a.download = data.filename || "voice_clips.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (e) {
    alert(e.message);
  } finally {
    updateBulkDeleteButton();
  }
});

// ✅ bulk delete
btnDeleteSelected.addEventListener("click", async () => {
  if (selectedClipIds.size === 0) return;

  const cnt = selectedClipIds.size;
  const ok = confirm(`선택한 클립 ${cnt}개를 삭제할까요?`);
  if (!ok) return;

  try {
    const ids = Array.from(selectedClipIds);
    const res = await apiPostJson("/api/clips/bulk_delete", { clip_ids: ids });

    const cur = downloadLink.href || "";
    for (const id of ids) {
      if (cur.includes(`/api/clip_audio/${id}`)) {
        resetPlayer();
        break;
      }
    }

    selectedClipIds.clear();
    updateBulkDeleteButton();
    await doSearch();

    alert(`삭제 완료: ${res.deleted ?? 0}개`);
  } catch (e) {
    alert(e.message);
  }
});

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// ===== Init =====
(async function init() {
  try {
    await refreshProfiles();
    await refreshAudios();
    await doSearch();
    updateBulkDeleteButton();
    updateMasterFromCards(); // master 숨김 상태 정리
  } catch (e) {
    alert(e.message);
  }
})();
