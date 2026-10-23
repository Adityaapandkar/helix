from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional
from core.orchestrator import Orchestrator
from core.utils.logger import get_logger
from server.routes.stream import create_stream, send_to_stream, register_resource
import asyncio
from fastapi.responses import JSONResponse

# Create router
router = APIRouter(tags=["prompt"], prefix="/api")

# Get logger
logger = get_logger(__name__)

# Initialize orchestrator
orchestrator = Orchestrator()

class PromptRequest(BaseModel):
    """Request model for prompt processing"""
    prompt: str
    
# Function to run the orchestrator in the background
async def run_orchestration(prompt: str, stream_id: str):
    """Run the orchestration process and send events to the stream"""
    logger.info(f"Starting orchestration for stream {stream_id}")
    
    try:
        # Send initial progress
        await send_to_stream(stream_id, {
            "type": "progress",
            "value": 0
        })
        
        # Send initial log
        await send_to_stream(stream_id, {
            "type": "log",
            "data": {
                "id": stream_id,
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "Orchestrator",
                "message": "Starting analysis...",
                "type": "info"
            }
        })
        
        # Run the orchestrator with a stream callback
        async def stream_callback(event):
            await send_to_stream(stream_id, event)
        
        # Process the prompt with the callback
        result = await orchestrator.process_prompt(prompt, stream_callback)
        
        # Register resources from the result
        if result and 'protein_analysis' in result and 'prepared_receptor_path' in result['protein_analysis']:
            register_resource(stream_id, "receptor_path", result['protein_analysis']['prepared_receptor_path'])
        
        # Register the latest molecule file if available
        if result and 'best_result' in result and result['best_result'] and 'molecule' in result['best_result']:
            molecule_path = result['best_result']['molecule'].get('molecule_path')
            if molecule_path:
                register_resource(stream_id, "ligand_path", molecule_path)
        
        # Register the latest docking result if available
        if result and 'best_result' in result and result['best_result'] and 'docking' in result['best_result']:
            if result['best_result']['docking'].get('top_poses') and len(result['best_result']['docking']['top_poses']) > 0:
                pose_path = result['best_result']['docking']['top_poses'][0].get('pose_path')
                if pose_path:
                    register_resource(stream_id, "docking_path", pose_path)
        
        # Send completion event
        await send_to_stream(stream_id, {
            "type": "complete"
        })
        
        logger.info(f"Orchestration completed for stream {stream_id}")
        
    except Exception as e:
        logger.error(f"Error in orchestration for stream {stream_id}: {str(e)}")
        
        # Send error event
        await send_to_stream(stream_id, {
            "type": "log",
            "data": {
                "id": stream_id,
                "timestamp": asyncio.get_event_loop().time(),
                "agent": "Orchestrator",
                "message": f"Error: {str(e)}",
                "type": "error"
            }
        })
        
        # Send completion event with error
        await send_to_stream(stream_id, {
            "type": "complete"
        })

@router.post("/process")
async def process_prompt(request: PromptRequest, background_tasks: BackgroundTasks):
    """
    Process a user prompt
    
    This endpoint takes a natural language prompt and starts the analysis process
    in the background. It returns a stream_id that can be used to connect to the
    streaming endpoint.
    """
    logger.info(f"Received prompt request: {request.prompt[:50]}...")
    
    try:
        # Ensure orchestrator is running
        if not orchestrator.is_running:
            orchestrator.start()
        
        # Create a new stream
        stream_id = create_stream()
        
        # Start the orchestration process in the background
        background_tasks.add_task(run_orchestration, request.prompt, stream_id)
        
        response_data = {
            "status": "success",
            "result": {
                "stream_id": stream_id
            }
        }
        
        # Return with CORS headers
        return JSONResponse(
            content=response_data,
            headers={
                "Access-Control-Allow-Origin": "http://localhost:8080",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
                "Access-Control-Allow-Credentials": "true"
            }
        )
    except Exception as e:
        logger.error(f"Error processing prompt: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.options("/process")
async def options_process():
    """
    Handle OPTIONS request for CORS preflight
    """
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "http://localhost:8080",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600"
        }
    ) 