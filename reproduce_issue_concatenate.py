import os
import sys
import logging
import json
from unittest.mock import patch, MagicMock
import ffmpeg

# Set environment variables before importing config
os.environ["API_KEY"] = "dummy_key"
os.environ["LOCAL_STORAGE_PATH"] = os.path.join(os.getcwd(), "local-files")
if not os.path.exists(os.environ["LOCAL_STORAGE_PATH"]):
    os.makedirs(os.environ["LOCAL_STORAGE_PATH"])

# Add workspace root to sys.path
sys.path.append(os.getcwd())

from services.v1.video.concatenate import process_video_concatenate

logging.basicConfig(level=logging.INFO)

def create_dummy_video(filename, duration=5, has_audio=True):
    """Creates a dummy video file using ffmpeg."""
    inputs = [ffmpeg.input(f"testsrc=duration={duration}:size=640x360:rate=30", f="lavfi")]
    if has_audio:
        inputs.append(ffmpeg.input(f"sine=frequency=1000:duration={duration}", f="lavfi"))
    
    output_args = {"vcodec": "libx264", "pix_fmt": "yuv420p"}
    if has_audio:
        output_args["acodec"] = "aac"
    
    stream = ffmpeg.output(*inputs, filename, **output_args)
    stream.run(overwrite_output=True, quiet=True)
    print(f"Created dummy video: {filename}")

def mock_download_file(url, dest_path):
    """Mocks download_file by copying a local dummy file."""
    # We assume the url is just the filename of the dummy file we created
    import shutil
    if os.path.exists(url):
        shutil.copy(url, dest_path)
        return dest_path
    else:
        # If url is not a local file, create a dummy one at dest_path
        create_dummy_video(dest_path)
        return dest_path

def reproduce():
    # Create dummy videos
    video1 = "dummy1.mp4"
    video2 = "dummy2.mp4"
    create_dummy_video(video1, duration=5, has_audio=True)
    create_dummy_video(video2, duration=5, has_audio=True)

    # Mock data
    job_id = "test_job"
    media_urls = [
        {"video_url": video1},
        {"video_url": video2}
    ]
    
    # Test case 1: Basic concatenation with default transition (none)
    print("\n--- Test Case 1: Basic Concatenation (No Transition) ---")
    try:
        with patch("services.v1.video.concatenate.download_file", side_effect=mock_download_file):
            output = process_video_concatenate(
                media_urls=media_urls,
                job_id=job_id + "_1",
                transition_type="none"
            )
            print(f"Success! Output: {output}")
    except Exception as e:
        print(f"Failed: {e}")

    # Test case 2: Concatenation with 'fade' transition
    print("\n--- Test Case 2: Concatenation with 'fade' Transition ---")
    try:
        with patch("services.v1.video.concatenate.download_file", side_effect=mock_download_file):
            output = process_video_concatenate(
                media_urls=media_urls,
                job_id=job_id + "_2",
                transition_type="fade",
                transition_duration=1.0
            )
            print(f"Success! Output: {output}")
    except Exception as e:
        print(f"Failed: {e}")

    # Test case 3: Concatenation with 'whip_pan' transition (complex logic)
    print("\n--- Test Case 3: Concatenation with 'whip_pan' Transition ---")
    try:
        with patch("services.v1.video.concatenate.download_file", side_effect=mock_download_file):
            # Mock the SFX file existence check
            with patch("os.path.exists", side_effect=lambda p: True if "whip_pan_whoosh.mp3" in p else os.path.exists(p)):
                 # We also need to mock the SFX input because the path might not exist
                 # Actually, let's just create a dummy SFX file
                 sfx_path = os.path.join(os.getcwd(), "assets", "audio", "whip_pan_whoosh.mp3")
                 os.makedirs(os.path.dirname(sfx_path), exist_ok=True)
                 if not os.path.exists(sfx_path):
                     ffmpeg.input("sine=frequency=500:duration=1", f="lavfi").output(sfx_path).run(quiet=True)

                 output = process_video_concatenate(
                    media_urls=media_urls,
                    job_id=job_id + "_3",
                    transition_type="whip_pan",
                    transition_duration=0.5
                )
                 print(f"Success! Output: {output}")
    except Exception as e:
        print(f"Failed: {e}")
        import traceback
        traceback.print_exc()

    # Clean up
    if os.path.exists(video1): os.remove(video1)
    if os.path.exists(video2): os.remove(video2)
    # Clean up outputs
    for f in os.listdir("local-files"):
        if f.startswith("test_job"):
            os.remove(os.path.join("local-files", f))

if __name__ == "__main__":
    reproduce()
