import tempfile
import threading
import time
import unittest
import json
import hashlib
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

from app import config
from app.api import Api
from app.main import dropped_paths, smoke_test
from app.pipeline import (
    ALL_MODEL_MODES,
    MODE_MODELS,
    MODEL_REQUIRED_FILES,
    Item,
    Pipeline,
    sanitize_name,
    unique_dir,
)
from app.platform_support import cuda_arch_supported


class FakeDownload:
    """urlopen 대신 쓸 응답. 컨텍스트 매니저와 read(n)만 있으면 된다."""

    def __init__(self, payload: bytes):
        self._data = payload
        self._position = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def info(self):
        return {"Content-Length": str(len(self._data))}

    def read(self, size=None):
        end = len(self._data) if size is None else self._position + size
        chunk = self._data[self._position:end]
        self._position += len(chunk)
        return chunk


class FakeSeparator:
    def __init__(self):
        self.output_dir = ""
        self.model_instance = None

    def separate(self, _source):
        out = Path(self.output_dir)
        vocals = out / "sample_(Vocals).wav"
        instrumental = out / "sample_(Instrumental).wav"
        vocals.write_bytes(b"vocals")
        instrumental.write_bytes(b"instrumental")
        return [vocals.name, instrumental.name]


class CoreTests(unittest.TestCase):
    def test_native_drop_paths(self):
        event = {"dataTransfer": {"files": [
            {"name": "song.wav", "pywebviewFullPath": r"D:\\Music\\song.wav"},
            {"name": "hidden.wav"},
        ]}}
        self.assertEqual(dropped_paths(event), [r"D:\\Music\\song.wav"])

    def test_reset_queue_only_while_idle(self):
        pipeline = Pipeline(lambda _event: None)
        pipeline.items.append(Item("file", __file__, "sample.wav"))
        self.assertTrue(pipeline.reset())
        self.assertEqual(pipeline.items, [])
        pipeline.items.append(Item("file", __file__, "sample.wav"))
        pipeline.running = True
        self.assertFalse(pipeline.reset())
        self.assertEqual(len(pipeline.items), 1)

    def test_cpu_is_the_default(self):
        self.assertFalse(config.DEFAULTS["use_gpu"])

    def test_mode_models_are_the_measured_winners(self):
        """실측으로 고른 모델이다. 바꾸려면 같은 방식으로 다시 재고 나서 바꿀 것."""
        self.assertEqual(MODE_MODELS["karaoke"], "mel_band_roformer_karaoke_becruily.ckpt")
        self.assertEqual(MODE_MODELS["best"], "mel_band_roformer_instrumental_becruily.ckpt")
        self.assertEqual(MODE_MODELS["vocals"], MODE_MODELS["best"])
        self.assertNotIn("karaoke_ensemble", MODE_MODELS)
        # 선언한 모델과 미리받기 목록이 어긋나면 첫 변환에서 다시 받게 된다.
        for mode, model in MODE_MODELS.items():
            if isinstance(model, str) and model.endswith(".ckpt"):
                self.assertIn(model, MODEL_REQUIRED_FILES[mode])

    def test_download_all_models_uses_each_model_group_once(self):
        events = []
        pipeline = Pipeline(events.append)
        downloaded = []
        pipeline.model_downloading = True
        pipeline._download_one_model_group = downloaded.append

        with mock.patch.object(config, "ensure_dirs"):
            pipeline._download_all_models_worker(dict(config.DEFAULTS))

        self.assertEqual(downloaded, list(ALL_MODEL_MODES))
        self.assertNotIn("vocals", downloaded)
        self.assertFalse(pipeline.model_downloading)
        self.assertEqual(events[-1]["mode"], "all")
        self.assertTrue(events[-1]["ok"])

    def test_sanitize_windows_filename(self):
        self.assertEqual(sanitize_name(' a:b*c?d"e<f>g| '), "a_b_c_d_e_f_g_")
        self.assertEqual(sanitize_name("..."), "제목없음")
        self.assertEqual(sanitize_name("이승윤"), "이승윤")

    def test_stem_label_handles_model_suffix(self):
        self.assertEqual(
            Pipeline._stem_label("song_(Vocals)_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.wav"),
            "보컬",
        )
        self.assertEqual(
            Pipeline._stem_label("song_(Instrumental)_mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.wav"),
            "반주",
        )
        self.assertEqual(
            Pipeline._stem_label("My Song_(Instrumental)_(Vocals)_model.wav"),
            "보컬",
        )

    def test_worker_setup_failure_unlocks_ui_and_marks_items_failed(self):
        events = []
        pipeline = Pipeline(events.append)
        item = Item("file", __file__, "sample.wav")
        pipeline.items.append(item)
        pipeline.running = True
        with mock.patch.object(config, "ensure_dirs", side_effect=OSError("bad output")):
            pipeline._worker("karaoke", dict(config.DEFAULTS))
        self.assertFalse(pipeline.running)
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.stage, "실패")
        self.assertTrue(any(event.get("type") == "run_state" and not event["running"] for event in events))
        self.assertTrue(any(event.get("type") == "finished" and event["total"] == 1 for event in events))

    def test_model_download_clears_previous_cancel_state(self):
        pipeline = Pipeline(lambda _event: None)
        pipeline._cancel.set()
        fake_thread = mock.Mock()
        with mock.patch.object(pipeline, "_model_group_installed", return_value=False), \
                mock.patch("app.pipeline.threading.Thread", return_value=fake_thread):
            self.assertTrue(pipeline.download_model("karaoke", dict(config.DEFAULTS)))
        self.assertFalse(pipeline._cancel.is_set())
        fake_thread.start.assert_called_once()

    def test_cuda_arch_check_rejects_missing_kernels(self):
        def fake_torch(capability, arch_list):
            return SimpleNamespace(cuda=SimpleNamespace(
                is_available=lambda: True,
                get_device_capability=lambda _index: capability,
                get_arch_list=lambda: arch_list,
            ))

        cuda12 = ["sm_50", "sm_60", "sm_70", "sm_80", "sm_86", "sm_90"]
        cuda13 = ["sm_75", "sm_80", "sm_86", "sm_90", "sm_100", "sm_120"]
        # RTX 50(sm_120)은 CUDA 12 빌드에서 커널이 없고, CUDA 13 빌드에서만 동작한다.
        self.assertFalse(cuda_arch_supported(fake_torch((12, 0), cuda12)))
        self.assertTrue(cuda_arch_supported(fake_torch((12, 0), cuda13)))
        # GTX 10xx(sm_61)는 반대로 CUDA 12 빌드에서만 동작한다.
        self.assertTrue(cuda_arch_supported(fake_torch((6, 1), cuda12)))
        self.assertFalse(cuda_arch_supported(fake_torch((6, 1), cuda13)))
        # 같은 세대의 상위 minor(RTX 4090 sm_89)는 sm_80 커널로 실행된다.
        self.assertTrue(cuda_arch_supported(fake_torch((8, 9), cuda13)))
        # PTX가 있으면 드라이버가 JIT 컴파일한다.
        self.assertTrue(cuda_arch_supported(fake_torch((12, 0), ["sm_90", "compute_90"])))

    def test_cpu_only_resource_smoke_is_successful(self):
        fake_torch = SimpleNamespace(cuda=SimpleNamespace(
            is_available=lambda: False,
            get_device_name=lambda _index: "",
        ))
        fake_run = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "smoke.json"
            with mock.patch.dict(sys.modules, {"torch": fake_torch, "audio_separator": SimpleNamespace()}),                     mock.patch("app.main.subprocess.run", return_value=fake_run):
                self.assertEqual(smoke_test(str(report)), 0)
            payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(payload["ok"], payload.get("error"))
        self.assertFalse(payload["checks"]["cuda"])


    def test_pasted_link_is_submitted_without_enter(self):
        """링크를 붙여넣으면 Enter 없이 대기열에 담겨야 한다."""
        ui_path = Path(__file__).resolve().parent.parent / "app" / "ui" / "index.html"
        ui = ui_path.read_text(encoding="utf-8")
        self.assertIn('$("urlInput").addEventListener("paste"', ui)
        self.assertIn("submitUrls", ui)
        self.assertNotIn("붙여넣기 후 Enter", ui)   # 안내 문구도 함께 바뀌어야 한다

    def test_window_has_no_maximize_control(self):
        """레이아웃이 고정 폭 기준이라 최대화를 없앴다. 버튼과 API가 함께 빠져야 한다."""
        self.assertFalse(hasattr(Api(), "win_toggle_max"))
        ui_path = Path(__file__).resolve().parent.parent / "app" / "ui" / "index.html"
        ui = ui_path.read_text(encoding="utf-8")
        self.assertNotIn("maxBtn", ui)
        self.assertIn("minBtn", ui)
        self.assertIn("closeBtn", ui)

    def test_title_candidates_reach_real_song_name(self):
        """업로더가 제목 뒤에 붙인 말을 잘라내 진짜 곡 제목에 도달해야 한다."""
        from app.lyrics import title_candidates

        # 실제로 가사를 못 찾았던 제목들
        self.assertIn("목이 멘다", title_candidates("'목이 멘다' ｜ Kim Do-Hyang"))
        self.assertIn("목이 멘다", title_candidates("목이 멘다 2005 - 나의 애청곡 No.2"))
        self.assertIn("이제 나만 믿어요", title_candidates("이제 나만 믿어요 full.ver"))
        self.assertIn("가로수 그늘 아래 서면", title_candidates("가로수 그늘 아래 서면 2018 LEE MOON SAE @ KSPO"))
        # 멀쩡한 제목은 건드리지 않는다
        self.assertEqual(title_candidates("벚꽃 엔딩"), ["벚꽃 엔딩"])
        # 너무 짧게 잘라 엉뚱한 곡이 걸리지 않도록 한 글자짜리는 만들지 않는다
        self.assertTrue(all(len(c) >= 2 for c in title_candidates("A - B - C")))

    def test_local_file_search_title_drops_extension(self):
        """로컬 파일은 확장자가 붙은 채로 검색되어 가사를 못 찾고 있었다."""
        song = Item("file", r"D:\music\벚꽃 엔딩.mp3", "벚꽃 엔딩.mp3")
        self.assertEqual(Pipeline._search_title(song), "벚꽃 엔딩")
        # 유튜브 제목은 확장자가 없으므로 그대로 쓴다
        link = Item("url", "https://youtu.be/x", "버스커 버스커 - 벚꽃 엔딩")
        self.assertEqual(Pipeline._search_title(link), "버스커 버스커 - 벚꽃 엔딩")

    def test_runtime_revision_tracks_requirements(self):
        """패키지를 바꾸면 런타임도 바뀐다. RUNTIME_REVISION을 안 올리면 패치가 앱을 망가뜨린다.

        예외는 하나다 — 새로 들어온 패키지를 패치가 직접 담고 있으면 런타임을 통째로
        다시 받게 할 이유가 없다. 그 경우 RUNTIME_PATCHED_PACKAGES에 적어 둔다.
        """
        from app.version import RUNTIME_PATCHED_PACKAGES, RUNTIME_REQUIREMENTS_SHA

        # 줄바꿈이 정규화되도록 텍스트로 읽는다. 바이트로 읽으면 CRLF 체크아웃에서 값이 달라진다.
        root = Path(__file__).resolve().parent.parent
        text = (root / "requirements.txt").read_text(encoding="utf-8")
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        self.assertEqual(
            actual, RUNTIME_REQUIREMENTS_SHA,
            "requirements.txt가 바뀌었습니다. app/version.py의 RUNTIME_REVISION을 올리거나, "
            "패치가 새 패키지를 담는다면 RUNTIME_PATCHED_PACKAGES에 적고 "
            f"RUNTIME_REQUIREMENTS_SHA를 '{actual}'로 갱신하세요.",
        )

        # 패치로 나간다고 적어 둔 패키지는 설치 스크립트가 실제로 담고 있어야 한다.
        script = (root / "installer" / "TubeVocalRemoval.iss").read_text(encoding="utf-8")
        # `#ifdef PATCH`는 [Setup]에도 있으므로 [Files] 안쪽만 본다.
        patch_block = script.split("[Files]", 1)[1].split("#ifdef PATCH", 1)[1].split("#else", 1)[0]
        for package in RUNTIME_PATCHED_PACKAGES:
            self.assertIn(
                f"runtime\\{package}\\*", patch_block,
                f"{package}를 패치로 내보내기로 했는데 설치 스크립트에 없습니다. "
                "이대로 나가면 업데이트한 앱이 그 패키지를 못 찾습니다.",
            )

    def test_installer_script_matches_app_version(self):
        """설치 스크립트의 버전·런타임 값이 version.py와 어긋나면 잘못된 파일명이 나간다."""
        from app.version import APP_VERSION, RUNTIME_REVISION

        script = Path(__file__).resolve().parent.parent / "installer" / "TubeVocalRemoval.iss"
        text = script.read_text(encoding="utf-8")
        self.assertIn(f'#define MyAppVersion "{APP_VERSION}"', text)
        self.assertIn(f'#define MyRuntimeRevision "{RUNTIME_REVISION}"', text)






    def test_reserved_windows_names_get_a_prefix(self):
        """제목이 CON·NUL이면 폴더를 만들 수 없어 곡 전체가 실패한다."""
        self.assertEqual(sanitize_name("CON"), "_CON")
        self.assertEqual(sanitize_name("nul.mp3"), "_nul.mp3")
        self.assertEqual(sanitize_name("COM1"), "_COM1")
        self.assertEqual(sanitize_name("CONCERT"), "CONCERT")      # 예약명이 아니다


    def test_start_is_blocked_while_models_download(self):
        """둘이 같은 취소 이벤트와 프로세스 슬롯을 공유해 서로 끊는다."""
        pipeline = Pipeline(lambda event: None)
        pipeline.items.append(Item("file", __file__, "sample.wav"))
        pipeline.model_downloading = True
        self.assertFalse(pipeline.start("karaoke", dict(config.DEFAULTS)))
        self.assertFalse(pipeline.running)

    def test_prepared_lyrics_are_reused_instead_of_looked_up_again(self):
        """시작할 때 확보한 가사를 변환에서 다시 조회하면 사용자가 고른 것이 버려진다."""
        pipeline = Pipeline(lambda event: None)
        item = Item("url", "https://youtu.be/x", "어떤 곡")
        pipeline.items.append(item)
        self.assertTrue(pipeline.set_lyrics_text(item.id, " 첫 줄 \n\n 둘째 줄 "))
        self.assertEqual(item.lyrics["text"], "첫 줄\n둘째 줄")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("app.lyrics.fetch_lyrics") as fetch, \
                    mock.patch("app.lyrics.save_lyrics") as save:
                result = pipeline._save_lyrics(item, Path(tmp))
            self.assertFalse(fetch.called)
            self.assertTrue(save.called)
        self.assertEqual(result["source"], "직접 입력")

    def test_missing_lyrics_are_reported_with_a_parsed_artist_and_track(self):
        """팝업의 가수·곡명 칸을 채우려면 제목을 정리해 나눠 줘야 한다."""
        pipeline = Pipeline(lambda event: None)
        found = Item("url", "https://youtu.be/a", "아이유 - 밤편지")
        found.lyrics, found.lyrics_checked = {"text": "가사"}, True
        missing = Item("url", "https://youtu.be/b", "버즈 - Monologue (Official Video)")
        missing.lyrics_checked = True
        missing.duration = 215
        pipeline.items.extend([found, missing])
        report = pipeline._lyrics_report()
        self.assertEqual([row["id"] for row in report], [missing.id])
        self.assertEqual(report[0]["artist"], "버즈")
        self.assertEqual(report[0]["track"], "Monologue")
        self.assertEqual(report[0]["duration"], 215)

    def test_manually_picked_lyrics_keep_timing_only_when_lengths_match(self):
        """라이브 영상(286초)에 스튜디오 LRC(279초)를 얹으면 자막이 통째로 밀린다.
        자동 조회는 원래 길이를 대조하는데, 직접 고르는 경로가 그걸 건너뛰었다."""
        pipeline = Pipeline(lambda event: None)
        live = Item("url", "https://youtu.be/x", "버즈 - 겁쟁이 [라이브]")
        live.duration = 286
        pipeline.items.append(live)
        candidates = [
            {"track": "겁쟁이", "artist": "버즈", "duration": 279, "hasSynced": True,
             "result": {"text": "가사", "synced": "[00:29.89] 미안합니다", "source": "LRCLIB"}},
            {"track": "겁쟁이 (Live)", "artist": "버즈", "duration": 285, "hasSynced": True,
             "result": {"text": "가사", "synced": "[00:18.00] 미안합니다", "source": "LRCLIB"}},
        ]
        with mock.patch("app.lyrics.search_candidates", return_value=candidates):
            rows = pipeline.search_lyrics(live.id, "버즈", "겁쟁이")
        # 길이가 7초 다른 후보는 싱크로 표시하지 않는다.
        self.assertFalse(rows[0]["hasSynced"])
        self.assertTrue(rows[0]["lengthOff"])
        self.assertTrue(rows[1]["hasSynced"])
        self.assertFalse(rows[1]["lengthOff"])

        pipeline.choose_lyrics(live.id, 0)
        self.assertIsNone(live.lyrics["synced"])      # 타이밍은 버리고 글자만 쓴다
        self.assertEqual(live.lyrics["text"], "가사")

        pipeline.choose_lyrics(live.id, 1)
        self.assertEqual(live.lyrics["synced"], "[00:18.00] 미안합니다")

    def test_lyrics_length_check_passes_when_a_length_is_unknown(self):
        """로컬 파일처럼 길이를 모르면 판단하지 않는다. 막으면 쓸 수 있는 가사도 버린다."""
        self.assertTrue(Pipeline._duration_fits(0, 279))
        self.assertTrue(Pipeline._duration_fits(286, 0))
        self.assertTrue(Pipeline._duration_fits(286, 283))
        self.assertFalse(Pipeline._duration_fits(286, 279))

    def test_hidden_panes_actually_hide(self):
        """.modal-body가 display:grid라 hidden 속성만으로는 안 숨는다.
        두 탭이 동시에 보이면 모달이 길어지고 무엇을 하라는 화면인지 알 수 없다."""
        ui = Path(__file__).resolve().parent.parent / "app" / "ui" / "index.html"
        self.assertIn("[hidden] { display: none !important; }", ui.read_text(encoding="utf-8"))

    def test_lyrics_are_not_searched_with_a_placeholder_title(self):
        """제목 확인 전에 시작을 누르면 '제목 확인 중'으로 가사를 찾게 된다."""
        pipeline = Pipeline(lambda event: None)
        item = Item("url", "https://youtu.be/x", "제목 확인 중")
        pipeline.items.append(item)
        self.assertTrue(pipeline.title_pending(item))
        with mock.patch("app.lyrics.fetch_lyrics") as fetch:
            pipeline._lookup_lyrics(item)
        self.assertFalse(fetch.called)
        self.assertTrue(item.lyrics_checked)
        # 채워 줄 가수·곡명이 없으므로 빈 칸으로 물어본다.
        report = pipeline._lyrics_report()
        self.assertEqual(report[0]["artist"], "")
        self.assertEqual(report[0]["track"], "")


    def test_volume_fix_only_applies_gain(self):
        """볼륨 보정은 게인만 건다. 구간별 게인을 다시 타면 조용한 곡의 잔재가 도드라진다."""
        from app.pipeline import LOUDNESS_TARGET_LUFS

        quiet = Pipeline.volume_filter(-19.2, "WAV")
        self.assertIn(f"volume={LOUDNESS_TARGET_LUFS - -19.2:.3f}dB", quiet)
        self.assertIn("level=false", quiet)          # 리미터의 자동 메이크업을 끈다
        self.assertNotIn("dynaudnorm", quiet)
        self.assertNotIn("loudnorm", quiet)
        # MP3는 디코딩 시 피크가 솟으므로 실링이 더 낮아야 한다.
        self.assertIn("limit=0.7943", Pipeline.volume_filter(-14.0, "MP3"))
        self.assertIn("limit=0.8913", Pipeline.volume_filter(-14.0, "WAV"))
        self.assertIn("limit=0.8913", Pipeline.volume_filter(-14.0, "FLAC"))

    def test_exe_version_resource_matches_app_version(self):
        """exe에 새겨지는 버전. 여기를 빠뜨리면 앱은 2.07인데 파일 속성은 옛 버전이 된다."""
        from app.version import APP_VERSION

        info = Path(__file__).resolve().parent.parent / "installer" / "version_info.txt"
        text = info.read_text(encoding="utf-8")
        self.assertIn(f"StringStruct('FileVersion', '{APP_VERSION}')", text)
        self.assertIn(f"StringStruct('ProductVersion', '{APP_VERSION}')", text)
        major, minor = (int(part) for part in APP_VERSION.split("."))
        self.assertIn(f"filevers=({major}, 0, {minor}, 0)", text)
        self.assertIn(f"prodvers=({major}, 0, {minor}, 0)", text)

    def test_update_prefers_patch_matching_runtime(self):
        from app.version import RUNTIME_REVISION

        full = {"name": "Tube-Vocal-Removal-Setup-v2.05.exe"}
        patch = {"name": f"Tube-Vocal-Removal-Patch-{RUNTIME_REVISION}-v2.05.exe"}
        stale = {"name": "Tube-Vocal-Removal-Patch-cu999-9-v2.05.exe"}
        dmg = {"name": "Tube-Vocal-Removal-macOS-arm64.dmg"}
        with mock.patch("app.api.IS_WINDOWS", True):
            # 런타임이 같으면 2GB 정식 설치 대신 패치를 받는다.
            self.assertEqual(Api.pick_asset([dmg, full, patch]), patch)
            # 다른 런타임용 패치는 무시하고 정식 설치 파일로 넘어간다.
            self.assertEqual(Api.pick_asset([dmg, full, stale]), full)
            self.assertEqual(Api.pick_asset([dmg, full]), full)
            self.assertIsNone(Api.pick_asset([dmg]))
        with mock.patch("app.api.IS_WINDOWS", False):
            self.assertEqual(Api.pick_asset([dmg, full, patch]), dmg)

    def test_update_version_comparison(self):
        self.assertGreater(Api._version_tuple("v1.02"), Api._version_tuple("1.01"))
        self.assertEqual(Api._version_tuple("v1.1.0"), Api._version_tuple("1.01"))

    def test_update_download_verifies_github_digest(self):
        payload = b"signed installer payload"

        class FakeResponse:
            headers = {"Content-Length": str(len(payload))}

            def __enter__(self):
                self.position = 0
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size=-1):
                if self.position >= len(payload):
                    return b""
                end = len(payload) if size < 0 else min(len(payload), self.position + size)
                chunk = payload[self.position:end]
                self.position = end
                return chunk

        with tempfile.TemporaryDirectory() as tmp:
            api = Api()
            api._update_busy = True
            api._update_release = {
                "version": "9.99",
                "url": "https://example.invalid/setup.exe",
                "size": len(payload),
                "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "name": "Tube-Vocal-Removal-Setup-test.exe",
            }
            with mock.patch("app.api.tempfile.gettempdir", return_value=tmp), \
                    mock.patch("app.api.urllib.request.urlopen", return_value=FakeResponse()):
                api._download_update_worker()
            self.assertTrue(Path(api._update_installer).is_file())
            states = [event for event in api.poll_events() if event.get("type") == "update_state"]
            self.assertEqual(states[-1]["state"], "ready")

    def test_apply_update_shows_progress_logs_and_closes_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "setup.exe"
            installer.write_bytes(b"installer")
            api = Api()
            api._window = mock.Mock()
            api._update_installer = installer
            with mock.patch("app.api.tempfile.gettempdir", return_value=tmp), \
                    mock.patch("app.api.IS_MACOS", False), \
                    mock.patch("app.api.subprocess.Popen") as popen:
                self.assertTrue(api.apply_update())
            command = popen.call_args.args[0]
            self.assertIn("/SILENT", command)
            self.assertIn("/CLOSEAPPLICATIONS", command)
            self.assertTrue(any(arg.startswith("/LOG=") for arg in command))
            self.assertNotIn("/RESTARTAPPLICATIONS", command)
            api._window.destroy.assert_called_once()
            states = [event for event in api.poll_events() if event.get("type") == "update_state"]
            self.assertEqual(states[-1]["state"], "installing")

    def test_macos_app_path_finds_bundle(self):
        from app import platform_support

        bundle = "/Applications/Tube Vocal Removal.app/Contents/MacOS/Tube Vocal Removal"
        with mock.patch.object(platform_support.sys, "executable", bundle):
            found = platform_support.macos_app_path()
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Tube Vocal Removal.app")
        # 번들 밖에서 실행하면(개발 중) 교체 대상이 없으므로 수동 설치로 넘어가야 한다.
        with mock.patch.object(platform_support.sys, "executable", "/usr/bin/python3"):
            self.assertIsNone(platform_support.macos_app_path())

    def test_apply_update_replaces_app_bundle_on_macos(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "Tube-Vocal-Removal.dmg"
            installer.write_bytes(b"dmg")
            api = Api()
            api._window = mock.Mock()
            api._update_installer = installer
            with mock.patch("app.api.IS_MACOS", True), \
                    mock.patch("app.api.macos_app_path", return_value=Path("/Applications/T.app")), \
                    mock.patch("app.api.macos_replace_app", return_value=True) as swap, \
                    mock.patch("app.api.open_path") as opener:
                self.assertTrue(api.apply_update())
            swap.assert_called_once()
            opener.assert_not_called()
            api._window.destroy.assert_called_once()

    def test_apply_update_opens_dmg_for_manual_install_on_macos(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "Tube-Vocal-Removal.dmg"
            installer.write_bytes(b"dmg")
            api = Api()
            api._window = mock.Mock()
            api._update_installer = installer
            with mock.patch("app.api.IS_MACOS", True), mock.patch("app.api.open_path") as open_path:
                self.assertTrue(api.apply_update())
            open_path.assert_called_once_with(installer)
            api._window.destroy.assert_not_called()
            states = [event for event in api.poll_events() if event.get("type") == "update_state"]
            self.assertEqual(states[-1]["state"], "manual_install")

    def test_apply_update_waits_for_model_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = Path(tmp) / "setup.exe"
            installer.write_bytes(b"installer")
            api = Api()
            api._update_installer = installer
            api._pipeline.model_downloading = True
            with mock.patch("app.api.subprocess.Popen") as popen:
                self.assertFalse(api.apply_update())
            popen.assert_not_called()

    def test_unique_dir_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            first = unique_dir(parent, "song")
            second = unique_dir(parent, "song")
            self.assertEqual(first.name, "song")
            self.assertEqual(second.name, "song (2)")

    def test_settings_validation(self):
        result = config.validated({
            "output_format": "EXE",
            "mp3_bitrate": "320k",
            "use_gpu": False,
            "keep_source": "yes",
            "unknown": 1,
        })
        self.assertEqual(result, {"mp3_bitrate": "320k", "use_gpu": False})

    def test_queue_validation_and_duplicate(self):
        events = []
        pipeline = Pipeline(events.append)
        # 잘못된 주소는 거르고, 같은 링크는 새 행으로 중복 허용한다.
        self.assertEqual(pipeline.add_urls("bad https://youtu.be/example https://youtu.be/example"), 2)
        self.assertEqual(len(pipeline.items), 2)
        self.assertNotEqual(pipeline.items[0].id, pipeline.items[1].id)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None):
            audio = Path(tmp) / "local.wav"
            audio.write_bytes(b"wav")
            self.assertEqual(pipeline.add_files([str(audio), str(audio)]), 1)

    def test_failed_url_can_be_added_again_as_new_work(self):
        events = []
        pipeline = Pipeline(events.append)
        response = SimpleNamespace(returncode=0, stdout='{"title":"재시도 노래"}')
        with mock.patch("app.pipeline.subprocess.run", return_value=response):
            self.assertEqual(pipeline.add_urls("https://youtu.be/retry"), 1)
            first = pipeline.items[0]
            deadline = time.time() + 2
            while first.title == "제목 확인 중..." and time.time() < deadline:
                time.sleep(0.01)
            first.status = "failed"
            self.assertEqual(pipeline.add_urls("https://youtu.be/retry"), 1)
        # 실패한 행은 그대로 두고 같은 링크가 새 행으로 추가된다.
        self.assertEqual(len(pipeline.items), 2)
        self.assertNotEqual(pipeline.items[1].id, first.id)
        self.assertEqual(pipeline.items[1].status, "wait")

    def test_url_title_is_resolved_after_enter(self):
        events = []
        pipeline = Pipeline(events.append)
        response = SimpleNamespace(returncode=0, stdout='{"title":"테스트 노래 제목"}')
        with mock.patch("app.pipeline.subprocess.run", return_value=response):
            self.assertEqual(pipeline.add_urls("https://youtu.be/example"), 1)
            deadline = time.time() + 2
            while pipeline.items[0].title == "제목 확인 중..." and time.time() < deadline:
                time.sleep(0.01)
        self.assertEqual(pipeline.items[0].title, "테스트 노래 제목")
        self.assertTrue(any(event.get("type") == "queue" for event in events))

    def test_instrumental_mode_saves_only_instrumental(self):
        events = []
        pipeline = Pipeline(events.append)
        def fake_runner(_source, _mode, _cfg, output_dir, _item_id=None):
            fake = FakeSeparator()
            fake.output_dir = str(output_dir)
            return fake.separate(_source)

        pipeline._separation_runner = fake_runner
        pipeline._prepare_tools = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            source.write_bytes(b"audio")
            output = root / "output"
            temp_dir = root / "temp"
            models_dir = root / "models"
            cfg = dict(config.DEFAULTS, output_dir=str(output), output_format="WAV", volume_fix=False, download_lyrics=False)
            with mock.patch.object(config, "TEMP_DIR", temp_dir), mock.patch.object(config, "MODELS_DIR", models_dir):
                item = Item("file", str(source), "source.wav")
                pipeline.items.append(item)
                self.assertTrue(pipeline.start("best", cfg))
                deadline = time.time() + 5
                while pipeline.running and time.time() < deadline:
                    time.sleep(0.01)
            self.assertFalse(pipeline.running)
            self.assertEqual(item.status, "done")
            files = sorted(Path(item.out_dir).glob("*.wav"))
            self.assertEqual(len(files), 1)
            self.assertTrue(any("반주" in f.name for f in files))

    def test_item_added_while_running_is_processed_in_same_run(self):
        events = []
        pipeline = Pipeline(events.append)
        first_started = threading.Event()
        release_first = threading.Event()
        calls = []

        def fake_runner(source, _mode, _cfg, output_dir, _item_id=None):
            calls.append(Path(source).name)
            if len(calls) == 1:
                first_started.set()
                release_first.wait(2)
            fake = FakeSeparator()
            fake.output_dir = str(output_dir)
            return fake.separate(source)

        pipeline._separation_runner = fake_runner
        pipeline._prepare_tools = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.wav"
            second = root / "second.wav"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            cfg = dict(config.DEFAULTS, output_dir=str(root / "output"), volume_fix=False, download_lyrics=False)
            with mock.patch.object(config, "TEMP_DIR", root / "temp"), \
                    mock.patch.object(config, "MODELS_DIR", root / "models"), \
                    mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None):
                pipeline.add_files([str(first)])
                self.assertTrue(pipeline.start("best", cfg))
                self.assertTrue(first_started.wait(2))
                pipeline.add_files([str(second)])
                release_first.set()
                deadline = time.time() + 5
                while pipeline.running and time.time() < deadline:
                    time.sleep(0.01)
        self.assertEqual(calls, ["first.wav", "second.wav"])
        self.assertTrue(all(item.status == "done" for item in pipeline.items))

    def test_volume_fix_normalizes_output_and_requests_wav(self):
        pipeline = Pipeline(lambda _event: None)
        normalized = []

        def fake_runner(_source, _mode, cfg, output_dir, _item_id=None):
            fake = FakeSeparator()
            fake.output_dir = str(output_dir)
            return fake.separate(_source)

        def fake_normalize(source, destination, cfg):
            normalized.append((Path(source).name, Path(destination).suffix, cfg["output_format"]))
            Path(destination).write_bytes(b"normalized")

        pipeline._separation_runner = fake_runner
        pipeline._normalize_and_encode = fake_normalize
        pipeline._prepare_tools = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song.wav"
            source.write_bytes(b"audio")
            cfg = dict(config.DEFAULTS, output_dir=str(root / "output"), output_format="MP3", volume_fix=True, download_lyrics=False)
            with mock.patch.object(config, "TEMP_DIR", root / "temp"), \
                    mock.patch.object(config, "MODELS_DIR", root / "models"), \
                    mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None):
                pipeline.add_files([str(source)])
                self.assertTrue(pipeline.start("best", cfg))
                deadline = time.time() + 5
                while pipeline.running and time.time() < deadline:
                    time.sleep(0.01)
        self.assertEqual(pipeline.items[0].status, "done")
        # 반주 하나만 보정을 거쳐 최종 형식(MP3)으로 저장된다.
        self.assertEqual(normalized, [("sample_(Instrumental).wav", ".mp3", "MP3")])

    def test_volume_fix_requests_lossless_intermediate(self):
        pipeline = Pipeline(lambda _event: None)
        cfg = {"output_format": "MP3", "volume_fix": True}
        # 보정을 거치면 워커에는 무손실 WAV를 요청하고, 악기별 분리는 원래 형식을 유지한다.
        with tempfile.TemporaryDirectory() as tmp:
            captured = {}

            def fake_worker_request(request, _request_path, _response_path, _item_id=None):
                captured.update(request)
                return []

            pipeline._run_worker_request = fake_worker_request
            with mock.patch.object(config, "MODELS_DIR", Path(tmp)):
                pipeline._run_separation_process(Path(tmp) / "a.wav", "best", cfg, Path(tmp))
                self.assertEqual(captured["output_format"], "WAV")
                pipeline._run_separation_process(Path(tmp) / "a.wav", "demucs", cfg, Path(tmp))
                self.assertEqual(captured["output_format"], "MP3")

    def test_demucs_keeps_all_four_stems(self):
        pipeline = Pipeline(lambda _event: None)

        def fake_demucs(_source, _mode, _cfg, output_dir, _item_id=None):
            names = ["song_(Vocals).wav", "song_(Drums).wav", "song_(Bass).wav", "song_(Other).wav"]
            for name in names:
                (output_dir / name).write_bytes(b"stem")
            return names

        pipeline._separation_runner = fake_demucs
        pipeline._prepare_tools = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "song.wav"
            source.write_bytes(b"audio")
            cfg = dict(config.DEFAULTS, output_dir=str(root / "output"), download_lyrics=False)
            with mock.patch.object(config, "TEMP_DIR", root / "temp"), \
                    mock.patch.object(config, "MODELS_DIR", root / "models"), \
                    mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None):
                pipeline.add_files([str(source)])
                self.assertTrue(pipeline.start("demucs", cfg))
                deadline = time.time() + 5
                while pipeline.running and time.time() < deadline:
                    time.sleep(0.01)
            outputs = list(Path(pipeline.items[0].out_dir).glob(f"*.{cfg['output_format'].lower()}"))
        self.assertEqual(len(outputs), 4)

    def test_system_exit_from_engine_marks_item_failed(self):
        events = []
        pipeline = Pipeline(events.append)
        pipeline._prepare_tools = lambda: None
        pipeline._separation_runner = lambda *_args: (_ for _ in ()).throw(SystemExit(1))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.wav"
            source.write_bytes(b"audio")
            cfg = dict(config.DEFAULTS, output_dir=str(root / "output"), download_lyrics=False)
            with mock.patch.object(config, "TEMP_DIR", root / "temp"), mock.patch.object(config, "MODELS_DIR", root / "models"):
                item = Item("file", str(source), "source.wav")
                pipeline.items.append(item)
                pipeline.start("best", cfg)
                deadline = time.time() + 5
                while pipeline.running and time.time() < deadline:
                    time.sleep(0.01)
            self.assertEqual(item.status, "failed")
            self.assertTrue(item.error)


