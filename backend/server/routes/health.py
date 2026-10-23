from fastapi import APIRouter
import logging

# Create router
router = APIRouter(tags=["health"])

logger = logging.getLogger(__name__)

@router.get("/")
async def root():
    """Root endpoint returning API information"""
    logger.debug("Health check requested")
    return {"message": "Helix Orchestrator API", "status": "active"}

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.debug("Health check requested")
    return {"status": "healthy"} 