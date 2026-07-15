# Vocal Inst — 체크리스트

## M1. 환경 구축
- [ ] Python 3.10+ venv 생성
- [ ] ffmpeg 설치 및 PATH 확인
- [ ] `pip install audio-separator[gpu]` + CUDA용 onnxruntime/torch 동작 확인
- [ ] 샘플 mp3 분리 성공 (CLI) — GPU 사용 확인
- [ ] 청음 테스트: 같은 곡을 BS-Roformer / MDX HQ 4 / Karaoke로 분리해 비교 → 앱 기본 모델 확정

## M2. 파이프라인 코어
- [ ] yt-dlp로 유튜브 URL → mp3 다운로드 함수
- [ ] audio-separator Python API로 분리 함수 (모델 파라미터화)
- [ ] 출력 폴더 구조 정리 (`output/<곡명>/`)
- [ ] CLI 진입점 (`python pipeline.py <URL>`)
- [ ] e2e 검증: 실제 링크 1개 처리 성공

## M3. UI v1 (pywebview + 확정 목업 HTML)
- [ ] 유튜브 URL 입력창
- [ ] 로컬 파일 선택 (드래그 앤 드롭 검토)
- [ ] 설정 화면: 출력 폴더 지정 (config 파일로 영구 저장, 매번 선택 없음)
- [ ] 모델 선택 드롭다운 (용도 기준 한국어 이름)
- [ ] 진행 상태 표시 (전체 n/m + 현재 곡 단계·%)
- [ ] 완료 시 출력 폴더 열기 버튼 (+ 완료된 곡별 폴더 열기)
- [ ] URL 경로 / 파일 경로 각각 수동 검증

### 외부 리뷰(Codex) 반영 항목 — 2026-07-15
- [ ] 취소/중단 흐름: 현재 곡 중단, 전체 중단, 처리 중 창 닫기 확인
- [ ] 곡별 실패 상태 (실패/건너뜀/취소됨) + 원인 표시 + 다시 시도, 한 곡 실패해도 대기열 계속
- [ ] 처리 중 입력·설정 잠금 (또는 "다음 실행 대기" 구분)
- [ ] URL 검증 (붙여넣기 시점), 중복 곡 안내
- [ ] 파일 드래그 앤 드롭 실제 구현 + 드롭 시 화면 강조
- [ ] GPU 감지: 시작 시 감지해서 사용 불가면 이유 표시 + CPU 자동 전환
- [ ] 접근성: 모달 Esc/포커스, 삭제 버튼 클릭 영역 확대, 보조 텍스트 대비 상향
- [ ] HTML 기본 구조 (doctype, charset=utf-8, lang=ko) — pywebview 전환 전 필수
- [ ] 파일명 안전화 (Windows 금지 문자, 중복 제목 폴더 충돌)

## M4. 개선
- [ ] 배치 처리 (여러 링크)
- [ ] 출력 포맷 선택 (wav/mp3/flac)
- [ ] 설정 프리셋

## M5. 패키징/배포 (필수)
- [ ] PyInstaller 폴더 모드 빌드 성공
- [ ] yt-dlp.exe / ffmpeg 동봉 + yt-dlp 자동 업데이트 동작
- [ ] Inno Setup 설치 파일 제작
- [ ] 깨끗한 PC에서 설치 → e2e 검증 (CPU 폴백 포함)
