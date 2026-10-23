import os
from typing import Dict, Any, Optional, List, Callable, Awaitable
import logfire
from core.agents.protein_analysis_agent import protein_analysis_agent
from core.agents.binding_site_agent import binding_site_agent
from core.agents.molecule_builder_agent import molecule_builder_agent, log_chain_of_thought
from core.agents.molecule_docking_agent import molecule_docking_agent, DockingParameters, DockingAnalysisResult, MoleculeDockingAgent
from dotenv import load_dotenv
import json
import time
import uuid
import re
import asyncio

# Define a type for the stream callback
StreamCallback = Callable[[Dict[str, Any]], Awaitable[None]]

load_dotenv()

logfire.configure(send_to_logfire=True, scrubbing=False, service_name="helix", token=os.getenv("LOGFIRE_API_KEY"))

# --- Helper Function to Read File Content ---
def read_file_content(file_path: Optional[str]) -> Optional[str]:
    """Safely read the content of a file."""
    if not file_path or not os.path.exists(file_path):
        logfire.warning(f"File not found or path is None: {file_path}")
        return None
    try:
        with open(file_path, 'r') as f:
            return f.read()
    except Exception as e:
        logfire.error(f"Error reading file {file_path}: {str(e)}")
        return None

# --- Logging Functions (Unchanged) ---
def log_molecule_details(molecule_result: Dict[str, Any], iteration: int):
    """Log detailed information about a generated molecule"""
    logfire.info(f"=== Molecule Details (Iteration {iteration + 1}) ===")
    logfire.info(f"SMILES: {molecule_result.smiles}")
    
    properties = molecule_result.properties
    if properties:
        logfire.info("Properties:")
        logfire.info(f"  - Molecular Weight: {properties.molecular_weight:.2f}")
        logfire.info(f"  - LogP: {properties.logp:.2f}")
        logfire.info(f"  - H-Bond Donors: {properties.num_hbd}")
        logfire.info(f"  - H-Bond Acceptors: {properties.num_hba}")
        logfire.info(f"  - TPSA: {properties.tpsa:.2f}")
        logfire.info(f"  - Rotatable Bonds: {properties.rotatable_bonds}")
        logfire.info(f"  - Ring Count: {properties.rings}")
    
    logfire.info(f"Output Files:")
    logfire.info(f"  - Molecule Path: {molecule_result.molecule_path}")
    logfire.info(f"  - Format: {molecule_result.molecule_format}")
    
    description = molecule_result.description
    if description:
        logfire.info(f"Design Rationale: {description}")

def log_docking_details(docking_result: DockingAnalysisResult, iteration: int):
    """Log detailed information about docking results"""
    logfire.info(f"=== Docking Results (Iteration {iteration + 1}) ===")
    logfire.info(f"Binding Affinity: {docking_result.binding_affinity:.2f} kcal/mol")
    
    # Log pose information
    poses = docking_result.top_poses
    if poses:
        logfire.info(f"Top Poses ({len(poses)} found):")
        for i, pose in enumerate(poses[:3], 1):  # Log top 3 poses
            logfire.info(f"  Pose {i}:")
            logfire.info(f"    - Affinity: {pose.binding_affinity:.2f} kcal/mol")
            logfire.info(f"    - RMSD from best: {pose.rmsd_lb:.2f}")
    
    # Log key interactions
    if docking_result.key_interactions:
        logfire.info("Key Interactions:")
        logfire.info(f"  {docking_result.key_interactions}")
    
    # Log recommendations
    if docking_result.recommendations:
        logfire.info("Recommendations:")
        logfire.info(f"  {docking_result.recommendations}")

