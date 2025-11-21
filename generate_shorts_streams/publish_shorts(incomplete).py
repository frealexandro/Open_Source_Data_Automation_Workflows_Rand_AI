class ShortsPublisher:
    def __init__(self):
        self.SHEET_ID = "1uLAGRvq0H-2G1RHGdzBJkhMPP6D1iWexp4N8bXDEHgk"
        self.AUDIO_TRANSCRIPTION_DIR = "/home/frealexandro/proyectos_personales/automate_scripts/audio_transcription"
        self.SHORTS_OUTPUT_DIR = "/home/frealexandro/proyectos_personales/automate_scripts/shorts_output"
        
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

    def clean_directories(self):
        """Clean working directories by removing each file."""
        try:
            # Clean transcription directory
            if os.path.exists(self.AUDIO_TRANSCRIPTION_DIR):
                for file in os.listdir(self.AUDIO_TRANSCRIPTION_DIR):
                    file_path = os.path.join(self.AUDIO_TRANSCRIPTION_DIR, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                            logger.info(f"File deleted: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {str(e)}")

            # Clean shorts directory
            if os.path.exists(self.SHORTS_OUTPUT_DIR):
                for file in os.listdir(self.SHORTS_OUTPUT_DIR):
                    file_path = os.path.join(self.SHORTS_OUTPUT_DIR, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                            logger.info(f"File deleted: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting {file_path}: {str(e)}")

            logger.info("Directories cleaned successfully")
        except Exception as e:
            logger.error(f"Error cleaning directories: {str(e)}")

def main():
    try:
        publisher = ShortsPublisher()
        publisher.process_pending_publications()
        
        # Clean directories once finished
        publisher.clean_directories()
        logger.info("Process finished and directories cleaned")
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}")
        # Try to clean directories even if there was an error
        try:
            publisher.clean_directories()
        except:
            pass 