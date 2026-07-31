# Tube Vocal Removal 개발 인계

최종 업데이트: 2026-07-15 (Codex)

## 배포 구조

- 최종 실행 파일: `dist/Tube Vocal Removal/Tube Vocal Removal.exe`
- `_internal`은 필수 런타임이므로 EXE만 단독 배포하면 실행되지 않는다.
- 모델은 배포본에 포함하지 않고 `%APPDATA%/TubeVocalRemoval/models`에 별도 다운로드한다.
- 기본값은 CPU이며 GPU는 설정에서 사용자가 켠 경우에만 사용한다.

## UI 및 프로세스 구조

- 원본 HTML 목업 기반 pywebview/WebView2 UI를 사용한다.
- 공개 API 객체에는 직렬화 가능한 메서드만 두고 window/pipeline/event 상태는 private 필드로 유지한다.
- 작업 스레드는 JS를 직접 호출하지 않는다. 이벤트 큐에 넣고 UI가 `poll_events()`로 가져간다.
- AI 분리는 `--separation-worker` 자식 프로세스에서 수행한다. GUI 시작 시 Torch/CUDA를 로드하지 않는다.
- GPU 표시는 가벼운 `nvidia-smi` 조회만 사용한다.
- FFmpeg, Deno, 다운로드 도구 등 자식 콘솔은 `CREATE_NO_WINDOW`로 숨긴다.

## 모델

- 추천 Karaoke: `mel_band_roformer_karaoke_gabox.ckpt` (2026-07-16 aufr33-viperx에서 교체 — 반주 SDR 14.65 → 16.37)
- 최고 품질: audio-separator의 Karaoke 3모델 앙상블
- 전체 보컬 제거/보컬 추출: `model_bs_roformer_ep_317_sdr_12.9755.ckpt`
- 빠른 Karaoke: `UVR_MDXNET_KARA_2.onnx`
- Demucs 4트랙: `htdemucs.yaml`

Roformer 계열은 UVR5 v5.6 기본 목록에 포함된 UVR 제작 모델이 아니라 UVR 호환 커뮤니티 모델이다. 모델 바이너리는 audio-separator 카탈로그가 참조하는 공개 저장소에서 내려받는다.

## 완료된 안정화

- CPU 기본값 및 GPU 명시 선택
- 모델 미리 받기는 추론 모델을 RAM에 적재하지 않고 파일만 다운로드
- 전체 모델 받기는 중복 모델을 제외한 5개 모델 그룹을 순차 다운로드
- URL Enter 제목 조회와 대기열 추가
- 실행 중 새 항목 추가 및 동일 실행에서 연속 처리
- 완료/실패/취소 URL 재시도
- Demucs 결과 4개 stem 보존
- YouTube 다운로드 진행률을 진행 막대에 표시
- AI 실제 청크 진행률을 진행 막대에 숫자 퍼센트로 표시
- 중단 시 다운로드/AI 자식 프로세스 종료
- 폴더 열기 버튼 왼쪽 배치와 CMD 창 숨김
- 설정 버튼을 왼쪽, 폴더 아이콘을 가운데, 붉은 녹음 스타일 분리 시작 버튼을 오른쪽에 배치
- 분리 방식을 계층 없이 결과물 기준 6개 한 줄 목록으로 정리하고 중복 설명 제거
- 대기열 내부 스크롤과 스크롤 위치 유지, 실패 원인을 항목 바로 아래 표시
- 진행 막대 중앙 문구를 숫자 퍼센트만 표시하도록 단순화
- YouTube 제목과 다운로드/출력 파일명을 NFC로 정규화해 한글 자모 분리 방지
- WebView JS의 비공개 `File.path` 대신 pywebview 네이티브 drop bridge로 실제 Windows 경로 수신
- 개별 삭제 X를 항상 표시하고 대기열 우측에 작업 중 잠기는 빨간 RESET 버튼 추가
- 전체 창 스크롤은 막고 대기열과 로그만 각 영역 안에서 스크롤
- 저장 대상 수동 설정을 제거하고 분리 방식에 따라 반주 계열 1개, 보컬 추출 1개, Demucs 4개를 자동 저장
- 기본 창 높이는 864px이며 로그 영역을 216px로 확대하고 바깥 스크롤 없이 표시
- Windows EXE 속성에 파일 설명, 파일/제품 버전, 저작권, 원본 파일명을 포함
- 초기 준비 실패 시 UI 잠금 복구, 취소 후 모델 다운로드, 스템 마커 판별, 네트워크 저장소 폴백 안정화
- CDN/프록시의 Content-Length 차이로 정상 모델 다운로드가 거부되지 않도록 서버 용량은 진행률 참고값으로만 사용
- 설정에서 현재/최신 버전을 표시하고 GitHub Releases 설치파일을 다운로드해 SHA-256 검증 후 무인 업데이트
- CUDA 없는 CPU PC도 리소스 스모크 성공 여부를 올바르게 판정

