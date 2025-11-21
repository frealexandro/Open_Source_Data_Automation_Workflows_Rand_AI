import os
import yt_dlp
from moviepy.editor import VideoFileClip, concatenate_videoclips, CompositeVideoClip, vfx, ColorClip, TextClip
from openai import OpenAI
from dotenv import load_dotenv
import json
from googleapiclient.discovery import build
import logging
import re
from pydub import AudioSegment
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from functools import partial
import moviepy.config
import time
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from datetime import datetime
import random

#! Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#! Load environment variables
load_dotenv()

class ContentOptimizer:
    def __init__(self, openai_client=None):
        if openai_client is None:
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OpenAI API key not found")
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = openai_client

    def optimize_transcription_for_social(self, transcription):
        """Generate an optimized short-form title from the transcription."""
        try:
            prompt = f"""Instructions:
            1. Analyze this 30-second technology video transcription.
            2. Generate an eye-catching title with a MAXIMUM of 40 characters.
            3. The title must reflect the main technical topic.
            4. The title must be in English.
            5. Keep the tone professional yet punchy.
            6. Do not include hashtags or emojis.
            7. Preserve technical terms as needed.
            8. Focus on Data Science and programming concepts.
            9. Do NOT add prefixes such as 'Title:' or similar.
            10. Return ONLY the title with no extra text.

            Video transcription:
            {transcription}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an expert in technical content marketing, specialized in transforming transcripts into compelling social titles. Return ONLY the title with no extra text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=50
            )

            title = response.choices[0].message.content.strip()
            
            # Remove any common prefixes GPT might add
            prefixes_to_remove = ["Title:", "Suggested Title:", "Suggestion:", "Proposed Title:"]
            for prefix in prefixes_to_remove:
                if title.startswith(prefix):
                    title = title.replace(prefix, "", 1).strip()
            
            # Keep the title at or under 40 characters
            if len(title) > 40:
                last_space = title[:37].rfind(' ')
                if last_space != -1:
                    title = title[:last_space] + "..."
                else:
                    title = title[:37] + "..."

            return title

        except Exception as e:
            logger.error(f"Error optimizing transcription: {str(e)}")
            # If optimization fails, fall back to the first few words of the transcript
            words = transcription.split()[:6]  # Use the first 6 words
            return " ".join(words)[:37] + "..." if len(" ".join(words)) > 40 else " ".join(words)

    def generate_hashtags(self, description):
        """Generate four relevant hashtags based on the description."""
        try:
            prompt = f"""Instructions:
            1. Generate EXACTLY 4 relevant hashtags.
            2. They must relate to: {description}
            3. Focus on technical terms from Data Science and programming.
            4. Use concise English terms only.
            5. Do NOT include spaces inside hashtags.
            6. Each hashtag must be at MOST 9 characters including '#'.
            7. Format: #tag1 #tag2 #tag3 #tag4

            Example outputs:
            #data #code #dev #ai
            #py #ml #ds #tech

            Description: {description}"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an SEO expert for technical Data Science and programming content. Generate concise short hashtags."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=50
            )

            hashtags = response.choices[0].message.content.strip()
            
            # Process and validate each hashtag
            processed_hashtags = []
            for hashtag in hashtags.split():
                if not hashtag.startswith('#'):
                    hashtag = '#' + hashtag
                # Limit to 9 characters including the '#'
                if len(hashtag) > 9:
                    hashtag = hashtag[:9]
                processed_hashtags.append(hashtag)
            
            # Ensure we have exactly 4 hashtags
            while len(processed_hashtags) < 4:
                processed_hashtags.append('#tech')
            processed_hashtags = processed_hashtags[:4]
            
            return ' '.join(processed_hashtags)

        except Exception as e:
            logger.error(f"Error generating hashtags: {str(e)}")
            return "#ds #dev #py #ai"

