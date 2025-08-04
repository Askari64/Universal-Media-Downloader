# Universal GUI Downloader
# A graphical user interface for downloading video and audio from various sites.
#
# This script uses the CustomTkinter library for a modern UI and yt-dlp for downloading.
# It is designed to be packaged into a standalone Windows executable.

import customtkinter as ctk
import yt_dlp
import threading
import os
import sys
import webbrowser
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# --- Helper Functions ---

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
    """Sanitizes YouTube URLs to remove tracking parameters."""
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname
    if not (hostname and ('youtube.com' in hostname or 'youtu.be' in hostname)):
        return url
    
    clean_url = ""
    if 'youtube.com' in hostname and parsed_url.path == '/watch':
        query_params = parse_qs(parsed_url.query)
        sanitized_params = {}
        if 'v' in query_params: sanitized_params['v'] = query_params['v'][0]
        if 'list' in query_params: sanitized_params['list'] = query_params['list'][0]
        if sanitized_params:
            clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', urlencode(sanitized_params), ''))
    elif 'youtu.be' in hostname:
        clean_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
    
    return clean_url if clean_url and url != clean_url else url

def get_ffmpeg_path():
    """Determines the path to FFmpeg, whether running as a script or a frozen .exe."""
    if getattr(sys, 'frozen', False):
        # The application is frozen (packaged by PyInstaller)
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    else:
        # The application is running in a normal Python environment.
        # Check if ffmpeg.exe is in the same directory as the script.
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ffmpeg_path = os.path.join(script_dir, 'ffmpeg.exe')
        if os.path.exists(ffmpeg_path):
            return ffmpeg_path
        else:
            # Fallback to assuming ffmpeg is in the system's PATH
            return 'ffmpeg'