## 최종 검증 결과

- Python compileall 통과
- 단위 테스트 20개 통과
- 새 EXE 리소스 점검 대상: UI, yt-dlp, Deno, FFmpeg, audio-separator (CUDA는 정보성)
- 새 EXE CPU 실제 분리 기준: 4초 WAV에서 선택 방식에 맞는 결과 파일 생성
- AI 진행 이벤트 확인: 50%, 100%
- 검증 장치: NVIDIA GeForce RTX 3060, 실제 분리는 `use_gpu=false`로 수행

## 남은 배포 작업

- 별도 깨끗한 Windows PC에서 CPU/GPU 설치 테스트
- 모델 다운로드 실패/재시도 UX의 다양한 네트워크 환경 검증
- 배포 용량 절감을 위한 CPU/GPU 런타임 분리 검토

## 설치본 검증

- Inno Setup 단일 설치 EXE 생성 완료
- 임시 경로 무인 설치 성공 및 설치된 EXE 리소스 스모크 통과
- 제거 프로그램 정상 종료 및 임시 설치 폴더 제거 확인

## 2026-07-16 v2.00 마무리 (Claude)

### UI 확정 (레트로 하드웨어 스킨)

- 창 폭 700 → 600px (min 560). P5 배지 제거, 프로그램 리드아웃은 텍스트 전용 (이름 18px)
- 패널 순서: 곡 추가 → 대기열 → 셀렉터/엔진 → 분리 시작 → 진행 상황. 대기열 "0곡" 배지 제거
- 진행 상황의 현재 곡 줄을 초록 LCD 스타일로, 퍼센트 숫자는 리드아웃 정중앙 (램프는 좌측 고정)
- 스테이지 램프 색 구분: INPUT 금색 / MODEL 주황 / SEPARATE 빨강 / OUTPUT 초록, 진행 중 램프는 점멸
- 진행률 미상 구간은 슬라이드 애니메이션 대신 바 전체 호흡 점멸 (indet 진입 시 인라인 width 초기화 필수)
- RESET은 라벨 + 원형 LED 푸시버튼 (비활성 시 소등). 설정 모달은 목업의 카드형 SETTINGS 디자인
- 설정에서 GPU 토글과 저장 형식 섹션 제거 — 메인 화면 GPU/FORMAT/QUALITY 노브가 담당하고, 모달 저장 시 노브 값을 그대로 유지

### 동작 정책 변경

- 같은 링크 중복 추가 허용 — 기존 "재시도 시 행 교체" 로직 삭제, 항상 새 행 (다른 프로그램으로 재분리하는 사용 패턴)
- 대기열의 빨간 실패 원인 줄 제거 — 실패 원인은 행 툴팁과 진행 로그로 이동
- yt-dlp 실패 시 마지막 출력(ERROR 줄)을 진행 로그에 기록, `--retries 10 --fragment-retries 10 --extractor-retries 3` 추가
  (반복 다운로드 실패의 원인은 유튜브측 일시 차단으로 확인 — 같은 영상 연속 3회 CLI 재현 시 전부 성공)

### 모델

- P2(karaoke)를 gabox로 교체. audio-separator 내장 벤치마크 기준 반주 SDR 14.65 → 16.37, 보컬 8.45 → 8.69
- P1(MDXNET KARA_2)은 CPU 경량 역할이므로 유지. P4/P5의 BS-Roformer 12.97은 공개 모델 중 최상위라 유지
- htdemucs_ft(전 스템 +0.7dB, 4배 느림)는 보류

### 데드 코드 정리

- `app/native_ui.py` 삭제 (구 tkinter UI — import되지 않고 빌드에서 tkinter 제외라 동작 불가)
- `api.is_running`, `api._emit` 삭제 (호출처 없음)
- CSS 잔재 삭제: `.logo`, `.bar-text`, `.mode-select`, `.mode-hint`, `.count-badge`, `.queue-error` 등

### 검증

- 단위 테스트 22개 통과, 스모크(cuda 포함) 전 항목 정상
- 업데이트 기능 실검증: 버전 0.99로 가장해 실제 GitHub 릴리즈 조회 → "available v1.01 · 1.77GB · sha256 지문" 정상 수신
- version_info.txt 숫자 버전 (2,0,0,0)으로 문자열 2.00과 일치시킴

### 남은 배포 작업 (v2.00)

- Inno Setup으로 `Tube-Vocal-Removal-Setup-v2.00.exe` 빌드 → 완료, 릴리즈 v2.00 업로드됨
- requirements.txt의 미사용 torchvision·imageio-ffmpeg 제거 검토

