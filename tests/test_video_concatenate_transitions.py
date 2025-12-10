import os
import shutil
import tempfile
import uuid
from unittest import mock

import ffmpeg

os.environ.setdefault("API_KEY", "test-api-key")
TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="video-concat-storage-")
os.environ["LOCAL_STORAGE_PATH"] = TEST_STORAGE_DIR

from services.v1.video.concatenate import process_video_concatenate  # noqa: E402


def _make_fixture_clip(path: str, color: str, duration: float) -> str:
    video = ffmpeg.input(
        f"color=c={color}:s=640x360:r=30:d={duration}",
        f="lavfi",
    )
    audio = ffmpeg.input(
        f"sine=frequency=440:sample_rate=48000:duration={duration}",
        f="lavfi",
    )
    (
        ffmpeg.output(
            video,
            audio,
            path,
            vcodec="libx264",
            pix_fmt="yuv420p",
            acodec="aac",
            movflags="faststart",
        )
        .run(overwrite_output=True, quiet=True)
    )
    return path


def _cleanup_storage() -> None:
    if os.path.exists(TEST_STORAGE_DIR):
        for entry in os.listdir(TEST_STORAGE_DIR):
            entry_path = os.path.join(TEST_STORAGE_DIR, entry)
            if os.path.isdir(entry_path):
                shutil.rmtree(entry_path, ignore_errors=True)
            else:
                os.remove(entry_path)


def _mock_download(url: str, storage_path: str) -> str:
    os.makedirs(storage_path, exist_ok=True)
    destination = os.path.join(storage_path, f"{uuid.uuid4()}_{os.path.basename(url)}")
    shutil.copy(url, destination)
    return destination


def test_concatenate_with_fade_transition(tmp_path=None):  # noqa: ARG001
    fixture_dir = tempfile.mkdtemp(prefix="video-concat-fixtures-")
    clip_paths = [
        _make_fixture_clip(os.path.join(fixture_dir, "clip1.mp4"), "red", 2.0),
        _make_fixture_clip(os.path.join(fixture_dir, "clip2.mp4"), "blue", 2.0),
    ]
    media_urls = [{"video_url": path} for path in clip_paths]

    output_path = None
    try:
        with mock.patch("services.v1.video.concatenate.download_file", side_effect=_mock_download):
            output_path = process_video_concatenate(
                media_urls,
                "transition-test",
                transition_type="fade_black",
                transition_duration=0.5,
            )

        assert output_path is not None and os.path.exists(output_path)
        probe = ffmpeg.probe(output_path)
        duration = float(probe.get("format", {}).get("duration", 0.0))
        assert duration > 3.0
    finally:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
        shutil.rmtree(fixture_dir, ignore_errors=True)
        _cleanup_storage()


def test_concatenate_with_whip_pan_audio(tmp_path=None):  # noqa: ARG001
    fixture_dir = tempfile.mkdtemp(prefix="video-concat-fixtures-")
    clip_paths = [
        _make_fixture_clip(os.path.join(fixture_dir, "clip1.mp4"), "red", 2.0),
        _make_fixture_clip(os.path.join(fixture_dir, "clip2.mp4"), "blue", 2.0),
    ]
    media_urls = [{"video_url": path} for path in clip_paths]

    output_path = None
    try:
        with mock.patch("services.v1.video.concatenate.download_file", side_effect=_mock_download):
            output_path = process_video_concatenate(
                media_urls,
                "whip-pan-test",
                transition_type="whip_pan",
                transition_duration=0.6,
                transition_sequence=["whip_pan"],
                whip_pan_sfx_gain_db=-3,
            )

        assert output_path is not None and os.path.exists(output_path)
        probe = ffmpeg.probe(output_path)
        duration = float(probe.get("format", {}).get("duration", 0.0))
        assert duration > 3.0
    finally:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
        shutil.rmtree(fixture_dir, ignore_errors=True)
        _cleanup_storage()
