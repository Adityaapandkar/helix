from pydantic import BaseModel
from pydantic_ai import Agent
from typing import List, Optional, Dict, Tuple, Any
from pydantic_ai.models.anthropic import AnthropicModel
import os
import subprocess
import numpy as np
import re
import logfire
from dotenv import load_dotenv

load_dotenv()

model = AnthropicModel(model_name=os.getenv("ANTHROPIC_MODEL_NAME"), api_key=os.getenv("ANTHROPIC_API_KEY"))

logfire.configure(send_to_logfire=True, scrubbing=False, service_name="helix", token=os.getenv("LOGFIRE_API_KEY"))

# Directory where AlphaFold structures are downloaded and fpocket writes its output
PDB_FILES_DIR = os.path.abspath(os.getenv("PDB_FILES_DIR", "pdb_files"))

system_prompt = """
    <BindingSiteAgent>
        You are a binding site agent.
        You are given a protein sequence and a natural language prompt.
        You need to analyze the protein sequence and return the correct AutoDock Vina configuration file.

        The flow of calling the tools is as follows:
        1. Run fpocket on the protein structure using run_fpocket_tool
        2. Analyze the fpocket results using analyze_fpocket_results
        3. Choose an appropriate pocket based on the analysis
        4. Extract coordinates for the chosen pocket using extract_pocket_coords
        5. Generate an AutoDock Vina configuration file using generate_vina_config
        
        <AgentCapabilities>
            You have access to the following tools:
            
            <Tool name="run_fpocket_tool">
                <Description>Runs fpocket in a Docker container to analyze protein binding sites</Description>
                <Input>PDB file name (e.g., "P0DP23.pdb" or just "P0DP23")</Input>
                <Output>Path to the output directory containing fpocket results</Output>
                <WhenToUse>When you need to analyze the binding sites of a protein structure</WhenToUse>
            </Tool>
            
            <Tool name="analyze_fpocket_results">
                <Description>Analyzes fpocket results to identify and rank binding pockets</Description>
                <Input>Path to fpocket output directory (e.g., "pdb_files/P0DP23_out")</Input>
                <Output>Dictionary with pocket rankings and information</Output>
                <WhenToUse>After running fpocket to understand the pocket rankings and properties</WhenToUse>
            </Tool>
            
            <Tool name="extract_pocket_coords">
                <Description>Extracts coordinates from a specific pocket file</Description>
                <Input>Pocket number (e.g., 1 for pocket1_atm.pdb) and fpocket output directory</Input>
                <Output>Center coordinates and dimensions for the pocket</Output>
                <WhenToUse>When you need to calculate binding site dimensions for AutoDock Vina</WhenToUse>
            </Tool>
            
            <Tool name="generate_vina_config">
                <Description>Generates AutoDock Vina configuration file</Description>
                <Input>Pocket center coordinates, pocket dimensions, receptor file, and ligand file</Input>
                <Output>Path to the generated Vina configuration file</Output>
                <WhenToUse>After extracting pocket coordinates to prepare for AutoDock Vina docking</WhenToUse>
            </Tool>
        </AgentCapabilities>
        
        <WorkflowGuide>
            A typical binding site analysis workflow:
            1. Run fpocket on a protein structure using run_fpocket_tool
            2. Analyze the fpocket results using analyze_fpocket_results
            3. Choose an appropriate pocket based on the analysis
            4. Extract coordinates for the chosen pocket using extract_pocket_coords
            5. Generate an AutoDock Vina configuration file using generate_vina_config
        </WorkflowGuide>
    </BindingSiteAgent>
"""

class BindingSiteAnalysisResult(BaseModel):
    """Result type for binding site analysis"""
    protein_id: str
    binding_sites: List[Dict]
    center: List[float]
    box_size: List[float]
    volume: float
    polar_surface_area: float
    apolar_surface_area: float
    residues: List[str]
    vina_config_path: Optional[str] = None
    analysis: str

# Create the agent first
binding_site_agent = Agent(
    system_prompt=system_prompt,
    model=model,
    name="binding_site_agent",
    result_type=BindingSiteAnalysisResult,
    retries=3
)