## 2026-07-16 v2.01 (Claude)

### 볼륨 보정 기능 (기본 ON, 설정에서 OFF 가능)

- 문제: 분리 결과가 곡마다 음량이 다르고(원본 차이 + 보컬 에너지 소실), 곡 안에서도 보컬 구간마다 반주가 꺼지는 출렁임(모델 아티팩트)이 있었음
- 해결 체인: 워커가 무손실 WAV로 중간 출력 → `dynaudnorm`(f=1000, 최대 6배)으로 구간 평탄화 → `loudnorm -14 LUFS` 2-pass linear로 최종 음량 고정 → 최종 형식 1회 인코딩 (추가 손실 0)
- 악기별 분리(demucs)는 스템 간 밸런스 보존을 위해 자동 제외
- -14 LUFS 선택 근거: 유튜브·스포티파이 재생 기준 음량. ffmpeg-normalize 패키지는 불필요 (동봉 ffmpeg의 loudnorm 필터 직접 사용). matchering(원곡 매칭 방식)도 검토했으나 고정 기준이 곡 간 통일에 더 적합
- 바탕화면 "볼륨 평준화 샘플" 폴더에 방식·강도별 비교 샘플 9종 생성해 청취 검증

### 기타

- 프로그램 셀렉터(P1~P6) 선택을 config `mode`로 저장해 재실행 시 복원
- UI: TRACK/PROGRESS 영문 헤더 통일, 대기열을 곡 추가 패널에 병합, 곡 제목 LCD 제거, RESET이 진행 상황(로그·램프·바)도 초기화, 초록 스크린 상단 픽셀 정렬, 입력창 중앙 정렬
- UVR5 대비 품질 의혹 검증: UVR5 설정 파일(data.pkl) 확인 결과 사용자는 Inst HQ 5(SDR 15.30)를 쓰고 있었고, 같은 소스 A/B에서 우리 P4 BS-Roformer(16.45)가 더 좋다고 사용자 확인. 엔진은 동일 계열
- 버전 v2.01, 테스트 24개, E2E 스모크(30초 클립 분리→보정→저장) 통과

## 2026-07-30 v2.02 (Claude)

### 가사 자동 저장 (기본 ON, 부가 기능)
- `app/lyrics.py` 신규. 흐름: 해외 싱크 소스(LRCLIB `/api/get`+길이→`/api/search`) → 국내 가사 소스(제목 검색→트랙 페이지 `<xmp>` 파싱) → 둘 다 없으면 조용히 스킵
- 오매칭 방지: 제목/가수/길이 정규화 후 substring 검증(`_similar`). 예 — "아이유 좋은날" 검색 시 "윤하 고백하기 좋은날" 같은 동명 부분일치를 가수 불일치로 거부
- 국내 소스는 코드·결과에서 이름 비노출(`source="web"`), 문서·UI에는 "가사 지원"으로만 표기. 브라우저 UA로 요청, LRCLIB 미스일 때만 호출해 트래픽 최소화
- 저장: 곡 폴더에 `{제목} (가사).txt`. 싱크 가사가 있으면 `.lrc`도 함께. 실패는 try/except로 삼켜 본 기능(분리)에 영향 없음
- 파이프라인 연결: `Pipeline._save_lyrics(item, song_dir)`를 `_separate` 말미(무브/보정 후)에서 `download_lyrics` 켜졌을 때 호출

### 키 감지 + 키 시프트 (기본 원키 ±0)
- `app/keyshift.py` 신규. `detect_key()`: librosa `chroma_cqt` + Krumhansl-Schmuckler 프로파일 상관도로 조성 추정("C# minor" 형식). madmom(0.17.dev, git-master)은 정확하나 PyInstaller 번들 리스크가 커서 미채용
- `shift_file()`: Signalsmith Stretch(`python-stretch` 0.3.1, MIT). 피치만 반음 이동, 템포·길이 완전 보존(실측 프레임 수 동일). R3(rubberband GPL exe) 대비 동급 품질 + 동봉 불필요 + 3배 빠름이라 채택. 입력 배열은 `ascontiguousarray(T)` 필수(메모리 레이아웃)
- 파이프라인 연결: `_run_separation_process`의 `needs_wav = volume_fix or key_shift`(demucs 제외)로 워커에서 무손실 WAV 수령 → `_separate`에서 시프트 → `_normalize_and_encode`(보정 시) 또는 `_encode_audio`(보정 없이 키만) 로 최종 1회 인코딩
- `config`: `key_shift`(-6~+6 클램프), `download_lyrics`(bool) 추가

