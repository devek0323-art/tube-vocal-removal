# Vocal Inst — 계획서

> 유튜브 링크/로컬 파일 → 보컬·반주 자동 분리 파이프라인 + 새 UI
> **용도: 보컬 연습** (반주 제작이 핵심 유스케이스). UI는 처음부터 100% 한국어로 만든다.
> **앱 이름(잠정): Tube Vocal Removal v1.00** — 앞 단어(Tube/Reel/Analog/Pure/Echo) 확정 대기.

작성일: 2026-07-15

## 1. 목표

- 유튜브 링크를 입력하면 mp3로 다운로드한 뒤 자동으로 보컬(Vocals) / 반주(Instrumental)를 분리해서 저장한다.
- 로컬 오디오 파일도 동일하게 처리할 수 있다.
- UVR의 낡은 Tkinter UI 대신 새 UI를 제공한다.
- 환경: Windows 10, NVIDIA GPU (CUDA 가속 사용).

## 2. 접근 방식 비교

| 항목 | A. UVR 전체 fork 후 수정 | B. 분리 엔진만 활용해 새 앱 (선택) |
|---|---|---|
| UI 변경 | UVR.py가 약 1.7만 줄의 Tkinter 모놀리스(GUI+로직 결합). UI 교체 = 사실상 전체 재작성 | 처음부터 원하는 UI로 시작 |
| 기능 추가 | 거대 파일 안에 끼워 넣어야 해서 파악/수정 비용 큼 | 파이프라인 코드가 독립적이라 단순 |
| 의존성 | Python 3.9~3.10 + 구버전 라이브러리에 고정 | 최신 Python/PyTorch 사용 가능 |
| 분리 품질 | UVR 모델 그대로 | **동일** — 같은 모델(MDX-Net, VR Arch, Demucs, MDX23C)을 그대로 사용 |
| 유지보수 | 업스트림 변경 반영 어려움 | pip 패키지 업데이트로 해결 |

**결정: B.** UVR의 분리 엔진은 [`python-audio-separator`](https://github.com/nomadkaraoke/python-audio-separator) (MIT)로 이미 패키지화되어 있다. UVR과 같은 모델 파일을 쓰기 때문에 분리 품질은 동일하고, pip 한 줄로 설치되며 Python API와 CLI를 모두 제공한다. "UVR 개조"라기보다 "UVR 엔진 기반 새 앱"이지만, 목표(파이프라인 + 새 UI)에 도달하는 가장 짧은 경로다.

라이선스: UVR, audio-separator 모두 MIT — 개조/배포 자유 (저작자 표기 유지).

## 3. 아키텍처

```
[UI — Gradio 웹앱 (로컬 실행)]
    │  유튜브 URL 또는 로컬 파일, 모델 선택
    ▼
[pipeline]
 1. yt-dlp        : bestaudio 다운로드 → ffmpeg로 mp3 변환
 2. audio-separator: 보컬/반주 분리 (GPU, 모델 선택 가능)
 3. 출력 정리      : output/<곡명>/{vocals,instrumental}.* 형태로 저장
```

### 기술 스택

| 역할 | 선택 | 비고 |
|---|---|---|
| 다운로드 | yt-dlp.exe (별도 동봉) | subprocess 호출. exe에 얼리지 않고 별도 바이너리로 두어 `yt-dlp -U` 자동 업데이트 가능하게 |
| 분리 엔진 | audio-separator | 개발은 CUDA(onnxruntime-gpu). 배포용으로 DirectML 경량 빌드 가능 여부 M1에서 검증 |
| UI | **pywebview + HTML/JS** | 확정된 HTML 목업(mockup/vocalab-mockup.html)을 그대로 네이티브 창에 담아 실제 UI로 사용. Windows 내장 WebView2 기반이라 가벼움. (Gradio → CustomTkinter → pywebview로 변경, 2026-07-15) |
| 패키징 | PyInstaller (폴더 모드) + Inno Setup | 단일 exe는 용량 때문에 비현실적 — 설치 파일로 배포 |
| 언어 | Python 3.10+ | venv 사용 |

## 4. 마일스톤

각 단계는 검증 기준을 통과해야 다음으로 진행한다.

1. **환경 구축** → 검증: 샘플 mp3 하나를 CLI로 분리 성공, GPU 사용 확인 (`nvidia-smi` 점유 확인)
   - venv 생성, ffmpeg 설치 확인, audio-separator[gpu] 설치
2. **파이프라인 코어** → 검증: 실제 유튜브 링크 1개로 다운로드→분리→저장 end-to-end 성공
   - `pipeline.py`: URL → mp3 → 분리 → 출력 폴더 정리, CLI로 실행 가능
3. **UI v1 (pywebview + 확정 목업 HTML)** → 검증: URL 입력→분리→결과 확인, 파일 입력→분리→결과 확인 수동 테스트
   - 확정된 목업(mockup/vocalab-mockup.html, 빈티지 랙 장비 스타일)을 pywebview 네이티브 창에 탑재하고 파이썬 엔진과 연결
   - 입력: 유튜브 URL 입력창(Enter로 추가) + 파일 선택 버튼 + 창 전체 드래그 앤 드롭 — 대기열(배치) 방식
   - 출력: 설정에서 출력 폴더 한 번 지정 → 항상 그 폴더에 곡별 하위 폴더로 저장 (config 파일로 영구 보존)
   - 분리 방식 드롭다운(용도 기준 한국어 이름), 진행 표시(전체 n/m + 현재 곡 단계·%), 폴더 열기 버튼
   - 외부 리뷰(Codex) 반영 항목은 checklist.md M3 참고 — 취소/실패 상태가 핵심
4. **개선** → 검증: 각 기능별 수동 테스트
   - 배치 처리(여러 링크), 출력 포맷 선택(wav/mp3/flac), 자주 쓰는 설정 프리셋
   - 보컬 연습 특화 기능 후보: 키(피치) 조절, 구간 반복(AB 루프) 재생, 미리듣기(30초) 모드
5. **패키징/배포 (필수)** → 검증: 개발 환경이 아닌 깨끗한 PC에서 설치 후 e2e 성공
   - PyInstaller 폴더 모드 빌드, yt-dlp.exe·ffmpeg 동봉, Inno Setup 설치 파일 제작
   - CPU 폴백 확인 (NVIDIA 없는 PC 대응), DirectML 경량 빌드 검토 결과 반영

## 5. 주의사항

- 모델 가중치는 첫 실행 시 자동 다운로드된다 (모델당 수십~수백 MB).
- yt-dlp는 개인적 용도로만 사용한다 (YouTube 약관 참고).
- MDX23C·Demucs 등 큰 모델은 VRAM을 수 GB 사용할 수 있다 — GPU 사양에 맞는 모델을 기본값으로 정한다.
