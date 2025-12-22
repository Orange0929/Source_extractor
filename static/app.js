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
const btnDeleteSelected = document.getElementById("btnDeleteSelected");

const audioPlayer = document.getElementById("audioPlayer");
const playerTitle = document.getElementById("playerTitle");
const downloadLink = document.getElementById("downloadLink");

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
  btnDeleteSelected.textContent = `선택 삭제(${selectedClipIds.size})`;
  btnDeleteSelected.disabled = selectedClipIds.size === 0;
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
function renderResults(items) {
  lastResults = items || [];
  elResults.innerHTML = "";

  const present = new Set(lastResults.map(x => x.id));
  for (const id of Array.from(selectedClipIds)) {
    if (!present.has(id)) selectedClipIds.delete(id);
  }
  updateBulkDeleteButton();

  if (!items || items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "hint notranslate";
    empty.textContent = "검색 결과가 없어요.";
    elResults.appendChild(empty);
    return;
  }

  for (const c of items) {
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
        await doSearch();
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

async function doSearch() {
  const q = elSearchInput.value || "";
  const pid = currentProfileId();
  const mode = elSearchMode.value || "basic";

  const url = new URL("/api/search", window.location.origin);
  url.searchParams.set("q", q);
  url.searchParams.set("mode", mode);
  if (pid) url.searchParams.set("profile_id", pid);

  const data = await apiGet(url.toString());
  renderResults(data.results || []);
}

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
  try { await doSearch(); } catch (e) { alert(e.message); }
});

btnReset.addEventListener("click", async () => {
  elSearchInput.value = "";
  selectedClipIds.clear();
  updateBulkDeleteButton();
  try { await doSearch(); } catch (e) { alert(e.message); }
});

elSearchMode.addEventListener("change", async () => {
  selectedClipIds.clear();
  updateBulkDeleteButton();
  try { await doSearch(); } catch (e) {}
});

// ✅ bulk select controls
btnSelectAll.addEventListener("click", async () => {
  for (const c of lastResults) selectedClipIds.add(c.id);
  updateBulkDeleteButton();
  renderResults(lastResults);
});

btnSelectNone.addEventListener("click", async () => {
  selectedClipIds.clear();
  updateBulkDeleteButton();
  renderResults(lastResults);
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
    await doSearch();
    updateBulkDeleteButton();
    updateMasterFromCards(); // master 숨김 상태 정리
  } catch (e) {
    alert(e.message);
  }
})();
