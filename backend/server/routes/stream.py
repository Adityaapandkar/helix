from fastapi import APIRouter, HTTPException, Request, Path
from fastapi.responses import StreamingResponse, Response
import asyncio
import json
import uuid
from typing import Dict, Any, AsyncGenerator, Optional
import os
import time
from pydantic import BaseModel
from fastapi import FastAPI
from contextlib import asynccontextmanager

# Create router
router = APIRouter(tags=["stream"], prefix="/api")

# In-memory storage for active streams
# In production, you might want to use Redis or another shared storage
active_streams: Dict[str, Dict[str, Any]] = {}

# Queue for each stream_id
stream_queues: Dict[str, asyncio.Queue] = {}

# Storage for the most recent file paths
stream_resources: Dict[str, Dict[str, str]] = {}

class StreamEvent(BaseModel):
    """Model for stream events"""
    type: str
    data: Optional[Dict[str, Any]] = None
    value: Optional[float] = None

async def event_generator(request: Request, stream_id: str) -> AsyncGenerator[str, None]:
    """Generate server-sent events"""
    # Create a queue for this stream if it doesn't exist
    if stream_id not in stream_queues:
        raise HTTPException(status_code=404, detail=f"Stream {stream_id} not found")
    
    queue = stream_queues[stream_id]
    
    # Keep track of how many consecutive keep-alive pings we've sent
    consecutive_keep_alives = 0
    last_real_message_time = time.time()
    
    try:
        # Send initial event
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        
        # Continue sending events as long as the client is connected
        while True:
            # Check if the client has disconnected
            if await request.is_disconnected():
                break
                
            # Try to get a message from the queue with a timeout
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                # Reset consecutive keep-alive counter since we got a real message
                consecutive_keep_alives = 0
                last_real_message_time = time.time()
                
                # Send the actual message
                yield f"data: {json.dumps(message)}\n\n"
                queue.task_done()
                
                # If this is the completion message, break the loop
                if message.get('type') == 'complete':
                    break
                    
            except asyncio.TimeoutError:
                # No message received, check how long we've been waiting
                consecutive_keep_alives += 1
                elapsed_time = time.time() - last_real_message_time
                
                # If it's been more than 5 seconds, send a keep-alive with meaningful status
                if consecutive_keep_alives % 5 == 0:
                    # Send a more informative keep-alive every 5 seconds
                    status_message = {
                        "type": "keep_alive",
                        "elapsed_seconds": int(elapsed_time),
                        "status": "Processing continues..."
                    }
                    yield f"data: {json.dumps(status_message)}\n\n"
                else:
                    # Otherwise just send a simple ping comment
                    yield ":\n\n"  # Comment line as a keep-alive
                
                continue
    finally:
        # Clean up when the client disconnects
        if stream_id in active_streams:
            active_streams[stream_id]['connected'] = False

@router.get("/stream/{stream_id}")
async def stream_results(request: Request, stream_id: str = Path(...)):
    """
    Stream analysis results for a given stream_id
    
    This endpoint establishes a server-sent events (SSE) connection
    and streams real-time updates from the orchestration process.
    """
    if stream_id not in active_streams:
        raise HTTPException(status_code=404, detail=f"Stream {stream_id} not found")
    
    # Mark stream as connected
    active_streams[stream_id]['connected'] = True
    
    return StreamingResponse(
        event_generator(request, stream_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "http://localhost:8080",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true"
        }
    )

@router.options("/stream/{stream_id}")
async def options_stream_results(stream_id: str = Path(...)):
    """
    Handle OPTIONS request for CORS preflight for the stream endpoint
    """
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "http://localhost:8080",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600"
        }
    )

@router.get("/pdb/{pdb_type}")
async def get_pdb_file(pdb_type: str, stream_id: Optional[str] = None):
    """
    Get PDB file content
    
    Args:
        pdb_type: Type of PDB file (receptor, ligand, docking)
        stream_id: Optional stream ID to get the latest file for
    """
    # If no stream_id is provided, use the most recent one
    if stream_id is None and active_streams:
        stream_id = next(reversed(active_streams.keys()), None)
    
    if not stream_id or stream_id not in stream_resources:
        raise HTTPException(status_code=404, detail="No PDB resources found")
    
    resources = stream_resources[stream_id]
    
    file_path = None
    if pdb_type == "receptor" and "receptor_path" in resources:
        file_path = resources["receptor_path"]
    elif pdb_type == "ligand" and "ligand_path" in resources:
        file_path = resources["ligand_path"]
    elif pdb_type == "docking" and "docking_path" in resources:
        file_path = resources["docking_path"]
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"{pdb_type} PDB file not found")
    
    try:
        with open(file_path, "r") as f:
            content = f.read()
        
        # Return with CORS headers
        return Response(
            content=content,
            media_type="text/plain",
            headers={
                "Access-Control-Allow-Origin": "http://localhost:8080",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
                "Access-Control-Allow-Credentials": "true"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading PDB file: {str(e)}")

@router.options("/pdb/{pdb_type}")
async def options_pdb_file(pdb_type: str):
    """
    Handle OPTIONS request for CORS preflight for the PDB file endpoint
    """
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "http://localhost:8080",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600"
        }
    )

# Utility function to create a new stream
def create_stream() -> str:
    """Create a new stream and return the stream_id"""
    stream_id = str(uuid.uuid4())
    active_streams[stream_id] = {
        "created_at": time.time(),
        "connected": False,
    }
    stream_queues[stream_id] = asyncio.Queue()
    stream_resources[stream_id] = {}
    return stream_id

# Utility function to send an event to a stream
async def send_to_stream(stream_id: str, event: Dict[str, Any]) -> bool:
    """Send an event to a stream queue"""
    if stream_id not in stream_queues:
        return False
    
    await stream_queues[stream_id].put(event)
    return True

# Utility function to register a resource file
def register_resource(stream_id: str, resource_type: str, file_path: str) -> bool:
    """Register a resource file for a stream"""
    if stream_id not in stream_resources:
        return False
    
    stream_resources[stream_id][resource_type] = file_path
    return True

# Add this function to periodically check for "stalled" streams and send status updates
async def monitor_inactive_streams():
    """Monitor streams that haven't had messages for a while and send status updates"""
    while True:
        await asyncio.sleep(30)  # Check every 30 seconds
        
        current_time = time.time()
        for stream_id, stream_data in list(active_streams.items()):
            # Skip if not connected
            if not stream_data.get('connected', False):
                continue
                
            # Get the queue for this stream
            queue = stream_queues.get(stream_id)
            if not queue:
                continue
                
            # Check last activity time
            last_activity = stream_data.get('last_activity', stream_data.get('created_at', current_time))
            inactive_time = current_time - last_activity
            
            # If inactive for more than 30 seconds, send a status update
            if inactive_time > 30 and inactive_time < 3600:  # Between 30 seconds and 1 hour
                try:
                    # Send a status update
                    await queue.put({
                        "type": "status_update",
                        "message": f"Still processing (inactive for {int(inactive_time)} seconds)",
                        "inactive_time": int(inactive_time)
                    })
                    
                    # Update the last activity time to avoid spamming
                    active_streams[stream_id]['last_activity'] = current_time
                except Exception as e:
                    pass  # Ignore errors

# Update the async context manager to start the monitoring task
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the monitoring task
    task = asyncio.create_task(monitor_inactive_streams())
    
    yield
    
    # Cancel the task when shutting down
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass 