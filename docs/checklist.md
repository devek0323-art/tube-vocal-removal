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

### 완료 (백엔드 + 빌드 준비, 테스트 36개 통과)
- [x] 가사 자동 저장 — `app/lyrics.py`: 해외 싱크 소스 우선 → 국내 가사 소스 폴백 → 없으면 스킵, 가수+곡+길이 검증으로 오매칭 방지
- [x] 키 감지 — `app/keyshift.py` `detect_key()`: librosa 크로마 + K-S 프로파일 (madmom은 git-master라 빌드 번들 리스크로 미채용)
- [x] 키 시프트 — `app/keyshift.py` `shift_file()`: Signalsmith Stretch(python-stretch, MIT), 템포 유지·길이 완전 보존 검증. 드럼 보존 경로는 이득 없어 폐기
- [x] 파이프라인 연결 — `_separate`에 키 이동(WAV 중간산출→시프트→인코딩) + 가사 저장, `config` key_shift(-6~+6)·download_lyrics 추가
- [x] 업데이트 UX — /SILENT(진행 표시) + /RESTARTAPPLICATIONS + .iss RestartApplications=yes (설치 후 앱 자동 재실행)
- [x] 빌드 준비 — spec에 python_stretch·soundfile·librosa 번들, contents_directory="runtime"(_internal 개명), 버전 2.02(version.py·iss·version_info)

### UI 반영 완료
- [x] 대기열 곡별 키(감지→목표 ±)·가사(♪) 컨트롤, 완료 시 폴더 버튼
- [x] 프로그램 셀렉터를 카세트 피아노키 버튼(P1~P6)으로 교체 (노브 폐기 — 정렬 이슈 해소)
- [x] LED 세그먼트 진행 미터(초록→노랑→빨강), PROGRESS 헤더·나사 장식 제거로 컴팩트화
- [x] 앰버 필 토글 스위치, 설정 설명 간결화

### 빌드·릴리즈 완료 (2026-07-31)
- [x] 단위 테스트 38개, compileall, 프로즌 리소스·분리 스모크 통과
- [x] PyInstaller 재빌드(런타임 폴더 개명, Signalsmith/soundfile 번들 확인)
- [x] Inno Setup 설치 파일 생성 — release/Tube-Vocal-Removal-Setup-v2.02.exe (1.78GB)

### 남음
- [x] 릴리즈 v2.02 업로드 (gh release) + 문서 커밋·푸시(코드 비공개)
- [ ] 빌드된 앱에서 키 변경 수동 확인 1회 (frozen python_stretch 실행 경로)
- [ ] 검토: CPU/GPU 런타임 분리(설치 용량·시간 축소), Microsoft Store MSIX 배포, 맥 포팅(GitHub Actions 매트릭스)

### 폐기 결정
- 코러스만 추출(P7): 리드-코러스가 원리적으로 겹쳐 리드 잔여 불가피. BVE 전용 모델·2단계 캐스케이드·2단계 모델 교체 모두 품질 미달. MVSep 등 유료도 동일 한계라 미채용.

## 배포 전 남은 작업

- [ ] 모델이 없는 깨끗한 PC에서 최초 다운로드 테스트
- [ ] NVIDIA GPU가 없는 PC에서 CPU 전체 E2E 테스트
- [ ] NVIDIA GPU PC에서 GPU 전체 E2E 테스트
- [ ] 접근성: 키보드 포커스, Esc, 명도 대비 점검
