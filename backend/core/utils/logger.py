import logging
import logfire
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logfire with default settings
logfire.configure(send_to_logfire=True, scrubbing=False, service_name="helix", token=os.getenv("LOGFIRE_API_KEY"))
logging.basicConfig(handlers=[logfire.LogfireLoggingHandler()])

# Create a default logger
default_logger = logging.getLogger("helix")

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger configured with logfire.
    
    Args:
        name: Optional name for the logger. If not provided, returns the default logger.
        
    Returns:
        A configured logger instance
    """
    if name is None:
        return default_logger
    
    return logging.getLogger(name)