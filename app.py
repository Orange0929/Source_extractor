from __future__ import annotations

import json
import os
import re
import uuid
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, File, Form, UploadFile, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from faster_whisper import WhisperModel

# =========================
# Paths / App
# =========================
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data.json"
UPLOAD_DIR = BASE_DIR / "uploads"
CACHE_DIR = BASE_DIR / "clips_cache"

UPLOAD_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Voice Search App")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# =========================
# Whisper model config
# =========================
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")   # "cuda" 가능
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")  # cpu면 int8 권장

_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(
            WHISPER_MODEL_NAME,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
    return _whisper_model


# =========================
# In-memory Job store
# =========================
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


class GravelJob:
    @staticmethod
    def default(job_id: str) -> Dict[str, Any]:
        return {
            "job_id": job_id,
            "status": "queued",      # queued | running | done | error
            "progress": 0,           # 0~100
            "message": "대기중...",
            "clips_created": 0,
        }


def set_job(job_id: str, **kwargs):
    with JOBS_LOCK:
        JOBS.setdefault(job_id, GravelJob.default(job_id)).update(kwargs)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with JOBS_LOCK:
        j = JOBS.get(job_id)
        return dict(j) if j else None


# =========================
# Data utils (json DB) - 깨진 JSON 자동 복구
# =========================
def load_data() -> Dict[str, Any]:
    if not DATA_PATH.exists():
        return {"profiles": [], "audios": [], "clips": []}

    try:
        txt = DATA_PATH.read_text(encoding="utf-8")
        if not txt.strip():
            return {"profiles": [], "audios": [], "clips": []}
        data = json.loads(txt)
    except Exception:
        try:
            bak = DATA_PATH.with_suffix(f".broken.{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            DATA_PATH.replace(bak)
        except Exception:
            pass
        return {"profiles": [], "audios": [], "clips": []}

    data.setdefault("profiles", [])
    data.setdefault("audios", [])
    data.setdefault("clips", [])
    return data


def save_data(data: Dict[str, Any]):
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# =========================
# Filename helper (다운로드 파일명 깔끔하게)
# =========================
def make_safe_filename(base: str, fallback: str = "clip", max_len: int = 80) -> str:
    """
    Windows/브라우저에서 깨지지 않도록 파일명 정리:
    - 공백 정리
    - 금지문자 제거: \ / : * ? " < > |
    - 끝의 점/공백 제거
    - 너무 길면 자르기
    """
    s = (base or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r'[\\/:*?"<>|]', "", s)  # Windows forbidden chars
    s = s.strip(" .")
    if not s:
        s = fallback
    if len(s) > max_len:
        s = s[:max_len].rstrip(" .")
    return s


# =========================
# Audio tools (ffmpeg)
# =========================
def ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(path)],
            stderr=subprocess.STDOUT
        ).decode("utf-8").strip()
        return float(out) if out else 0.0
    except Exception:
        return 0.0