class DriveUploader:
    def __init__(self):
        # Drive and Sheet IDs
        self.DRIVE_FOLDER_ID = "1XdlovWoQNRjKN6DpOZVcSL3ThgV-L_XL"
        self.SHEET_ID = "1uLAGRvq0H-2G1RHGdzBJkhMPP6D1iWexp4N8bXDEHgk"
        
        try:
            # Load service-account credentials
            self.credentials = service_account.Credentials.from_service_account_file(
                'river-surf-452722-t6-24c6cdaf896b.json',
                scopes=[
                    'https://www.googleapis.com/auth/drive',
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/youtube'
                ]
            )
            
            # Initialize Google services with the same account
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
            self.youtube = build('youtube', 'v3', credentials=self.credentials)
            
            logger.info("Google services initialized successfully with the service account")
        except Exception as e:
            logger.error(f"Error initializing Google services: {str(e)}")
            raise

    def upload_video_to_drive(self, video_path, max_retries=3):
        """Upload the video to Google Drive using the service account."""
        retry_count = 0
        while retry_count < max_retries:
            try:
                file_metadata = {
                    'name': os.path.basename(video_path),
                    'parents': [self.DRIVE_FOLDER_ID],
                    'mimeType': 'video/mp4'
                }
                
                media = MediaFileUpload(
                    video_path, 
                    mimetype='video/mp4',
                    resumable=True
                )
                
                file = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, webViewLink',
                    supportsAllDrives=True
                ).execute()
                
                # Configure link sharing permissions
                try:
                    self.drive_service.permissions().create(
                        fileId=file.get('id'),
                        body={
                            'type': 'anyone',
                            'role': 'reader'
                        },
                        supportsAllDrives=True
                    ).execute()
                except Exception as perm_error:
                    # Retry if permission configuration fails
                    time.sleep(2)  # Wait 2 seconds before retrying
                    self.drive_service.permissions().create(
                        fileId=file.get('id'),
                        body={
                            'type': 'anyone',
                            'role': 'reader'
                        },
                        supportsAllDrives=True
                    ).execute()
                
                logger.info(f"Video uploaded to Drive: {file.get('webViewLink')}")
                return file.get('webViewLink')
                
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff
                    logger.warning(f"Attempt {retry_count} failed. Waiting {wait_time} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Failed to upload video to Drive after {max_retries} attempts: {str(e)}")
                    raise

    def update_metadata_sheet(self, video_link, optimized_title, hashtags, transcription):
        """Update the Google Sheet using the service account."""
        try:
            # Prepare data for the new row
            row_data = [
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Date
                    video_link,                                     # Link
                    optimized_title,                               # Suggested Title
                    hashtags,                                      # Hashtags
                    transcription[:1000],                          # Original Text
                    "NO"                                           # Approve (default NO)
                ]
            ]
            
            # Fetch the current data range
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.SHEET_ID,
                range='A:F'  # Includes the Approve column
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                # If the sheet is empty, seed headers first
                headers = [["Date", "Link", "Suggested Title", "Hashtags", "Original Text", "Approve"]]
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=self.SHEET_ID,
                    range='A1:F1',
                    valueInputOption='USER_ENTERED',
                    body={'values': headers}
                ).execute()
                next_row = 2
            else:
                # Otherwise append after the last row
                next_row = len(values) + 1
            
            # Update the sheet
            body = {
                'values': row_data
            }
            
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=self.SHEET_ID,
                range=f'A{next_row}:F{next_row}',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
            logger.info(f"Metadata updated in the sheet, row {next_row}")
            
        except Exception as e:
            logger.error(f"Error updating Google Sheet: {str(e)}")
            raise

