# Tube Vocal Removal 체크리스트

## 완료

- [x] Python 가상환경과 FFmpeg/yt-dlp/Deno 구성
- [x] YouTube URL 및 로컬 파일 입력
- [x] 파일 드래그 앤 드롭
- [x] 원본 HTML 목업 기반 Windows EXE UI
- [x] 출력 폴더/형식/원본 보관/CPU·GPU 설정 저장
- [x] 6개 분리 방식 및 모델 별도 다운로드
- [x] 기본 CPU, 선택 GPU
- [x] 자식 AI 프로세스 격리와 중단
- [x] 처리 중 대기열 추가 및 완료·실패 항목 재시도
- [x] 다운로드 및 AI 분리 진행률 표시
- [x] Demucs 4트랙 결과 보존
- [x] PyInstaller 폴더형 빌드
- [x] 단위 테스트 13개
- [x] 최종 EXE 리소스 스모크 테스트
- [x] 최종 EXE CPU 실제 분리 스모크 테스트

## v2.00 완료 (2026-07-16)

- [x] 레트로 하드웨어 UI 확정 (창 폭 600px, LCD 진행 헤더, 스테이지 램프 색 구분)
- [x] 설정 모달 카드형 재설계 (GPU·저장 형식은 메인 노브로 이동)
- [x] P2 추천 모델 gabox 교체 (반주 SDR 14.65 → 16.37)
- [x] 링크 중복 추가 허용, yt-dlp 실제 오류 로그 + 자동 재시도
- [x] 데드 코드 정리 (native_ui.py, 미사용 API 메서드/CSS)
- [x] 업데이트 확인 기능 실검증 (실제 GitHub 릴리즈 조회, sha256 지문 수신)
- [x] 단위 테스트 22개 통과, 스모크(cuda 포함) 정상

## v2.01 완료 (2026-07-16)

- [x] Inno Setup v2.00 설치 파일 빌드 및 GitHub 릴리즈 v2.00 업로드
- [x] 볼륨 보정 기능 (구간 평탄화 + -14 LUFS, 기본 ON, demucs 제외)
- [x] 분리 프로그램(P1~P6) 선택 저장·복원
- [x] UI 마무리 (TRACK/PROGRESS 헤더, 대기열 병합, RESET 통합 초기화)
- [x] v2.01 릴리즈 업로드 (v2.00 사용자 앱 내 업데이트 대상)

## v2.02 진행 상황

### 완료 (백엔드 + 빌드 준비, 테스트 40개 통과)
- [x] 가사 자동 저장 — `app/lyrics.py`: 해외 싱크 소스 우선 → 국내 가사 소스 폴백 → 없으면 스킵, 가수+곡+길이 검증으로 오매칭 방지
- [x] 키 감지 — `app/keyshift.py` `detect_key()`: librosa 크로마 + K-S 프로파일 (madmom은 git-master라 빌드 번들 리스크로 미채용)
- [x] 키 시프트 — `app/keyshift.py` `shift_file()`: Signalsmith Stretch(python-stretch, MIT), 템포 유지·길이 완전 보존 검증. 드럼 보존 경로는 이득 없어 폐기
- [x] 파이프라인 연결 — `_separate`에 키 이동(WAV 중간산출→시프트→인코딩) + 가사 저장, `config` key_shift(-6~+6)·download_lyrics 추가
- [x] 업데이트 UX — 다운로드·무결성 검사 후 설치 실행 상태를 즉시 표시하고, 설치기에서 앱을 안정적으로 재실행
- [x] 빌드 준비 — spec에 python_stretch·soundfile·librosa 번들, contents_directory="runtime"(_internal 개명), 버전 2.02(version.py·iss·version_info)

### UI 반영 완료
- [x] 대기열 곡별 키(감지→목표 ±)·가사(♪) 컨트롤, 완료 시 폴더 버튼
- [x] 프로그램 셀렉터를 카세트 피아노키 버튼(P1~P6)으로 교체 (노브 폐기 — 정렬 이슈 해소)
- [x] LED 세그먼트 진행 미터(초록→노랑→빨강), PROGRESS 헤더·나사 장식 제거로 컴팩트화
- [x] 앰버 필 토글 스위치, 설정 설명 간결화

### 빌드·릴리즈 완료 (2026-07-31)
- [x] 단위 테스트 40개, compileall, 프로즌 리소스·분리 스모크 통과
- [x] PyInstaller 재빌드(런타임 폴더 개명, Signalsmith/soundfile 번들 확인)
- [x] Inno Setup 설치 파일 생성 — release/Tube-Vocal-Removal-Setup-v2.02.exe (1.78GB)
- [x] GitHub Release v2.02 업로드 및 설치 파일 교체 검증
- [x] 로컬 정리 — 재생성 가능한 build/dist, 테스트 output, v2.00·v2.01 설치 파일, Python 캐시 제거
- [x] 같은 URL 재사용 시 임시 해시가 아닌 원래 곡 제목으로 폴더·파일명 유지
- [x] 소스 공개 전환 — 런타임 모델·바이너리·빌드 결과만 제외하도록 `.gitignore` 정리
- [x] Windows/macOS 플랫폼 분기 — 실행 파일명, subprocess 플래그, 폴더 열기, 프로세스 종료
- [x] Apple Silicon MPS/CoreML 가속 및 CPU 폴백
- [x] macOS 의존성·PyInstaller `.app` spec·DMG GitHub Actions 빌드 추가