class LyricsTests(unittest.TestCase):
    def test_clean_title_and_split(self):
        from app import lyrics
        self.assertEqual(lyrics.clean_title("아이유(IU) _ 좋은 날(Good Day) M/V"), "아이유 _ 좋은 날")
        self.assertEqual(lyrics.split_artist_title("아이유 _ 좋은 날"), ("아이유", "좋은 날"))
        self.assertEqual(lyrics.split_artist_title("좋은 날"), (None, "좋은 날"))

    def test_lrclib_exact_match_prefers_synced(self):
        from app import lyrics
        body = json.dumps({
            "trackName": "좋은 날", "artistName": "아이유", "duration": 214,
            "syncedLyrics": "[00:16.25] 어쩜 이렇게\n[00:23.62] 오늘따라",
            "plainLyrics": "어쩜 이렇게\n오늘따라",
        }).encode("utf-8")

        def fake_get(url):
            if "/api/get" in url:
                return body
            raise AssertionError("검색까지 갈 필요 없음")

        with mock.patch("app.lyrics._http_get", fake_get):
            result = lyrics.fetch_lyrics("아이유 - 좋은 날", duration=214)
        self.assertEqual(result["source"], "LRCLIB")
        self.assertIn("어쩜 이렇게", result["text"])
        self.assertNotIn("[00:16", result["text"])   # 텍스트는 타임스탬프 제거
        self.assertIsNotNone(result["synced"])         # 싱크 원본은 보존

    def test_lrclib_rejects_wrong_artist(self):
        from app import lyrics
        search = json.dumps([{
            "trackName": "고백하기 좋은 날", "artistName": "Younha", "duration": 240,
            "syncedLyrics": "[00:01.00] 엉뚱한 가사",
        }]).encode("utf-8")

        def fake_get(url):
            if "/api/get" in url:
                raise RuntimeError("404")       # 정확 매칭 실패 → 검색 폴백
            if "/api/search" in url:
                return search
            return b""                            # boom4u도 빈 응답

        with mock.patch("app.lyrics._http_get", fake_get):
            result = lyrics.fetch_lyrics("아이유 - 좋은 날", duration=214)
        self.assertIsNone(result)                 # 가수 불일치 → 엉뚱한 가사 거부

    def test_kr_fallback_matches_and_extracts_lyrics(self):
        from app import lyrics
        search_html = "<html><body><a href='/track/476239'>노스탤지어</a></body></html>".encode("utf-8")
        track_html = ("<html><head><title>노스탤지어/미르(Mir) - 벅스</title></head><body>"
                      "<xmp id='lyricsContainer'>창밖으로 쓸쓸히 비가 내리네\n네가 떠나던 그날도 슬피 울었지\n"
                      "긴 시간이 흘러 지나가 버린 꿈\n그리 허무한 바람만이 불어오나</xmp>"
                      "</body></html>").encode("utf-8")

        def fake_get(url):
            if "lrclib" in url:
                raise RuntimeError("가사 없음")     # LRCLIB 미스
            if "/track/" in url:
                return track_html
            return search_html

        with mock.patch("app.lyrics._http_get", fake_get):
            result = lyrics.fetch_lyrics("미르 - 노스탤지어")
        self.assertIsNotNone(result)
        self.assertIn("창밖으로 쓸쓸히 비가 내리네", result["text"])

    def test_kr_fallback_rejects_wrong_artist(self):
        from app import lyrics
        search_html = "<html><body><a href='/track/999'>좋은 날</a></body></html>".encode("utf-8")
        track_html = ("<html><head><title>좋은 날/윤하(Younha) - 벅스</title></head><body>"
                      "<xmp>엉뚱한 가사 한 줄</xmp></body></html>").encode("utf-8")

        def fake_get(url):
            if "lrclib" in url:
                raise RuntimeError("미스")
            if "/track/" in url:
                return track_html
            return search_html

        with mock.patch("app.lyrics._http_get", fake_get):
            result = lyrics.fetch_lyrics("아이유 - 좋은 날")
        self.assertIsNone(result)               # 가수 불일치 → 거부

    def test_save_lyrics_writes_txt_only(self):
        from app import lyrics
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "가사.txt"
            lyrics.save_lyrics({"text": "가사 본문", "synced": "[00:01.00] 가사 본문"}, dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "가사 본문")
            self.assertFalse(dest.with_suffix(".lrc").exists())   # .lrc 저장 안 함


