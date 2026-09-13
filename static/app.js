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

const audioPlayer = document.getElementById("audioPlayer");
const playerTitle = document.getElementById("playerTitle");
const downloadLink = document.getElementById("downloadLink");

// manual waveform editor
const sourceAudioSelect = document.getElementById("sourceAudioSelect");
const btnLoadWaveform = document.getElementById("btnLoadWaveform");
const waveformStatus = document.getElementById("waveformStatus");
const waveformViewport = document.getElementById("waveformViewport");
const waveformSurface = document.getElementById("waveformSurface");
const waveformImage = document.getElementById("waveformImage");
const waveSelection = document.getElementById("waveSelection");
const wavePlayhead = document.getElementById("wavePlayhead");
const waveZoom = document.getElementById("waveZoom");
const waveZoomValue = document.getElementById("waveZoomValue");
const sourceAudioPlayer = document.getElementById("sourceAudioPlayer");
const rangeStart = document.getElementById("rangeStart");
const rangeEnd = document.getElementById("rangeEnd");
const rangeDuration = document.getElementById("rangeDuration");
const btnPlaySelection = document.getElementById("btnPlaySelection");
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
let selectionStart = 0;
let selectionEnd = 1;
let dragAnchorTime = null;
let editorLoadToken = 0;

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

    const editBtn = document.createElement("button");
    editBtn.textContent = "구간 편집";
    editBtn.className = "ghost notranslate";
    editBtn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        await openClipInEditor(c);
      } catch (e) {
        alert(e.message);
      }
    });

    rightBox.appendChild(right);
    rightBox.appendChild(editBtn);
    rightBox.appendChild(delBtn);

    m.appendChild(left);
    m.appendChild(rightBox);

    card.appendChild(t);
    card.appendChild(m);

    row.appendChild(cb);
    row.appendChild(card);

    row.addEventListener("click", () => {
      const url = `/api/clip_audio/${c.id}`;
      playerTitle.textContent = c.transcript || "재생";
      audioPlayer.src = url;
      audioPlayer.play().catch(() => {});
      downloadLink.href = url;
      downloadLink.style.display = "inline";
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
  if (editorDuration <= 0) return;

  selectionStart = clamp(selectionStart, 0, editorDuration);
  selectionEnd = clamp(selectionEnd, 0, editorDuration);
  if (selectionEnd < selectionStart) {
    [selectionStart, selectionEnd] = [selectionEnd, selectionStart];
  }
  if (selectionEnd - selectionStart < 0.01) {
    selectionEnd = Math.min(editorDuration, selectionStart + 0.01);
    if (selectionEnd - selectionStart < 0.01) {
      selectionStart = Math.max(0, selectionEnd - 0.01);
    }
  }

  const leftPct = (selectionStart / editorDuration) * 100;
  const widthPct = ((selectionEnd - selectionStart) / editorDuration) * 100;
  waveSelection.style.left = `${leftPct}%`;
  waveSelection.style.width = `${widthPct}%`;

  rangeStart.value = selectionStart.toFixed(3);
  rangeEnd.value = selectionEnd.toFixed(3);
  rangeDuration.value = `${(selectionEnd - selectionStart).toFixed(3)}초`;

  if (scrollIntoView) {
    requestAnimationFrame(() => {
      const leftPx = waveformSurface.offsetWidth * (selectionStart / editorDuration);
      waveformViewport.scrollLeft = Math.max(0, leftPx - waveformViewport.clientWidth * 0.3);
    });
  }
}

function setSelection(start, end, scrollIntoView = false) {
  selectionStart = Number(start || 0);
  selectionEnd = Number(end || 0);
  updateSelectionUI(scrollIntoView);
}

function applyWaveZoom() {
  const zoom = Number(waveZoom.value || 1);
  waveZoomValue.textContent = `${zoom}x`;
  const centerRatio = editorDuration > 0 && waveformSurface.offsetWidth > 0
    ? (waveformViewport.scrollLeft + waveformViewport.clientWidth / 2) / waveformSurface.offsetWidth
    : 0;
  waveformSurface.style.width = `${zoom * 100}%`;
  updateSelectionUI(false);
  requestAnimationFrame(() => {
    if (centerRatio > 0) {
      waveformViewport.scrollLeft = Math.max(
        0,
        waveformSurface.offsetWidth * centerRatio - waveformViewport.clientWidth / 2
      );
    }
  });
}

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

  const token = ++editorLoadToken;
  editorAudioId = audioId;
  editorDuration = 0;
  sourceAudioPlayer.pause();
  waveformViewport.style.display = "none";
  waveformStatus.textContent = "정규화 시간축과 파형을 준비하는 중...";
  btnLoadWaveform.disabled = true;

  const mediaReady = waitForMediaMetadata(sourceAudioPlayer, token);
  const imageReady = waitForImage(waveformImage, token);
  sourceAudioPlayer.src = `/api/audio_source/${encodeURIComponent(audioId)}`;
  waveformImage.src = `/api/audio_waveform/${encodeURIComponent(audioId)}?width=6000&height=160`;
  sourceAudioPlayer.load();

  try {
    await Promise.all([mediaReady, imageReady]);
  } catch (e) {
    if (e.message !== "cancelled") waveformStatus.textContent = e.message;
    throw e;
  } finally {
    if (token === editorLoadToken) btnLoadWaveform.disabled = false;
  }

  if (token !== editorLoadToken) return;
  editorDuration = Number(sourceAudioPlayer.duration || 0);
  if (!Number.isFinite(editorDuration) || editorDuration <= 0) {
    throw new Error("원본 길이를 읽지 못했어요.");
  }

  waveformViewport.style.display = "block";
  waveformStatus.textContent = `전체 ${formatTime(editorDuration)} · 파형을 드래그해 범위를 선택하세요.`;
  manualTranscript.value = transcript || "";
  if (preferredStart != null && preferredEnd != null) {
    const selectedLength = Math.max(0.01, Number(preferredEnd) - Number(preferredStart));
    const suggestedZoom = clamp(Math.ceil(editorDuration / (selectedLength * 5)), 1, 40);
    waveZoom.value = String(suggestedZoom);
  }
  applyWaveZoom();

  const start = preferredStart == null ? 0 : Number(preferredStart);
  const end = preferredEnd == null ? Math.min(editorDuration, start + 1) : Number(preferredEnd);
  setSelection(start, end, true);
}

