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

## 배포 전 남은 작업

- [ ] Inno Setup으로 v2.00 설치 파일 빌드
- [ ] GitHub 릴리즈 v2.00 업로드 (README·태그 v2.00 형식)
- [ ] 모델이 없는 깨끗한 PC에서 최초 다운로드 테스트
- [ ] NVIDIA GPU가 없는 PC에서 CPU 전체 E2E 테스트
- [ ] NVIDIA GPU PC에서 GPU 전체 E2E 테스트
- [ ] 접근성: 키보드 포커스, Esc, 명도 대비 점검
