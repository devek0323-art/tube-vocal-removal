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

## 배포 전 남은 작업

- [ ] Inno Setup 설치 파일 빌드
- [ ] 모델이 없는 깨끗한 PC에서 최초 다운로드 테스트
- [ ] NVIDIA GPU가 없는 PC에서 CPU 전체 E2E 테스트
- [ ] NVIDIA GPU PC에서 GPU 전체 E2E 테스트
- [ ] 접근성: 키보드 포커스, Esc, 명도 대비 점검
