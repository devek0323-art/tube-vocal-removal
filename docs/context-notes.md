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

- 추천 Karaoke: `mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt`
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
