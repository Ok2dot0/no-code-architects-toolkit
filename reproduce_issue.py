import os
import sys
import ffmpeg
import uuid
from unittest.mock import MagicMock, patch

# Add the current directory to sys.path so we can import services
sys.path.append(os.getcwd())

from services.v1.video.concatenate import process_video_concatenate

def generate_test_video(filename, duration=2, color='black'):
    """Generates a test video with audio."""
    if os.path.exists(filename):
        return
    
    print(f"Generating {filename}...")
    video = ffmpeg.input(f'color=c={color}:s=320x240:d={duration}', f='lavfi')
    audio = ffmpeg.input(f'anullsrc=r=48000:cl=stereo', f='lavfi').audio.filter('atrim', duration=duration)
    
    ffmpeg.output(video, audio, filename, vcodec='libx264', acodec='aac', pix_fmt='yuv420p').run(overwrite_output=True, quiet=True)

def reproduce():
    # Create dummy video files
    num_videos = 13
    video_files = []
    for i in range(num_videos):
        filename = f"test_video_{i}.mp4"
        generate_test_video(filename, duration=2, color='red' if i % 2 == 0 else 'blue')
        video_files.append(filename)

    # Mock download_file to just return the local file path
    # We need to patch services.v1.video.concatenate.download_file
    # But process_video_concatenate imports it from services.file_management
    
    # Also need to mock WHIP_PAN_SFX_PATH if it doesn't exist
    # The code checks os.path.exists(WHIP_PAN_SFX_PATH)
    # If it doesn't exist, it returns None for sfx, which is fine, but we want to test the crash.
    # The user has "whip_pan", so sfx is likely involved.
    
    # Let's check if the sfx file exists in the workspace
    # It is at assets/audio/whip_pan_whoosh.mp3
    
    # Mocking download_file
    with patch('services.v1.video.concatenate.download_file') as mock_download:
        mock_download.side_effect = lambda url, dest: f"test_video_{url.split('_')[-1]}.mp4"

        # Prepare input
        media_urls = [{"video_url": f"http://mock/video_{i}"} for i in range(num_videos)]
        job_id = "reproduce_test"
        
        transition_sequence = ["whip_pan"] * (num_videos - 1)
        
        print("Running process_video_concatenate...")
        try:
            output = process_video_concatenate(
                media_urls=media_urls,
                job_id=job_id,
                transition_type="whip_pan",
                transition_sequence=transition_sequence,
                whip_pan_sfx_gain_db=-4,
                transition_sfx_track_id=0
            )
            print(f"Success! Output: {output}")
        except ffmpeg.Error as e:
            print(f"Caught ffmpeg.Error: {e}")
            if e.stderr:
                print("STDERR:")
                print(e.stderr.decode('utf8'))
            raise
        except Exception as e:
            print(f"Caught exception: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    reproduce()