class KeyShiftTests(unittest.TestCase):
    def _sine(self, path, freq=220.0, seconds=1.0, sr=22050):
        import numpy as np
        import soundfile as sf
        t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
        sf.write(str(path), (0.3 * np.sin(2 * np.pi * freq * t)).astype("float32"), sr)

    def test_shift_preserves_length(self):
        from app import keyshift
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
            self._sine(src)
            keyshift.shift_file(src, 2, dst)
            a, b = sf.info(str(src)), sf.info(str(dst))
            self.assertEqual(a.samplerate, b.samplerate)
            self.assertLess(abs(a.frames - b.frames), a.samplerate * 0.05)  # 템포 유지

    def test_shift_raises_pitch_one_octave(self):
        from app import keyshift
        import numpy as np
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
            self._sine(src, freq=220.0)
            keyshift.shift_file(src, 12, dst)  # +12반음 = 1옥타브 → 주파수 2배
            y, sr = sf.read(str(dst))
            spectrum = np.abs(np.fft.rfft(y))
            peak_hz = np.fft.rfftfreq(len(y), 1 / sr)[int(np.argmax(spectrum))]
            self.assertTrue(400 < peak_hz < 480, f"peak {peak_hz}Hz")

    def test_detect_key_returns_valid_label(self):
        from app import keyshift
        import numpy as np
        import soundfile as sf
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "chord.wav"
            sr = 22050
            t = np.linspace(0, 2.0, sr * 2, endpoint=False)
            # C-E-G 화음 → 조성 추정이 동작하는지 형식만 검증
            tone = sum(0.2 * np.sin(2 * np.pi * f * t) for f in (261.6, 329.6, 392.0))
            sf.write(str(src), tone.astype("float32"), sr)
            label = keyshift.detect_key(src)
            self.assertRegex(label, r"^[A-G]#? (major|minor)$")