class YouTubeShortsCreator:
    def __init__(self, num_shorts=10, start_time_minutes=5):
        # Configure OpenAI
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found")
        self.client = OpenAI(api_key=api_key)
        
        # Directory setup
        self.output_dir = 'shorts_output'
        self.temp_dir = 'temp'
        self.audio_dir = 'audio_transcription'
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)
        
        # Processing configuration
        self.max_duration = 30  # Maximum duration in seconds for each short
        self.num_shorts = num_shorts  # Number of shorts to generate
        self.start_time_seconds = start_time_minutes * 60  # Convert minutes to seconds
        
        # API cost configuration
        self.whisper_cost_per_minute = 0.006  # Whisper API cost per minute
        self.gpt35_input_cost_per_1k = 0.0005
        self.gpt35_output_cost_per_1k = 0.0015
        self.estimated_tokens_per_segment = 500
        self.usd_to_cop = 4000
        
        # Cost tracking
        self.real_costs = {
            "whisper_minutes": 0,
            "gpt_input_tokens": 0,
            "gpt_output_tokens": 0
        }
        self.detailed_costs = {
            "whisper_transcriptions": [],
            "gpt_corrections": []
        }
        
        # Audio/video quality configuration
        self.max_workers = multiprocessing.cpu_count()
        self.temp_quality = {
            'audio': {
                'codec': 'mp3'  # Format for Whisper API
            },
            'video': {
                'fps': None,
                'preset': 'medium',
                'threads': self.max_workers,
                'bitrate': None
            }
        }
        
        # Initialize services
        self.drive_uploader = DriveUploader()
        self.content_optimizer = ContentOptimizer(openai_client=self.client)

    def extract_video_id(self, url):
    #!    """Extract the video ID from a YouTube URL."""
        pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:&|\/|$)'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return None

    
    
    def download_video(self, url):
    #!   """Download the video from YouTube."""
        def sanitize_filename(filename):
            # Replace special characters and spaces
            filename = re.sub(r'[^\w\s-]', '', filename)
            filename = re.sub(r'[-\s]+', '_', filename)
            return filename.strip('-_')

        try:
            with yt_dlp.YoutubeDL({'format': 'best'}) as ydl:
                # First get metadata without downloading
                info = ydl.extract_info(url, download=False)
                
                # Sanitize the title for the filename
                safe_title = sanitize_filename(info['title'])
                output_path = os.path.join(self.output_dir, f"{safe_title}.mp4")
                
                # Configure options with the sanitized filename
                ydl_opts = {
                    'format': 'best',
                    'outtmpl': output_path
                }
                
                # Download the video with the new name
                with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                    ydl_download.download([url])
                
                return {
                    'path': output_path,
                    'title': info['title'],
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0)
                }
        except Exception as e:
            logger.error(f"Error downloading the video: {e}")
            raise

    def get_video_transcript(self, video_id):
        #!"""Retrieve the video transcript using the YouTube API."""
        try:
            captions = self.youtube.captions().list(
                part='snippet',
                videoId=video_id
            ).execute()
            
            if 'items' in captions and len(captions['items']) > 0:
                caption_id = captions['items'][0]['id']
                subtitle = self.youtube.captions().download(
                    id=caption_id,
                    tfmt='srt'
                ).execute()
                return subtitle
            return None
        except Exception as e:
            logger.warning(f"Unable to obtain transcript: {e}")
            return None

    
    
    def analyze_video_content(self, video_info):
        """Extract random segments from the video to produce shorts."""
        video = None
        try:
            logger.info("Analyzing video content...")
            logger.info(f"Attempting to open file: {video_info['path']}")
            
            # Ensure the file exists
            if not os.path.exists(video_info['path']):
                logger.error(f"File not found: {video_info['path']}")
                return []
            
            # Load the video
            video = VideoFileClip(video_info['path'])
            
            # Extract the portion of the video we want to analyze
            start_after = self.start_time_seconds
            available_duration = video.duration - start_after - self.max_duration
            
            # Ensure there is enough duration left
            if available_duration < self.max_duration:
                logger.warning(f"The video is not long enough after minute {self.start_time_seconds//60}")
                return []
            
            logger.info(f"Extracting segments starting at second {start_after}...")
            
            # Calculate the number of segments we can extract
            max_possible_segments = int(available_duration // self.max_duration)
            
            if max_possible_segments < self.num_shorts:
                logger.warning(f"Only {max_possible_segments} segments can be extracted from this video")
                num_segments = max_possible_segments
            else:
                num_segments = self.num_shorts
            
            # Generate potential start times
            possible_start_times = []
            current_time = start_after
            
            while current_time + self.max_duration <= video.duration:
                possible_start_times.append(current_time)
                current_time += self.max_duration
            
            # Randomly select start times
            selected_times = random.sample(possible_start_times, min(num_segments, len(possible_start_times)))
            selected_times.sort()  # Sort chronologically
            
            # Build the segment list
            segments = []
            for start_time in selected_times:
                segments.append({
                    "start_time": start_time,
                    "description": f"Segment from {start_time} to {start_time + self.max_duration}",
                    "duration": self.max_duration
                })
            
            if segments:
                logger.info(f"Selected {len(segments)} random segments.")
                return segments
            
            return []
                
        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            return []
        finally:
            if video is not None:
                try:
                    video.close()
                except:
                    pass

    
    def detect_voice_segments(self, audio_path, min_duration=1.0):
        #!"""Detect regions of speech within the audio."""
        try:
            # Load audio
            y, sr = librosa.load(audio_path)
            
            # Calculate audio energy
            energy = librosa.feature.rms(y=y)[0]
            
            # Calculate energy threshold (tunable if needed)
            threshold = np.mean(energy) * 1.5
            
            # Identify segments where energy exceeds the threshold
            voice_segments = []
            is_voice = False
            start_time = 0
            
            frames_to_time = lambda x: float(x) * len(y) / (sr * len(energy))
            
            for i, e in enumerate(energy):
                if not is_voice and e > threshold:
                    start_time = frames_to_time(i)
                    is_voice = True
                elif is_voice and e <= threshold:
                    end_time = frames_to_time(i)
                    if end_time - start_time >= min_duration:
                        voice_segments.append((start_time, end_time))
                    is_voice = False
            
            return voice_segments
        except Exception as e:
            logger.error(f"Error detecting voice segments: {e}")
            return []

    def adjust_segment_to_voice(self, video_path, start_time, end_time):
        #!"""Adjust segment boundaries to align with detected voice."""
        try:
            # Extract segment audio
            video = VideoFileClip(video_path)
            audio = video.audio
            
            # Save audio temporarily
            temp_audio_path = os.path.join(self.temp_dir, "temp_audio.wav")
            audio.write_audiofile(temp_audio_path)
            
            # Detect voice segments
            voice_segments = self.detect_voice_segments(temp_audio_path)
            
            # Find the nearest voice segment to the start
            if voice_segments:
                for vs_start, vs_end in voice_segments:
                    if vs_start >= start_time and vs_start < end_time:
                        start_time = vs_start
                        break
            
            # Clean up
            os.remove(temp_audio_path)
            video.close()
            
            return start_time, end_time
        except Exception as e:
            logger.error(f"Error aligning segment to voice: {e}")
            return start_time, end_time

    
    
    def create_vertical_video(self, clip):
        #!"""Create a vertical video while preserving the original quality."""
        try:
            # Vertical video dimensions
            target_height = 1920
            target_width = 1080
            
            # Calculate the scale factor while preserving aspect ratio
            width_scale = target_width / clip.w
            height_scale = target_height / clip.h
            scale_factor = min(width_scale, height_scale)
            
            # Resize clip while keeping quality
            scaled_clip = clip.resize(width=int(clip.w * scale_factor))
            
            # Create a black background
            background = ColorClip(
                size=(target_width, target_height),
                color=(0, 0, 0),
                duration=clip.duration
            )
            
            # Center the clip
            x_center = (target_width - scaled_clip.w) // 2
            y_center = (target_height - scaled_clip.h) // 2
            
            # Combine clips
            return CompositeVideoClip(
                [background, scaled_clip.set_position((x_center, y_center))],
                size=(target_width, target_height)
            )
            
        except Exception as e:
            logger.error(f"Error creating vertical video: {str(e)}")
            raise

    def track_whisper_usage(self, audio_duration_seconds):
        """Track actual Whisper usage."""
        minutes_used = audio_duration_seconds / 60
        self.real_costs["whisper_minutes"] += minutes_used
        cost_usd = minutes_used * self.whisper_cost_per_minute
        cost_cop = cost_usd * self.usd_to_cop
        
        # Store details for this transcription
        self.detailed_costs["whisper_transcriptions"].append({
            "duration_minutes": minutes_used,
            "cost_usd": cost_usd,
            "cost_cop": cost_cop,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        
        return cost_usd

    def track_gpt_usage(self, response):
        #!"""Track actual token usage for GPT-3.5."""
        if hasattr(response, 'usage'):
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            
            self.real_costs["gpt_input_tokens"] += input_tokens
            self.real_costs["gpt_output_tokens"] += output_tokens
            
            input_cost_usd = (input_tokens / 1000) * self.gpt35_input_cost_per_1k
            output_cost_usd = (output_tokens / 1000) * self.gpt35_output_cost_per_1k
            total_cost_usd = input_cost_usd + output_cost_usd
            
            input_cost_cop = input_cost_usd * self.usd_to_cop
            output_cost_cop = output_cost_usd * self.usd_to_cop
            total_cost_cop = total_cost_usd * self.usd_to_cop
            
            # Store details for this correction
            self.detailed_costs["gpt_corrections"].append({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_cost_usd": input_cost_usd,
                "output_cost_usd": output_cost_usd,
                "total_cost_usd": total_cost_usd,
                "total_cost_cop": total_cost_cop,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            
            logger.info("\nActual GPT-3.5 cost for this request:")
            logger.info(f"  Input tokens: {input_tokens}")
            logger.info(f"  Output tokens: {output_tokens}")
            logger.info(f"  Input cost USD: ${input_cost_usd:.4f}")
            logger.info(f"  Input cost COP: ${input_cost_cop:,.2f}")
            
            return total_cost_usd
        return 0

    def get_total_real_costs(self):
        #!"""Compute total actual costs."""
        whisper_cost_usd = self.real_costs["whisper_minutes"] * self.whisper_cost_per_minute
        gpt_input_cost_usd = (self.real_costs["gpt_input_tokens"] / 1000) * self.gpt35_input_cost_per_1k
        gpt_output_cost_usd = (self.real_costs["gpt_output_tokens"] / 1000) * self.gpt35_output_cost_per_1k
        
        total_cost_usd = whisper_cost_usd + gpt_input_cost_usd + gpt_output_cost_usd
        total_cost_cop = total_cost_usd * self.usd_to_cop
        whisper_cost_cop = whisper_cost_usd * self.usd_to_cop
        gpt_input_cost_cop = gpt_input_cost_usd * self.usd_to_cop
        gpt_output_cost_cop = gpt_output_cost_usd * self.usd_to_cop
        
        return {
            "whisper_cost_usd": round(whisper_cost_usd, 4),
            "whisper_cost_cop": round(whisper_cost_cop, 2),
            "gpt_input_cost_usd": round(gpt_input_cost_usd, 4),
            "gpt_input_cost_cop": round(gpt_input_cost_cop, 2),
            "gpt_output_cost_usd": round(gpt_output_cost_usd, 4),
            "gpt_output_cost_cop": round(gpt_output_cost_cop, 2),
            "total_cost_usd": round(total_cost_usd, 4),
            "total_cost_cop": round(total_cost_cop, 2),
            "total_whisper_minutes": round(self.real_costs["whisper_minutes"], 2),
            "total_gpt_input_tokens": self.real_costs["gpt_input_tokens"],
            "total_gpt_output_tokens": self.real_costs["gpt_output_tokens"]
        }

    def correct_text_with_gpt(self, text):
        """Use GPT-3.5 to correct spelling and grammar in the text."""
        try:
            # Split text into chunks if it is too long
            max_chars_per_chunk = 4000  # Roughly 1k tokens
            if len(text) > max_chars_per_chunk:
                # Split text into sentences
                sentences = text.replace('? ', '?|').replace('! ', '!|').replace('. ', '.|').split('|')
                chunks = []
                current_chunk = []
                current_length = 0
                
                for sentence in sentences:
                    sentence_length = len(sentence)
                    if current_length + sentence_length > max_chars_per_chunk:
                        # Persist the current chunk and start a new one
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [sentence]
                        current_length = sentence_length
                    else:
                        current_chunk.append(sentence)
                        current_length += sentence_length
                
                # Append the last chunk if it exists
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                
                # Correct each chunk separately
                corrected_chunks = []
                for chunk in chunks:
                    try:
                        corrected_chunk = self._correct_text_chunk(chunk)
                        corrected_chunks.append(corrected_chunk)
                    except Exception as e:
                        logger.error(f"Error correcting chunk: {str(e)}")
                        corrected_chunks.append(chunk)  # Keep original text if correction fails
                
                # Merge corrected chunks
                return ' '.join(corrected_chunks)
            else:
                # Correct the text directly if short enough
                return self._correct_text_chunk(text)

        except Exception as e:
            logger.error(f"Error correcting text with GPT-3.5: {str(e)}")
            return text

    def _correct_text_chunk(self, text):
        """Correct a chunk of text using GPT-3.5."""
        prompt = f"""Instructions:
        1. Fix grammar and punctuation mistakes in English.
        2. KEEP every technical term exactly as written, including:
           - Data Science, Data Engineering, Data Warehouse
           - Delta Lake, Business Intelligence, Data Lakehouse, Databricks
           - Machine Learning, Deep Learning, AI
           - Languages: Python, SQL, R, Java, JavaScript
           - Frameworks: TensorFlow, PyTorch, Pandas, NumPy
           - Cloud: AWS, Azure, GCP
           - Big Data: Hadoop, Spark, Kafka
        3. Do NOT add or remove information.
        4. Do NOT add prefixes or extra text.
        5. Maintain the original tone and meaning.

        Text to correct: {text}"""

        response = self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert English proofreader for technical Data Science and programming content."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=4000
        )

        # Track token usage
        self.track_gpt_usage(response)

        # Extract and clean corrected text
        corrected_text = response.choices[0].message.content.strip()
        
        # Remove any prefix the model might add
        prefixes_to_remove = ["Corrected text:", "Text:", "Correction:", "Result:"]
        for prefix in prefixes_to_remove:
            if corrected_text.startswith(prefix):
                corrected_text = corrected_text.replace(prefix, "", 1).strip()

        return corrected_text

    def get_audio_transcription(self, clip):
        """Transcribe the audio, ensuring it matches the video content accurately."""
        try:
            if not clip.audio:
                logger.error("Clip has no audio track")
                return []
            
            temp_dir = os.path.join(self.temp_dir, 'audio_transcription')
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                audio_path = os.path.join(temp_dir, f"audio_{timestamp}.mp3")
                
                # Export audio with high quality
                clip.audio.write_audiofile(
                    audio_path,
                    codec='mp3',
                    bitrate='32k',
                    fps=44100,
                    ffmpeg_params=['-ac', '1'],
                    logger=None,
                    verbose=False
                )
                
                def transcribe_with_size(audio_file, max_retries=3):
                    """Attempt to transcribe the audio, splitting into smaller parts if needed."""
                    if max_retries <= 0:
                        return []
                    
                    try:
                        with open(audio_file, 'rb') if isinstance(audio_file, str) else audio_file as f:
                            response = self.client.audio.transcriptions.create(
                                model="whisper-1",
                                file=f,
                                language="en",
                                response_format="json"
                            )
                        
                        # Track cost only once transcription succeeds
                        self.track_whisper_usage(clip.duration)
                        
                        # Process the simple JSON response
                        if hasattr(response, 'text') and response.text.strip():
                            corrected_text = self.correct_text_with_gpt(response.text)
                            return [{
                                "text": corrected_text,
                                "start": 0,
                                "end": clip.duration,
                                "words": []
                            }]
                        return []
                        
                    except Exception as e:
                        logger.error(f"Transcription error: {str(e)}")
                        if max_retries > 1:
                            # Split the audio into two halves
                            audio = AudioSegment.from_file(audio_file if isinstance(audio_file, str) else audio_file.name)
                            mid_point = len(audio) // 2
                            
                            # Save first half
                            first_half = audio[:mid_point]
                            first_half_path = f"{audio_path}_part1.mp3"
                            first_half.export(first_half_path, format="mp3")
                            
                            # Save second half
                            second_half = audio[mid_point:]
                            second_half_path = f"{audio_path}_part2.mp3"
                            second_half.export(second_half_path, format="mp3")
                            
                            # Transcribe each half recursively
                            first_transcription = transcribe_with_size(first_half_path, max_retries - 1)
                            second_transcription = transcribe_with_size(second_half_path, max_retries - 1)
                            
                            # Remove temporary files
                            try:
                                os.remove(first_half_path)
                                os.remove(second_half_path)
                            except:
                                pass
                            
                            # Combine results
                            return first_transcription + second_transcription
                        return []
                
                # Try to transcribe the entire file first
                transcriptions = transcribe_with_size(audio_path)
                if transcriptions:
                    return transcriptions
                
                return []
                
            finally:
                # Clean up temporary files
                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except:
                        pass
                try:
                    os.rmdir(temp_dir)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"General transcription error: {str(e)}")
            return []

    def create_subtitles(self, clip, segments):
        #!"""Create speech-synced subtitles with subtle visual effects."""
        try:
            subtitle_clips = []
            clip_width = clip.w
            clip_height = clip.h
            
            # Fixed sizing for all subtitles
            fontsize = min(50, int(clip_height * 3.5))
            max_width = int(clip_width * 0.85)
            fixed_height = int(clip_height * 0.15)  # 15% of the video height
            
            for segment in segments:
                start_time = segment["start"]
                end_time = segment["end"]
                text = segment["text"].strip()
                duration = end_time - start_time  # Match the original audio duration
                
                # Split text into shorter sub-segments if necessary
                words = text.split()
                if len(words) > 7:
                    sub_segments = []
                    current_segment = []
                    for word in words:
                        current_segment.append(word)
                        if len(current_segment) >= 4:
                            sub_segments.append(" ".join(current_segment))
                            current_segment = []
                    if current_segment:
                        sub_segments.append(" ".join(current_segment))
                    
                    sub_duration = duration / len(sub_segments)
                    
                    for i, sub_text in enumerate(sub_segments):
                        sub_start = start_time + (i * sub_duration)
                        
                        try:
                            txt_clip = TextClip(
                                sub_text,
                                fontsize=fontsize,
                                color='white',
                                font='Arial',
                                method='label',
                                size=(max_width, fixed_height),
                                stroke_color='white',
                                stroke_width=2.0,
                                bg_color='black'
                            )
                            
                            if txt_clip is None:
                                continue
                            
                            y_position = int(clip_height * 0.70)
                            fade_duration = min(0.15, sub_duration / 4)
                            txt_comp = (txt_clip
                                      .set_position(('center', y_position))
                                      .set_start(sub_start)
                                      .set_duration(sub_duration)
                                      .crossfadein(fade_duration)
                                      .crossfadeout(fade_duration))
                            
                            subtitle_clips.append(txt_comp)
                            
                        except Exception as e:
                            logger.error(f"Error processing subtitle chunk: {str(e)}")
                            continue
                else:
                    try:
                        txt_clip = TextClip(
                            text,
                            fontsize=fontsize,
                            color='white',
                            font='Arial',
                            method='label',
                            size=(max_width, fixed_height),
                            stroke_color='white',
                            stroke_width=2.0,
                            bg_color='black'
                        )
                        
                        if txt_clip is None:
                            continue
                        
                        y_position = int(clip_height * 0.70)
                        fade_duration = min(0.15, duration / 4)
                        txt_comp = (txt_clip
                                  .set_position(('center', y_position))
                                  .set_start(start_time)
                                  .set_duration(duration)
                                  .crossfadein(fade_duration)
                                  .crossfadeout(fade_duration))
                        
                        subtitle_clips.append(txt_comp)
                        
                    except Exception as e:
                        logger.error(f"Error processing subtitle: {str(e)}")
                        continue
            
            return subtitle_clips
            
        except Exception as e:
            logger.error(f"Error creating subtitles: {str(e)}")
            return []

    
    def show_detailed_costs_summary(self):
        #!"""Display a detailed breakdown of all costs."""
        logger.info("\n=== DETAILED COST SUMMARY ===")
        
        # Whisper summary
        total_whisper_minutes = sum(t["duration_minutes"] for t in self.detailed_costs["whisper_transcriptions"])
        total_whisper_usd = sum(t["cost_usd"] for t in self.detailed_costs["whisper_transcriptions"])
        total_whisper_cop = total_whisper_usd * self.usd_to_cop
        
        logger.info("\nWhisper transcriptions:")
        logger.info(f"Total transcriptions: {len(self.detailed_costs['whisper_transcriptions'])}")
        logger.info(f"Total minutes processed: {total_whisper_minutes:.2f}")
        logger.info(f"Total cost USD: ${total_whisper_usd:.4f}")
        logger.info(f"Total cost COP: ${total_whisper_cop:,.2f}")
        
        # GPT-3.5 summary
        total_gpt_input_tokens = sum(c["input_tokens"] for c in self.detailed_costs["gpt_corrections"])
        total_gpt_output_tokens = sum(c["output_tokens"] for c in self.detailed_costs["gpt_corrections"])
        total_gpt_usd = sum(c["total_cost_usd"] for c in self.detailed_costs["gpt_corrections"])
        total_gpt_cop = total_gpt_usd * self.usd_to_cop
        
        logger.info("\nGPT-3.5 corrections:")
        logger.info(f"Total corrections: {len(self.detailed_costs['gpt_corrections'])}")
        logger.info(f"Total input tokens: {total_gpt_input_tokens}")
        logger.info(f"Total output tokens: {total_gpt_output_tokens}")
        logger.info(f"Total cost USD: ${total_gpt_usd:.4f}")
        logger.info(f"Total cost COP: ${total_gpt_cop:,.2f}")
        
        # Grand total
        total_usd = total_whisper_usd + total_gpt_usd
        total_cop = total_usd * self.usd_to_cop
        
        logger.info("\n=== GRAND TOTAL ===")
        logger.info(f"USD: ${total_usd:.4f}")
        logger.info(f"COP: ${total_cop:,.2f}")
        logger.info("============================")

    def process_video(self, url):
        """Process a YouTube video and generate shorts."""
        try:
            logger.info("Starting video processing...")
            video_info = self.download_video(url)
            
            # Calculate and display estimated costs
            video_duration_minutes = video_info['duration'] / 60
            cost_estimate = self.calculate_estimated_cost(video_duration_minutes, self.num_shorts)
            self._show_cost_estimate(cost_estimate)
            
            # Analyze video content
            interesting_segments = self.analyze_video_content(video_info)
            
            if not interesting_segments:
                logger.warning("No segments detected for short creation")
                return []
            
            # Process each segment sequentially
            created_shorts = []
            video = VideoFileClip(video_info['path'])
            
            try:
                for segment in interesting_segments:
                    start_time = int(float(segment["start_time"]))
                    end_time = start_time + self.max_duration
                    
                    if end_time > video.duration:
                        end_time = int(video.duration)
                        start_time = end_time - self.max_duration
                    
                    # Extract clip
                    clip = video.subclip(start_time, end_time)
                    
                    try:
                        # Create vertical version
                        vertical_clip = self.create_vertical_video(clip)
                        
                        # Obtain transcription and create subtitles
                        segments = self.get_audio_transcription(clip)
                        
                        if segments:
                            # Combine all transcribed segments for this clip
                            full_transcription = " ".join([seg["text"] for seg in segments])
                            
                            # Create subtitles
                            subtitle_clips = self.create_subtitles(vertical_clip, segments)
                            if subtitle_clips:
                                vertical_clip = CompositeVideoClip([vertical_clip] + subtitle_clips)
                        
                            # Save the video
                            timestamp = time.strftime("%Y%m%d_%H%M%S")
                            output_path = f"{self.audio_dir}/short_{start_time}_{end_time}_{timestamp}.mp4"
                            logger.info(f"Saving short to {output_path}...")
                            
                            vertical_clip.write_videofile(
                                output_path,
                                codec='libx264',
                                audio_codec='aac',
                                preset=self.temp_quality['video']['preset'],
                                threads=self.temp_quality['video']['threads'],
                                ffmpeg_params=['-pix_fmt', 'yuv420p'],
                                logger=None,
                                verbose=False
                            )
                            
                            # Generate title and hashtags
                            optimized_title = self.content_optimizer.optimize_transcription_for_social(full_transcription)
                            hashtags = self.content_optimizer.generate_hashtags(full_transcription)
                            
                            # Upload to Drive and update the Sheet
                            video_link = self.drive_uploader.upload_video_to_drive(output_path)
                            self.drive_uploader.update_metadata_sheet(
                                video_link,
                                optimized_title,
                                hashtags,
                                full_transcription
                            )
                            
                            created_shorts.append({
                                "path": output_path,
                                "link": video_link,
                                "title": optimized_title,
                                "hashtags": hashtags,
                                "transcription": full_transcription
                            })
                            
                            logger.info(f"Short {len(created_shorts)} procesado y guardado")
                        
                    except Exception as e:
                        logger.error(f"Error al procesar segmento: {e}")
                    finally:
                        try:
                            clip.close()
                        except:
                            pass
                        try:
                            vertical_clip.close()
                        except:
                            pass
            
            finally:
                video.close()
            
            if len(created_shorts) < self.num_shorts:
                logger.warning(f"Requested {self.num_shorts} shorts but only created {len(created_shorts)}")
            
            # Display actual costs and detailed summary
            self._show_real_costs()
            self.show_detailed_costs_summary()
            
            logger.info("Processing completed successfully")
            return created_shorts
            
        except Exception as e:
            logger.error(f"Error during video processing: {e}")
            raise

    def calculate_estimated_cost(self, video_duration_minutes, num_shorts):
        #!"""Calculate the estimated processing cost."""
        try:
            # Approximate exchange rate (1 USD = 4000 COP)
            usd_to_cop = 4000
            
            # Whisper cost (full transcription)
            whisper_cost_usd = video_duration_minutes * self.whisper_cost_per_minute
            whisper_cost_cop = whisper_cost_usd * usd_to_cop
            
            # Estimated GPT-3.5 cost per short
            # Estimate input and output tokens per segment
            total_input_tokens = num_shorts * self.estimated_tokens_per_segment
            total_output_tokens = num_shorts * 100  # Approximate 100 tokens per response
            
            gpt_input_cost_usd = (total_input_tokens / 1000) * self.gpt35_input_cost_per_1k
            gpt_output_cost_usd = (total_output_tokens / 1000) * self.gpt35_output_cost_per_1k
            
            total_cost_usd = whisper_cost_usd + gpt_input_cost_usd + gpt_output_cost_usd
            
            # Convert to COP
            gpt_input_cost_cop = gpt_input_cost_usd * usd_to_cop
            gpt_output_cost_cop = gpt_output_cost_usd * usd_to_cop
            total_cost_cop = total_cost_usd * usd_to_cop
            
            cost_details = {
                "whisper_cost_usd": round(whisper_cost_usd, 4),
                "whisper_cost_cop": round(whisper_cost_cop, 2),
                "gpt_input_cost_usd": round(gpt_input_cost_usd, 4),
                "gpt_input_cost_cop": round(gpt_input_cost_cop, 2),
                "gpt_output_cost_usd": round(gpt_output_cost_usd, 4),
                "gpt_output_cost_cop": round(gpt_output_cost_cop, 2),
                "total_cost_usd": round(total_cost_usd, 4),
                "total_cost_cop": round(total_cost_cop, 2)
            }
            
            return cost_details
            
        except Exception as e:
            logger.error(f"Error calculating costs: {str(e)}")
            return None

    def _show_cost_estimate(self, cost_estimate):
        #!"""Show the estimated costs in a formatted output."""
        if cost_estimate:
            logger.info("\nESTIMATED processing cost:")
            logger.info("----------------------------------------")
            logger.info("Whisper (transcription):")
            logger.info(f"  USD: ${cost_estimate['whisper_cost_usd']}")
            logger.info(f"  COP: ${cost_estimate['whisper_cost_cop']:,.2f}")
            logger.info(f"GPT-3.5 (entrada):")
            logger.info(f"  USD: ${cost_estimate['gpt_input_cost_usd']}")
            logger.info(f"  COP: ${cost_estimate['gpt_input_cost_cop']:,.2f}")
            logger.info("GPT-3.5 (output):")
            logger.info(f"  USD: ${cost_estimate['gpt_output_cost_usd']}")
            logger.info(f"  COP: ${cost_estimate['gpt_output_cost_cop']:,.2f}")
            logger.info("----------------------------------------")
            logger.info("Estimated total:")
            logger.info(f"  USD: ${cost_estimate['total_cost_usd']}")
            logger.info(f"  COP: ${cost_estimate['total_cost_cop']:,.2f}")
            logger.info("----------------------------------------")

    def _show_real_costs(self):
        #!"""Display the actual processing costs."""
        real_costs = self.get_total_real_costs()
        logger.info("\nACTUAL processing costs:")
        logger.info("========================================")
        logger.info("Whisper:")
        logger.info(f"  Minutes processed: {real_costs['total_whisper_minutes']}")
        logger.info(f"  USD: ${real_costs['whisper_cost_usd']}")
        logger.info(f"  COP: ${real_costs['whisper_cost_cop']:,.2f}")
        logger.info("\nGPT-3.5:")
        logger.info(f"  Input tokens: {real_costs['total_gpt_input_tokens']}")
        logger.info(f"  Output tokens: {real_costs['total_gpt_output_tokens']}")
        logger.info(f"  Input cost USD: ${real_costs['gpt_input_cost_usd']}")
        logger.info(f"  Input cost COP: ${real_costs['gpt_input_cost_cop']:,.2f}")
        logger.info(f"  Output cost USD: ${real_costs['gpt_output_cost_usd']}")
        logger.info(f"  Output cost COP: ${real_costs['gpt_output_cost_cop']:,.2f}")
        logger.info("----------------------------------------")
        logger.info("ACTUAL TOTAL:")
        logger.info(f"  USD: ${real_costs['total_cost_usd']}")
        logger.info(f"  COP: ${real_costs['total_cost_cop']:,.2f}")
        logger.info("========================================")


#all: Program entry point
def main():
    # Validate environment variables
    if not os.getenv('OPENAI_API_KEY') or not os.getenv('YOUTUBE_API_KEY'):
        print("Error: OpenAI and YouTube API keys are required.")
        print("Please create a .env file with:")
        print("OPENAI_API_KEY=your_openai_key")
        print("YOUTUBE_API_KEY=your_youtube_key")
        return

    #all: Customizable configuration
    num_shorts = 1  # Number of shorts to generate
    start_time_minutes = 10  # Minute mark to start analyzing the video
    
    # Create the shorts creator instance
    creator = YouTubeShortsCreator(num_shorts=num_shorts, start_time_minutes=start_time_minutes)
    url = "https://www.youtube.com/watch?v=JzoXW7_aoag&t=489s"
    
    try:
        print("\nConfiguration:")
        print(f"- Number of shorts: {num_shorts}")
        print(f"- Start time: {start_time_minutes} minutes")
        print("\nStarting processing...")
        
        shorts = creator.process_video(url)
        print("\nProcess completed!")
        print(f"Generated shorts (starting at minute {start_time_minutes}):")
        for i, short in enumerate(shorts, 1):
            print(f"\nShort {i} of {num_shorts}:")
            print(f"Location: {short['path']}")
            print(f"Transcript: {short['transcription']}")
    except Exception as e:
        print(f"Error during processing: {e}")

if __name__ == "__main__":
    main() 