# Source Extractor

음MAD 발음 소스를 검색하고, 파형·피치선을 보면서 구간을 선택해 WAV로 추출하는 Windows 로컬 앱입니다. 기존 화면을 WebView2 전용 창으로 실행합니다.

## 기존 사용자가 앱으로 전환하기

1. 기존 서버를 종료하고, 최신 ZIP의 파일을 **기존 프로그램 폴더에 덮어씁니다**. 기존 `uploads`, `data.json`, 캐시 폴더는 지우지 않습니다. 새 ZIP에는 빈 `data.json`을 넣지 않아 기존 프로필이 덮어써지지 않습니다.
2. `install_windows.bat`을 **이번에 한 번** 실행합니다.
3. 바탕화면 **Source Extractor** 또는 `run_windows.bat`을 실행합니다. 브라우저 주소 입력은 필요 없습니다.

설치 중 진행 단계가 창에 표시되며 상세 내역은 `install_log.txt`에 기록됩니다. 첫 설치는 AI 실행 패키지 때문에 시간이 걸릴 수 있습니다. 설치한 폴더는 앱과 자료의 저장 위치이므로 유지하세요.

## 새로 설치하는 경우

Python **3.12.10 (64비트, 설치 시 Add Python to PATH)**와 FFmpeg/ffprobe가 필요합니다. Windows의 **Microsoft Edge WebView2 Runtime**도 필요합니다. 준비 후 ZIP 압축을 쓰기 가능한 폴더에 풀고 위의 2–3번을 진행하세요.

- [Python 3.12.10](https://www.python.org/downloads/release/python-31210/)
- [FFmpeg](https://www.ffmpeg.org/download.html)
- [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)

## 앱 안에서 업데이트

앱 상단 **업데이트 확인 → 다운로드 및 준비 → 재시작하여 적용**.

이 저장소(`Orange0929/Source_extractor`)의 **main 커밋**을 기준으로 확인합니다. Git이나 `git pull`은 필요 없습니다. GitHub가 공개한 커밋 SHA로 고정한 ZIP을 받아 검사합니다. 처음 ZIP으로 설치한 버전은 `local`로 표시되며, 첫 앱 내 업데이트 후 커밋 번호가 표시됩니다.

새 코드는 `.desktop/versions`에 준비하며 원본 오디오·프로필·클립·피치 캐시를 덮어쓰지 않습니다. 실행 패키지가 같으면 현재 환경을 재사용하고, 달라졌으면 별도 환경에 설치합니다. 다운로드/설치가 실패하면 현재 버전을 유지하며, 새 버전의 시작이 실패하면 이전 버전으로 돌아갑니다. 실행 중인 업로드·분석·다운로드를 마친 후 재시작하세요. AI 모델은 코드 업데이트 때 다시 받지 않습니다.

설치에 쓰는 Python과 FFmpeg는 유지해야 합니다. 버전 변경으로 처음 필요한 모델이 생기면 해당 모델의 첫 다운로드가 필요할 수 있습니다. 이전 버전과 실행 환경은 복구용으로 보관됩니다.

## 파형 편집

| 조작 | 동작 |
|---|---|
| Ctrl + 휠 | 마우스 위치를 기준으로 가로 확대/축소 |
| Alt + 휠 | 마우스 위치를 기준으로 세로 확대/축소 |
| Shift + 휠 | 가로 이동 |
| 휠 | 세로 이동 |
| 스크롤바 가운데 드래그 | 해당 축 이동 |
| 스크롤바 양 끝 드래그 | 해당 축 확대/축소 |
| 상단 띠 클릭 | 재생 시작 커서 지정 |
| 아래 파형 드래그 | 선택 구간 지정 |
| Space | 선택 안의 커서부터 재생 / 정지 후 커서 복귀 |
| 우측 상단 확대 / Esc | 편집 화면 확대 / 원래 화면으로 복귀 |

파형 위 Ctrl+휠은 페이지 전체 확대를 막고 가로 배율만 조절합니다. 커서가 선택 구간 밖에 있으면 선택 시작부터 재생하고 선택 끝에서 멈춥니다. 반복을 켰다면 이후 선택 전체를 반복합니다. 프로필 ZIP에는 분석해 둔 피치 결과도 포함됩니다.

## 문제 확인

- 앱 시작/실행 기록: `.desktop/app.log`, 로컬 서버 기록: `.desktop/server.log`
- 업데이트 패키지 설치 기록: `.desktop/update.log`
- 앱 상단 **진단 로그 저장**으로 위 로그와 버전 정보를 TXT 하나로 저장할 수 있습니다.
- **서버 CMD 열기**는 현재 로컬 서버 주소와 `server.log`의 실시간 출력을 보여주는 디버그 창입니다. CMD를 닫아도 앱은 종료되지 않습니다.
- 앱이 열리지 않으면 WebView2 Runtime 설치 여부를 확인하세요.
- 브라우저 방식이 필요하면 앱을 닫고 `run_browser_windows.bat` 실행 후 `http://127.0.0.1:8000`에 접속하세요. 이 방식은 마지막 정상 적용 버전으로 실행하며, 앱 내 업데이트 버튼은 표시하지 않습니다. 앱과 브라우저 서버를 동시에 실행하지 마세요.

## 개발 검증

한국어 발음 검색과 연속음 검색은 g2pk2 및 MeCab 형태소 분석을 사용합니다.
된소리되기, 구개음화, ㅎ 변화, ㄴ 첨가, 겹받침, 7종성 중화와 문맥에 따른
일부 발음 변화를 처리합니다. 사투리·고유명사·실제 화자의 발음까지 보장하지는 않습니다.
기존/가져온 프로필은 원래 대사에서 새 검색 키를 계산하므로 재추출할 필요가 없습니다.
변환 결과는 실행 중 캐시하며, 재시작 후 첫 발음 검색은 다시 계산합니다.
이번 의존성 변경 업데이트는 별도 실행 환경을 설치하므로 코드만 바뀐 업데이트보다 오래 걸릴 수 있습니다.
검색 중 추가 다운로드나 pip 설치는 하지 않습니다. ZIP 덮어쓰기 사용자는
`install_windows.bat`를 다시 실행해 의존성을 설치하세요.

Python API 테스트에는 FastAPI/NumPy/ffmpeg 외에 `httpx`가 필요합니다. 데스크톱 업데이트 테스트는 GUI·네트워크·AI 모델 없이 수행할 수 있습니다.

```text
python -m unittest discover -s tests -p test_desktop_update.py -v
python -m unittest discover -s tests -p test_desktop_server.py -v
python -m unittest discover -s tests -p test_profile_roundtrip.py -v
python -m unittest discover -s tests -p test_search_modes.py -v
python -m unittest discover -s tests -p test_korean_offline.py -v
node tests/test_plot_wheel.cjs
node tests/test_editor_transport.cjs
```

Windows에서 WebView2 창, 파일 선택/다운로드 대화상자와 실제 오디오 출력은 별도 확인이 필요합니다.