### 남음
- [ ] 빌드된 앱에서 키 변경 수동 확인 1회 (frozen python_stretch 실행 경로)
- [x] 업데이트 용량 축소 — 패치 설치 파일 도입 (v2.04). CPU/GPU 런타임 분리와 MSIX는 계속 검토
- [ ] 검토: Microsoft Store MSIX 배포
- [ ] 실제 Apple Silicon Mac에서 최초 실행·모델 다운로드·전체 분리 E2E 검증

### 폐기 결정
- 코러스만 추출(P7): 리드-코러스가 원리적으로 겹쳐 리드 잔여 불가피. BVE 전용 모델·2단계 캐스케이드·2단계 모델 교체 모두 품질 미달. MVSep 등 유료도 동일 한계라 미채용.

## v2.03 진행 상황 — RTX 50(Blackwell) 지원

원인: 기존 배포본 torch 2.13.0+cu126은 sm_50~sm_90 커널만 포함(PTX 없음) → RTX 50(sm_120)에서 커널 실행 실패로 분리 파일 미생성. `torch.cuda.is_available()`은 True라 GPU 경로로 진입한 뒤 첫 커널에서 죽음.

결정: CUDA 13(cu130) **단일 빌드**. sm_75~sm_120 지원(RTX 20xx~50). CUDA 13이 Pascal 이하를 드랍해 GTX 10xx 이하는 GPU 가속 상실 → preflight 가드로 CPU 자동 폴백. 2종 빌드는 릴리스 3.6GB·선택 혼란 대비 이득이 적어 폐기.

- [x] requirements — cu130 + onnxruntime-gpu>=1.27 (ORT는 1.27부터 CUDA 13 빌드). 실제 설치: torch 2.13.0+cu130, ORT 1.28.0
- [x] GPU preflight — arch 목록 비교(UI 표시용) + 실제 커널 1회 실행(워커 최종 판정), 실패 시 CPU 폴백 + 안내 로그
- [x] 버전 2.03 일괄 반영 (version.py·iss·version_info·index.html·lyrics UA·mac spec)
- [x] README — 지원 그래픽 카드 명기
- [x] .venv cu130 재설치, 테스트 42개 통과 (arch 가드 테스트 추가)
- [x] cu130 arch 목록 실측 확인 — `['sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']` (RTX 50 포함, Pascal 제외)
- [x] 폴백 E2E — venv/frozen EXE 양쪽에서 use_gpu=True 요청 시 CPU 전환 + 결과 파일 정상 생성 확인
- [x] PyInstaller 빌드(3.5GB), 리소스 스모크·실오디오 분리 스모크 통과
- [x] 설치파일 생성 + SHA-256 갱신 (Windows 1.91GB / macOS DMG 393MB)
- [x] GitHub Release v2.03 정식 업로드 — Windows exe + macOS DMG, 업데이터 digest 검증 완료
- [x] CI 간헐 실패 수정 — `add_files()`의 키 감지 스레드가 임시 오디오를 잡은 채 테스트가 폴더를 지워
      Windows에서 `PermissionError(WinError 32)` 발생. 같은 구조 5곳에서 감지를 비활성화
- [x] 저장소 정리 — 과거 커밋 5건의 `Co-Authored-By` 트레일러 제거(히스토리 재작성, 파일 내용 무변경),
      백업 브랜치·빌드 산출물·구버전 설치 파일 제거로 약 6GB 확보
- [x] GPU 실검증 완료 (v2.04) — RTX 3060에서 CUDA 분리 35초, CPU 대비 10배
      단 RTX 50(sm_120) 실기기 검증은 여전히 제보자 확인 필요

### 드라이버 요구사항 (릴리스 노트에 반드시 포함)
CUDA 13은 NVIDIA 드라이버 **580 이상**을 요구한다. 카드가 sm_75 이상이어도 드라이버가 낮으면
`cudaGetDeviceCount()`가 `cudaErrorNotSupported`를 반환해 GPU를 못 쓴다. 즉 v2.02에서 GPU가 되던
RTX 30/40 사용자도 드라이버가 낮으면 CPU로 떨어진다(폴백 안내 문구로 업데이트 유도).
`torch.cuda.get_device_capability(0)`은 이 상태에서 예외가 아니라 **세그폴트**를 내므로
`cuda_arch_supported()`는 반드시 `is_available()` 확인을 먼저 한다.

## 배포 전 남은 작업

- [ ] 모델이 없는 깨끗한 PC에서 최초 다운로드 테스트
- [ ] NVIDIA GPU가 없는 PC에서 CPU 전체 E2E 테스트
- [ ] NVIDIA GPU PC에서 GPU 전체 E2E 테스트
- [ ] 접근성: 키보드 포커스, Esc, 명도 대비 점검
