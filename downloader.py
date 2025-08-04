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
    Sanitizes YouTube URLs to remove tracking parameters.
    """
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname

    # Only proceed if it's a recognizable YouTube domain
    if not (hostname and ('youtube.com' in hostname or 'youtu.be' in hostname)):
        return url

    clean_url = ""
    # For youtube.com/watch links, keep only the 'v' and 'list' parameters.
    if 'youtube.com' in hostname and parsed_url.path == '/watch':
        query_params = parse_qs(parsed_url.query)
        sanitized_params = {}
        if 'v' in query_params:
            sanitized_params['v'] = query_params['v'][0]
        if 'list' in query_params:
            sanitized_params['list'] = query_params['list'][0]
        
        if sanitized_params:
            sanitized_query = urlencode(sanitized_params, doseq=True)
            clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', sanitized_query, ''))

    # For youtu.be links, the path is the video ID. Remove all query params.
    elif 'youtu.be' in hostname:
        clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))

    if clean_url and url != clean_url:
        print(f"Sanitizing URL to: {clean_url}")
        return clean_url
    
    return url

def get_smart_choices(url):
    """
    Fetches format information for a SINGLE video and selects the best options.
    """
    # 'noplaylist': True ensures we only get info for the single video
    ydl_opts = {'quiet': True, 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Fetching available formats for the single video, please wait...")
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        if 'DRM' in str(e):
            print("\nError: This content is protected by DRM and cannot be downloaded.")
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
        target_streams = [s for s in streams if s.get('height') == height]
        if not target_streams: return None
        sized_streams = [s for s in target_streams if s.get('filesize') or s.get('filesize_approx')]
        return max(sized_streams or target_streams, key=lambda f: f.get('tbr', 0), default=None)

    best_1080p = find_best_video(video_streams, 1080)
    best_720p = find_best_video(video_streams, 720)
    best_merged = max((f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') != 'none'), key=lambda f: f.get('height', 0), default=None)

    # --- Build the Choices Menu ---
    final_choices = []
    if best_1080p and best_audio_for_merge:
        video_size = best_1080p.get('filesize') or best_1080p.get('filesize_approx') or 0
        audio_size = best_audio_for_merge.get('filesize') or best_audio_for_merge.get('filesize_approx') or 0
        final_choices.append({'label': f"Best Quality Video ({best_1080p.get('resolution')})", 'format_id': f"{best_1080p['format_id']}+{best_audio_for_merge['format_id']}", 'filesize': video_size + audio_size, 'type': 'video'})
    if best_720p and best_audio_for_merge:
        video_size = best_720p.get('filesize') or best_720p.get('filesize_approx') or 0
        audio_size = best_audio_for_merge.get('filesize') or best_audio_for_merge.get('filesize_approx') or 0
        final_choices.append({'label': f"Good Quality Video ({best_720p.get('resolution')})", 'format_id': f"{best_720p['format_id']}+{best_audio_for_merge['format_id']}", 'filesize': video_size + audio_size, 'type': 'video'})
    if best_merged:
        final_choices.append({'label': f"Standard Quality Video ({best_merged.get('resolution')}, single file)", 'format_id': best_merged['format_id'], 'filesize': best_merged.get('filesize') or best_merged.get('filesize_approx'), 'type': 'video'})

    # --- Find and Add Audio-Only Choices ---
    all_audio_streams = sorted([f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None], key=lambda f: f.get('abr', 0), reverse=True)
    added_audio_labels = set()
    if all_audio_streams:
        audio_options_to_add = [all_audio_streams[0]] # Best
        if len(all_audio_streams) > 2: audio_options_to_add.append(all_audio_streams[len(all_audio_streams) // 2]) # Medium
        if len(all_audio_streams) > 1: audio_options_to_add.append(all_audio_streams[-1]) # Low
        
        for audio in audio_options_to_add:
            label = f"Audio (~{round(audio.get('abr', 0))}kbps, MP3)"
            if label not in added_audio_labels:
                final_choices.append({'label': label, 'format_id': audio['format_id'], 'filesize': audio.get('filesize') or audio.get('filesize_approx'), 'type': 'audio'})
                added_audio_labels.add(label)

    unique_choices = [dict(t) for t in {tuple(d.items()) for d in final_choices}]
    return sorted(unique_choices, key=lambda x: x.get('filesize', 0), reverse=True)

def handle_single_download(url, audio_folder, video_folder):
    """
    Presents a detailed menu for a single video and handles the download.
    """
    choices = get_smart_choices(url)
    if not choices: return

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
                return
            else:
                print("Invalid choice.")
        except ValueError:
            print("Please enter a number.")
            
    # --- Configure Download Options ---
    output_path_template = os.path.join(audio_folder if selected['type'] == 'audio' else video_folder, '%(clean_title)s - [%(id)s].%(ext)s')
    ydl_opts = {'format': selected['format_id'], 'outtmpl': output_path_template, 'noplaylist': True}

    if selected['type'] == 'audio':
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
    elif '+' in selected['format_id']:
         ydl_opts['postprocessors'] = [{'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'}]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("\nStarting download... please wait.")
            ydl.download([url])
            print("\nDownload finished successfully!")
    except Exception as e:
        print(f"\nAn unexpected error occurred during download: {e}")

def handle_playlist_download(url, audio_folder, video_folder):
    """
    Handles the download process for an entire playlist.
    """
    print("\n--- Choose a Quality for the ENTIRE Playlist ---")
    print("1: Best Quality Video (up to 1080p)")
    print("2: Good Quality Video (up to 720p)")
    print("3: Standard Quality Video (up to 480p)")
    print("4: Best Quality Audio (MP3)")
    print("5: Standard Quality Audio (MP3)")
    print("6: Low Quality Audio (MP3)")
    print("7: Go back")
    
    while True:
        try:
            choice = int(input("Enter your choice (1-7): "))
            if 1 <= choice <= 7: break
            else: print("Invalid choice.")
        except ValueError: print("Please enter a number.")
            
    if choice == 7:
        print("\nReturning to URL selection...")
        return

    postprocessors = []
    output_folder = video_folder # Default to video
    
    if choice == 1:
        format_selection = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        postprocessors.append({'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
    elif choice == 2:
        format_selection = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        postprocessors.append({'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
    elif choice == 3:
        format_selection = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        postprocessors.append({'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
    elif choice == 4: # Best Audio
        format_selection = 'bestaudio/best'
        output_folder = audio_folder
        postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
    elif choice == 5: # Standard Audio
        format_selection = 'bestaudio[abr<=128]'
        output_folder = audio_folder
        postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'})
    elif choice == 6: # Low Audio
        format_selection = 'worstaudio/bestaudio[abr<=64]'
        output_folder = audio_folder
        postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '96'})

    output_path_template = os.path.join(output_folder, '%(playlist)s/%(playlist_index)s - %(clean_title)s - [%(id)s].%(ext)s')
    ydl_opts = {'format': format_selection, 'outtmpl': output_path_template, 'postprocessors': postprocessors, 'ignoreerrors': True}

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("\nStarting playlist download... this may take a while.")
            ydl.download([url])
            print("\nPlaylist download finished!")
    except Exception as e:
        print(f"\nAn unexpected error occurred during playlist download: {e}")

def process_url(url, audio_folder, video_folder):
    """
    Checks if a URL is a playlist and dispatches to the correct handler.
    """
    sanitized_url = sanitize_youtube_url(url)
    
    ydl_opts = {'quiet': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(sanitized_url, download=False)
            
        if 'entries' in info and info.get('playlist_count'):
            print(f"\nThis URL contains a playlist with {info['playlist_count']} videos.")
            print("1: Download the entire playlist")
            print("2: Download only the single video from the URL")
            print("3: Go back")
            
            while True:
                choice = input("Enter your choice (1-3): ")
                if choice == '1':
                    handle_playlist_download(sanitized_url, audio_folder, video_folder)
                    break
                elif choice == '2':
                    handle_single_download(sanitized_url, audio_folder, video_folder)
                    break
                elif choice == '3':
                    break
                else:
                    print("Invalid choice.")
        else:
            handle_single_download(sanitized_url, audio_folder, video_folder)

    except Exception as e:
        if 'DRM' in str(e):
            print("\nError: This content is protected by DRM.")
        else:
            print(f"\nAn error occurred while checking the URL: {e}")

def main():
    """
    Main function to run the downloader script in a loop.
    """
    try:
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        main_download_folder = os.path.join(desktop_path, 'Universal Audio Video Downloader')
        audio_folder = os.path.join(main_download_folder, 'Audio')
        video_folder = os.path.join(main_download_folder, 'Video')
        os.makedirs(audio_folder, exist_ok=True)
        os.makedirs(video_folder, exist_ok=True)
        print(f"Downloads will be saved to: {main_download_folder}")
    except Exception as e:
        print(f"Error creating download directories: {e}. Using current directory.")
        audio_folder, video_folder = 'Audio', 'Video'
        os.makedirs(audio_folder, exist_ok=True)
        os.makedirs(video_folder, exist_ok=True)
        
    # --- Main Loop ---
    try:
        while True:
            print("\n--- Universal Audio/Video Downloader ---")
            print("Supports YouTube, Vimeo, SoundCloud, etc. Does NOT support DRM sites like Spotify.")
            url = input("Please enter the URL (or type 'exit' to quit): ")

            if url.lower() in ['exit', 'quit']:
                print("Exiting. Goodbye!")
                break
            if not url:
                print("No URL provided.")
                continue
            
            process_url(url, audio_folder, video_folder)
            print("\n" + "="*50 + "\n")
    except KeyboardInterrupt:
        print("\n\nExiting downloader. Goodbye!")
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)


if __name__ == "__main__":
    main()
