APP_VERSION = "3.0"
# 번들된 파이썬·CUDA 런타임의 식별자. 의존성이 바뀔 때만 올린다.
# 이 값이 같은 릴리스끼리는 런타임을 뺀 패치 파일로 업데이트할 수 있다.
RUNTIME_REVISION = "cu128-1"
# 위 식별자가 어느 requirements.txt를 가리키는지 기록해 둔다. 패키지를 바꿔 놓고
# RUNTIME_REVISION을 안 올리면 런타임 파일이 빠진 패치가 나가 앱이 죽는다.
# requirements.txt를 고쳤다면 이 해시와 RUNTIME_REVISION을 함께 갱신할 것.
RUNTIME_REQUIREMENTS_SHA = "0fea51b50021"
# requirements가 바뀌었지만 패치가 직접 담아 나르는 패키지. 여기 적힌 것은
# RUNTIME_REVISION을 올리지 않아도 되며, 설치 스크립트에 실제로 들어 있어야 한다.
RUNTIME_PATCHED_PACKAGES = ("whisper", "tiktoken", "regex")

GITHUB_REPOSITORY = "devek0323-art/tube-vocal-removal"
GITHUB_API_VERSION = "2022-11-28"