# Define the tools
@binding_site_agent.tool_plain
async def run_fpocket_tool(pdb_file: str) -> str:
    """
    Run fpocket Docker container with the specified PDB file.
    
    Args:
        pdb_file: Name of the PDB file (with or without .pdb extension)
        
    Returns:
        Path to the output directory with fpocket results
    """
    # Ensure the filename has .pdb extension
    if not pdb_file.endswith('.pdb'):
        pdb_file = f"{pdb_file}.pdb"
    
    # Strip the extension for the output directory name
    pdb_id = pdb_file.replace('.pdb', '')
    
    # Define the Docker command
    docker_cmd = f"docker run -v {PDB_FILES_DIR}:/workdir fpocket/fpocket fpocket -f /workdir/{pdb_file}"
    
    logfire.info(f"Running fpocket for {pdb_file}")
    
    try:
        # Run the Docker command
        result = subprocess.run(
            docker_cmd,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        
        # Log the command output
        logfire.info(f"fpocket output: {result.stdout}")
        
        # Return the path to the output directory
        output_dir = os.path.join(PDB_FILES_DIR, f"{pdb_id}_out")
        return output_dir
    
    except subprocess.CalledProcessError as e:
        logfire.error(f"Error running fpocket: {e.stderr}")
        raise Exception(f"Failed to run fpocket on {pdb_file}: {e.stderr}")

@binding_site_agent.tool_plain
async def analyze_fpocket_results(fpocket_dir: str) -> Dict:
    """
    Read fpocket results info file and analyze the contents.
    
    Args:
        fpocket_dir: Path to fpocket output directory
        
    Returns:
        Dictionary containing analyzed fpocket results
    """
    info_file = os.path.join(fpocket_dir, f"{os.path.basename(fpocket_dir).replace('_out', '')}_info.txt")
    
    logfire.info(f"Reading fpocket results from {info_file}")
    
    if not os.path.exists(info_file):
        raise Exception(f"Fpocket info file not found: {info_file}")
    
    try:
        with open(info_file, 'r') as f:
            content = f.read()
        
        # Parse the content to extract meaningful information
        pockets = []
        current_pocket = {}
        
        for line in content.split('\n'):
            if line.startswith('Pocket'):
                if current_pocket:
                    pockets.append(current_pocket)
                current_pocket = {'id': len(pockets) + 1}
            elif ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower().replace(' ', '_')
                value = value.strip()
                try:
                    # Try to convert to float if possible
                    value = float(value)
                except:
                    pass
                current_pocket[key] = value
        
        if current_pocket:
            pockets.append(current_pocket)
        
        result = {
            'num_pockets': len(pockets),
            'pockets': pockets
        }
        
        return result
    
    except Exception as e:
        logfire.error(f"Error reading fpocket results: {str(e)}")
        raise Exception(f"Failed to read fpocket results: {str(e)}")

@binding_site_agent.tool_plain
async def extract_pocket_coords(pocket_number: int, fpocket_dir: str) -> Dict:
    """
    Extract coordinates from a specific pocket file.
    
    Args:
        pocket_number: Pocket number (e.g., 1 for pocket1_atm.pdb)
        fpocket_dir: Path to fpocket output directory
        
    Returns:
        Dictionary containing center coordinates and dimensions for AutoDock Vina
    """
    pocket_file = os.path.join(fpocket_dir, "pockets", f"pocket{pocket_number}_atm.pdb")
    
    logfire.info(f"Extracting coordinates from {pocket_file}")
    
    if not os.path.exists(pocket_file):
        raise Exception(f"Pocket file not found: {pocket_file}")
    
    try:
        # Parse the PDB file manually since we might not have BioPython installed
        coords = []
        with open(pocket_file, 'r') as f:
            for line in f:
                if line.startswith('ATOM') or line.startswith('HETATM'):
                    # Extract X, Y, Z coordinates from PDB format
                    x = float(line[30:38].strip())
                    y = float(line[38:46].strip())
                    z = float(line[46:54].strip())
                    coords.append([x, y, z])
        
        if not coords:
            raise Exception(f"No atom coordinates found in {pocket_file}")
        
        # Convert to numpy array for calculations
        coords = np.array(coords)
        
        # Calculate center and dimensions
        center = np.mean(coords, axis=0)
        min_coords = np.min(coords, axis=0)
        max_coords = np.max(coords, axis=0)
        size = max_coords - min_coords + 8  # Add 8Å padding
        
        # Format results for AutoDock Vina
        result = {
            "center": [float(center[0]), float(center[1]), float(center[2])],
            "size": [float(size[0]), float(size[1]), float(size[2])],
            "volume": float(np.prod(size)),
            # Calculate surface areas (simplified approximation)
            "polar_surface_area": float(2 * (size[0] * size[1] + size[1] * size[2] + size[0] * size[2])) * 0.3,  # 30% assumed polar
            "apolar_surface_area": float(2 * (size[0] * size[1] + size[1] * size[2] + size[0] * size[2])) * 0.7,  # 70% assumed apolar
            "residues": []  # This would need to be populated from actual residue analysis
        }
        
        return result
    
    except Exception as e:
        logfire.error(f"Error extracting pocket coordinates: {str(e)}")
        raise Exception(f"Failed to extract pocket coordinates: {str(e)}")

@binding_site_agent.tool_plain
async def generate_vina_config(center_x: float, center_y: float, center_z: float, 
                        size_x: float, size_y: float, size_z: float, 
                        receptor_pdb_file: str, ligand_file: str = "ligand.pdbqt",
                        output_dir: str = None) -> str:
    """
    Generate AutoDock Vina configuration file and convert PDB to PDBQT.
    
    Args:
        center_x: X-coordinate of the binding site center
        center_y: Y-coordinate of the binding site center
        center_z: Z-coordinate of the binding site center
        size_x: X-dimension of the search box
        size_y: Y-dimension of the search box
        size_z: Z-dimension of the search box
        receptor_pdb_file: Path to the receptor PDB file (or just filename)
        ligand_file: Path to the ligand PDBQT file (default: ligand.pdbqt)
        output_dir: Directory to save the config file (default: same as receptor)
        
    Returns:
        Path to the generated Vina configuration file
    """
    # Set default pdb files directory
    pdb_files_dir = PDB_FILES_DIR
    
    # If only a filename was provided, look for it in the pdb_files directory
    if os.path.dirname(receptor_pdb_file) == '':
        receptor_pdb_file = os.path.join(pdb_files_dir, receptor_pdb_file)
    
    # Add .pdb extension if missing
    if not receptor_pdb_file.endswith('.pdb'):
        receptor_pdb_file = f"{receptor_pdb_file}.pdb"
    
    # Determine output directory
    if not output_dir:
        output_dir = os.path.dirname(receptor_pdb_file)
        if not output_dir:
            output_dir = pdb_files_dir
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate config file path
    config_path = os.path.join(output_dir, "vina_config.txt")
    
    logfire.info(f"Generating Vina config file at {config_path}")
    
    try:
        # Create configuration content
        config_content = f"""receptor = {os.path.basename(receptor_pdb_file)}
ligand = {os.path.basename(ligand_file)}

center_x = {center_x}
center_y = {center_y}
center_z = {center_z}

size_x = {size_x}
size_y = {size_y}
size_z = {size_z}

exhaustiveness = 8
num_modes = 9
energy_range = 3
"""
        
        # Write the configuration file
        with open(config_path, 'w') as f:
            f.write(config_content)
        
        logfire.info(f"Successfully created Vina configuration file")
        return config_path
    
    except Exception as e:
        logfire.error(f"Error generating Vina configuration: {str(e)}")
        raise Exception(f"Failed to generate Vina configuration: {str(e)}")

async def run_binding_site_analysis(prompt: str) -> BindingSiteAnalysisResult:
    """Run the binding site analysis workflow"""
    try:
        # Run fpocket
        fpocket_dir = await run_fpocket_tool(prompt)
        
        # Analyze results
        fpocket_analysis = await analyze_fpocket_results(fpocket_dir)
        
        # Get the best pocket (assuming first one is best)
        if fpocket_analysis['num_pockets'] > 0:
            best_pocket = fpocket_analysis['pockets'][0]
            pocket_coords = await extract_pocket_coords(best_pocket['id'], fpocket_dir)
            
            # Return the Pydantic model directly
            return BindingSiteAnalysisResult(
                protein_id=os.path.basename(fpocket_dir).replace('_out', ''),
                binding_sites=fpocket_analysis['pockets'],
                center=pocket_coords['center'],
                box_size=pocket_coords['size'],
                volume=pocket_coords['volume'],
                polar_surface_area=pocket_coords['polar_surface_area'],
                apolar_surface_area=pocket_coords['apolar_surface_area'],
                residues=pocket_coords['residues'],
                analysis=f"Found {fpocket_analysis['num_pockets']} potential binding sites. Selected pocket {best_pocket['id']} as the primary binding site.",
                vina_config_path=None  # Optional field
            )
        else:
            raise Exception("No binding pockets found")
            
    except Exception as e:
        logfire.error(f"Error in binding site analysis: {str(e)}")
        raise

# Register the run method
binding_site_agent.run = run_binding_site_analysis

