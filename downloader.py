# Universal Audio/Video Downloader
# This script allows you to download video or extract audio from a given URL.
# It uses the yt-dlp library, a powerful tool that supports hundreds of websites.
#
# Before running:
# 1. Make sure you have Python installed.
# 2. Install the yt-dlp library by running this command in your terminal:
#    pip install yt-dlp
# 3. It's also highly recommended to have FFmpeg installed for better format
#    conversion and merging. You can download it from ffmpeg.org.

import yt_dlp
import sys

def get_user_choice():
    """
    Asks the user whether they want to download video or audio.
    """
    print("\nWhat would you like to download?")
    print("1: Video (best available quality)")
    print("2: Audio only (MP3 format)")
    
    while True:
        choice = input("Please enter your choice (1 or 2): ")
        if choice in ['1', '2']:
            return choice
        else:
            print("Invalid input. Please enter 1 or 2.")

def get_download_options(choice):
    """
    Returns the appropriate yt-dlp options based on user's choice.
    """
    if choice == '1':
        # Video options:
        # 'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        # This selects the best MP4 video and M4A audio, and merges them.
        # If not available, it falls back to the best single MP4 file, then any best quality file.
        # 'outtmpl': '%(title)s.%(ext)s' saves the file with its title.
        print("\nConfigured for best quality video download.")
        return {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': '%(title)s.%(ext)s',
            'noplaylist': True,
        }
    else:
        # Audio options:
        # 'format': 'bestaudio/best' selects the best quality audio stream.
        # 'postprocessors': specifies actions to take after downloading.
        #   - 'key': 'FFmpegExtractAudio' tells it to extract audio.
        #   - 'preferredcodec': 'mp3' sets the output format to MP3.
        #   - 'preferredquality': '192' sets the bitrate to 192kbps.
        # 'outtmpl': saves the file with its title and .mp3 extension.
        print("\nConfigured for audio-only (MP3) download.")
        return {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '%(title)s.%(ext)s',
            'noplaylist': True,
        }

def download_media(url, ydl_opts):
    """
    Initializes YoutubeDL and starts the download process.
    """
    try:
        # The 'with' statement ensures that resources are managed correctly.
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("\nStarting download... please wait.")
            # The download method takes a list of URLs.
            ydl.download([url])
            print("\nDownload finished successfully!")
    except yt_dlp.utils.DownloadError as e:
        print(f"\nAn error occurred during download: {e}")
        print("Please check the URL and your network connection.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

def main():
    """
    Main function to run the downloader script.
    """
    print("--- Universal Audio/Video Downloader ---")
    
    # Get URL from command line argument or user input
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(f"URL provided: {url}")
    else:
        url = input("Please enter the URL of the media you want to download: ")

    if not url:
        print("No URL provided. Exiting.")
        return

    # Get user's choice and set options
    choice = get_user_choice()
    ydl_opts = get_download_options(choice)

    # Start the download
    download_media(url, ydl_opts)

if __name__ == "__main__":
    main()