def extract_clip(src: Path, start_s: float, end_s: float, dst: Path):
    """
    -to 대신 -t(길이) 사용: '항상 2초로 잘림' 같은 문제를 근본 차단
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    start_s = max(0.0, float(start_s))
    end_s = max(start_s + 0.01, float(end_s))
    dur_s = max(0.01, end_s - start_s)

    subprocess.check_call([
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-ss", f"{start_s:.3f}",
        "-t", f"{dur_s:.3f}",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        str(dst)
    ])


# =========================
# Common sanitize
# =========================
def sanitize_text_keep_unicode(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s)
    return s


# =========================
# Korean normalize (basic + sound)
# =========================
_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")


def is_hangul_syllable(ch: str) -> bool:
    return 0xAC00 <= ord(ch) <= 0xD7A3


def sanitize_for_ko(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\"'.,!?(){}\[\]:;~`@#$%^&*+=/\\|<>—\-]", "", s)
    return s


def hangul_to_jamo(s: str) -> str:
    out = []
    for ch in s:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            cho = idx // 588
            jung = (idx % 588) // 28
            jong = idx % 28
            out.append(_CHO[cho])
            out.append(_JUNG[jung])
            if _JONG[jong]:
                out.append(_JONG[jong])
        else:
            if ch.isalnum():
                out.append(ch.lower())
    return "".join(out)


def norm_basic(s: str) -> str:
    return hangul_to_jamo(sanitize_for_ko(s))


JONG_TO_ONSET = {
    "ㄱ": "ㄱ", "ㄲ": "ㄲ", "ㄳ": "ㄱ",
    "ㄴ": "ㄴ", "ㄵ": "ㄴ", "ㄶ": "ㄴ",
    "ㄷ": "ㄷ",
    "ㄹ": "ㄹ", "ㄺ": "ㄹ", "ㄻ": "ㄹ", "ㄼ": "ㄹ", "ㄽ": "ㄹ", "ㄾ": "ㄹ", "ㄿ": "ㄹ", "ㅀ": "ㄹ",
    "ㅁ": "ㅁ",
    "ㅂ": "ㅂ", "ㅄ": "ㅂ",
    "ㅅ": "ㅅ", "ㅆ": "ㅆ",
    "ㅇ": "ㅇ",
    "ㅈ": "ㅈ", "ㅊ": "ㅊ",
    "ㅋ": "ㅋ", "ㅌ": "ㅌ", "ㅍ": "ㅍ",
    "ㅎ": "ㅎ",
}


def simplify_final_for_pron(jong: str) -> str:
    if not jong:
        return ""
    return JONG_TO_ONSET.get(jong, jong)


def decompose_syllables_ko(s: str) -> List[Dict[str, str]]:
    s2 = sanitize_for_ko(s)
    items: List[Dict[str, str]] = []
    for ch in s2:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            cho = _CHO[idx // 588]
            jung = _JUNG[(idx % 588) // 28]
            jong = _JONG[idx % 28]
            items.append({"type": "hangul", "cho": cho, "jung": jung, "jong": jong})
        else:
            if ch.isalnum():
                items.append({"type": "other", "val": ch})
    return items


def apply_liaison(items: List[Dict[str, str]]) -> None:
    for i in range(len(items) - 1):
        a = items[i]
        b = items[i + 1]
        if a.get("type") != "hangul" or b.get("type") != "hangul":
            continue
        if not a.get("jong"):
            continue
        if b.get("cho") != "ㅇ":
            continue
        move = JONG_TO_ONSET.get(a["jong"], "")
        if not move:
            continue
        b["cho"] = move
        a["jong"] = ""


def apply_assimilation(items: List[Dict[str, str]]) -> None:
    nasal_next = {"ㄴ", "ㅁ"}
    velar = {"ㄱ", "ㅋ", "ㄲ", "ㄳ", "ㄺ"}
    alveolar = {"ㄷ", "ㅅ", "ㅆ", "ㅈ", "ㅊ", "ㅌ", "ㅎ"}
    labial = {"ㅂ", "ㅍ", "ㅄ"}

    for i in range(len(items) - 1):
        a = items[i]
        b = items[i + 1]
        if a.get("type") != "hangul" or b.get("type") != "hangul":
            continue

        jong = a.get("jong") or ""
        if not jong:
            continue

        jong_rep = simplify_final_for_pron(jong)
        next_cho = b.get("cho") or ""

        if jong_rep == "ㄴ" and next_cho == "ㄹ":
            a["jong"] = "ㄹ"
            b["cho"] = "ㄹ"
            continue
        if jong_rep == "ㄹ" and next_cho == "ㄴ":
            a["jong"] = "ㄹ"
            b["cho"] = "ㄹ"
            continue

        if next_cho in nasal_next:
            if jong in velar:
                a["jong"] = "ㅇ"
            elif jong in alveolar:
                a["jong"] = "ㄴ"
            elif jong in labial:
                a["jong"] = "ㅁ"


def syllables_to_jamo(items: List[Dict[str, str]]) -> str:
    out = []
    for it in items:
        if it["type"] == "other":
            out.append(it["val"])
        else:
            out.append(it["cho"])
            out.append(it["jung"])
            if it["jong"]:
                out.append(it["jong"])
    return "".join(out)


def norm_ko_sound(s: str) -> str:
    items = decompose_syllables_ko(s)
    apply_liaison(items)
    apply_assimilation(items)

    out_items: List[Dict[str, str]] = []
    for it in items:
        if it["type"] == "other":
            out_items.append(it)
        else:
            it2 = dict(it)
            it2["jong"] = simplify_final_for_pron(it.get("jong") or "")
            out_items.append(it2)

    return syllables_to_jamo(out_items)


# =========================
# Japanese normalize + input conversions
# =========================
def is_hiragana(ch: str) -> bool:
    return 0x3040 <= ord(ch) <= 0x309F


def is_katakana(ch: str) -> bool:
    return 0x30A0 <= ord(ch) <= 0x30FF


def kata_to_hira(ch: str) -> str:
    code = ord(ch)
    if 0x30A1 <= code <= 0x30F6:
        return chr(code - 0x60)
    return ch


def jp_kana_norm(text: str) -> str:
    t = sanitize_text_keep_unicode(text)
    out = []
    for ch in t:
        if is_katakana(ch):
            out.append(kata_to_hira(ch))
        elif is_hiragana(ch):
            out.append(ch)
        elif ch == "ー":
            pass
    return "".join(out)


_ROMAJI_TABLE = [
    ("kya", "きゃ"), ("kyu", "きゅ"), ("kyo", "きょ"),
    ("gya", "ぎゃ"), ("gyu", "ぎゅ"), ("gyo", "ぎょ"),
    ("sha", "しゃ"), ("shu", "しゅ"), ("sho", "しょ"),
    ("sya", "しゃ"), ("syu", "しゅ"), ("syo", "しょ"),
    ("ja", "じゃ"), ("ju", "じゅ"), ("jo", "じょ"),
    ("jya", "じゃ"), ("jyu", "じゅ"), ("jyo", "じょ"),
    ("cha", "ちゃ"), ("chu", "ちゅ"), ("cho", "ちょ"),
    ("tya", "ちゃ"), ("tyu", "ちゅ"), ("tyo", "ちょ"),
    ("nya", "にゃ"), ("nyu", "にゅ"), ("nyo", "にょ"),
    ("hya", "ひゃ"), ("hyu", "ひゅ"), ("hyo", "ひょ"),
    ("bya", "びゃ"), ("byu", "びゅ"), ("byo", "びょ"),
    ("pya", "ぴゃ"), ("pyu", "ぴゅ"), ("pyo", "ぴょ"),
    ("mya", "みゃ"), ("myu", "みゅ"), ("myo", "みょ"),
    ("rya", "りゃ"), ("ryu", "りゅ"), ("ryo", "りょ"),
    ("shi", "し"), ("chi", "ち"), ("tsu", "つ"),
    ("fu", "ふ"),
    ("ka", "か"), ("ki", "き"), ("ku", "く"), ("ke", "け"), ("ko", "こ"),
    ("sa", "さ"), ("si", "し"), ("su", "す"), ("se", "せ"), ("so", "そ"),
    ("ta", "た"), ("ti", "ち"), ("tu", "つ"), ("te", "て"), ("to", "と"),
    ("na", "な"), ("ni", "に"), ("nu", "ぬ"), ("ne", "ね"), ("no", "の"),
    ("ha", "は"), ("hi", "ひ"), ("hu", "ふ"), ("he", "へ"), ("ho", "ほ"),
    ("ma", "ま"), ("mi", "み"), ("mu", "む"), ("me", "め"), ("mo", "も"),
    ("ya", "や"), ("yu", "ゆ"), ("yo", "よ"),
    ("ra", "ら"), ("ri", "り"), ("ru", "る"), ("re", "れ"), ("ro", "ろ"),
    ("wa", "わ"), ("wo", "を"),
    ("ga", "が"), ("gi", "ぎ"), ("gu", "ぐ"), ("ge", "げ"), ("go", "ご"),
    ("za", "ざ"), ("zi", "じ"), ("zu", "ず"), ("ze", "ぜ"), ("zo", "ぞ"),
    ("da", "だ"), ("di", "ぢ"), ("du", "づ"), ("de", "で"), ("do", "ど"),
    ("ba", "ば"), ("bi", "び"), ("bu", "ぶ"), ("be", "べ"), ("bo", "ぼ"),
    ("pa", "ぱ"), ("pi", "ぴ"), ("pu", "ぷ"), ("pe", "ぺ"), ("po", "ぽ"),
    ("a", "あ"), ("i", "い"), ("u", "う"), ("e", "え"), ("o", "お"),
    ("n", "ん"),
]


def romaji_to_hiragana(s: str) -> str:
    x = re.sub(r"[^a-z]", "", (s or "").lower())
    if not x:
        return ""
    out = []
    i = 0
    while i < len(x):
        if i + 1 < len(x) and x[i] == x[i + 1] and x[i] in "kstphgzbdrjmc":
            out.append("っ")
            i += 1
            continue
        matched = False
        for key, val in _ROMAJI_TABLE:
            if x.startswith(key, i):
                out.append(val)
                i += len(key)
                matched = True
                break
        if not matched:
            i += 1
    return "".join(out)


def hangul_syllable_to_chojung(ch: str) -> Optional[Tuple[str, str]]:
    if not is_hangul_syllable(ch):
        return None
    idx = ord(ch) - 0xAC00
    cho = _CHO[idx // 588]
    jung = _JUNG[(idx % 588) // 28]
    return cho, jung


KO_ONSET_TO_ROMA = {
    "ㅇ": "", "ㄱ": "g", "ㄲ": "k", "ㅋ": "k",
    "ㄴ": "n", "ㄷ": "d", "ㄸ": "t", "ㅌ": "t",
    "ㄹ": "r", "ㅁ": "m", "ㅂ": "b", "ㅃ": "p", "ㅍ": "p",
    "ㅅ": "s", "ㅆ": "s", "ㅈ": "j", "ㅉ": "ch", "ㅊ": "ch",
    "ㅎ": "h",
}
KO_VOWEL_TO_ROMA = {
    "ㅏ": "a", "ㅐ": "e", "ㅑ": "ya", "ㅒ": "ya",
    "ㅓ": "o", "ㅔ": "e", "ㅕ": "yo", "ㅖ": "ye",
    "ㅗ": "o", "ㅘ": "wa", "ㅙ": "we", "ㅚ": "o",
    "ㅛ": "yo", "ㅜ": "u", "ㅝ": "wo", "ㅞ": "we", "ㅟ": "wi",
    "ㅠ": "yu", "ㅡ": "u", "ㅢ": "i", "ㅣ": "i",
}


def hangul_to_hiragana_guess(s: str) -> str:
    s2 = sanitize_text_keep_unicode(s)
    romaji = []
    for ch in s2:
        cj = hangul_syllable_to_chojung(ch)
        if not cj:
            if ("a" <= ch.lower() <= "z"):
                romaji.append(ch.lower())
            continue
        cho, jung = cj
        r1 = KO_ONSET_TO_ROMA.get(cho, "")
        r2 = KO_VOWEL_TO_ROMA.get(jung, "")
        romaji.append(r1 + r2)
    return romaji_to_hiragana("".join(romaji))


# =========================
# Scoring
# =========================
def score_contains(needle: str, hay: str) -> int:
    if not needle:
        return 0
    if needle in hay:
        return 100
    n = 3
    if len(needle) < n or len(hay) < n:
        return 0
    a = {hay[i:i + n] for i in range(len(hay) - n + 1)}
    b = {needle[i:i + n] for i in range(len(needle) - n + 1)}
    if not a or not b:
        return 0
    inter = len(a & b)
    union = len(a | b)
    return int(100 * (inter / union))


# =========================
# Pages
# =========================
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# =========================
# Profiles API
# =========================
@app.get("/api/profiles")
def api_get_profiles():
    return {"profiles": load_data()["profiles"]}


@app.post("/api/profiles")
def api_create_profile(name: str = Form(...)):
    name = (name or "").strip()
    if not name:
        return JSONResponse({"error": "프로필 이름이 비어있어요."}, status_code=400)

    data = load_data()
    pid = str(uuid.uuid4())
    data["profiles"].append({"id": pid, "name": name, "created_at": now_iso()})
    save_data(data)
    return {"ok": True, "profile": {"id": pid, "name": name}}


@app.delete("/api/profiles/{profile_id}")
def api_delete_profile(profile_id: str):
    data = load_data()
    if not any(p["id"] == profile_id for p in data["profiles"]):
        return JSONResponse({"error": "프로필을 찾을 수 없어요."}, status_code=404)

    clips_to_delete = [c for c in data["clips"] if c.get("profile_id") == profile_id]
    audio_ids = set(c.get("audio_id") for c in clips_to_delete)

    data["profiles"] = [p for p in data["profiles"] if p.get("id") != profile_id]
    data["clips"] = [c for c in data["clips"] if c.get("profile_id") != profile_id]

    audios_to_delete = [a for a in data["audios"] if a.get("id") in audio_ids]
    data["audios"] = [a for a in data["audios"] if a.get("id") not in audio_ids]

    save_data(data)

    try:
        for c in clips_to_delete:
            cid = c.get("id")
            if cid:
                for f in CACHE_DIR.glob(f"{cid}_*.wav"):
                    f.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        for a in audios_to_delete:
            path = a.get("path")
            if path:
                (UPLOAD_DIR / path).unlink(missing_ok=True)
    except Exception:
        pass

    return {"ok": True, "deleted_clips": len(clips_to_delete), "deleted_audios": len(audios_to_delete)}


# =========================
# Clips API  (⚠️ bulk routes MUST come BEFORE /api/clips/{clip_id})
# =========================
class BulkDeleteRequest(BaseModel):
    clip_ids: List[str]


def _bulk_delete_impl(clip_ids: List[str]) -> Dict[str, Any]:
    clip_ids = [x for x in (clip_ids or []) if isinstance(x, str) and x.strip()]
    clip_ids = list(dict.fromkeys(clip_ids))  # unique keep order
    if not clip_ids:
        return {"ok": True, "deleted": 0}

    data = load_data()
    id_set = set(clip_ids)

    existing = [c for c in data["clips"] if c.get("id") in id_set]
    if not existing:
        return {"ok": True, "deleted": 0}

    data["clips"] = [c for c in data["clips"] if c.get("id") not in id_set]
    save_data(data)

    for cid in clip_ids:
        try:
            for f in CACHE_DIR.glob(f"{cid}_*.wav"):
                f.unlink(missing_ok=True)
        except Exception:
            pass

    return {"ok": True, "deleted": len(existing)}


@app.post("/api/clips/bulk_delete")
def api_bulk_delete_clips_compat(req: BulkDeleteRequest):
    return _bulk_delete_impl(req.clip_ids)


@app.post("/api/clips/bulk-delete")
def api_bulk_delete_clips(req: BulkDeleteRequest):
    return _bulk_delete_impl(req.clip_ids)


@app.delete("/api/clips/{clip_id}")
def api_delete_clip(clip_id: str):
    data = load_data()
    clip = next((c for c in data["clips"] if c.get("id") == clip_id), None)
    if not clip:
        return JSONResponse({"error": "클립을 찾을 수 없어요."}, status_code=404)

    data["clips"] = [c for c in data["clips"] if c.get("id") != clip_id]
    save_data(data)

    try:
        for f in CACHE_DIR.glob(f"{clip_id}_*.wav"):
            f.unlink(missing_ok=True)
    except Exception:
        pass

    return {"ok": True}


# =========================
# Search API
# =========================
@app.get("/api/search")
def api_search(
    q: str = "",
    profile_id: Optional[str] = None,
    limit: int = 50,
    mode: str = "basic",
):
    data = load_data()
    mode = (mode or "basic").lower()
    if mode not in ("basic", "ko_sound", "jp_sound"):
        mode = "basic"

    clips = data["clips"]
    if profile_id:
        clips = [c for c in clips if c.get("profile_id") == profile_id]

    if mode == "basic":
        needle = norm_basic(q)
    elif mode == "ko_sound":
        needle = norm_ko_sound(q)
    else:
        raw = sanitize_text_keep_unicode(q)
        has_kana = any(is_hiragana(ch) or is_katakana(ch) for ch in raw)
        has_latin = bool(re.search(r"[A-Za-z]", raw))
        has_hangul = any(is_hangul_syllable(ch) for ch in raw)

        if has_kana:
            needle = jp_kana_norm(raw)
        elif has_latin:
            needle = romaji_to_hiragana(raw)
        elif has_hangul:
            needle = hangul_to_hiragana_guess(raw)
        else:
            needle = ""

    if not needle:
        clips_sorted = sorted(clips, key=lambda c: c.get("created_at", ""), reverse=True)[:limit]
        return {"results": clips_sorted}

    scored: List[Tuple[int, Dict[str, Any]]] = []

    for c in clips:
        txt = c.get("transcript") or ""

        if mode == "basic":
            hay = c.get("norm") or norm_basic(txt)
        elif mode == "ko_sound":
            if not any(is_hangul_syllable(ch) for ch in txt):
                continue
            hay = c.get("ko_pron_norm") or norm_ko_sound(txt)
        else:
            hay = c.get("jp_kana_norm") or jp_kana_norm(txt)
            if not hay:
                continue

        s = score_contains(needle, hay)
        if s > 0:
            scored.append((s, c))

    scored.sort(key=lambda x: (x[0], x[1].get("created_at", "")), reverse=True)
    return {"results": [c for _, c in scored[:limit]]}


# =========================
# Clip audio (on-demand cut)
# =========================
@app.get("/api/clip_audio/{clip_id}")
def api_clip_audio(clip_id: str):
    data = load_data()
    clip = next((c for c in data["clips"] if c.get("id") == clip_id), None)
    if not clip:
        return JSONResponse({"error": "클립을 찾을 수 없어요."}, status_code=404)

    audio = next((a for a in data["audios"] if a.get("id") == clip.get("audio_id")), None)
    if not audio:
        return JSONResponse({"error": "원본 오디오를 찾을 수 없어요."}, status_code=404)

    src = UPLOAD_DIR / audio["path"]
    if not src.exists():
        return JSONResponse({"error": "원본 파일이 없어요."}, status_code=404)

    start_s = float(clip["start_s"])
    end_s = float(clip["end_s"])

    cache_name = f"{clip_id}_{start_s:.3f}_{end_s:.3f}.wav"
    cache_path = CACHE_DIR / cache_name

    if not cache_path.exists():
        try:
            extract_clip(src, start_s, end_s, cache_path)
        except subprocess.CalledProcessError as e:
            return JSONResponse({"error": f"ffmpeg 실패: {e}"}, status_code=500)

    # ✅ 다운로드 파일명: "대사.wav" 기본
    transcript = (clip.get("transcript") or "").strip()
    safe_base = make_safe_filename(transcript, fallback="clip", max_len=80)

    # ✅ 같은 대사(=safe_base)가 여러 개면 "(2)", "(3)" 붙이기
    # 기준: data.json에 있는 클립들 중 같은 safe_base를 가진 것들에서의 순번
    same = []
    for c in data.get("clips", []):
        t = (c.get("transcript") or "").strip()
        b = make_safe_filename(t, fallback="clip", max_len=80)
        if b == safe_base:
            same.append(c)

    # 안정적으로 만들기 위해 created_at + id로 정렬
    same.sort(key=lambda x: ((x.get("created_at") or ""), (x.get("id") or "")))

    # 현재 clip이 몇 번째인지 찾기
    idx = 0
    for i, c in enumerate(same):
        if c.get("id") == clip_id:
            idx = i + 1  # 1-based
            break

    if len(same) <= 1 or idx <= 1:
        dl_name = f"{safe_base}.wav"
    else:
        dl_name = f"{safe_base} ({idx}).wav"

    return FileResponse(cache_path, media_type="audio/wav", filename=dl_name)


# =========================
# Jobs API
# =========================
@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "job을 찾을 수 없어요."}, status_code=404)
    return {"job": job}


# =========================
# Background STT job
# =========================
def run_stt_job(job_id: str, profile_id: str, audio_id: str, saved_path: Path):
    try:
        set_job(job_id, status="running", progress=0, message="STT 분석 시작...", clips_created=0)

        data = load_data()
        duration = ffprobe_duration(saved_path)

        model = get_whisper_model()

        segments, info = model.transcribe(
            str(saved_path),
            task="transcribe",     # 번역 금지
            language=None,         # auto
            vad_filter=True,
        )

        created = 0
        last_p = 0.0

        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue

            start_s = float(seg.start)
            end_s = float(seg.end)

            if end_s - start_s < 0.15:
                continue

            clip = {
                "id": str(uuid.uuid4()),
                "profile_id": profile_id,
                "audio_id": audio_id,
                "start_s": start_s,
                "end_s": end_s,
                "transcript": text,

                "norm": norm_basic(text),
                "ko_pron_norm": norm_ko_sound(text),
                "jp_kana_norm": jp_kana_norm(text),

                "created_at": now_iso(),
            }
            data["clips"].append(clip)
            created += 1

            if duration > 0:
                p = min(0.99, max(last_p, end_s / duration))
            else:
                p = min(0.99, max(last_p, 0.02 + created * 0.01))
            last_p = p

            set_job(
                job_id,
                progress=int(p * 100),
                message=f"STT 처리중... (구간 {created}개)",
                clips_created=created,
            )

        save_data(data)
        set_job(job_id, status="done", progress=100, message=f"완료! 클립 {created}개 생성", clips_created=created)

    except Exception as e:
        set_job(job_id, status="error", progress=0, message=f"에러: {type(e).__name__}: {e}", clips_created=0)


# =========================
# Upload API (single file per request; front can call multiple times)
# =========================
@app.post("/api/upload")
async def api_upload(
    background_tasks: BackgroundTasks,
    profile_id: str = Form(...),
    audio: UploadFile = File(...),
):
    data = load_data()

    if not any(p["id"] == profile_id for p in data["profiles"]):
        return JSONResponse({"error": "존재하지 않는 프로필이에요."}, status_code=400)

    ext = Path(audio.filename or "").suffix.lower()
    if ext not in [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"]:
        return JSONResponse({"error": f"지원하지 않는 확장자: {ext}"}, status_code=400)

    audio_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"{audio_id}{ext}"
    content = await audio.read()
    saved_path.write_bytes(content)

    audio_rec = {
        "id": audio_id,
        "profile_id": profile_id,
        "orig_filename": audio.filename,
        "path": saved_path.name,
        "duration": ffprobe_duration(saved_path),
        "created_at": now_iso(),
    }
    data["audios"].append(audio_rec)
    save_data(data)

    job_id = str(uuid.uuid4())
    set_job(job_id, status="queued", progress=0, message="대기중...", clips_created=0)

    background_tasks.add_task(run_stt_job, job_id, profile_id, audio_id, saved_path)

    return {"ok": True, "job_id": job_id, "audio": audio_rec}