### 코러스 추출(P7) 폐기
- 리드/코러스가 주파수·시간에서 겹쳐 원리적으로 리드 잔여 불가피. 체인(보컬추출→카라오케), BVE 전용 모델, 2단계 모델 교체(becruily/gaboxV2/UVR6HP) 모두 품질 미달. MVSep 등 유료도 다단계 캐스케이드로 동일 한계라 미채용

### 빌드
- `TubeVocalRemoval.spec`: python_stretch·soundfile·librosa `collect_all` 번들 + hiddenimports. `EXE(contents_directory="runtime")`로 `_internal` 폴더 개명. 폰트 폴더(`app/ui/fonts`) datas 추가
- 업데이트 UX: `apply_update`를 `/SILENT`(진행 막대 노출) + `/RESTARTAPPLICATIONS`로, `.iss`는 `RestartApplications=yes`로 바꿔 무음 설치 후 앱 자동 재실행
- 버전 2.02: `version.py`, `installer/version_info.txt`(2,0,2,0), `installer/TubeVocalRemoval.iss`
- ISCC 경로: `C:\Users\RYAN\AppData\Local\Programs\Inno Setup 6\ISCC.exe` (Program Files 아님 — 이전에 못 찾았던 원인). 설치 파일 빌드 ~12분

### UI 개편 (카세트 버튼 + 폰트 번들)
- 프로그램 셀렉터를 로터리 노브 → **카세트 피아노키 버튼 P1~P6**(2열 3행)로 교체. 노브의 동심원 정렬 이슈 완전 해소. 버튼 폰트는 `var(--font)`(산세리프), 눌림 시 초록 점등
- LED 세그먼트 진행 미터(초록→노랑→빨강), PROGRESS 헤더·나사 장식 제거로 컴팩트화, 앰버 필 토글, 타이틀바 버전만 흐린 텍스트로(동적, `get_app_version`), 대기열 곡별 키(감지→목표 ±)·가사(♪), 창 728px, 패딩 11px 균일
- **폰트 번들**: `app/ui/fonts`에 PretendardVariable.woff2(2MB)·Cascadia 400/700(각 30KB) + OFL LICENSE.txt. index.html에 `@font-face`(file:// 상대경로), spec datas 등록. 사용자 PC에 글꼴 없어도 동일 화면. 둘 다 OFL이라 번들 합법

### 다운로드 캐시 (같은 링크 다중 키 차단 수정)
- 문제: 같은 URL을 여러 키로 넣으면 항목마다 따로 다운로드 → 유튜브 반복 차단으로 "실패"
- 수정: `Pipeline._download_cache`(URL→파일). 첫 항목만 yt-dlp, 나머지는 `TEMP_DIR/download_cache`에서 복사 재사용. `reset()`에서 캐시 클리어. 테스트 38개

### 릴리즈
- v2.02 릴리즈: 설치 파일 `Setup-v2.02.exe`(폰트 포함) → GitHub Releases 업로드. 저장소 PUBLIC(배포), 코드는 gitignore로 비공개 유지

### 맥 포팅 (v2.1 예정, 방향 확정)
- **배포: 무료(서명·공증 없이)** — Apple $99 미사용. 사용자가 Gatekeeper에서 "확인 없이 열기"(시스템 설정) 한 단계 거침. Windows SmartScreen과 동급 마찰. 최신 macOS 15+는 우클릭 열기 불가라 시스템 설정 경로 안내 필요
- **GPU: 애플실리콘 MPS 가속** — CUDA(엔비디아 전용)는 맥에 없음. M1/M2/M3은 PyTorch `mps` 백엔드로 자체 GPU 사용. 인텔 맥은 CPU 폴백. audio-separator의 MPS 지원 범위는 실기기 검증 필요(일부 연산 CPU 폴백 가능)
- **작업 항목**: ①플랫폼 분기(`.exe`→OS별 바이너리, `CREATE_NO_WINDOW` 등 `if sys.platform=="win32"`, torch device에 mps 분기) ②맥 바이너리 3종(ffmpeg/yt-dlp/deno) ③`requirements-mac.txt`(CPU/MPS torch, onnxruntime, CUDA 제거) ④`TubeVocalRemoval-mac.spec`(.app, .icns) ⑤`.github/workflows/build.yml`(windows+macos 매트릭스, macos runner가 .app→.dmg 빌드) ⑥맥 있는 베타테스터 실사용 검증
- 코드를 GitHub에 올려야 Actions가 빌드 → 현재 public repo(문서+배포) 그대로 쓰거나 코드용 저장소 필요 (코드 공개 여부는 사용자가 크게 개의치 않음)

### 그 외 향후
- 검토: CPU/GPU 런타임 분리(용량 축소), Microsoft Store MSIX
