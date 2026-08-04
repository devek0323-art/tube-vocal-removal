import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from pathlib import Path

from app import config
from app.platform_support import IS_WINDOWS, hidden_process_kwargs, terminate_process_tree, tool_name


BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
YTDLP = BASE_DIR / "bin" / tool_name("yt-dlp")
FFMPEG_DIR = BASE_DIR / "bin"
FFMPEG = FFMPEG_DIR / tool_name("ffmpeg")

MODE_MODELS = {
    # becruily 카라오케 — 3곡 실측에서 gabox v1·v2보다 무보컬 구간 악기 손실이 일관되게 적었다.
    "karaoke": "mel_band_roformer_karaoke_becruily.ckpt",
    # becruily 반주 — ep_317(2023)보다 보컬 구간 아티팩트가 적고 35% 빠르다.
    "best": "mel_band_roformer_instrumental_becruily.ckpt",
    "karaoke_fast": "UVR_MDXNET_KARA_2.onnx",
    "vocals": "mel_band_roformer_instrumental_becruily.ckpt",
    "demucs": "htdemucs.yaml",
}

# `vocals`와 `best`는 같은 모델을 공유하므로 전체 받기에서는 한 번만 처리한다.
ALL_MODEL_MODES = ("karaoke", "best", "karaoke_fast", "demucs")

# audio-separator 0.44.3이 각 선택지에 요구하는 캐시 파일이다. 모델 본체뿐 아니라
# 설정 파일과 Demucs 가중치까지 있어야 설치 완료로 본다.
MODEL_REQUIRED_FILES = {
    "karaoke": (
        "mel_band_roformer_karaoke_becruily.ckpt",
        "config_mel_band_roformer_karaoke_becruily.yaml",
    ),
    "best": (
        "mel_band_roformer_instrumental_becruily.ckpt",
        "config_mel_band_roformer_instrumental_becruily.yaml",
    ),
    "vocals": (
        "mel_band_roformer_instrumental_becruily.ckpt",
        "config_mel_band_roformer_instrumental_becruily.yaml",
    ),
    "karaoke_fast": ("UVR_MDXNET_KARA_2.onnx",),
    "demucs": ("htdemucs.yaml", "955717e8-8726e21a.th"),
}

# 볼륨 보정 — 곡 전체에 같은 게인을 한 번만 걸고 넘치는 피크만 리미터로 잡는다.
# 예전에는 dynaudnorm으로 구간마다 게인을 다시 계산했는데, 조용한 스템에서 구간별
# 편차가 20dB까지 벌어져 분리 잔재가 도드라졌다. 다이내믹은 건드리지 않는다.
LOUDNESS_TARGET_LUFS = -14.0
LOUDNESS_MEASURE = "loudnorm=I=-14:TP=-1:LRA=11:print_format=json"
# MP3·AAC는 디코딩 시 원본보다 피크가 솟으므로 실링을 더 낮게 잡는다.
PEAK_CEILING_DB = {"MP3": -2.0, "FLAC": -1.0, "WAV": -1.0}

AUDIO_EXTS = frozenset({".mp3", ".wav", ".flac", ".m4a", ".opus", ".ogg", ".webm", ".aac"})
_id_counter = itertools.count(1)


def sanitize_name(name: str) -> str:
    """Windows에서 폴더/파일명으로 쓸 수 없는 문자를 제거한다."""
    name = unicodedata.normalize("NFC", str(name))
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip(" .")
    return cleaned[:120] or "제목없음"


def unique_dir(parent: Path, name: str) -> Path:
    """기존 결과를 덮어쓰지 않는 곡 폴더 경로를 만든다."""
    base = sanitize_name(name)
    candidate = parent / base
    number = 2
    while candidate.exists():
        candidate = parent / f"{base} ({number})"
        number += 1
    candidate.mkdir(parents=True)
    return candidate


class Item:
    def __init__(self, kind: str, source: str, title: str):
        self.id = next(_id_counter)
        self.kind = kind
        self.source = source
        self.title = title
        self.status = "wait"
        self.stage = ""
        self.error = ""
        self.out_dir = ""
        self.key_shift = 0          # 이 곡의 목표 키 이동 반음 수 (-6~+6)
        self.detected_key = ""      # 감지된 원곡 키 (예: 'C# minor'), 오디오 확보 후 채워짐
        self.want_lyrics = True     # 이 곡의 가사 저장 여부

    def to_dict(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "stage": self.stage,
            "error": self.error,
            "outDir": self.out_dir,
            "keyShift": self.key_shift,
            "detectedKey": self.detected_key,
            "wantLyrics": self.want_lyrics,
        }