# --- Custom Logger for GUI ---
class MyLogger:
    def __init__(self, app):
        self.app = app
    def debug(self, msg):
        # This is for messages that are not about the download progress itself,
        # such as post-processing steps.
        if msg.startswith('[Merger]'):
            self.app.after(0, self.app.update_status, f"Status: Merging video and audio...")
        elif msg.startswith('[ExtractAudio]'):
             self.app.after(0, self.app.update_status, f"Status: Converting to MP3...")
        elif msg.startswith('[VideoRemuxer]'):
             self.app.after(0, self.app.update_status, f"Status: Finalizing video file...")

    def info(self, msg):
        pass # Usually redundant with debug messages
    def warning(self, msg):
        self.app.after(0, self.app.update_status, f"Status: Warning - {msg}")
    def error(self, msg):
        self.app.after(0, self.app.update_status, f"Status: Error - {msg}")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Universal Audio/Video Downloader")
        self.geometry("700x550")
        self.minsize(650, 450) # Set a minimum size for the window
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Widgets ---
        # URL Input Frame
        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="Enter URL here...")
        self.url_entry.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        # Bind the Enter key to the fetch button's command
        self.url_entry.bind("<Return>", lambda event: self.start_fetch_thread())

        self.fetch_button = ctk.CTkButton(self.url_frame, text="Fetch Info", command=self.start_fetch_thread)
        self.fetch_button.grid(row=0, column=1, padx=10, pady=10)

        # Options Frame (for radio buttons)
        self.options_frame = ctk.CTkFrame(self)
        self.options_frame.grid(row=1, column=0, padx=10, pady=0, sticky="ew")
        self.options_frame.grid_columnconfigure(0, weight=1)
        self.options_label = ctk.CTkLabel(self.options_frame, text="Download Options", font=ctk.CTkFont(weight="bold"))
        self.options_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        
        # Scrollable Frame for download choices
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Choices")
        self.scrollable_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.radio_buttons = []
        self.download_choice = ctk.StringVar()

        # Download and Status Frame
        self.download_frame = ctk.CTkFrame(self)
        self.download_frame.grid(row=3, column=0, padx=10, pady=10, sticky="ew")
        self.download_frame.grid_columnconfigure(0, weight=1)
        self.download_frame.grid_columnconfigure(1, weight=1) # Allow attribution to be centered

        self.download_button = ctk.CTkButton(self.download_frame, text="Download", command=self.start_download_thread, state="disabled")
        self.download_button.grid(row=0, column=2, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(self.download_frame, text="Status: Ready")
        self.status_label.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky="w")

        self.progress_bar = ctk.CTkProgressBar(self.download_frame)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=2, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        
        self.path_label = ctk.CTkLabel(self.download_frame, text="", font=ctk.CTkFont(size=10), text_color="gray")
        self.path_label.grid(row=3, column=0, columnspan=3, padx=10, pady=(0, 5), sticky="w")

        # --- Attribution Label ---
        attribution_font = ctk.CTkFont(size=10, underline=True)
        self.attribution_label = ctk.CTkLabel(self.download_frame, text="Made by Askari (github.com/Askari64)", font=attribution_font, text_color="#5699d2", cursor="hand2")
        self.attribution_label.grid(row=4, column=0, columnspan=3, padx=10, pady=(0, 5), sticky="s")
        self.attribution_label.bind("<Button-1>", lambda e: self.open_link("https://github.com/Askari64"))
        
        # --- Setup Download Folders ---
        self.setup_folders()

    def open_link(self, url):
        """Opens the specified URL in a web browser."""
        webbrowser.open_new(url)

    def setup_folders(self):
        """Creates the necessary download folders on the user's desktop."""
        try:
            desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
            self.main_download_folder = os.path.join(desktop_path, 'Universal Audio Video Downloader')
            self.audio_folder = os.path.join(self.main_download_folder, 'Audio')
            self.video_folder = os.path.join(self.main_download_folder, 'Video')
            os.makedirs(self.audio_folder, exist_ok=True)
            os.makedirs(self.video_folder, exist_ok=True)
        except Exception:
            # Fallback to current directory if desktop is not writable
            self.main_download_folder = os.path.abspath(os.getcwd())
            self.audio_folder = 'Audio'
            self.video_folder = 'Video'
            os.makedirs(self.audio_folder, exist_ok=True)
            os.makedirs(self.video_folder, exist_ok=True)
        
        self.path_label.configure(text=f"Downloads will be saved to: {self.main_download_folder}")

    def start_fetch_thread(self):
        """Starts a new thread to fetch video/playlist info without freezing the GUI."""
        self.fetch_button.configure(state="disabled", text="Fetching...")
        self.download_button.configure(state="disabled")
        self.clear_options()
        self.status_label.configure(text="Status: Fetching URL info...")
        url = self.url_entry.get()
        if url:
            thread = threading.Thread(target=self.fetch_info, args=(url,), daemon=True)
            thread.start()

    def fetch_info(self, url):
        """The actual fetching logic that runs in a separate thread."""
        sanitized_url = sanitize_youtube_url(url)
        # Check for playlist first
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(sanitized_url, download=False)
                if 'entries' in info and info.get('playlist_count'):
                    self.after(0, self.display_playlist_options, info, sanitized_url)
                else:
                    # If not a playlist, get detailed info for size calculation
                    with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl_single:
                        single_info = ydl_single.extract_info(sanitized_url, download=False)
                    self.after(0, self.display_quality_options, False, single_info)
        except Exception as e:
            error_message = f"Error: {str(e).splitlines()[-1]}"
            if 'DRM' in str(e):
                error_message = "Error: This content is DRM protected."
            self.after(0, self.update_status, error_message)
            self.after(0, self.enable_fetch_button)

    def display_playlist_options(self, info, url):
        """Displays options for a playlist."""
        self.status_label.configure(text=f"Status: Playlist found with {info['playlist_count']} items.")
        
        options = [
            ("Download Entire Playlist", "playlist"),
            ("Download Single Video Only", "single")
        ]
        
        for text, value in options:
            radio_button = ctk.CTkRadioButton(self.scrollable_frame, text=text, variable=self.download_choice, value=value)
            radio_button.grid(sticky="w", padx=20, pady=5)
            self.radio_buttons.append(radio_button)

        self.download_choice.set("playlist") # Default selection
        self.download_button.configure(state="normal", text="Next", command=lambda: self.handle_playlist_or_single(url))
        self.enable_fetch_button()

    def handle_playlist_or_single(self, url):
        """Decides whether to show playlist quality options or single video options."""
        choice = self.download_choice.get()
        self.clear_options()
        if choice == "playlist":
            self.display_quality_options(True, None) # No info needed for playlist quality
        else:
            # Re-fetch detailed info for the single video to show sizes
            self.fetch_button.configure(state="disabled", text="Fetching...")
            thread = threading.Thread(target=self.fetch_info, args=(url,), daemon=True)
            thread.start()

    def display_quality_options(self, is_playlist, info):
        """Displays a standardized list of quality options."""
        if is_playlist:
            self.status_label.configure(text="Status: Choose a quality for the entire playlist.")
        else:
            self.status_label.configure(text="Status: Choose a quality for the single video.")

        self.download_button.configure(text="Download", command=self.start_download_thread)
        
        # Define the standard set of options
        options_map = {
            "Best Video (1080p)": 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            "Standard Video (720p)": 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            "Low Video (480p)": 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            "Best Audio (MP3)": 'bestaudio/best',
            "Standard Audio (MP3)": 'bestaudio[abr<=128]',
            "Low Audio (MP3)": 'worstaudio/bestaudio[abr<=64]'
        }

        # For single videos, calculate approximate sizes (aligned with CLI logic)
        sizes = [0] * 6 # Default to no size info
        if not is_playlist and info:
            formats = info.get('formats', [])
            
            # --- Robust Size Calculation Logic (aligned with CLI) ---
            best_audio_for_merge = max(
                (f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None),
                key=lambda f: f.get('abr', 0),
                default=None
            )
            best_audio_size = best_audio_for_merge.get('filesize') or best_audio_for_merge.get('filesize_approx') or 0 if best_audio_for_merge else 0

            # Filter video streams with ext=='mp4' (fix to match CLI)
            video_streams = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none' and f.get('ext') == 'mp4' and f.get('tbr') is not None]
            
            def find_best_video(streams, height):
                target_streams = [s for s in streams if s.get('height') == height]
                if not target_streams: return None
                sized_streams = [s for s in target_streams if s.get('filesize') or s.get('filesize_approx')]
                return max(sized_streams or target_streams, key=lambda f: f.get('tbr', 0), default=None)

            best_1080p = find_best_video(video_streams, 1080)
            best_720p = find_best_video(video_streams, 720)
            best_480p = find_best_video(video_streams, 480)

            size_1080 = (best_1080p.get('filesize') or best_1080p.get('filesize_approx') or 0) + best_audio_size if best_1080p else 0
            size_720 = (best_720p.get('filesize') or best_720p.get('filesize_approx') or 0) + best_audio_size if best_720p else 0
            size_480 = (best_480p.get('filesize') or best_480p.get('filesize_approx') or 0) + best_audio_size if best_480p else 0

            # Audio streams (fix to include filesize_approx for all)
            audio_streams = sorted([f for f in formats if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('abr') is not None], key=lambda x: x['abr'], reverse=True)
            std_audio_size = (audio_streams[len(audio_streams)//2].get('filesize') or audio_streams[len(audio_streams)//2].get('filesize_approx') or 0) if len(audio_streams) > 2 else best_audio_size
            low_audio_size = (audio_streams[-1].get('filesize') or audio_streams[-1].get('filesize_approx') or 0) if len(audio_streams) > 1 else best_audio_size

            sizes = [size_1080, size_720, size_480, best_audio_size, std_audio_size, low_audio_size]

        for i, ((text, value), size) in enumerate(zip(options_map.items(), sizes)):
            label = f"{text} (~{format_size(size)})" if not is_playlist and size > 0 else text
            radio_button = ctk.CTkRadioButton(self.scrollable_frame, text=label, variable=self.download_choice, value=value)
            radio_button.grid(row=i, column=0, sticky="w", padx=20, pady=5)
            self.radio_buttons.append(radio_button)
        
        self.download_choice.set(list(options_map.values())[0]) # Default to best video
        self.download_button.configure(state="normal")
        self.enable_fetch_button()

    def start_download_thread(self):
        """Starts the download in a new thread."""
        self.fetch_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.progress_bar.set(0)
        
        url = self.url_entry.get()
        format_selection = self.download_choice.get()
        
        thread = threading.Thread(target=self.download_media, args=(url, format_selection), daemon=True)
        thread.start()

    def download_media(self, url, format_selection):
        """The actual download logic that runs in a thread."""
        is_audio_only = ('bestaudio' in format_selection or 'worstaudio' in format_selection) and '+' not in format_selection
        
        # Re-check if it's a playlist for correct output path
        is_playlist = False
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info and info.get('playlist_count'):
                    is_playlist = True
        except Exception:
            pass # Ignore errors here, main error handling is elsewhere

        output_folder = self.audio_folder if is_audio_only else self.video_folder
        
        if is_playlist:
             output_template = os.path.join(output_folder, '%(playlist)s/%(playlist_index)s - %(clean_title)s [%(id)s].%(ext)s')
        else:
             output_template = os.path.join(output_folder, '%(clean_title)s - [%(id)s].%(ext)s')

        postprocessors = []
        if is_audio_only:
            postprocessors.append({'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'})
        elif '+' in format_selection:
            postprocessors.append({'key': 'FFmpegVideoRemuxer', 'preferedformat': 'mp4'})
            
        ydl_opts = {
            'format': format_selection,
            'outtmpl': output_template,
            'postprocessors': postprocessors,
            'ffmpeg_location': get_ffmpeg_path(),
            'progress_hooks': [self.update_progress],
            'logger': MyLogger(self),
            'ignoreerrors': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            final_message = "Status: Playlist download complete!" if is_playlist else "Status: Download complete!"
            self.after(0, self.update_status, final_message)

        except Exception as e:
            self.after(0, self.update_status, f"Error: {str(e).splitlines()[-1]}")
        finally:
            self.after(0, self.enable_fetch_button)
            self.after(0, self.clear_options)
            self.after(0, lambda: self.status_label.configure(text="Status: Ready"))


    def update_progress(self, d):
        """Hook for yt-dlp to update the GUI's progress bar and status."""
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total_bytes:
                percentage = d['downloaded_bytes'] / total_bytes
                self.progress_bar.set(percentage)

                # Build a more user-friendly status string
                status_str = f"Status: Downloading"
                
                info_dict = d.get('info_dict', {})
                playlist_index = info_dict.get('playlist_index')
                playlist_count = info_dict.get('n_entries')

                if playlist_index and playlist_count:
                    status_str += f" (File {playlist_index}/{playlist_count})"
                
                percent_str = d.get('_percent_str', '').strip()
                total_bytes_str = d.get('_total_bytes_str', '').strip()
                speed_str = d.get('_speed_str', '').strip()
                eta_str = d.get('_eta_str', '').strip()

                status_str += f" | {percent_str} of {total_bytes_str}"
                
                if speed_str:
                    status_str += f" at {speed_str}"
                if eta_str:
                    status_str += f" (ETA: {eta_str})"

                self.status_label.configure(text=status_str)

        elif d['status'] == 'finished':
            self.progress_bar.set(1)
            self.status_label.configure(text="Status: Download complete. Processing...")
        elif d['status'] == 'error':
             self.status_label.configure(text="Status: Error during download.")

    def clear_options(self):
        """Removes all radio buttons from the options frame."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.radio_buttons = []

    def update_status(self, text):
        """Schedules a status label update on the main thread."""
        self.status_label.configure(text=text)

    def enable_fetch_button(self):
        """Schedules enabling the fetch button on the main thread."""
        self.fetch_button.configure(state="normal", text="Fetch Info")

if __name__ == "__main__":
    app = App()
    app.mainloop()
