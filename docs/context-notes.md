# Vocal Inst — 컨텍스트 노트

작업 중 내린 결정과 근거를 기록한다. 새 세션은 이 파일부터 읽을 것.

## 2026-07-15

- **프로젝트 시작.** 목표: 유튜브 링크 → mp3 → 보컬/반주 자동 분리 + 새 UI. 환경: Windows 10 + NVIDIA GPU.
- **UVR 전체 fork 대신 엔진 활용 결정.** UVR.py는 약 1.7만 줄 Tkinter 모놀리스라 UI 교체가 사실상 재작성. 대신 UVR 엔진을 MIT로 패키지화한 `python-audio-separator`(nomadkaraoke) 사용 — 같은 모델 파일이라 분리 품질 동일, pip 설치, Python API 제공.
- **UI는 Gradio로 v1 진행 예정** (사용자 최종 확인 대기). 근거: 진행률/오디오 재생 내장, 최소 코드. 데스크톱 네이티브가 필요해지면 CustomTkinter/PySide6 재검토.
- 라이선스: UVR, audio-separator 모두 MIT.
- 작업 폴더는 빈 상태에서 시작 (`.bkit`만 존재). 원본 UVR 저장소 clone은 불필요해짐 — 참고용으로만 필요 시 조회.
- **용도 확정: 보컬 연습.** M4에 키 조절·구간 반복·미리듣기 후보 추가. UI는 처음부터 100% 한국어.
- **exe 배포 요구 추가 → UI를 Gradio에서 CustomTkinter로 변경.** 근거: Gradio는 PyInstaller 패키징이 취약하고 브라우저 UX가 exe와 안 맞음. 패키징(M5)은 필수 마일스톤으로 승격 — PyInstaller 폴더 모드 + Inno Setup.
- **yt-dlp는 파이썬 라이브러리가 아니라 yt-dlp.exe 동봉 + subprocess 호출.** 근거: exe에 얼리면 유튜브 변경 시 앱 전체를 재배포해야 함. 별도 바이너리면 `yt-dlp -U` 자동 업데이트 가능.
- **용어: "MR" 사용 금지 (사용자 피드백 — 콩글리시).** UI·문서에서 "반주"로 통일.
- **다운로드 후 중간 mp3 변환은 기본 OFF 추천.** 원본 오디오(m4a/webm)를 바로 분리 엔진에 넣는 게 재인코딩 손실이 없음. mp3는 최종 출력 포맷 옵션으로만.
- **다운로드 도구는 yt-dlp 확정 (대안 조사 완료 2026-07-15).** pytubefix·cobalt 등 대안 조사 결과 yt-dlp가 유지보수·안정성 최상. 프리미엄 없이 받을 수 있는 유튜브 음질 상한은 Opus 포맷 251(~130-160kbps VBR) — 어떤 도구를 써도 동일한 서버측 제한. 256kbps(포맷 774)는 Premium 계정 쿠키 필요.
- **UI 입출력 방식 확정 (사용자 요구).** 입력은 유튜브 URL + 로컬 파일 두 경로 모두. 출력 폴더는 UVR처럼 매번 선택하지 않고 설정 화면에서 한 번 지정 → config 파일로 영구 저장, 항상 그 폴더로 출력.
- **설정 간소화 방침 확정.** UVR이 노출하는 모델 파라미터(segment size, overlap, aggression 등)는 전부 모델별 권장값으로 코드에 내장하고 사용자에게 묻지 않는다. 설정 화면은 4개 항목만: 출력 폴더 / 저장 형식 / GPU / 저장 대상(반주만·둘 다). 모델 다운로드는 최초 사용 시 자동. Ensemble 등 파워유저 기능은 v1 제외.
- **UI 목업 완성 (mockup/vocalab-mockup.html + 아티팩트).** HTML로 제작 — 확정 시 pywebview로 그대로 실제 UI화 예정. UI 프레임워크 최종 결정은 목업 피드백 후 (CustomTkinter vs pywebview+HTML).
- **UI 프레임워크 최종 확정: pywebview + HTML/JS (2026-07-15).** 목업을 HTML로 반복 수정하며 사용자가 확정 → 그 HTML을 그대로 실제 UI로 사용. CustomTkinter 계획은 폐기. 스타일: 빈티지 아날로그 랙 장비(크림/호박색, 나사·주얼램프·VU미터 디테일), 대기열 배치 방식, 곡 추가는 한 줄(URL Enter + 파일 선택), 진행 표시는 곡 제목 + 바 안 "단계 · %".
- **UI 목업 외부 리뷰(Codex/GPT) 완료 (2026-07-15).** 핵심 지적: ① 취소/중단/실패 상태 부재가 최우선 ② 처리 중 입력 잠금 필요 ③ 진행률 의미(전체 vs 현재 곡) 구분 ④ pywebview 전환 시 무거운 작업은 파이썬 작업 큐로 분리하고 JS엔 상태 이벤트만 전달, 진행 이벤트 빈도 제한, 자식 프로세스 정리 필수. 상세 항목은 checklist.md M3 "외부 리뷰 반영 항목" 참고.
- **이름 방향: "(한 단어) Vocal Removal v1.00" 형식 (사용자 결정).** 앞 단어 후보 제안: Tube(잠정 적용) / Reel / Analog / Pure / Echo. 확정 대기.
- **기본 분리 모델 후보: BS-Roformer** (audio-separator 기본값, SDR 12.98). 사용자가 쓰던 MDX-NET Inst HQ 3보다 분리 품질 우수. 보컬 연습용으로 Karaoke 계열(리드 보컬만 제거, 코러스 유지) 모델도 드롭다운에 포함할 것.
