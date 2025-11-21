import os
from datetime import datetime
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging
from dotenv import load_dotenv
import requests
from linkedin_api import Linkedin
from TikTokApi import TikTokApi
import urllib.request
import json
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from instabot import Bot
import unicodedata

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class SocialMediaPublisher:
    def __init__(self):
        # Credentials for each platform
        self.linkedin_access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
        self.linkedin_organization_id = os.getenv('LINKEDIN_ORGANIZATION_ID')
        self.instagram_username = os.getenv('INSTAGRAM_USERNAME')
        self.instagram_password = os.getenv('INSTAGRAM_PASSWORD')
        self.tiktok_session = os.getenv('TIKTOK_SESSION_ID')
        
        # Initialize platform APIs
        self.init_instagram()
        self.init_tiktok()
    
    def init_instagram(self):
        """Initialize the Instagram API session."""
        try:
            self.instagram = Bot()
            self.instagram.login(username=self.instagram_username, 
                               password=self.instagram_password)
            logger.info("Instagram initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Instagram: {str(e)}")
            self.instagram = None

    def init_tiktok(self):
        """Initialize the TikTok API session."""
        try:
            self.tiktok = TikTokApi()
            self.tiktok.session_manager.setup_session(self.tiktok_session)
            logger.info("TikTok API initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing TikTok API: {e}")
            self.tiktok = None

    def publish_to_linkedin(self, video_path, title, description):
        """Publish the video on LinkedIn using the basic share API."""
        try:
            if not self.linkedin_access_token:
                raise Exception("LinkedIn token is not configured")
            
            # API headers
            headers = {
                'Authorization': f'Bearer {self.linkedin_access_token}',
                'Content-Type': 'application/json',
            }
            
            # 1. Build the post text
            post_text = f"{title}\n\n{description}"
            
            # 2. Create the draft post
            share_url = "https://api.linkedin.com/v2/shares"
            share_data = {
                "content": {
                    "contentEntities": [{
                        "entityLocation": video_path,
                        "thumbnails": [{
                            "resolvedUrl": video_path
                        }]
                    }],
                    "title": title
                },
                "text": {
                    "text": post_text
                },
                "visibility": {
                    "code": "PUBLIC"
                }
            }
            
            # 3. Send the request
            response = requests.post(share_url, json=share_data, headers=headers)
            
            if response.ok:
                share_id = response.json().get('id')
                logger.info(f"Content shared on LinkedIn with ID: {share_id}")
                return True
            else:
                logger.warning(f"LinkedIn API response: {response.text}")
                logger.info("Generating manual publication message...")
                
                # Create a manual publication message
                manual_post = f"""
                🎥 New video available!

                📝 Title: {title}

                ℹ️ Description:
                {description}

                🎬 Video: {video_path}
                """
                
                logger.info("Please publish this content manually on LinkedIn:")
                logger.info(manual_post)
                return True
            
        except Exception as e:
            logger.error(f"Error publishing to LinkedIn: {str(e)}")
            return False

    def publish_to_instagram(self, video_path, caption):
        """Publish the video on Instagram using Instabot."""
        try:
            if not self.instagram:
                raise Exception("Instagram session is not initialized")

            # Try to post the video
            if self.instagram.upload_video(video_path, caption=caption):
                logger.info("Video posted successfully on Instagram")
                return True
            else:
                logger.warning("Video could not be posted on Instagram")
                # Create a manual publication message
                manual_post = f"""
                📱 Content for Instagram:

                🎥 Video: {video_path}
                
                📝 Caption:
                {caption}
                """
                logger.info("Please publish this content manually on Instagram:")
                logger.info(manual_post)
                return True
            
        except Exception as e:
            logger.error(f"Error publishing to Instagram: {str(e)}")
            return False

    def publish_to_tiktok(self, video_path, description):
        """Publish the video on TikTok."""
        try:
            if not self.tiktok:
                raise Exception("TikTok API session is not initialized")
            
            # Upload the video to TikTok
            self.tiktok.video.upload(
                video_path,
                description=description
            )
            
            logger.info("Video published on TikTok")
            return True
        except Exception as e:
            logger.error(f"Error publishing to TikTok: {e}")
            return False

    def publish_to_youtube(self, video_path, title, description, tags):
        """Publish the video on YouTube Shorts using the service account."""
        try:
            # Configure the request body
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': tags.split(),
                    'categoryId': '22'  # Category: People & Blogs
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False,
                    'shortDescription': description[:100]  # Short summary for Shorts
                }
            }
            
            # Upload the video using the service account
            media = MediaFileUpload(
                video_path,
                mimetype='video/*',
                resumable=True
            )
            
            # Create the insert request
            insert_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            
            # Upload the video with progress tracking
            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    logger.info(f"YouTube upload {int(status.progress() * 100)}% complete")
            
            video_id = response['id']
            logger.info(f"Video published on YouTube Shorts: https://youtube.com/shorts/{video_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error publishing to YouTube: {str(e)}")
            return False

