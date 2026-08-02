# Tube Vocal Removal v2.03

YouTube 링크 또는 로컬 오디오에서 보컬/반주를 분리하는 Windows·macOS 데스크톱 앱입니다. 원본 HTML 목업을 pywebview(WebView2) 창으로 실행하며 별도 웹 서버는 사용하지 않습니다.

## 실행

최종 실행 파일:

```text
dist\Tube Vocal Removal\Tube Vocal Removal.exe
```

`runtime` 폴더가 반드시 EXE와 같은 폴더에 있어야 하므로 배포할 때는 `Tube Vocal Removal` 폴더 전체를 전달해야 합니다. 모델은 EXE에 포함하지 않으며 처음 사용하거나 설정에서 미리 받기를 누르면 `%APPDATA%\TubeVocalRemoval\models`에 저장됩니다.

- 기본 연산 장치: CPU
- GPU: 설정에서 사용자가 직접 켠 경우에만 사용. Windows는 CUDA 13 빌드라 Turing(sm_75) 이상 + NVIDIA 드라이버 580 이상이 필요하고, macOS는 Apple Silicon MPS/CoreML을 쓴다
- 지원하지 않는 GPU는 워커가 커널을 1회 시험 실행해 걸러내고 CPU로 폴백한다
- 기본 추천: 코러스 유지 Karaoke 모델
- 빠른 처리, 최고 품질 3모델, 전체 보컬 제거, 보컬 추출, Demucs 4트랙 지원
- 저장 파일은 분리 방식에 따라 자동 결정됩니다: 반주 계열 1개, 보컬 추출 1개, 악기별 분리 4개

## 개발 및 빌드

```powershell
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\build.ps1
```

리소스 점검:

```powershell
& '.\dist\Tube Vocal Removal\Tube Vocal Removal.exe' --smoke-test '.\smoke-report.json'
```

실제 오디오 분리 점검:

```powershell
& '.\dist\Tube Vocal Removal\Tube Vocal Removal.exe' --smoke-audio '.\sample.wav' '.\smoke-output' '.\smoke-audio-report.json'
```

## 현재 동작

- 링크 입력 후 Enter를 누르면 제목을 조회해 대기열에 추가합니다.
- 처리 중에도 링크/파일을 추가할 수 있고 같은 실행에서 이어서 처리합니다.
- 같은 링크도 중복으로 추가할 수 있으며 항상 새 대기열 행으로 들어갑니다.
- YouTube 다운로드율과 AI 청크 처리율을 진행 막대에 표시합니다.
- YouTube 한글 제목과 결과 파일명은 Windows 조합형 유니코드로 정규화합니다.
- 실패 원인은 진행 상황 로그에 yt-dlp/워커의 실제 오류와 함께 기록됩니다 (대기열에는 상태 칩만 표시).
- 파일 드롭은 pywebview 네이티브 경로 브리지를 사용하며 RESET으로 대기열 전체를 비울 수 있습니다.
- AI 엔진은 자식 프로세스로 분리되어 중단 시 종료할 수 있습니다.
- 자식 FFmpeg/다운로드 프로세스의 CMD 창을 숨깁니다.
- 설정에서 개별 모델 또는 중복을 제외한 전체 모델을 미리 받을 수 있습니다.
- 전체 창에는 스크롤을 만들지 않고 대기열과 로그만 내부 스크롤합니다.
- 곡별 키 이동(-6~+6)과 가사 저장을 지원하며, 볼륨 보정은 구간 평탄화 후 -14 LUFS로 맞춥니다.
- GPU를 켜 두어도 해당 그래픽 카드로 연산이 불가능하면 오류 없이 CPU로 이어서 처리합니다.

최종 검증일: 2026-08-02
