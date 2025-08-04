# Universal Audio/Video Downloader (with Smart Selection)
# This script automatically finds the best download options for video and audio
# and presents a simple menu to the user.
#
# Before running:
# 1. Make sure you have Python installed.
# 2. Install the yt-dlp library:
#    pip install yt-dlp
# 3. For the best quality options (merging video and audio) and for MP3 conversion,
#    you MUST have FFmpeg installed. You can download it from ffmpeg.org.

import yt_dlp
import sys
import os
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

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

def sanitize_youtube_url(url):
    """
    Sanitizes YouTube URLs to remove tracking parameters, playlists, etc.
    """
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname

    # Only proceed if it's a recognizable YouTube domain
    if not (hostname and ('youtube.com' in hostname or 'youtu.be' in hostname)):
        return url

    clean_url = ""
    if 'youtu.be' in hostname:
        # For youtu.be links, the path is the video ID. Remove all query params.
        # e.g., https://youtu.be/iQYxjOAAbu4?si=... -> https://youtu.be/iQYxjOAAbu4
        clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
    elif 'youtube.com' in hostname and parsed_url.path == '/watch':
        # For youtube.com/watch links, keep only the 'v' parameter.
        query_params = parse_qs(parsed_url.query)
        if 'v' in query_params:
            # Rebuild the URL with only the 'v' parameter
            sanitized_query = urlencode({'v': query_params['v'][0]}, doseq=True)
            clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', sanitized_query, ''))

    if clean_url and url != clean_url:
        print(f"Sanitizing URL to: {clean_url}")
        return clean_url
    
    # If no changes were made or pattern didn't match, return original URL
    return url

