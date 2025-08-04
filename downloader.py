# Universal Audio/Video Downloader (with Smart Selection)
# This script automatically finds the best download options and presents
# a simple menu to the user, limited to a maximum of 4 choices.
#
# Before running:
# 1. Make sure you have Python installed.
# 2. Install the yt-dlp library:
#    pip install yt-dlp
# 3. For the best quality options (merging video and audio) and for MP3 conversion,
#    you MUST have FFmpeg installed. You can download it from ffmpeg.org.

import yt_dlp
import sys

def format_size(size_in_bytes):
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if size_in_bytes is None or size_in_bytes == 0:
        return "N/A"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size_in_bytes >= power and n < len(power_labels):
        size_in_bytes /= power
        n += 1
    return f"{size_in_bytes:.2f} {power_labels[n]}B"

def get_smart_choices(url):
    """
    Fetches format information and intelligently selects the best 4 options.
    """
    ydl_opts = {'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Fetching available formats, please wait...")
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"\nCould not fetch video information. Error: {e}")
        return None

    formats = info.get('formats', [])
    if not formats:
        print("No downloadable formats found.")
        return None

    choices = {}
    
    # --- Find Best Audio ---
    best_audio = max(
        (f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None),
        key=lambda f: f.get('abr', 0),
        default=None
    )
    if best_audio:
        choices['audio_only'] = {
            'label': f"Audio Only (Best Quality, MP3)",
            'format_id': best_audio['format_id'],
            'filesize': best_audio.get('filesize') or best_audio.get('filesize_approx'),
            'type': 'audio'
        }

    # --- Find Best Video-only Streams, prioritizing those with file sizes ---
    video_streams = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4' and f.get('tbr') is not None]
    
    def find_best_video(streams, height):
        """Helper function to find the best video stream at a given height."""
        target_streams = [s for s in streams if s.get('height') == height]
        if not target_streams:
            return None
        
        # Prioritize streams that have a size estimate
        sized_streams = [s for s in target_streams if s.get('filesize') or s.get('filesize_approx')]
        
        if sized_streams:
            # If we have streams with size, pick the best bitrate from them
            return max(sized_streams, key=lambda f: f.get('tbr', 0), default=None)
        else:
            # Fallback: if no streams have size, pick the best bitrate from all available
            return max(target_streams, key=lambda f: f.get('tbr', 0), default=None)

    best_1080p = find_best_video(video_streams, 1080)
    best_720p = find_best_video(video_streams, 720)

    # --- Find Best Pre-merged Stream (video+audio) ---
    best_merged = max(
        (f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none'),
        key=lambda f: f.get('height', 0),
        default=None
    )

    # --- Build the Choices Menu ---
    final_choices = []
    if best_1080p and best_audio:
        video_size = best_1080p.get('filesize') or best_1080p.get('filesize_approx') or 0
        audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx') or 0
        final_choices.append({
            'label': f"Best Quality ({best_1080p.get('resolution')})",
            'format_id': f"{best_1080p['format_id']}+{best_audio['format_id']}",
            'filesize': video_size + audio_size,
            'type': 'video'
        })
    if best_720p and best_audio:
        video_size = best_720p.get('filesize') or best_720p.get('filesize_approx') or 0
        audio_size = best_audio.get('filesize') or best_audio.get('filesize_approx') or 0
        final_choices.append({
            'label': f"Good Quality ({best_720p.get('resolution')})",
            'format_id': f"{best_720p['format_id']}+{best_audio['format_id']}",
            'filesize': video_size + audio_size,
            'type': 'video'
        })
    if best_merged:
        final_choices.append({
            'label': f"Standard Quality ({best_merged.get('resolution')}, single file)",
            'format_id': best_merged['format_id'],
            'filesize': best_merged.get('filesize') or best_merged.get('filesize_approx'),
            'type': 'video'
        })
    if 'audio_only' in choices:
        final_choices.append(choices['audio_only'])

    # Ensure we have at most 4 unique choices
    unique_choices = []
    seen_labels = set()
    for choice in final_choices:
        if choice['label'] not in seen_labels:
            unique_choices.append(choice)
            seen_labels.add(choice['label'])
    
    return unique_choices[:4]

def select_and_download(url):
    """
    Presents the simplified menu and handles the download process.
    """
    choices = get_smart_choices(url)
    if not choices:
        return

    print("\n--- Please Select a Download Option ---")
    for i, choice in enumerate(choices, 1):
        size_str = format_size(choice['filesize'])
        print(f"{i}: {choice['label']} (~{size_str})")
    print("-" * 40)

    while True:
        try:
            user_choice = int(input(f"Enter your choice (1-{len(choices)}): "))
            if 1 <= user_choice <= len(choices):
                selected = choices[user_choice - 1]
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a number.")
            
    # --- Configure Download Options ---
    format_selection = selected['format_id']
    ydl_opts = {
        'format': format_selection,
        'outtmpl': '%(title)s.%(ext)s',
        'noplaylist': True,
    }

    # Special handling for audio conversion to MP3
    if selected['type'] == 'audio':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    # If merging, remux to mp4 for best compatibility
    elif '+' in format_selection:
         ydl_opts['postprocessors'] = [{
            'key': 'FFmpegVideoRemuxer',
            'preferedformat': 'mp4',
        }]

    # --- Start Download ---
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("\nStarting download... please wait.")
            ydl.download([url])
            print("\nDownload finished successfully!")
    except yt_dlp.utils.DownloadError as e:
        print(f"\nAn error occurred during download: {e}")
        print("Please check the URL and your network connection.")
        print("If merging or converting, ensure you have FFmpeg installed correctly.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

def main():
    """
    Main function to run the downloader script.
    """
    print("--- Universal Audio/Video Downloader ---")
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"URL provided: {url}")
    else:
        url = input("Please enter the URL of the media you want to download: ")

    if not url:
        print("No URL provided. Exiting.")
        return

    select_and_download(url)

if __name__ == "__main__":
    main()
