# Tube Vocal Removal v2.02

유튜브 링크나 오디오 파일에서 **보컬과 반주를 AI로 분리**하는 데스크톱 프로그램입니다.
개인 보컬 연습 용도로 만들어졌습니다.

## 다운로드

| 운영체제 | 다운로드 | 지원 환경 | GPU 가속 |
|---|---|---|---|
| Windows | [Tube-Vocal-Removal-Setup-v2.02.exe](https://github.com/devek0323-art/tube-vocal-removal/releases/download/v2.02/Tube-Vocal-Removal-Setup-v2.02.exe) | Windows 10/11 64비트 | NVIDIA CUDA 또는 CPU |
| macOS | [Tube-Vocal-Removal-macOS-arm64.dmg](https://github.com/devek0323-art/tube-vocal-removal/releases/download/v2.02/Tube-Vocal-Removal-macOS-arm64.dmg) | macOS 14 이상, Apple Silicon(M1 이상) | Apple MPS/CoreML 또는 CPU |

파일 무결성 확인용 SHA-256:

- Windows: `B53E2ED4B0AD8A7C0384D5640B7DCDCA473684335DD23876876B116F358BFD48`
- macOS: `4682859E58AE0445835B90CBE2104CB5F383128498834375F11D62EECA0A4B11`

- AI 모델은 첫 사용 시 자동으로 다운로드됩니다 (인터넷 연결 필요)
- 기본은 CPU로 동작하며, 지원 GPU가 감지되면 설정에서 가속을 켤 수 있습니다
- 설정에서 GitHub Releases의 최신 버전을 확인하고 안전하게 업데이트할 수 있습니다

### macOS 안내

macOS 버전은 Apple Silicon ARM64용 `.app`을 DMG로 제공합니다. NVIDIA CUDA 대신
PyTorch MPS와 ONNX Runtime CoreML을 사용합니다.

- GitHub의 Apple Silicon macOS 러너에서 빌드·앱 실행·리소스 검사·DMG 패키징을 통과했습니다
- 실제 Mac에서 모델 다운로드 후 전체 곡 분리는 추가 실기기 검증이 필요합니다
- 서명·공증되지 않은 개발 빌드이므로 Gatekeeper 경고가 표시될 수 있습니다

## 사용법

1. 유튜브 링크를 붙여넣고 Enter — 또는 오디오 파일을 창에 드래그
2. 분리 방식 선택 (기본 추천: 반주 + 코러스)
3. 곡마다 **키(음정)를 올리거나 내릴** 수 있고, **가사도 함께 저장**됩니다
4. "분리 시작" 클릭 → 완료되면 출력 폴더에 곡별로 저장

여러 곡을 한 번에 담아 순차 처리할 수 있고, 처리 중에도 곡을 추가할 수 있습니다.

## 소스에서 빌드

Python 3.12를 사용합니다. `bin/`의 FFmpeg, yt-dlp, Deno는 저장소에 직접 넣지 않고
`scripts/prepare_tools.py`가 공식 배포본을 준비합니다.

```powershell
# Windows
python -m pip install -r requirements.txt
python scripts/prepare_tools.py windows
pyinstaller TubeVocalRemoval.spec --noconfirm
```

```bash
# macOS (Apple Silicon)
python3 -m pip install -r requirements-mac.txt
python3 scripts/prepare_tools.py macos
bash scripts/create_macos_icon.sh
pyinstaller TubeVocalRemoval-mac.spec --noconfirm
```

두 플랫폼의 전체 패키징 절차는 `.github/workflows/build.yml`에 정의되어 있습니다.

### v2.02 새 기능

- **키 변경** — 곡의 원래 키를 자동 감지해 표시하고, 음질 손실 없이 반음 단위로 올리거나 내립니다 (노래방식 조옮김, 템포 유지)
- **가사 저장** — 분리 시 곡 폴더에 가사(`.txt`)를 함께 저장합니다 (없는 곡은 건너뜀)

### 분리 방식

| 방식 | 설명 |
|---|---|
| 반주 + 코러스 · 추천 | 메인 보컬만 제거하고 코러스는 유지 |
| 반주 + 코러스 · 빠른 처리 | 구형 PC를 위한 빠른 모델 |
| 반주 + 코러스 · 최고 품질 | 3개 모델 앙상블 (가장 정교, 느림) |
| 반주만 · 모든 보컬 제거 | 코러스 포함 목소리 전부 제거 |
| 보컬만 추출 | 반주를 지우고 보컬만 저장 |
| 악기별 분리 · 4트랙 | 보컬·드럼·베이스·기타 악기 각각 저장 |

## 이용 안내

이 프로그램은 **개인 연습 목적**으로 제공됩니다. 저작권이 있는 음원을 다운로드하거나 분리한
결과물을 공개적으로 배포·상업적으로 이용하는 것은 저작권 침해가 될 수 있으며, 그 책임은
사용자에게 있습니다.

## 사용된 오픈소스

- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator) (MIT) — UVR 호환 분리 엔진
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) — 유튜브 다운로드
- [FFmpeg](https://ffmpeg.org/) (GPL/LGPL) — 오디오 변환 · [소스 코드](https://github.com/FFmpeg/FFmpeg)
- [Deno](https://deno.land/) (MIT) · [PyTorch](https://pytorch.org/) (BSD-3) · [pywebview](https://pywebview.flowrl.com/) (BSD-3)
- 분리 모델: [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) 및 커뮤니티 제작 모델 (첫 사용 시 공개 저장소에서 자동 다운로드)
- [Demucs](https://github.com/facebookresearch/demucs) (MIT) — 4트랙 분리 모델