def get_smart_choices(url):
    """
    Fetches format information and intelligently selects the best options.
    """
    ydl_opts = {'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Fetching available formats, please wait...")
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        # Add a specific check for DRM errors for a graceful exit.
        if 'DRM' in str(e):
            print("\nError: This content is protected by DRM and cannot be downloaded.")
            print("This script does not support services like Spotify, Netflix, etc.")
            return None # Return None to allow the main loop to continue
        else:
            print(f"\nCould not fetch video information. Error: {e}")
            return None

    formats = info.get('formats', [])
    if not formats:
        print("No downloadable formats found.")
        return None

    # --- Find Best Audio for Merging ---
    best_audio_for_merge = max(
        (f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None),
        key=lambda f: f.get('abr', 0),
        default=None
    )

    # --- Find Best Video-only Streams, prioritizing those with file sizes ---
    video_streams = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4' and f.get('tbr') is not None]
    
    def find_best_video(streams, height):
        """Helper function to find the best video stream at a given height."""
        target_streams = [s for s in streams if s.get('height') == height]
        if not target_streams:
            return None
        sized_streams = [s for s in target_streams if s.get('filesize') or s.get('filesize_approx')]
        if sized_streams:
            return max(sized_streams, key=lambda f: f.get('tbr', 0), default=None)
        else:
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
    if best_1080p and best_audio_for_merge:
        video_size = best_1080p.get('filesize') or best_1080p.get('filesize_approx') or 0
        audio_size = best_audio_for_merge.get('filesize') or best_audio_for_merge.get('filesize_approx') or 0
        final_choices.append({
            'label': f"Best Quality Video ({best_1080p.get('resolution')})",
            'format_id': f"{best_1080p['format_id']}+{best_audio_for_merge['format_id']}",
            'filesize': video_size + audio_size,
            'type': 'video'
        })
    if best_720p and best_audio_for_merge:
        video_size = best_720p.get('filesize') or best_720p.get('filesize_approx') or 0
        audio_size = best_audio_for_merge.get('filesize') or best_audio_for_merge.get('filesize_approx') or 0
        final_choices.append({
            'label': f"Good Quality Video ({best_720p.get('resolution')})",
            'format_id': f"{best_720p['format_id']}+{best_audio_for_merge['format_id']}",
            'filesize': video_size + audio_size,
            'type': 'video'
        })
    if best_merged:
        final_choices.append({
            'label': f"Standard Quality Video ({best_merged.get('resolution')}, single file)",
            'format_id': best_merged['format_id'],
            'filesize': best_merged.get('filesize') or best_merged.get('filesize_approx'),
            'type': 'video'
        })

    # --- Find and Add Audio-Only Choices ---
    all_audio_streams = sorted(
        [f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None],
        key=lambda f: f.get('abr', 0),
        reverse=True
    )

    added_audio_labels = set()
    if all_audio_streams:
        # Best Audio
        best_audio = all_audio_streams[0]
        label = f"Best Audio (~{round(best_audio.get('abr', 0))}kbps, MP3)"
        if label not in added_audio_labels:
            final_choices.append({
                'label': label, 'format_id': best_audio['format_id'],
                'filesize': best_audio.get('filesize') or best_audio.get('filesize_approx'), 'type': 'audio'
            })
            added_audio_labels.add(label)

        # Medium Audio (if more than 2 options exist)
        if len(all_audio_streams) > 2:
            medium_audio = all_audio_streams[len(all_audio_streams) // 2]
            label = f"Standard Audio (~{round(medium_audio.get('abr', 0))}kbps, MP3)"
            if label not in added_audio_labels:
                 final_choices.append({
                    'label': label, 'format_id': medium_audio['format_id'],
                    'filesize': medium_audio.get('filesize') or medium_audio.get('filesize_approx'), 'type': 'audio'
                })
                 added_audio_labels.add(label)

        # Low Audio (if more than 1 option exists)
        if len(all_audio_streams) > 1:
            low_audio = all_audio_streams[-1]
            label = f"Low Quality Audio (~{round(low_audio.get('abr', 0))}kbps, MP3)"
            if label not in added_audio_labels:
                final_choices.append({
                    'label': label, 'format_id': low_audio['format_id'],
                    'filesize': low_audio.get('filesize') or low_audio.get('filesize_approx'), 'type': 'audio'
                })
                added_audio_labels.add(label)

    # --- Final Cleanup ---
    unique_choices = []
    seen_labels = set()
    for choice in final_choices:
        if choice['label'] not in seen_labels:
            unique_choices.append(choice)
            seen_labels.add(choice['label'])
    
    return unique_choices

def select_and_download(url, audio_folder, video_folder):
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
    
    exit_option_number = len(choices) + 1
    print(f"{exit_option_number}: Go back (Choose another URL)")
    print("-" * 40)

    while True:
        try:
            user_choice = int(input(f"Enter your choice (1-{exit_option_number}): "))
            if 1 <= user_choice <= len(choices):
                selected = choices[user_choice - 1]
                break
            elif user_choice == exit_option_number:
                print("\nReturning to URL selection...")
                return # Go back to the main loop
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a number.")
            
    # --- Configure Download Options ---
    if selected['type'] == 'audio':
        # Use %(clean_title)s and add the ID as a fallback for a reliable filename
        output_path_template = os.path.join(audio_folder, '%(clean_title)s - [%(id)s].%(ext)s')
    else: # 'video'
        # Use %(clean_title)s and add the ID as a fallback for a reliable filename
        output_path_template = os.path.join(video_folder, '%(clean_title)s - [%(id)s].%(ext)s')

    format_selection = selected['format_id']
    ydl_opts = {
        'format': format_selection,
        'outtmpl': output_path_template,
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
    Main function to run the downloader script in a loop.
    """
    # --- Setup Download Folders on Desktop ---
    try:
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        main_download_folder = os.path.join(desktop_path, 'Universal Audio Video Downloader')
        audio_folder = os.path.join(main_download_folder, 'Audio')
        video_folder = os.path.join(main_download_folder, 'Video')

        os.makedirs(audio_folder, exist_ok=True)
        os.makedirs(video_folder, exist_ok=True)
        print(f"Downloads will be saved to: {main_download_folder}")
    except Exception as e:
        print(f"Error creating download directories on Desktop: {e}")
        print("Downloads will be saved to the current directory instead.")
        # Fallback to current directory if desktop can't be accessed
        audio_folder = 'Audio'
        video_folder = 'Video'
        os.makedirs(audio_folder, exist_ok=True)
        os.makedirs(video_folder, exist_ok=True)
        
    # --- Main Loop ---
    while True:
        print("\n--- Universal Audio/Video Downloader ---")
        print("Supports YouTube, Vimeo, SoundCloud, and many other sites.")
        print("NOTE: Does NOT support DRM-protected services like Spotify or Netflix.\n")
        
        url = input("Please enter the URL of the media (or type 'exit' to quit): ")

        if url.lower() in ['exit', 'quit']:
            print("Exiting downloader. Goodbye!")
            break
            
        if not url:
            print("No URL provided. Please try again.")
            continue
        
        # Sanitize the URL before processing
        sanitized_url = sanitize_youtube_url(url)

        select_and_download(sanitized_url, audio_folder, video_folder)
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    main()