class LyricsAndKeyPipelineTests(unittest.TestCase):
    def test_key_shift_requests_lossless_intermediate(self):
        pipeline = Pipeline(lambda _event: None)
        cfg = {"output_format": "MP3", "volume_fix": False, "key_shift": 2}
        with tempfile.TemporaryDirectory() as tmp:
            captured = {}

            def fake_worker_request(request, _rp, _resp, _item_id=None):
                captured.update(request)
                return []

            pipeline._run_worker_request = fake_worker_request
            with mock.patch.object(config, "MODELS_DIR", Path(tmp)):
                pipeline._run_separation_process(Path(tmp) / "a.wav", "karaoke", cfg, Path(tmp))
                self.assertEqual(captured["output_format"], "WAV")   # 키 이동 → 무손실 WAV 요청

    def test_key_shift_applies_shift_and_encode(self):
        pipeline = Pipeline(lambda _event: None)
        calls = []

        def fake_runner(_source, _mode, _cfg, output_dir, _item_id=None):
            fake = FakeSeparator()
            fake.output_dir = str(output_dir)
            return fake.separate(_source)

        def fake_shift(source, semitones, destination):
            calls.append(("shift", Path(source).name, semitones))
            Path(destination).write_bytes(b"shifted")

        def fake_encode(source, destination, _cfg):
            calls.append(("encode", Path(destination).suffix))
            Path(destination).write_bytes(b"encoded")

        pipeline._separation_runner = fake_runner
        pipeline._encode_audio = fake_encode
        pipeline._prepare_tools = lambda: None
        with mock.patch("app.keyshift.shift_file", fake_shift):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "song.wav"
                source.write_bytes(b"audio")
                cfg = dict(config.DEFAULTS, output_dir=str(root / "output"),
                           output_format="MP3", volume_fix=False, download_lyrics=False)
                with mock.patch.object(config, "TEMP_DIR", root / "temp"), \
                        mock.patch.object(config, "MODELS_DIR", root / "models"), \
                        mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None):
                    pipeline.add_files([str(source)])
                    pipeline.items[0].key_shift = 3   # 곡별 목표 키 +3
                    self.assertTrue(pipeline.start("best", cfg))
                    deadline = time.time() + 5
                    while pipeline.running and time.time() < deadline:
                        time.sleep(0.01)
        self.assertEqual(pipeline.items[0].status, "done")
        self.assertIn(("shift", "sample_(Instrumental).wav", 3), calls)
        self.assertIn(("encode", ".mp3"), calls)

    def test_set_item_key_clamps_and_lyrics_toggle(self):
        pipeline = Pipeline(lambda _event: None)
        item = Item("url", "https://x", "곡")
        pipeline.items.append(item)
        self.assertEqual(pipeline.set_item_key(item.id, 3), 3)
        self.assertEqual(pipeline.set_item_key(item.id, 99), 6)    # -6~+6 클램프
        self.assertEqual(pipeline.set_item_key(item.id, -99), -6)
        self.assertFalse(pipeline.set_item_lyrics(item.id, False))
        self.assertFalse(item.want_lyrics)
        self.assertIn("keyShift", item.to_dict())
        self.assertIn("detectedKey", item.to_dict())
        # 실행 중인 곡은 키를 못 바꾼다
        item.status = "run"
        self.assertIsNone(pipeline.set_item_key(item.id, 1))

    def test_same_url_downloads_once_and_reuses(self):
        # 같은 링크를 여러 키로 넣으면 첫 곡만 yt-dlp를 돌리고 나머지는 캐시를 재사용한다.
        pipeline = Pipeline(lambda _event: None)
        calls = []

        def fake_popen(cmd, **kwargs):
            calls.append(cmd)
            work_dir = Path(cmd[cmd.index("-o") + 1]).parent
            (work_dir / "song.webm").write_bytes(b"audio-data")
            return SimpleNamespace(
                stdout=iter(["[download] 100%\n"]),
                wait=lambda: 0,
            )

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, "TEMP_DIR", Path(tmp)), \
                    mock.patch("app.pipeline.subprocess.Popen", side_effect=fake_popen), \
                    mock.patch.object(pipeline, "_detect_key_async", lambda *_a: None), \
                    mock.patch.object(Path, "is_file", lambda self: self.exists() or str(self).endswith(".webm")):
                a = Item("url", "https://youtu.be/same", "곡")
                b = Item("url", "https://youtu.be/same", "곡")
                src_a = pipeline._download(a, 1, 2)
                src_b = pipeline._download(b, 2, 2)
        self.assertEqual(len(calls), 1)            # 다운로드는 한 번만
        self.assertTrue(str(src_a).endswith(".webm"))
        self.assertTrue(str(src_b).endswith(".webm"))
        self.assertEqual(a.title, "song")
        self.assertEqual(b.title, "song")         # 캐시 해시가 아니라 원래 제목 유지

    def test_lyrics_saved_when_enabled(self):
        pipeline = Pipeline(lambda _event: None)
        with tempfile.TemporaryDirectory() as tmp:
            song_dir = Path(tmp)
            item = Item("url", "https://x", "아이유 - 좋은 날")
            with mock.patch("app.lyrics.fetch_lyrics", return_value={"text": "가사", "synced": None}):
                pipeline._save_lyrics(item, song_dir)
            saved = list(song_dir.glob("*(가사).txt"))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_text(encoding="utf-8"), "가사")


if __name__ == "__main__":
    unittest.main()
