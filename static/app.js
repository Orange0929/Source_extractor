// ===== DOM =====
const elProfileName = document.getElementById("profileName");
const btnAddProfile = document.getElementById("btnAddProfile");
const elProfileSelect = document.getElementById("profileSelect");
const btnDeleteProfile = document.getElementById("btnDeleteProfile");

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

// progress UI
const jobBox = document.getElementById("jobBox");
const jobText = document.getElementById("jobText");
const jobPct = document.getElementById("jobPct");
const jobProgress = document.getElementById("jobProgress");

let profiles = [];
let jobPollTimer = null;

// 검색 결과 캐시 + 선택 상태
let lastResults = [];
const selectedClipIds = new Set();

// ===== Helpers =====
function currentProfileId() {
  return elProfileSelect.value || "";
}

async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiPostForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiPostJson(url, obj) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj || {})
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "요청 실패");
  return data;
}

async function apiDelete(url) {
  const res = await fetch(url, { method: "DELETE" });
  const data = await res.json();
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

function showJobBox(show) {
  jobBox.style.display = show ? "block" : "none";
}

function setJobProgress(pct, text) {
  const p = Math.max(0, Math.min(100, Math.floor(pct)));
  jobProgress.value = p;
  jobPct.textContent = `${p}%`;
  jobText.textContent = text || "";
}

function stopJobPolling() {
  if (jobPollTimer) {
    clearInterval(jobPollTimer);
    jobPollTimer = null;
  }
}

function disableDuringJob(disabled) {
  btnAddProfile.disabled = disabled;
  btnDeleteProfile.disabled = disabled || profiles.length === 0;
  elProfileSelect.disabled = disabled;
  elAudioFile.disabled = disabled;
  uploadForm.querySelector("button[type='submit']").disabled = disabled;

  btnSearch.disabled = disabled;
  btnReset.disabled = disabled;
  elSearchMode.disabled = disabled;

  btnSelectAll.disabled = disabled;
  btnSelectNone.disabled = disabled;
  btnDeleteSelected.disabled = disabled || selectedClipIds.size === 0;
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
  } else {
    for (const p of profiles) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      opt.className = "notranslate";
      elProfileSelect.appendChild(opt);
    }
    btnDeleteProfile.disabled = false;
  }
}

// ===== Results Rendering with checkboxes =====
function renderResults(items) {
  lastResults = items || [];
  elResults.innerHTML = "";

  // 선택 상태 중, 현재 결과에 없는 건 제거(선택 유지 원하면 이 줄 빼면 됨)
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

    // checkbox
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

    // click to play
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

// ===== Job polling =====
async function startJobPolling(jobId, prefixText) {
  stopJobPolling();
  showJobBox(true);
  disableDuringJob(true);
  setJobProgress(0, (prefixText ? prefixText + " / " : "") + "STT 처리 대기중...");

  async function tick() {
    try {
      const data = await apiGet(`/api/jobs/${jobId}`);
      const job = data.job;

      setJobProgress(job.progress ?? 0, (prefixText ? prefixText + " / " : "") + (job.message || "처리중..."));

      if (job.status === "done") {
        stopJobPolling();
        disableDuringJob(false);
        await doSearch();
        return "done";
      } else if (job.status === "error") {
        stopJobPolling();
        disableDuringJob(false);
        alert(job.message || "처리 중 에러");
        return "error";
      }
    } catch (e) {
      // ignore and retry
    }
    return "running";
  }

  const first = await tick();
  if (first === "done" || first === "error") return first;

  return await new Promise((resolve) => {
    jobPollTimer = setInterval(async () => {
      const r = await tick();
      if (r === "done" || r === "error") {
        clearInterval(jobPollTimer);
        jobPollTimer = null;
        resolve(r);
      }
    }, 700);
  });
}

// ===== Upload with upload-progress (XHR) =====
function uploadWithProgress(profileId, file, prefixText) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload", true);

    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable) {
        const pct = Math.floor((evt.loaded / evt.total) * 100);
        showJobBox(true);
        const mapped = Math.min(20, Math.floor(pct * 0.2));
        setJobProgress(mapped, `${prefixText} / 업로드중... (${pct}%)`);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || "업로드 실패"));
      } catch (e) {
        reject(new Error("서버 응답 파싱 실패"));
      }
    };

    xhr.onerror = () => reject(new Error("네트워크 오류"));

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

// ✅ Multi upload: sequential per file
uploadForm.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    const pid = currentProfileId();
    if (!pid) return alert("프로필을 먼저 선택/생성하세요.");

    const files = Array.from(elAudioFile.files || []);
    if (files.length === 0) return alert("오디오 파일을 선택하세요.");

    disableDuringJob(true);
    showJobBox(true);

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const prefix = `(${i + 1}/${files.length}) ${f.name}`;

      setJobProgress(0, `${prefix} / 업로드 준비중...`);
      const res = await uploadWithProgress(pid, f, prefix);

      if (!res.job_id) {
        alert(`${prefix} / job_id를 받지 못했어요.`);
        continue;
      }

      setJobProgress(20, `${prefix} / STT 시작...`);
      const r = await startJobPolling(res.job_id, prefix);
      if (r === "error") {
        // 에러 나도 다음 파일은 계속 진행(원하면 break로 바꾸면 됨)
      }
    }

    elAudioFile.value = "";
    setJobProgress(100, "모든 파일 처리 완료!");
    setTimeout(() => showJobBox(false), 1200);
    disableDuringJob(false);

  } catch (e) {
    disableDuringJob(false);
    alert(e.message);
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

    // 재생중인 클립이 삭제됐으면 player 초기화
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

// ===== Init =====
(async function init() {
  try {
    await refreshProfiles();
    await doSearch();
    showJobBox(false);
    updateBulkDeleteButton();
  } catch (e) {
    alert(e.message);
  }
})();