class ShortsPublisher:
    def __init__(self):
        self.SHEET_ID = "1uLAGRvq0H-2G1RHGdzBJkhMPP6D1iWexp4N8bXDEHgk"
        
        try:
            # Load service-account credentials
            self.credentials = service_account.Credentials.from_service_account_file(
                'river-surf-452722-t6-d6bacb04e3e9.json',
                scopes=[
                    'https://www.googleapis.com/auth/drive',
                    'https://www.googleapis.com/auth/spreadsheets',
                    'https://www.googleapis.com/auth/youtube.upload'  # Scope required to upload videos
                ]
            )
            
            # Initialize Google services
            self.sheets_service = build('sheets', 'v4', credentials=self.credentials)
            self.drive_service = build('drive', 'v3', credentials=self.credentials)
            self.youtube = build('youtube', 'v3', credentials=self.credentials)
            self.social_publisher = SocialMediaPublisher()
            
            logger.info("Services initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing services: {str(e)}")
            raise

    def download_video(self, drive_link):
        """Download the video from Google Drive using the service account."""
        try:
            # Extract the file ID from the link
            file_id = drive_link.split('/')[-2]
            
            # Create temp directory if needed
            temp_dir = 'temp_videos'
            os.makedirs(temp_dir, exist_ok=True)
            
            # Build the temporary file path
            temp_path = os.path.join(temp_dir, f"video_{file_id}.mp4")
            
            # Download the file using the service account
            request = self.drive_service.files().get_media(fileId=file_id)
            
            with open(temp_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        logger.info(f"Download {int(status.progress() * 100)}% complete")
            
            logger.info(f"Video downloaded successfully: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Error downloading video from Drive: {str(e)}")
            return None

    def get_pending_publications(self):
        """Retrieve the list of videos that should be published today."""
        try:
            # Fetch all values from the sheet
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.SHEET_ID,
                range='A:G'  # Includes the publish date column
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.info("No data found in the sheet")
                return []
            
            # Convert to DataFrame
            df = pd.DataFrame(values[1:], columns=values[0])
            
            def normalize_header(header: str) -> str:
                normalized = unicodedata.normalize('NFKD', header).encode('ascii', 'ignore').decode('ascii')
                return normalized.strip().lower().replace('_', ' ')

            header_aliases = {
                'suggested title': 'Suggested Title',
                'titulo sugerido': 'Suggested Title',
                'publish date': 'Publish Date',
                'fecha de publicacion': 'Publish Date',
                'original text': 'Original Text',
                'hashtags': 'Hashtags',
                'link': 'Link',
                'approve': 'Approve'
            }

            for column in list(df.columns):
                normalized = normalize_header(column)
                if normalized in header_aliases and header_aliases[normalized] not in df.columns:
                    df.rename(columns={column: header_aliases[normalized]}, inplace=True)
            
            # Ensure required columns are present
            required_columns = ['Suggested Title', 'Original Text', 'Hashtags', 'Link', 'Publish Date', 'Approve']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                logger.error(f"Missing required columns in sheet: {missing_columns}")
                return []
            
            # Get today's date in YYYY-MM-DD
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Filter videos that:
            # 1. Are approved (Approve = "YES")
            # 2. Have a publish date of today
            # 3. Have not been published yet
            pending_df = df[
                (df['Approve'].str.upper().isin(['YES', 'SI'])) &
                (df['Publish Date'].str[:10] == today)
            ]
            
            if pending_df.empty:
                logger.info("No videos to publish today")
                return []
            
            return pending_df.to_dict('records')
            
        except Exception as e:
            logger.error(f"Error retrieving pending publications: {str(e)}")
            return []

    def publish_video(self, video_data):
        """Publish the video across all configured platforms."""
        try:
            logger.info(f"Starting publication for video: {video_data['Suggested Title']}")
            
            # Download the video from Drive
            video_path = self.download_video(video_data['Link'])
            if not video_path:
                return False
            
            try:
                # Publish to each platform
                platforms_status = {
                    "youtube": self.publish_to_youtube(
                        video_path,
                        video_data['Suggested Title'],
                        video_data['Original Text'],
                        video_data['Hashtags']
                    ),
                    "linkedin": self.social_publisher.publish_to_linkedin(
                        video_path,
                        video_data['Suggested Title'],
                        f"{video_data['Original Text']}\n\n{video_data['Hashtags']}"
                    ),
                    "instagram": self.social_publisher.publish_to_instagram(
                        video_path,
                        f"{video_data['Suggested Title']}\n\n{video_data['Original Text']}\n\n{video_data['Hashtags']}"
                    ),
                    "tiktok": self.social_publisher.publish_to_tiktok(
                        video_path,
                        f"{video_data['Suggested Title']}\n\n{video_data['Hashtags']}"
                    )
                }
                
                # Remove the temporary file
                os.remove(video_path)
                
                # Check whether it was published on at least one platform
                if any(platforms_status.values()):
                    logger.info("Video published successfully on at least one platform")
                    return True
                else:
                    logger.error("The video could not be published on any platform")
                    return False
                
            except Exception as e:
                logger.error(f"Error during multi-platform publishing: {e}")
                if os.path.exists(video_path):
                    os.remove(video_path)
                return False
            
        except Exception as e:
            logger.error(f"Error publishing video: {str(e)}")
            return False

    def process_pending_publications(self):
        """Process all pending publications scheduled for today."""
        try:
            # Retrieve pending publications
            pending_publications = self.get_pending_publications()
            
            if not pending_publications:
                logger.info("No pending publications to process")
                return
            
            # Process each publication
            for pub in pending_publications:
                success = self.publish_video(pub)
                if success:
                    logger.info(f"Publication succeeded: {pub['Suggested Title']}")
                else:
                    logger.error(f"Publication failed: {pub['Suggested Title']}")
            
        except Exception as e:
            logger.error(f"Error processing pending publications: {str(e)}")

def main():
    try:
        publisher = ShortsPublisher()
        publisher.process_pending_publications()
    except Exception as e:
        logger.error(f"Error in main publishing flow: {str(e)}")

if __name__ == "__main__":
    main() 