class Pipeline:
    def __init__(self, emit):
        self.emit = emit
        self.items = []
        self.running = False
        self._cancel = threading.Event()
        self._proc = None
        self._proc_lock = threading.Lock()
        self._separation_runner = self._run_separation_process
        self.model_downloading = False
        # 같은 URL을 여러 키로 넣을 때 재다운로드로 유튜브에 차단되지 않도록 URL→파일 캐시
        self._download_cache = {}

    def add_urls(self, text: str) -> int:
        added = 0
        new_items = []
        for raw in re.split(r"\s+", (text or "").strip()):
            if not raw:
                continue
            if not re.match(r"https?://", raw):
                self._log(f"주소 형식이 아니라서 건너뜀: {raw}", False)
                continue
            # 같은 링크도 새 행으로 허용한다 — 다른 프로그램(P1~P6)으로 다시 돌리는 경우가 잦다.
            item = Item("url", raw, "제목 확인 중")
            self.items.append(item)
            new_items.append(item)
            added += 1
        self._emit_queue()
        if new_items:
            threading.Thread(target=self._resolve_url_titles, args=(new_items,), daemon=True).start()
        return added

    def _resolve_url_titles(self, items):
        """Resolve YouTube titles without blocking the UI or downloading audio."""
        for item in items:
            if item not in self.items or item.status != "wait":
                continue
            try:
                result = subprocess.run(
                    [
                        str(YTDLP),
                        "--dump-single-json",
                        "--skip-download",
                        "--no-playlist",
                        "--no-warnings",
                        "--socket-timeout",
                        "10",
                        item.source,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=35,
                    **hidden_process_kwargs(),
                )
                if result.returncode != 0:
                    raise RuntimeError("yt-dlp metadata lookup failed")
                info = json.loads(result.stdout)
                title = unicodedata.normalize("NFC", str(info.get("title") or "").strip())
                if not title:
                    raise RuntimeError("video title is empty")
                if item in self.items and item.status == "wait":
                    item.title = title
                    self._emit_queue()
                    self._log(f"제목 확인: {title}", True)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, RuntimeError):
                if item in self.items and item.status == "wait":
                    short = re.sub(r"^https?://", "", item.source)[:42]
                    item.title = short + " (제목 확인 실패)"
                    self._emit_queue()
                    self._log("유튜브 제목을 확인하지 못했습니다. 분리 시작 시 다시 확인합니다.", False)

    def add_files(self, paths) -> int:
        added = 0
        for raw in paths or []:
            path = Path(raw)
            if not path.exists() or path.suffix.lower() not in AUDIO_EXTS:
                self._log(f"지원하지 않는 파일: {path.name}", False)
                continue
            source = str(path.resolve())
            if any(item.source == source for item in self.items):
                continue
            item = Item("file", source, unicodedata.normalize("NFC", path.name))
            self.items.append(item)
            self._detect_key_async(item, source)   # 로컬 파일은 바로 키 감지
            added += 1
        self._emit_queue()
        return added

    def remove(self, item_id: int):
        self.items = [item for item in self.items if item.id != item_id or item.status == "run"]
        self._emit_queue()

    def reset(self) -> bool:
        """Clear the queue only while idle so an active worker is never orphaned."""
        if self.running:
            return False
        self.items.clear()
        self._download_cache.clear()   # 대기열을 비우면 다운로드 캐시도 초기화
        self._emit_queue()
        return True

    def set_item_key(self, item_id: int, semitones):
        """대기 중인 곡의 목표 키 이동을 -6~+6 범위로 설정한다."""
        for item in self.items:
            if item.id == item_id and item.status in {"wait", "failed", "canceled"}:
                item.key_shift = max(-6, min(6, int(semitones)))
                self._emit_queue()
                return item.key_shift
        return None

    def set_item_lyrics(self, item_id: int, enabled: bool):
        """곡별 가사 저장 여부를 설정한다."""
        for item in self.items:
            if item.id == item_id:
                item.want_lyrics = bool(enabled)
                self._emit_queue()
                return item.want_lyrics
        return None

    def _detect_key_async(self, item: "Item", path: str):
        """오디오가 확보되면 백그라운드로 키를 감지해 대기열에 표시한다 (실패는 무시)."""
        def worker():
            try:
                from app import keyshift
                key = keyshift.detect_key(path)
                if key:
                    item.detected_key = key
                    self._emit_queue()
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def start(self, mode: str, cfg: dict) -> bool:
        if self.running:
            return False
        targets = [item for item in self.items if item.status in {"wait", "failed", "canceled"}]
        if not targets:
            self._log("처리할 곡이 없습니다.", False)
            return False
        self._cancel.clear()
        self.running = True
        threading.Thread(target=self._worker, args=(mode, dict(cfg)), daemon=True).start()
        return True

    def cancel(self):
        self._cancel.set()
        with self._proc_lock:
            proc = self._proc
        if proc and proc.poll() is None:
            self._terminate_process_tree(proc)
        self._log("중단 요청됨 — 실행 중인 작업을 종료합니다.")

    def _worker(self, mode: str, cfg: dict):
        processed_ids = set()
        processed_count = 0
        done = 0
        total = sum(item.status in {"wait", "failed", "canceled"} for item in self.items)
        self.emit({"type": "run_state", "running": True})
        try:
            config.ensure_dirs(cfg)
            self._prepare_tools()
            while True:
                if self._cancel.is_set():
                    break
                pending = [
                    item for item in self.items
                    if item.id not in processed_ids and item.status in {"wait", "failed", "canceled"}
                ]
                if not pending:
                    break
                item = pending[0]
                processed_ids.add(item.id)
                processed_count += 1
                idx = processed_count
                total = max(total, processed_count + len(pending) - 1)
                item.status = "run"
                item.error = ""
                item.stage = "준비"
                self._emit_queue()
                self.emit({"type": "current", "id": item.id, "title": item.title, "index": idx, "total": total})
                try:
                    if item.kind == "url":
                        source = self._download(item, idx, total)
                    else:
                        source = Path(item.source)
                        self._log(f"[{idx}/{total}] 로컬 파일 — 다운로드 건너뜀")
                    self._check_canceled()
                    out_dir = self._separate(item, source, mode, cfg, idx, total)
                    item.out_dir = str(out_dir)
                    item.status = "done"
                    item.stage = "완료"
                    done += 1
                    self._log(f"[{idx}/{total}] 완료 → {out_dir}", True)
                except CanceledError as exc:
                    item.status = "canceled"
                    item.stage = "중단"
                    item.error = str(exc)
                    self._log(f"[{idx}/{total}] 중단됨: {exc}", False)
                    self._emit_queue()
                    break
                except (Exception, SystemExit) as exc:
                    item.status = "failed"
                    item.stage = "실패"
                    item.error = str(exc) or "분리 엔진이 예기치 않게 종료되었습니다."
                    self._log(f"[{idx}/{total}] 실패: {item.error}", False)
                finally:
                    self._emit_queue()
                    shutil.rmtree(config.TEMP_DIR / f"item_{item.id}", ignore_errors=True)
                    shutil.rmtree(config.TEMP_DIR / "separated" / f"item_{item.id}", ignore_errors=True)
        except (Exception, SystemExit) as exc:
            self._log(f"작업을 시작하지 못했습니다 — {exc}", False)
            for item in self.items:
                if item.status in {"wait", "run", "failed", "canceled"} and item.id not in processed_ids:
                    item.status = "failed"
                    item.stage = "실패"
                    item.error = str(exc)
            self._emit_queue()
        finally:
            with self._proc_lock:
                self._proc = None
            self.running = False
            if self._cancel.is_set():
                self._log("작업이 중단되었습니다.", False)
            else:
                self._log(f"대기열 처리 완료 — 성공 {done}곡 / 전체 {total}곡", True)
            self.emit({"type": "run_state", "running": False})
            self.emit({"type": "finished", "done": done, "total": total})

    @staticmethod
    def _prepare_tools():
        if not YTDLP.is_file():
            raise RuntimeError("다운로드 구성요소가 없습니다. 프로그램을 다시 설치하세요.")
        if FFMPEG_DIR.is_dir():
            current = os.environ.get("PATH", "")
            ffmpeg_dir = str(FFMPEG_DIR)
            if ffmpeg_dir.lower() not in current.lower().split(os.pathsep):
                os.environ["PATH"] = ffmpeg_dir + os.pathsep + current

    def _download(self, item: Item, idx: int, total: int) -> Path:
        item.stage = "다운로드 중"
        self._emit_queue()
        self.emit({"type": "progress", "id": item.id, "stage": "다운로드 중", "pct": 0})
        self._log(f"[{idx}/{total}] 다운로드 중")
        work_dir = config.TEMP_DIR / f"item_{item.id}"
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        cached = self._download_cache.get(item.source) if item.kind == "url" else None
        cached_path = Path(cached["path"]) if isinstance(cached, dict) else (Path(cached) if cached else None)
        cached_title = cached.get("title") if isinstance(cached, dict) else None
        if cached_path and cached_path.is_file():
            # 같은 링크를 여러 키로 넣은 경우 재다운로드 없이 캐시를 재사용해 유튜브 반복 차단을 피한다.
            source = work_dir / cached_path.name
            shutil.copy2(cached_path, source)
            self._log(f"[{idx}/{total}] 같은 링크 재사용 — 다운로드 생략", True)
        else:
            cmd = [
                str(YTDLP), "--no-playlist", "-f", "bestaudio",
                "--retries", "10", "--fragment-retries", "10", "--extractor-retries", "3",
                "--newline", "--no-part", "-o", str(work_dir / "%(title)s.%(ext)s"), item.source,
            ]
            if IS_WINDOWS:
                cmd.insert(4, "--windows-filenames")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **hidden_process_kwargs(),
            )
            self._set_proc(proc)
            # 실패 시 원인 파악용으로 진행률 이외의 마지막 출력 줄들을 보관한다.
            output_tail = []
            try:
                for line in proc.stdout or []:
                    match = re.search(r"\[download\]\s+([\d.]+)%", line)
                    if not match:
                        stripped = line.strip()
                        if stripped:
                            output_tail.append(stripped)
                            del output_tail[:-6]
                        continue
                    pct = max(0.0, min(100.0, float(match.group(1))))
                    self.emit({"type": "progress", "id": item.id, "stage": "다운로드 중", "pct": round(pct, 1)})
                code = proc.wait()
            finally:
                self._clear_proc(proc)
            self._check_canceled()
            if code != 0:
                detail = [line for line in output_tail if "ERROR" in line.upper()] or output_tail[-1:]
                for line in detail:
                    self._log(f"[{idx}/{total}] yt-dlp: {line}", False)
                raise RuntimeError("다운로드 실패 — 링크가 유효한지, 비공개/삭제 영상이 아닌지 확인하세요.")
            files = [path for path in work_dir.iterdir() if path.is_file()]
            if not files:
                raise RuntimeError("다운로드된 파일을 찾지 못했습니다.")
            source = max(files, key=lambda path: path.stat().st_size)
            normalized_name = unicodedata.normalize("NFC", source.name)
            if normalized_name != source.name:
                normalized_source = source.with_name(normalized_name)
                if not normalized_source.exists():
                    source = source.rename(normalized_source)
            if item.kind == "url":
                self._cache_download(item.source, source)
        # 캐시 파일명은 URL 해시이므로 재사용 항목의 제목에는 최초 다운로드 제목을 사용한다.
        item.title = unicodedata.normalize("NFC", cached_title or source.stem)
        self._log(f"[{idx}/{total}] 제목 확인: {item.title}")
        self.emit({"type": "current", "id": item.id, "title": item.title, "index": idx, "total": total})
        if not item.detected_key:
            self._detect_key_async(item, str(source))   # 오디오로 키 감지
        return source

    def _cache_download(self, url: str, source: Path):
        """받은 오디오를 URL 기준으로 캐시해 같은 링크의 다음 항목이 재사용하게 한다."""
        try:
            cache_dir = config.TEMP_DIR / "download_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            key = hashlib.md5(url.encode("utf-8")).hexdigest()
            cache_file = cache_dir / (key + source.suffix)
            shutil.copy2(source, cache_file)
            self._download_cache[url] = {"path": cache_file, "title": source.stem}
        except OSError:
            pass

    def _separate(self, item: Item, src: Path, mode: str, cfg: dict, idx: int, total: int) -> Path:
        item.stage = "분리 중"
        self._emit_queue()
        self.emit({"type": "progress", "id": item.id, "stage": "분리 중", "pct": None})
        self._log(f"[{idx}/{total}] AI 추출 진행 중")
        separation_dir = config.TEMP_DIR / "separated" / f"item_{item.id}"
        shutil.rmtree(separation_dir, ignore_errors=True)
        separation_dir.mkdir(parents=True, exist_ok=True)

        # 곡별 목표 키를 이 실행의 설정에 반영한다 (악기별 분리는 키 이동 제외).
        item_key = 0 if mode == "demucs" else int(getattr(item, "key_shift", 0) or 0)
        cfg = dict(cfg, key_shift=item_key)
        out_files = self._separation_runner(src, mode, cfg, separation_dir, item.id)
        self._check_canceled()
        item.stage = "저장"
        # Inference has already reached 100%; keep the bar complete while the
        # generated stems are being moved/renamed instead of jumping backwards.
        self.emit({"type": "progress", "id": item.id, "stage": "저장 중", "pct": 100})

        output_root = Path(cfg["output_dir"])
        song_dir = unique_dir(output_root, item.title)
        extension = cfg.get("output_format", "WAV").lower()
        if mode == "demucs":
            wanted = {
                self._stem_label(f"track_({stem}).wav")
                for stem in ("Vocals", "Drums", "Bass", "Other")
            }
        elif mode == "vocals":
            wanted = {"보컬"}
        else:
            wanted = {"반주"}
        normalize = bool(cfg.get("volume_fix", False)) and mode != "demucs"
        key_shift = 0 if mode == "demucs" else int(cfg.get("key_shift", 0))
        if key_shift:
            self.emit({"type": "progress", "id": item.id, "stage": "키 이동 중", "pct": 100})
        elif normalize:
            self.emit({"type": "progress", "id": item.id, "stage": "볼륨 보정 중", "pct": 100})
        moved = []
        for raw in out_files:
            path = Path(raw)
            if not path.is_absolute():
                path = separation_dir / path
            if not path.is_file():
                continue
            stem = self._stem_label(path.name)
            if stem not in wanted:
                path.unlink(missing_ok=True)
                continue
            destination = song_dir / f"{sanitize_name(item.title)} ({stem}).{extension}"
            source_path = path
            if key_shift:
                from app import keyshift
                shifted = path.with_name(path.stem + "_shift.wav")
                keyshift.shift_file(path, key_shift, shifted)
                source_path = shifted
            if normalize:
                self._normalize_and_encode(source_path, destination, cfg)
            elif key_shift:
                self._encode_audio(source_path, destination, cfg)
            else:
                shutil.move(str(path), str(destination))
            if source_path is not path:
                source_path.unlink(missing_ok=True)
            if normalize or key_shift:
                path.unlink(missing_ok=True)
            moved.append(destination)
        if not moved:
            shutil.rmtree(song_dir, ignore_errors=True)
            raise RuntimeError("분리 결과 파일이 생성되지 않았습니다.")
        if cfg.get("download_lyrics", True) and getattr(item, "want_lyrics", True):
            self._save_lyrics(item, song_dir, src)
        if item.kind == "url" and cfg.get("keep_source", False):
            shutil.copy2(src, song_dir / sanitize_name(src.name))
        self.emit({"type": "progress", "id": item.id, "stage": "완료", "pct": 100})
        return song_dir

    def _run_separation_process(self, src: Path, mode: str, cfg: dict, separation_dir: Path, item_id=None):
        request_path = separation_dir / "worker-request.json"
        response_path = separation_dir / "worker-response.json"
        # 볼륨 보정·키 이동을 거치는 경우 중간 결과를 무손실 WAV로 받아 인코딩 손실이 한 번만 생기게 한다.
        needs_wav = mode != "demucs" and (bool(cfg.get("volume_fix", False)) or int(cfg.get("key_shift", 0)))
        request = {
            "source": str(src.resolve()),
            "output_dir": str(separation_dir.resolve()),
            "models_dir": str(config.MODELS_DIR.resolve()),
            "mode": mode if mode in MODE_MODELS else "karaoke",
            "output_format": "WAV" if needs_wav else cfg.get("output_format", "WAV"),
            "mp3_bitrate": cfg.get("mp3_bitrate", "320k"),
            "use_gpu": bool(cfg.get("use_gpu", False)),
            "response_path": str(response_path.resolve()),
        }
        return self._run_worker_request(request, request_path, response_path, item_id)

    def _run_worker_request(self, request: dict, request_path: Path, response_path: Path, item_id=None):
        progress_path = request_path.with_name("worker-progress.jsonl")
        request["progress_path"] = str(progress_path.resolve())
        response_path.unlink(missing_ok=True)
        progress_path.unlink(missing_ok=True)
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--separation-worker", str(request_path)]
        else:
            command = [sys.executable, "-m", "app.main", "--separation-worker", str(request_path)]
        proc = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(BASE_DIR),
            **hidden_process_kwargs(new_group=True),
        )
        self._set_proc(proc)
        last_inference_pct = None

        def handle_event(event):
            nonlocal last_inference_pct
            if event.get("type") == "notice":
                self._log(event.get("text", ""), False)
                return
            if event.get("type") == "inference_progress":
                last_inference_pct = max(0.0, min(100.0, float(event.get("pct", 0))))
                self.emit({
                    "type": "progress",
                    "id": item_id,
                    "stage": f"AI 분리 중 · {last_inference_pct:.0f}%",
                    "pct": round(last_inference_pct, 1),
                })
                return
            if event.get("type") == "inference_elapsed":
                seconds = int(event.get("seconds", 0))
                elapsed = f"{seconds // 60}분 {seconds % 60:02d}초" if seconds >= 60 else f"{seconds}초"
                if last_inference_pct is None:
                    stage = f"AI 분리 준비 중 · {elapsed} 경과"
                    pct = None
                else:
                    stage = f"AI 분리 중 · {last_inference_pct:.0f}% · {elapsed} 경과"
                    pct = round(last_inference_pct, 1)
                self.emit({"type": "progress", "id": item_id, "stage": stage, "pct": pct})
                return
            if event.get("type") != "model_download":
                return
            pct = event.get("pct")
            received_mb = event.get("received", 0) / 1024 / 1024
            total_mb = event.get("total", 0) / 1024 / 1024
            speed_mb = event.get("speed", 0) / 1024 / 1024
            eta = event.get("eta")
            if total_mb:
                eta_text = f" · 약 {int(eta // 60)}분 {int(eta % 60):02d}초 남음" if eta is not None else ""
                stage = f"모델 다운로드 {received_mb:.0f}/{total_mb:.0f}MB · {speed_mb:.1f}MB/s{eta_text}"
            else:
                stage = f"모델 다운로드 {received_mb:.0f}MB"
            self.emit({"type": "progress", "id": item_id, "stage": stage, "pct": pct})

        position = 0
        try:
            while True:
                if progress_path.is_file():
                    with progress_path.open("r", encoding="utf-8") as progress_file:
                        progress_file.seek(position)
                        for line in progress_file:
                            try:
                                handle_event(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                        position = progress_file.tell()
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            code = proc.wait()
        finally:
            self._clear_proc(proc)
        self._check_canceled()
        if not response_path.is_file():
            raise RuntimeError(f"AI 분리 프로세스가 응답 없이 종료되었습니다. (코드 {code})")
        response = json.loads(response_path.read_text(encoding="utf-8"))
        if code != 0 or not response.get("ok"):
            raise RuntimeError(response.get("error") or f"AI 분리 실패 (코드 {code})")
        return response.get("outputs", [])

    def download_model(self, mode: str, cfg: dict) -> bool:
        if self.running or self.model_downloading:
            return False
        if mode not in MODE_MODELS:
            return False
        self._cancel.clear()
        if self._model_group_installed(mode):
            self._log("AI 모델이 이미 설치되어 있어 다운로드를 건너뜁니다.", True)
            self.emit({"type": "model_download_state", "running": False, "mode": mode,
                       "ok": True, "already_installed": True})
            return True
        self.model_downloading = True
        threading.Thread(target=self._download_model_worker, args=(mode, dict(cfg)), daemon=True).start()
        return True

    def download_all_models(self, cfg: dict) -> bool:
        if self.running or self.model_downloading:
            return False
        self._cancel.clear()
        if all(self._model_group_installed(mode) for mode in ALL_MODEL_MODES):
            self._log("전체 AI 모델이 이미 설치되어 있어 다운로드를 건너뜁니다.", True)
            self.emit({"type": "model_download_state", "running": False, "mode": "all",
                       "ok": True, "already_installed": True})
            return True
        self.model_downloading = True
        threading.Thread(target=self._download_all_models_worker, args=(dict(cfg),), daemon=True).start()
        return True

    def _download_model_worker(self, mode: str, cfg: dict):
        self.emit({"type": "model_download_state", "running": True, "mode": mode, "ok": None})
        try:
            config.ensure_dirs(cfg)
            self._download_one_model_group(mode)
            self._log("AI 모델 준비 완료", True)
            self.emit({"type": "model_download_state", "running": False, "mode": mode, "ok": True})
        except (Exception, SystemExit) as exc:
            self._log(f"AI 모델 다운로드 실패: {exc}", False)
            self.emit({"type": "model_download_state", "running": False, "mode": mode, "ok": False, "error": str(exc)})
        finally:
            self.model_downloading = False

    def _download_all_models_worker(self, cfg: dict):
        total = len(ALL_MODEL_MODES)
        self.emit({"type": "model_download_state", "running": True, "mode": "all", "ok": None, "index": 0, "total": total})
        try:
            config.ensure_dirs(cfg)
            for index, mode in enumerate(ALL_MODEL_MODES, 1):
                self.emit({"type": "model_download_state", "running": True, "mode": "all", "ok": None, "index": index, "total": total})
                self._download_one_model_group(mode)
            self._log("전체 AI 모델 준비 완료", True)
            self.emit({"type": "model_download_state", "running": False, "mode": "all", "ok": True, "index": total, "total": total})
        except (Exception, SystemExit) as exc:
            self._log(f"전체 AI 모델 다운로드 실패: {exc}", False)
            self.emit({"type": "model_download_state", "running": False, "mode": "all", "ok": False, "error": str(exc)})
        finally:
            self.model_downloading = False

    def _download_one_model_group(self, mode: str):
        if self._model_group_installed(mode):
            self._log(f"이미 설치된 AI 모델 건너뜀: {mode}", True)
            return
        work_dir = config.TEMP_DIR / "model-download" / mode
        work_dir.mkdir(parents=True, exist_ok=True)
        request_path = work_dir / "worker-request.json"
        response_path = work_dir / "worker-response.json"
        request = {
            "action": "download_only",
            "output_dir": str(work_dir.resolve()),
            "models_dir": str(config.MODELS_DIR.resolve()),
            "mode": mode,
            "output_format": "WAV",
            "mp3_bitrate": "320k",
            "use_gpu": False,
            "response_path": str(response_path.resolve()),
        }
        self._run_worker_request(request, request_path, response_path)

    @staticmethod
    def _model_group_installed(mode: str) -> bool:
        required = MODEL_REQUIRED_FILES.get(mode)
        if not required:
            return False
        return all((config.MODELS_DIR / filename).is_file()
                   and (config.MODELS_DIR / filename).stat().st_size > 0
                   for filename in required)

    def model_download_status(self) -> dict:
        installed = {mode: self._model_group_installed(mode) for mode in MODE_MODELS}
        return {
            "installed": installed,
            "all_installed": all(installed.get(mode, False) for mode in ALL_MODEL_MODES),
        }

    @staticmethod
    def volume_filter(measured_lufs: float, output_format: str) -> str:
        """측정한 음량으로 걸 필터. 게인은 곡 전체에 한 번, 리미터는 넘치는 피크에만."""
        gain = LOUDNESS_TARGET_LUFS - measured_lufs
        ceiling = PEAK_CEILING_DB.get(output_format.upper(), -1.0)
        # level=false — 켜 두면 리미터가 제멋대로 메이크업 게인을 얹는다.
        return f"volume={gain:.3f}dB,alimiter=limit={10 ** (ceiling / 20):.4f}:level=false"

    def _normalize_and_encode(self, source: Path, destination: Path, cfg: dict):
        """-14 LUFS로 맞춰 최종 형식으로 1회 인코딩한다. 다이내믹은 건드리지 않는다."""
        ffmpeg = str(FFMPEG)
        measure = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(source),
             "-af", LOUDNESS_MEASURE, "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", **hidden_process_kwargs(),
        )
        match = re.search(r"\{[^{}]+\}", measure.stderr[-3000:], re.S)
        if measure.returncode != 0 or not match:
            raise RuntimeError("볼륨 보정 측정에 실패했습니다.")
        metrics = json.loads(match.group(0))
        output_format = cfg.get("output_format", "WAV").upper()
        codec = {
            "MP3": ["-c:a", "libmp3lame", "-b:a", cfg.get("mp3_bitrate", "320k")],
            "FLAC": ["-c:a", "flac"],
            "WAV": ["-c:a", "pcm_s16le"],
        }.get(output_format, ["-c:a", "pcm_s16le"])
        encode = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-y", "-i", str(source),
             "-af", self.volume_filter(float(metrics["input_i"]), output_format),
             "-ar", "44100", *codec, str(destination)],
            capture_output=True, **hidden_process_kwargs(),
        )
        if encode.returncode != 0 or not destination.is_file():
            raise RuntimeError("볼륨 보정 인코딩에 실패했습니다.")

    def _encode_audio(self, source: Path, destination: Path, cfg: dict):
        """볼륨 보정 없이 WAV를 최종 형식으로 1회 인코딩한다 (키 이동만 적용된 경우)."""
        ffmpeg = str(FFMPEG)
        output_format = cfg.get("output_format", "WAV").upper()
        codec = {
            "MP3": ["-c:a", "libmp3lame", "-b:a", cfg.get("mp3_bitrate", "320k")],
            "FLAC": ["-c:a", "flac"],
            "WAV": ["-c:a", "pcm_s16le"],
        }.get(output_format, ["-c:a", "pcm_s16le"])
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-y", "-i", str(source),
             "-ar", "44100", *codec, str(destination)],
            capture_output=True, **hidden_process_kwargs(),
        )
        if result.returncode != 0 or not destination.is_file():
            raise RuntimeError("키 이동 인코딩에 실패했습니다.")

    @staticmethod
    def _search_title(item: Item) -> str:
        """가사 검색어. 로컬 파일은 확장자를 뗀다 — `.mp3`가 붙으면 검색이 실패한다."""
        if item.kind == "file":
            return Path(item.title).stem or item.title
        return item.title

    @staticmethod
    def _audio_duration(path) -> float | None:
        """가사 오매칭을 막는 길이 검증에 쓸 재생시간(초)."""
        try:
            import soundfile
            info = soundfile.info(str(path))
            return info.frames / info.samplerate if info.samplerate else None
        except Exception:
            return None

    def _save_lyrics(self, item: Item, song_dir: Path, source=None):
        """가사를 조회해 곡 폴더에 .txt로 저장한다. 실패는 조용히 넘긴다(부가 기능)."""
        try:
            from app import lyrics
            duration = self._audio_duration(source) if source else None
            result = lyrics.fetch_lyrics(self._search_title(item), duration=duration)
            if result:
                lyrics.save_lyrics(result, song_dir / f"{sanitize_name(item.title)} (가사).txt")
                self._log(f"가사 저장: {item.title}")
        except Exception:
            pass

    @staticmethod
    def _stem_label(filename: str) -> str:
        name = Path(filename).stem.lower()
        labels = {
            "instrumental": "반주", "no_vocals": "반주", "vocals": "보컬",
            "drums": "드럼", "bass": "베이스", "other": "그외악기",
        }
        # audio-separator는 실제 스템을 `_(Vocals)`처럼 붙인다. 제목에도
        # `(Instrumental)`이 있을 수 있으므로 마지막 스템 마커만 사용한다.
        markers = re.findall(r"_\((instrumental|no_vocals|vocals|drums|bass|other)\)(?=_|$)", name)
        if markers:
            return labels[markers[-1]]
        if name in labels:
            return labels[name]
        return "반주"

    def _check_canceled(self):
        if self._cancel.is_set():
            raise CanceledError("사용자가 작업을 중단했습니다.")

    def _set_proc(self, proc):
        with self._proc_lock:
            self._proc = proc

    def _clear_proc(self, proc):
        with self._proc_lock:
            if self._proc is proc:
                self._proc = None

    @staticmethod
    def _terminate_process_tree(proc):
        terminate_process_tree(proc)

    def _emit_queue(self):
        self.emit({"type": "queue", "items": [item.to_dict() for item in self.items]})

    def _log(self, text: str, ok=None):
        self.emit({"type": "log", "text": text, "ok": ok})


class CanceledError(Exception):
    pass
