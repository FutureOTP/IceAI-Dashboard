import os
import logging

logger = logging.getLogger(__name__)

class Config:
    # Discord OAuth2 Configuration
    DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
    DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET") 
    DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
    DISCORD_API_BASE = "https://discord.com/api"
    SELLHUB_SECRET = os.getenv("SELLHUB_SECRET", "")
    
    @classmethod
    def validate(cls):
        """Validate required environment variables"""
        required_vars = ["DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_REDIRECT_URI"]
        missing_vars = [var for var in required_vars if not getattr(cls, var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            raise ValueError(f"Missing required environment variables: {missing_vars}")
        
        logger.info("Configuration validated successfully")