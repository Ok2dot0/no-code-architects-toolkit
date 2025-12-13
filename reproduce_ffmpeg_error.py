import os
import sys
import subprocess
import ffmpeg

# Add current directory to sys.path to ensure imports work
sys.path.append(os.getcwd())

try:
    from services.v1.video.concatenate import _concatenate_with_transitions
except ImportError as e:
    print(f"Error importing services: {e}")
    sys.exit(1)

def generate_dummy_video(filename, color, freq):
    """Generates a 1-second dummy video with audio."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'color=c={color}:s=1280x720:d=1',
        '-f', 'lavfi', '-i', f'sine=f={freq}:d=1',
        '-c:v', 'libx264', '-c:a', 'aac',
        filename
    ]
    print(f"Generating {filename}...")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    input1 = 'input1.mp4'
    input2 = 'input2.mp4'
    output = 'output.mp4'

    # 1. Generate dummy videos
    try:
        generate_dummy_video(input1, 'red', 440)
        generate_dummy_video(input2, 'blue', 880)
    except subprocess.CalledProcessError as e:
        print(f"Error generating dummy videos: {e}")
        return

    # 2. Setup arguments
    input_files = [os.path.abspath(input1), os.path.abspath(input2)]
    output_path = os.path.abspath(output)
    transition_plan = ['whip_pan']
    transition_duration = 0.5
    whip_pan_sfx_gain_db = -6.0
    transition_sfx_track_id = 1

    print("Calling _concatenate_with_transitions...")
    try:
        _concatenate_with_transitions(
            input_files=input_files,
            output_path=output_path,
            transition_plan=transition_plan,
            transition_duration=transition_duration,
            whip_pan_sfx_gain_db=whip_pan_sfx_gain_db,
            transition_sfx_track_id=transition_sfx_track_id
        )
        print("Success! Output generated at", output_path)
    except ffmpeg.Error as e:
        print("Caught ffmpeg.Error:")
        print(e.stderr.decode('utf8') if e.stderr else str(e))
    except Exception as e:
        print(f"Caught unexpected exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