class Orchestrator:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.is_running = False
        self.output_dir = os.path.join(os.getcwd(), "helix_output")
        os.makedirs(self.output_dir, exist_ok=True)
        self.max_iterations = self.config.get('max_iterations', 10)
        logfire.info("Orchestrator initialized")
        logfire.info(f"Output directory: {self.output_dir}")
        logfire.info(f"Maximum iterations: {self.max_iterations}")
        
    def start(self) -> bool:
        """Start the orchestrator process"""
        if self.is_running:
            logfire.warning("Orchestrator is already running")
            return False

        try:
            logfire.info("Starting orchestrator...")
            self.is_running = True
            return True
        except Exception as e:
            logfire.error(f"Failed to start orchestrator: {str(e)}")
            return False
        
    async def send_progress_update(self, stream_callback, progress_value, operation_name=None):
        """Send a progress update to the stream with an optional operation message"""
        if not stream_callback:
            return
        
        # Send progress update
        await stream_callback({"type": "progress", "value": progress_value})
        
        # If an operation name is provided, send a log message too
        if operation_name:
            await stream_callback({
                "type": "log",
                "data": {
                    "id": str(uuid.uuid4()),
                    "timestamp": time.time(),
                    "agent": "Orchestrator",
                    "message": f"Processing: {operation_name}",
                    "type": "info"
                }
            })
    
    # Add this function to implement periodic progress updates during long operations
    async def run_with_progress_updates(self, coroutine, start_progress, end_progress, 
                                       stream_callback, operation_name, update_interval=1.0):
        """
        Run a coroutine while sending periodic progress updates.
        
        Args:
            coroutine: The coroutine to run
            start_progress: The progress value at the start
            end_progress: The progress value at the end
            stream_callback: The stream callback function
            operation_name: The name of the operation (for logging)
            update_interval: How often to send updates in seconds
        
        Returns:
            The result of the coroutine
        """
        if not stream_callback:
            # If no stream callback, just run the coroutine directly
            return await coroutine
        
        # Send initial progress
        await self.send_progress_update(stream_callback, start_progress, operation_name)
        
        # Create a task for the coroutine
        task = asyncio.create_task(coroutine)
        
        # Set up progress updates
        current_progress = start_progress
        progress_step = (end_progress - start_progress) / 10  # Divide the progress into 10 steps
        
        # Send periodic updates while the task is running
        update_count = 0
        while not task.done():
            # Wait a bit
            await asyncio.sleep(update_interval)
            
            # Update progress (slowly approach end_progress)
            update_count += 1
            if update_count <= 10:  # Limit to 10 updates
                current_progress = min(start_progress + (progress_step * update_count), end_progress - 0.1)
                await self.send_progress_update(stream_callback, current_progress)
        
        # Get the result from the task
        result = await task
        
        # Send final progress
        await self.send_progress_update(stream_callback, end_progress, f"Completed: {operation_name}")
        
        return result

    # --- Helper to send structure data ---
    async def send_structure_data(self, stream_callback: Optional[StreamCallback],
                                event_type: str, file_path: Optional[str]):
        """Reads a file and sends its content via the stream callback."""
        if not stream_callback:
            return

        content = read_file_content(file_path)
        if content:
            logfire.info(f"Sending {event_type} data from {file_path}")
            await stream_callback({
                "type": event_type,
                "data": content
            })
        else:
            logfire.warning(f"Could not read or send {event_type} data from {file_path}")
            await stream_callback({
                "type": "log",
                "data": {
                    "id": str(uuid.uuid4()),
                    "timestamp": time.time(),
                    "agent": "Orchestrator",
                    "message": f"Warning: Could not load structure file for {event_type}",
                    "type": "warning"
                }
            })

    async def process_prompt(self, prompt: str, stream_callback: Optional[StreamCallback] = None) -> Dict[str, Any]:
        """
        Process a user prompt and return the results
        
        Args:
            prompt: The natural language prompt from the user
            stream_callback: Optional callback to send streaming updates
            
        Returns:
            A dictionary containing the processing results
        """
        logfire.info(f"Processing prompt: {prompt}...")
        
        # Generate session ID for this run
        session_id = str(uuid.uuid4())
        
        try:
            # Step 1: Protein Analysis
            logfire.info("=== Starting Protein Analysis ===")
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "analysis",  # Frontend expects this specific agent name
                        "message": "Starting protein analysis",
                        "type": "info"
                    }
                })
                await stream_callback({"type": "progress", "value": 5})
            
            # Run the protein analysis with progress updates
            protein_analysis = await self.run_with_progress_updates(
                protein_analysis_agent.run(prompt),
                5, 20,
                stream_callback,
                "Analyzing protein structure and sequence"
            )
            
            protein_analysis_result = protein_analysis.data
            logfire.info("Protein Analysis Results:")
            logfire.info(f"  - Receptor Path: {protein_analysis_result.prepared_receptor_path}")
            logfire.info(f"  - Structure Type: {protein_analysis_result.structure_type}")
            logfire.info(f"  - Resolution: {protein_analysis_result.resolution} Å")
            
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "analysis",
                        "message": f"Analysis complete: {protein_analysis_result.structure_type}, Resolution: {protein_analysis_result.resolution} Å",
                        "type": "success"
                    }
                })
                
                # Extract information from the XML in the analysis field
                analysis_text = protein_analysis_result.analysis
                
                # Extract protein name
                protein_name_match = re.search(r'<ProteinName>(.*?)</ProteinName>', analysis_text, re.DOTALL)
                protein_name = protein_name_match.group(1).strip() if protein_name_match else "Unknown protein"
                
                # Extract protein ID
                protein_id_match = re.search(r'<ProteinID>(.*?)</ProteinID>', analysis_text, re.DOTALL)
                protein_id = protein_id_match.group(1).strip() if protein_id_match else prompt
                
                # Extract organism
                organism_match = re.search(r'<Organism>(.*?)</Organism>', analysis_text, re.DOTALL)
                organism = organism_match.group(1).strip() if organism_match else "Unknown"
                
                # Extract molecular weight and sequence length from SequenceSummary
                sequence_summary_match = re.search(r'<SequenceSummary>(.*?)</SequenceSummary>', analysis_text, re.DOTALL)
                sequence_summary = sequence_summary_match.group(1).strip() if sequence_summary_match else ""
                
                # Try to extract molecular weight from the summary
                mol_weight_match = re.search(r'molecular weight of (\d+\.?\d*) kDa', sequence_summary)
                mol_weight = mol_weight_match.group(1) if mol_weight_match else "N/A"
                
                # Try to extract length from the summary
                length_match = re.search(r'(\d+)-amino acid protein', sequence_summary)
                length = length_match.group(1) if length_match else "N/A"
                
                await stream_callback({
                    "type": "protein_properties",
                    "data": {
                        "name": protein_name,
                        "uniprotId": protein_id,
                        "length": length,
                        "molecularWeight": f"{mol_weight} kDa" if mol_weight != "N/A" else "N/A",
                        "structureSource": protein_analysis_result.structure_type or "N/A",
                    }
                })

            # Send Receptor PDB Data
            await self.send_structure_data(
                stream_callback,
                "receptor_pdb",
                protein_analysis_result.prepared_receptor_path
            )

            # Step 2: Binding Site Analysis
            logfire.info("=== Starting Binding Site Analysis ===")
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "binding",  # Frontend expects this specific agent name
                        "message": "Starting binding site analysis",
                        "type": "info"
                    }
                })
            
            # Run binding site analysis with progress updates
            binding_site_result = await self.run_with_progress_updates(
                binding_site_agent.run(prompt),
                20, 40,
                stream_callback,
                "Analyzing protein binding sites"
            )
            
            # Access properties directly on the BindingSiteAnalysisResult
            logfire.info("Binding Site Analysis Results:")
            logfire.info(f"  - Center: {binding_site_result.center}")
            logfire.info(f"  - Box Size: {binding_site_result.box_size}")
            logfire.info(f"  - Volume: {binding_site_result.volume:.2f} Å³")
            logfire.info(f"  - Polar Surface Area: {binding_site_result.polar_surface_area:.2f} Å²")
            logfire.info(f"  - Apolar Surface Area: {binding_site_result.apolar_surface_area:.2f} Å²")
            
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "binding",
                        "message": f"Found primary binding site with volume {binding_site_result.volume:.2f} Å³",
                        "type": "success"
                    }
                })
                
                # Send binding sites data
                # Create an array of binding sites for the frontend
                binding_sites = [
                    {
                        "id": 1,
                        "residues": ", ".join(binding_site_result.residues[:5]) + "..." if binding_site_result.residues and len(binding_site_result.residues) > 5 else "N/A",
                        "confidence": 0.85,  # Example value
                        "volume": binding_site_result.volume,
                        "active": True,
                        "warning": None
                    }
                ]
                # Add a secondary site as an example
                if binding_site_result.volume > 0:
                    binding_sites.append({
                        "id": 2,
                        "residues": "GLY234, LEU41, VAL78...",  # Example
                        "confidence": 0.42,
                        "volume": binding_site_result.volume * 0.7,  # Smaller than primary
                        "active": False,
                        "warning": "Small pocket, may not accommodate drug-like molecules"
                    })
                
                await stream_callback({
                    "type": "binding_sites",
                    "data": binding_sites
                })

            # Prepare binding site info for molecule builder
            binding_site_info = {
                "center": binding_site_result.center,
                "size": binding_site_result.box_size,
                "volume": binding_site_result.volume,
                "polar_area": binding_site_result.polar_surface_area,
                "apolar_area": binding_site_result.apolar_surface_area,
                "residues": binding_site_result.residues
            }

            # Step 2.5: Prepare Receptor PDBQT file *once*
            logfire.info("=== Preparing Receptor for Docking (PDBQT format) ===")
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "binding",
                        "message": "Preparing receptor for docking",
                        "type": "info"
                    }
                })
                await stream_callback({"type": "progress", "value": 42})
            
            # Create a background task for receptor preparation with progress updates
            docking_agent_instance = MoleculeDockingAgent() 
            
            # This is potentially a long-running operation
            async def prepare_receptor_task():
                return docking_agent_instance.prepare_receptor(
                    pdb_path=protein_analysis_result.prepared_receptor_path
                )
            
            # Send periodic updates during receptor preparation
            prepared_receptor_pdbqt_path = await self.run_with_progress_updates(
                prepare_receptor_task(),
                42, 50,
                stream_callback,
                "Preparing receptor for docking"
            )
            
            logfire.info(f"Receptor prepared for docking: {prepared_receptor_pdbqt_path}")
            
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "binding",
                        "message": "Receptor prepared for docking",
                        "type": "success"
                    }
                })
                
            # Clean up the temporary agent instance if necessary (depends on __del__ logic)
            del docking_agent_instance

            # Step 3: Iterative Molecule Building and Docking
            logfire.info("=== Starting Iterative Molecule Building and Docking ===")
            iteration = 0
            best_result = None
            best_affinity = float('inf')
            results = []

            while iteration < self.max_iterations:
                logfire.info(f"\n=== Iteration {iteration + 1}/{self.max_iterations} ===")

                try:
                    # Build molecule
                    logfire.info(f"Running molecule builder (Iteration {iteration + 1})...")
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "log",
                            "data": {
                                "id": str(uuid.uuid4()),
                                "timestamp": time.time(),
                                "agent": "molecule",  # Frontend expects this specific agent name
                                "message": f"Building molecule (Iteration {iteration + 1})",
                                "type": "info"
                            }
                        })
                    
                    # Calculate progress range for this iteration's molecule building
                    molecule_progress_start = 50 + (iteration * 50 / self.max_iterations)
                    molecule_progress_end = 50 + ((iteration + 0.5) * 50 / self.max_iterations)
                    
                    # Run molecule builder with progress updates
                    builder_result = await self.run_with_progress_updates(
                        molecule_builder_agent.run({
                            "binding_site_info": binding_site_info,
                            "previous_results": results,
                            "iteration": iteration,
                            "max_iterations": self.max_iterations,
                            "session_id": session_id
                        }),
                        molecule_progress_start,
                        molecule_progress_end,
                        stream_callback,
                        f"Building molecule (iteration {iteration + 1})"
                    )
                    
                    if not builder_result:
                        logfire.warning("Molecule builder returned no result")
                        if stream_callback:
                            await stream_callback({
                                "type": "log",
                                "data": {
                                    "id": str(uuid.uuid4()),
                                    "timestamp": time.time(),
                                    "agent": "molecule",
                                    "message": "Failed to build molecule",
                                    "type": "error"
                                }
                            })
                        break

                    # Log molecule details
                    log_molecule_details(builder_result, iteration)
                    
                    if stream_callback and builder_result.properties:
                        # Send molecule properties to the frontend
                        await stream_callback({
                            "type": "log",
                            "data": {
                                "id": str(uuid.uuid4()),
                                "timestamp": time.time(),
                                "agent": "molecule",
                                "message": f"Molecule built: {builder_result.smiles}...",
                                "type": "success"
                            }
                        })
                        
                        # Send detailed molecule properties
                        await stream_callback({
                            "type": "molecule_properties",
                            "data": {
                                "molecularWeight": f"{builder_result.properties.molecular_weight:.1f}",
                                "logP": f"{builder_result.properties.logp:.2f}",
                                "hBondDonors": builder_result.properties.num_hbd,
                                "hBondAcceptors": builder_result.properties.num_hba,
                                "rotatableBonds": builder_result.properties.rotatable_bonds,
                                "polarSurfaceArea": f"{builder_result.properties.tpsa:.1f}",
                                "heavyAtoms": builder_result.properties.heavy_atoms,
                                "rings": builder_result.properties.rings,
                                "smiles": builder_result.smiles
                            }
                        })

                    # Check termination flag
                    if builder_result.terminate:
                        logfire.info("Molecule builder signaled termination - stopping iterations")
                        logfire.info(f"Termination reason: {builder_result.termination_reason}")
                        
                        if stream_callback:
                            await stream_callback({
                                "type": "log",
                                "data": {
                                    "id": str(uuid.uuid4()),
                                    "timestamp": time.time(),
                                    "agent": "molecule",
                                    "message": f"Optimization complete: {builder_result.termination_reason}",
                                    "type": "info"
                                }
                            })
                        break

                    # Prepare for docking
                    ligand_path = builder_result.molecule_path
                    if not ligand_path:
                        logfire.error("No ligand path in builder result")
                        
                        if stream_callback:
                            await stream_callback({
                                "type": "log",
                                "data": {
                                    "id": str(uuid.uuid4()),
                                    "timestamp": time.time(),
                                    "agent": "molecule",
                                    "message": "Error: No molecule file generated",
                                    "type": "error"
                                }
                            })
                        break

                    # Configure docking parameters
                    docking_params = DockingParameters(
                        receptor_path=prepared_receptor_pdbqt_path,
                        ligand_path=ligand_path,
                        center=binding_site_result.center,
                        box_size=binding_site_result.box_size,
                        exhaustiveness=8,
                        num_modes=9,
                        energy_range=3.0
                    )

                    # Perform docking
                    logfire.info(f"Running molecular docking (Iteration {iteration + 1})...")
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "log",
                            "data": {
                                "id": str(uuid.uuid4()),
                                "timestamp": time.time(),
                                "agent": "docking",  # Frontend expects this specific agent name
                                "message": f"Docking molecule (Iteration {iteration + 1})",
                                "type": "info"
                            }
                        })
                    
                    # Calculate progress range for this iteration's docking
                    docking_progress_start = molecule_progress_end
                    docking_progress_end = 50 + ((iteration + 1) * 50 / self.max_iterations)
                    
                    # Run docking with progress updates
                    docking_result = await self.run_with_progress_updates(
                        molecule_docking_agent.run({
                            "params": docking_params.dict(),
                            "iteration": iteration
                        }),
                        docking_progress_start,
                        docking_progress_end,
                        stream_callback,
                        f"Docking molecule (iteration {iteration + 1})"
                    )

                    if not docking_result:
                        logfire.warning("Docking returned no result")
                        
                        if stream_callback:
                            await stream_callback({
                                "type": "log",
                                "data": {
                                    "id": str(uuid.uuid4()),
                                    "timestamp": time.time(),
                                    "agent": "docking",
                                    "message": "Docking failed",
                                    "type": "error"
                                }
                            })
                        continue

                    # Log docking details
                    log_docking_details(docking_result, iteration)

                    # Process docking results
                    current_affinity = docking_result.binding_affinity
                    results.append({
                        "iteration": iteration,
                        "molecule": builder_result,  # Store the original Pydantic object
                        "docking": docking_result    # Store the original Pydantic object
                    })
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "log",
                            "data": {
                                "id": str(uuid.uuid4()),
                                "timestamp": time.time(),
                                "agent": "docking",
                                "message": f"Docking complete: Affinity = {current_affinity:.2f} kcal/mol",
                                "type": "success"
                            }
                        })
                        
                        # Format docking results for frontend
                        formatted_docking_results = []
                        # Add current result
                        formatted_docking_results.append({
                            "candidate": iteration + 1,
                            "site": 1,  # Assuming primary binding site
                            "affinity": current_affinity
                        })
                        
                        # Add previously found results for comparison
                        for prev_idx, prev_result in enumerate(results[:-1]):
                            if "docking" in prev_result and hasattr(prev_result["docking"], "binding_affinity"):
                                formatted_docking_results.append({
                                    "candidate": prev_idx + 1,
                                    "site": 1,
                                    "affinity": prev_result["docking"].binding_affinity
                                })
                        
                        # Sort by affinity (lowest first)
                        formatted_docking_results.sort(key=lambda x: x["affinity"])
                        
                        await stream_callback({
                            "type": "docking_results",
                            "data": formatted_docking_results
                        })

                    # Update best result
                    if current_affinity < best_affinity:
                        best_affinity = current_affinity
                        # best_result now holds the dict containing the Pydantic objects
                        best_result = results[-1] 
                        logfire.info(f"New best binding affinity: {best_affinity:.2f} kcal/mol")
                        logfire.info("=== Best Result Details ===")
                        # Logging functions expect the Pydantic objects
                        log_molecule_details(best_result["molecule"], iteration)
                        log_docking_details(best_result["docking"], iteration)
                        
                        if stream_callback:
                            await stream_callback({
                                "type": "log",
                                "data": {
                                    "id": str(uuid.uuid4()),
                                    "timestamp": time.time(),
                                    "agent": "docking",
                                    "message": f"New best result: {best_affinity:.2f} kcal/mol",
                                    "type": "success"
                                }
                            })

                except Exception as e:
                    logfire.error(f"Error in iteration {iteration + 1}: {str(e)}")
                    
                    if stream_callback:
                        await stream_callback({
                            "type": "log",
                            "data": {
                                "id": str(uuid.uuid4()),
                                "timestamp": time.time(),
                                "agent": "Orchestrator",
                                "message": f"Error in iteration {iteration + 1}: {str(e)}",
                                "type": "error"
                            }
                        })
                    
                    if iteration == 0:  # If first iteration fails, abort
                        raise

                iteration += 1

            # Set progress to 100% when complete
            if stream_callback:
                await stream_callback({"type": "progress", "value": 100})
                
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "Orchestrator",
                        "message": "Analysis complete",
                        "type": "success"
                    }
                })

            # Log final summary
            logfire.info("\n=== Final Summary ===")
            logfire.info(f"Iterations completed: {iteration}")
            if best_result:
                logfire.info(f"Best binding affinity: {best_affinity:.2f} kcal/mol")
            logfire.info(f"Terminated early: {iteration < self.max_iterations}")

            # Prepare final results dictionary
            final_results = {
                "protein_analysis": protein_analysis_result.dict(),
                "binding_site_analysis": binding_site_result.dict(),
                # Convert results list Pydantic objects to dicts for JSON
                "docking_results": [
                    {
                        "iteration": r["iteration"],
                        "molecule": r["molecule"].dict(),
                        "docking": r["docking"].dict()
                    } for r in results
                ],
                 # Convert best_result Pydantic objects to dicts for JSON if it exists
                "best_result": {
                    "iteration": best_result["iteration"],
                    "molecule": best_result["molecule"].dict(),
                    "docking": best_result["docking"].dict()
                } if best_result else None,
                "iterations_completed": iteration,
                "terminated_early": iteration < self.max_iterations
            }

            # Saving results could take time - add progress updates
            if stream_callback:
                await stream_callback({
                    "type": "log",
                    "data": {
                        "id": str(uuid.uuid4()),
                        "timestamp": time.time(),
                        "agent": "Orchestrator",
                        "message": "Saving results",
                        "type": "info"
                    }
                })
            
            # Save results
            results_file = os.path.join(self.output_dir, f"helix_results_{session_id}.json")
            with open(results_file, 'w') as f:
                json.dump(final_results, f, indent=2)
            logfire.info(f"Results saved to: {results_file}")

            logfire.info("Prompt processing completed successfully")
            return final_results

        except Exception as e:
            logfire.error(f"Error processing prompt: {str(e)}")
            raise
            