async function openClipInEditor(clip) {
  await refreshAudios(clip.audio_id);
  sourceAudioSelect.value = clip.audio_id;
  document.querySelector(".clip-editor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  await loadWaveform(clip.audio_id, clip.start_s, clip.end_s, clip.transcript || "");
}

function pointerTime(ev) {
  const rect = waveformSurface.getBoundingClientRect();
  if (!rect.width || editorDuration <= 0) return 0;
  return clamp(((ev.clientX - rect.left) / rect.width) * editorDuration, 0, editorDuration);
}

let dragMode = "";
waveformSurface.addEventListener("pointerdown", (ev) => {
  if (editorDuration <= 0) return;
  ev.preventDefault();
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
    setSelection(t, Math.min(editorDuration, t + 0.01));
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
}
waveformSurface.addEventListener("pointerup", finishWaveDrag);
waveformSurface.addEventListener("pointercancel", finishWaveDrag);

sourceAudioPlayer.addEventListener("timeupdate", () => {
  if (editorDuration > 0) {
    const pct = clamp(sourceAudioPlayer.currentTime / editorDuration, 0, 1) * 100;
    wavePlayhead.style.left = `${pct}%`;
  }
  if (!sourceAudioPlayer.paused && sourceAudioPlayer.currentTime >= selectionEnd - 0.005) {
    if (loopSelection.checked) {
      sourceAudioPlayer.currentTime = selectionStart;
      sourceAudioPlayer.play().catch(() => {});
    } else {
      sourceAudioPlayer.pause();
      sourceAudioPlayer.currentTime = selectionEnd;
    }
  }
});

rangeStart.addEventListener("change", () => setSelection(Number(rangeStart.value), selectionEnd));
rangeEnd.addEventListener("change", () => setSelection(selectionStart, Number(rangeEnd.value)));
waveZoom.addEventListener("input", applyWaveZoom);

btnLoadWaveform.addEventListener("click", async () => {
  try { await loadWaveform(sourceAudioSelect.value); }
  catch (e) { if (e.message !== "cancelled") alert(e.message); }
});

btnPlaySelection.addEventListener("click", () => {
  if (!editorAudioId || editorDuration <= 0) return alert("파형을 먼저 불러오세요.");
  sourceAudioPlayer.currentTime = selectionStart;
  sourceAudioPlayer.play().catch(() => {});
});

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
    alert(`가져오기 완료! (클립 ${res.clips ?? 0}개 / 오디오 ${res.audios ?? 0}개)`);
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
  selectedClipIds.clear();
  updateBulkDeleteButton();
  try { await doSearch(false); } catch (e) {}
});

elProfileSelect.addEventListener("change", async () => {
  selectedClipIds.clear();
  updateBulkDeleteButton();
  resetPlayer();
  sourceAudioPlayer.pause();
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
