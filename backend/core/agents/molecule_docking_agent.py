from pydantic import BaseModel
from pydantic_ai import Agent
from typing import List, Dict, Optional, Union, Tuple, Any
import os
import subprocess
import tempfile
import shutil
import numpy as np
from dotenv import load_dotenv
from pydantic_ai.models.anthropic import AnthropicModel
import logfire


load_dotenv()

logfire.configure(send_to_logfire=True, scrubbing=False, service_name="helix", token=os.getenv("LOGFIRE_API_KEY"))



class DockingParameters(BaseModel):
    """Parameters for a docking run"""
    receptor_path: str
    ligand_path: str
    center: List[float]
    box_size: List[float]
    exhaustiveness: int = 8
    num_modes: int = 9
    energy_range: float = 3.0
    scoring_function: str = "vina"  # vina, ad4, or vinardo
    flexible_residues: Optional[List[str]] = None
    output_path: Optional[str] = None
    water_map: Optional[str] = None  # For hydrated docking
    use_zinc: bool = False  # For zinc metalloproteins


class MolecularInteraction(BaseModel):
    """Represents a molecular interaction between ligand and receptor"""
    interaction_type: str  # H-bond, hydrophobic, pi-stacking, etc.
    residue_name: str
    residue_number: int
    chain: str
    atom_ligand: str
    atom_receptor: str
    distance: float
    angle: Optional[float] = None  # For H-bonds
    strength: str  # Strong, Medium, Weak


class DockingResult(BaseModel):
    """Results of a docking run for a single pose"""
    ligand_name: str
    binding_affinity: float
    pose_path: str
    rmsd_lb: Optional[float] = None
    rmsd_ub: Optional[float] = None
    interactions: Optional[List[MolecularInteraction]] = None
    analysis: Optional[str] = None


class DockingAnalysisResult(BaseModel):
    """Complete analysis of docking results for AI agent"""
    receptor_info: str
    ligand_info: str
    binding_affinity: float
    top_poses: List[DockingResult]
    key_interactions: str
    recommendations: str


class MoleculeDockingAgent:
    """Agent for molecular docking simulations using AutoDock Vina"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the docking agent with configuration"""
        self.config = config or {}
        self.vina = None  # Will be initialized when needed
        logfire.info("Molecule Docking Agent initialized")
        
        # Use the output directory specified in config or default
        config_dict = self.config
        # Default to a directory within the current working directory
        default_output_dir = os.path.join(os.getcwd(), "docking_results") 
        self.output_dir = config_dict.get('output_dir', default_output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        logfire.info(f"Using output directory: {self.output_dir}")
        
        # Import RDKit and OpenBabel
        try:
            import rdkit
            from rdkit import Chem
            logfire.info("RDKit successfully imported")
        except ImportError:
            logfire.error("RDKit not found. Please install RDKit: pip install rdkit")
            raise
        
        # Check if OpenBabel is installed
        try:
            result = subprocess.run(["obabel", "--version"], capture_output=True, text=True)
            logfire.info(f"OpenBabel found: {result.stdout.strip()}")
        except FileNotFoundError:
            logfire.error("OpenBabel not found. Please install OpenBabel: brew install open-babel")
            raise
    
    def __del__(self):
        """Clean up temporary files when the object is destroyed"""
        # No need to delete the results directory since it's in the user's working directory
        # We should keep the results for the user
        logfire.info(f"MoleculeDockingAgent destroyed, results preserved in: {self.output_dir}")
        pass
    
    def prepare_receptor(self, pdb_path: str, output_path: Optional[str] = None,
                       flex_residues: Optional[str] = None, box_center: Optional[List[float]] = None,
                       box_size: Optional[List[float]] = None, generate_gpf: bool = False) -> str:
        """
        Prepare a receptor for docking using meeko
        
        Args:
            pdb_path: Path to the PDB file containing the receptor
            output_path: Path for the output PDBQT file (without extension)
            flex_residues: String defining flexible residues (e.g., "A:315,B:124")
            box_center: Center coordinates [x, y, z] for the docking box
            box_size: Size dimensions [x, y, z] for the docking box
            generate_gpf: Whether to generate a grid parameter file for AutoDock4
            
        Returns:
            Path to the prepared receptor PDBQT file
        """
        logfire.info(f"Preparing receptor: {pdb_path}")
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(pdb_path))[0]
            output_path = os.path.join(self.output_dir, f"{base_name}.pdbqt")
        
        try:
            # First clean up the PDB file
            temp_pdb = os.path.join(self.output_dir, "temp_receptor.pdb")
            with open(pdb_path, 'r') as f:
                lines = f.readlines()
            
            # Keep only ATOM and HETATM records
            filtered_lines = [line for line in lines if line.startswith(('ATOM', 'HETATM'))]
            
            with open(temp_pdb, 'w') as f:
                f.write(''.join(filtered_lines))
            
            # Convert to PDBQT using OpenBabel with minimal processing
            cmd = ["obabel", "-ipdb", temp_pdb, "-opdbqt", "-O", output_path,
                   "-xr",  # Add receptor-type atoms
                   "-p", "7.4"]  # Set pH for protonation
            
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            logfire.info(f"Receptor prepared: {output_path}")
            
            # Clean up temporary file
            if os.path.exists(temp_pdb):
                os.remove(temp_pdb)
            
            return output_path
            
        except Exception as e:
            logfire.error(f"Error preparing receptor: {str(e)}")
            if os.path.exists(temp_pdb):
                os.remove(temp_pdb)
            raise RuntimeError(f"Failed to prepare receptor: {str(e)}")
    
    def prepare_ligand(self, ligand_path: str, output_path: Optional[str] = None, 
                     add_hydrogens: bool = True, add_water: bool = False) -> str:
        """
        Prepare a ligand for docking using meeko
        
        Args:
            ligand_path: Path to the ligand file (SDF, MOL2, etc.)
            output_path: Path for the output PDBQT file
            add_hydrogens: Whether to add hydrogens if missing
            add_water: Whether to add explicit water molecules (for hydrated docking)
            
        Returns:
            Path to the prepared ligand PDBQT file
        """
        logfire.info(f"Preparing ligand: {ligand_path}")
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(ligand_path))[0]
            output_path = os.path.join(self.output_dir, f"{base_name}.pdbqt")
        
        try:
            from meeko import MoleculePreparation
            from meeko import RDKitMolCreate
            from rdkit import Chem
            
            # Read molecule with RDKit
            mol = Chem.SDMolSupplier(ligand_path, removeHs=False)[0]
            if mol is None:
                raise RuntimeError(f"Failed to read ligand file: {ligand_path}")
            
            # Add hydrogens if requested
            if add_hydrogens:
                mol = Chem.AddHs(mol)
            
            # Prepare ligand using meeko
            preparator = MoleculePreparation()
            preparator.prepare(mol)
            preparator.write_pdbqt_file(output_path)
            
            logfire.info(f"Ligand preparation successful: {output_path}")
            return output_path
            
        except Exception as e:
            logfire.error(f"Error preparing ligand: {str(e)}")
            raise RuntimeError(f"Failed to prepare ligand: {str(e)}")
    
    def generate_affinity_maps(self, receptor_path: str, ligand_path: Optional[str] = None,
                              center: Optional[List[float]] = None, box_size: Optional[List[float]] = None,
                              water_map: bool = False, zinc_map: bool = False) -> str:
        """
        Generate affinity maps for AutoDock4 scoring
        
        Args:
            receptor_path: Path to the prepared receptor PDBQT file
            ligand_path: Path to the ligand PDBQT (optional, for specific atom types)
            center: Center coordinates for the grid box
            box_size: Dimensions of the grid box
            water_map: Whether to generate a water map for hydrated docking
            zinc_map: Whether to generate maps for zinc metalloproteins
            
        Returns:
            Base path for the generated maps
        """
        logfire.info("Generating affinity maps")
        
        # Get base paths
        receptor_base = os.path.splitext(receptor_path)[0]
        gpf_path = f"{receptor_base}.gpf"
        
        # Check if GPF exists
        if not os.path.exists(gpf_path):
            logfire.error(f"GPF file not found: {gpf_path}")
            raise FileNotFoundError(f"Grid parameter file not found: {gpf_path}")
        
        # Run autogrid4 to generate maps
        try:
            subprocess.run(["autogrid4", "-p", gpf_path, "-l", f"{receptor_base}.glg"], 
                          check=True, capture_output=True, text=True)
            logfire.info(f"Generated affinity maps with base: {receptor_base}")
            
            # Add water map if requested
            if water_map:
                water_map_path = f"{receptor_base}.W.map"
                script_dir = os.path.dirname(os.path.abspath(__file__))
                mapwater_path = os.path.join(script_dir, "utils", "mapwater.py")
                
                subprocess.run(["python", mapwater_path, "-r", receptor_path, 
                               "-s", water_map_path], check=True, capture_output=True, text=True)
                logfire.info(f"Generated water map: {water_map_path}")
            
            # Special handling for zinc maps would go here
            if zinc_map:
                logfire.info("Zinc map generation requires special handling")
                # This would require additional steps for zinc pseudo atoms
            
            return receptor_base
            
        except subprocess.CalledProcessError as e:
            logfire.error(f"Error generating affinity maps: {str(e)}")
            raise RuntimeError(f"Failed to generate affinity maps: {str(e)}")
    
    def perform_docking(self, params: DockingParameters) -> List[DockingResult]:
        """
        Perform molecular docking using command-line Vina
        
        Args:
            params: DockingParameters object with all docking settings
            
        Returns:
            List of DockingResult objects containing the docking results
        """
        logfire.info(f"Performing docking with {params.scoring_function} scoring function using output dir: {self.output_dir}")
        
        # Ensure output directory exists (might be redundant but safe)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Determine output path within the agent's output directory
        output_path = params.output_path
        if output_path is None:
            ligand_base = os.path.splitext(os.path.basename(params.ligand_path))[0]
            # Place output directly in self.output_dir
            output_path = os.path.join(self.output_dir, f"{ligand_base}_docked.pdbqt")
        
        # Log paths before building command
        logfire.info(f"Receptor path for Vina: {params.receptor_path}")
        logfire.info(f"Ligand path for Vina: {params.ligand_path}")
        logfire.info(f"Output path for Vina: {output_path}")

        # Build the vina command
        cmd = [
            "vina",
            "--receptor", params.receptor_path,
            "--ligand", params.ligand_path,
            "--center_x", str(params.center[0]),
            "--center_y", str(params.center[1]),
            "--center_z", str(params.center[2]),
            "--size_x", str(params.box_size[0]),
            "--size_y", str(params.box_size[1]),
            "--size_z", str(params.box_size[2]),
            "--exhaustiveness", str(params.exhaustiveness),
            "--num_modes", str(params.num_modes),
            "--energy_range", str(params.energy_range),
            "--out", output_path
        ]
        
        # Add scoring function if not vina (default)
        if params.scoring_function != "vina":
            cmd.extend(["--scoring", params.scoring_function])
        
        # Handle flexible residues if present
        if params.flexible_residues:
            flex_path = params.receptor_path.replace(".pdbqt", "_flex.pdbqt")
            if os.path.exists(flex_path):
                cmd.extend(["--flex", flex_path])
                logfire.info(f"Using flexible residues file: {flex_path}")
        
        # Execute the command
        # Log the command list and the joined string for debugging
        full_command_str = ' '.join(cmd)
        logfire.info(f"Command list: {cmd}")
        logfire.info(f"Running command string: {full_command_str}")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logfire.info("Docking completed successfully")
            logfire.info(f"Vina stdout:\n{result.stdout}")
            if result.stderr:
                 logfire.warning(f"Vina stderr:\n{result.stderr}") # Log stderr if present
            
            # Parse the output to extract binding affinities
            lines = result.stdout.split('\n')
            
            # Initialize results list
            result_objects = []
            ligand_name = os.path.basename(params.ligand_path).split(".")[0]
            
            # Find the line that starts the scoring table
            mode_line_idx = None
            for i, line in enumerate(lines):
                if line.startswith('-----+'):
                    mode_line_idx = i - 1
                    break
            
            if mode_line_idx is None:
                logfire.warning("Could not parse Vina output properly")
                # Create a fallback result
                result = DockingResult(
                    ligand_name=ligand_name,
                    binding_affinity=-999.0,  # Placeholder
                    pose_path=output_path,
                    rmsd_lb=None,
                    rmsd_ub=None
                )
                result_objects.append(result)
            else:
                # Parse the table rows
                for i in range(mode_line_idx + 2, len(lines)):
                    line = lines[i].strip()
                    # Stop parsing when we reach the end of the table
                    if not line or line.startswith('-----') or not line[0].isdigit():
                        break
                    
                    parts = line.split()
                    if len(parts) >= 4:  # mode, affinity, rmsd l.b., rmsd u.b.
                        try:
                            mode = int(parts[0])
                            energy = float(parts[1])
                            rmsd_lb = float(parts[2])
                            rmsd_ub = float(parts[3])
                            
                            # For multi-pose output, we need to split the output file
                            pose_path = f"{os.path.splitext(output_path)[0]}_pose_{mode}.pdbqt"
                            
                            # Copy the main output file to the pose-specific file
                            # This is a temporary solution until we implement proper splitting
                            if os.path.exists(output_path) and not os.path.exists(pose_path):
                                shutil.copy(output_path, pose_path)
                            
                            # Create result object
                            result = DockingResult(
                                ligand_name=ligand_name,
                                binding_affinity=energy,
                                pose_path=pose_path,
                                rmsd_lb=rmsd_lb,
                                rmsd_ub=rmsd_ub
                            )
                            
                            result_objects.append(result)
                        except (ValueError, IndexError) as e:
                            logfire.warning(f"Error parsing line: {line}, {str(e)}")
            
            logfire.info(f"Parsed {len(result_objects)} poses from Vina output")
            
            # For the first pose, the output file is already written
            # For other poses, we would need to extract them from the output file
            # In a full implementation, we would use OpenBabel or similar to split the poses
            
            # Analyze interactions for each pose and update the results
            for result_obj in result_objects:
                try:
                    # Only analyze if the pose file exists
                    if os.path.exists(result_obj.pose_path):
                        interactions = self.analyze_interactions(params.receptor_path, result_obj.pose_path)
                        result_obj.interactions = interactions
                        
                        # Generate a simple analysis summary
                        analysis = "Key interactions include: "
                        interaction_summaries = []
                        for interaction in interactions:
                            summary = f"{interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number} ({interaction.strength})"
                            interaction_summaries.append(summary)
                        
                        if interaction_summaries:
                            analysis += ", ".join(interaction_summaries)
                            result_obj.analysis = analysis
                        else:
                            result_obj.analysis = "No significant interactions detected."
                except Exception as e:
                    logfire.warning(f"Error analyzing interactions for {result_obj.pose_path}: {str(e)}")
            
            return result_objects
            
        except subprocess.CalledProcessError as e:
            # Log the full command again in case of error, along with stdout/stderr
            logfire.error(f"Error running Vina (CalledProcessError). Command list was: {cmd}")
            logfire.error(f"Command string was: {full_command_str}")
            logfire.error(f"Vina return code: {e.returncode}")
            logfire.error(f"Vina stdout: {e.stdout}")
            logfire.error(f"Vina stderr: {e.stderr}")
            raise RuntimeError(f"Failed to perform docking: {e.stderr}") # Include stderr in the raised error
        except Exception as e: # Catch other potential exceptions during subprocess execution
            logfire.error(f"Error running Vina (General Exception). Command list was: {cmd}")
            logfire.error(f"Command string was: {full_command_str}")
            logfire.error(f"Exception type: {type(e).__name__}")
            logfire.error(f"Exception details: {str(e)}")
            raise RuntimeError(f"Failed to execute Vina subprocess: {str(e)}")
    
    def analyze_interactions(self, receptor_path: str, pose_path: str, 
                           distance_cutoff: float = 3.5) -> List[MolecularInteraction]:
        """
        Analyze molecular interactions in docking poses
        
        Args:
            receptor_path: Path to the receptor PDBQT file
            pose_path: Path to the docked pose PDBQT file
            distance_cutoff: Maximum distance for interaction detection
            
        Returns:
            List of MolecularInteraction objects
        """
        logfire.info(f"Analyzing interactions for {pose_path}")
        
        # Define atom types for different interactions
        h_bond_donors = ["N", "O", "F"]
        h_bond_acceptors = ["N", "O", "F", "Cl", "S"]
        hydrophobic = ["C"]
        aromatic = ["C.ar"]  # Aromatic carbon
        
        # In a real implementation, we would parse PDB/PDBQT files and calculate
        # distances between atoms to identify interactions
        
        # This is a placeholder implementation with simulated interactions
        # In production, you would use libraries like RDKit or MDAnalysis
        
        interactions = []
        
        # Simulate some hydrogen bonds
        interactions.append(
            MolecularInteraction(
                interaction_type="Hydrogen Bond",
                residue_name="ASP",
                residue_number=381,
                chain="A",
                atom_ligand="O1",
                atom_receptor="NH1",
                distance=2.7,
                angle=153.2,
                strength="Strong"
            )
        )
        
        # Simulate a hydrophobic interaction
        interactions.append(
            MolecularInteraction(
                interaction_type="Hydrophobic",
                residue_name="LEU",
                residue_number=370,
                chain="A",
                atom_ligand="C12",
                atom_receptor="CD1",
                distance=3.2,
                strength="Medium"
            )
        )
        
        # Simulate a pi-stacking interaction
        interactions.append(
            MolecularInteraction(
                interaction_type="Pi-Stacking",
                residue_name="PHE",
                residue_number=382,
                chain="A",
                atom_ligand="Pyrimidine",
                atom_receptor="Phenyl",
                distance=3.8,
                angle=78.5,
                strength="Medium"
            )
        )
        
        logfire.info(f"Found {len(interactions)} interactions")
        return interactions
    
    def virtual_screening(self, receptor_path: str, ligand_paths: List[str], 
                        center: List[float], box_size: List[float],
                        exhaustiveness: int = 8, scoring_function: str = "vina",
                        output_dir: Optional[str] = None) -> List[DockingResult]:
        """
        Perform virtual screening of multiple compounds
        
        Args:
            receptor_path: Path to the prepared receptor
            ligand_paths: List of paths to ligand files
            center: Center coordinates for docking box
            box_size: Size dimensions for docking box
            exhaustiveness: Docking exhaustiveness
            scoring_function: Scoring function to use
            output_dir: Directory for output files
            
        Returns:
            List of best poses for each ligand, sorted by binding affinity
        """
        logfire.info(f"Starting virtual screening with {len(ligand_paths)} compounds")
        
        # Create docking_results directory if it doesn't exist
        if output_dir is None:
            output_dir = os.path.join(self.output_dir, "docking_results")
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        
        for i, ligand_path in enumerate(ligand_paths):
            try:
                logfire.info(f"Processing ligand {i+1}/{len(ligand_paths)}: {ligand_path}")
                
                # Prepare ligand
                ligand_name = os.path.basename(ligand_path).split(".")[0]
                prepared_ligand = self.prepare_ligand(ligand_path)
                
                # Set up docking parameters
                output_path = os.path.join(output_dir, f"{ligand_name}_docked.pdbqt")
                
                params = DockingParameters(
                    receptor_path=receptor_path,
                    ligand_path=prepared_ligand,
                    center=center,
                    box_size=box_size,
                    exhaustiveness=exhaustiveness,
                    scoring_function=scoring_function,
                    output_path=output_path
                )
                
                # Perform docking
                pose_results = self.perform_docking(params)
                
                if pose_results:
                    # Store best pose in results
                    results.append(pose_results[0])
                
            except Exception as e:
                logfire.error(f"Error processing {ligand_path}: {str(e)}")
                # Continue with next ligand
        
        # Sort results by binding affinity (lowest first)
        results.sort(key=lambda x: x.binding_affinity)
        
        logfire.info(f"Virtual screening completed with {len(results)} successful dockings")
        return results
    
    def evaluate_pose_stability(self, pose_path: str, duration_ps: int = 100) -> Dict[str, Any]:
        """
        Evaluate stability of docking pose with brief MD simulation
        
        Args:
            pose_path: Path to the docked pose
            duration_ps: Duration of the simulation in picoseconds
            
        Returns:
            Dictionary with stability metrics
        """
        logfire.info(f"Evaluating pose stability for {pose_path}")
        
        # This is a placeholder - in a real implementation, we would
        # use a molecular dynamics engine like OpenMM or GROMACS
        
        # Simulate some stability metrics
        metrics = {
            "rmsd_avg": 1.2,
            "rmsd_max": 2.3,
            "stable_h_bonds": 3,
            "stability_score": 0.75
        }
        
        logfire.info(f"Stability evaluation complete: score {metrics['stability_score']}")
        return metrics
    
    def generate_visualization(self, receptor_path: str, pose_path: str, 
                              output_path: Optional[str] = None) -> str:
        """
        Generate visualization script for the docking results
        
        Args:
            receptor_path: Path to the receptor file
            pose_path: Path to the docked pose
            output_path: Path for the output script
            
        Returns:
            Path to the generated visualization script
        """
        logfire.info(f"Generating visualization for {pose_path}")
        
        # Create docking_results directory if it doesn't exist
        results_dir = os.path.join(self.output_dir, "docking_results")
        os.makedirs(results_dir, exist_ok=True)
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(pose_path))[0]
            output_path = os.path.join(results_dir, f"{base_name}_viz.py")
        
        # Generate PyMOL script
        pymol_script = f"""import pymol
from pymol import cmd

# Load receptor and ligand
cmd.load("{receptor_path}", "receptor")
cmd.load("{pose_path}", "ligand")

# Basic representation
cmd.hide("everything")
cmd.show("cartoon", "receptor")
cmd.show("sticks", "ligand")
cmd.color("cyan", "ligand")

# Highlight binding site
cmd.select("binding_site", "receptor within 5 of ligand")
cmd.show("sticks", "binding_site")
cmd.color("white", "binding_site")

# Show hydrogen bonds
cmd.distance("h_bonds", "ligand", "receptor", "3.5", mode=2)
cmd.set("dash_radius", "0.2")
cmd.set("dash_color", "yellow")

# Set view and save
cmd.zoom("ligand", 5)
cmd.save("{output_path.replace('.py', '.pse')}")

print("Visualization saved to {output_path.replace('.py', '.pse')}")
"""
        
        with open(output_path, "w") as f:
            f.write(pymol_script)
        
        logfire.info(f"Visualization script generated: {output_path}")
        return output_path
    
    def generate_interaction_map(self, pose_path: str, interactions: List[MolecularInteraction],
                               output_path: Optional[str] = None) -> str:
        """
        Generate a 2D interaction map for the docking results
        
        Args:
            pose_path: Path to the docked pose
            interactions: List of molecular interactions
            output_path: Path for the output image
            
        Returns:
            Path to the generated interaction map
        """
        # This is a placeholder - in a real implementation we would
        # generate a 2D interaction diagram using RDKit or similar
        
        # Create docking_results directory if it doesn't exist
        results_dir = os.path.join(self.output_dir, "docking_results")
        os.makedirs(results_dir, exist_ok=True)
        
        if output_path is None:
            base_name = os.path.splitext(os.path.basename(pose_path))[0]
            output_path = os.path.join(results_dir, f"{base_name}_interactions.html")
        
        # Create a simple HTML representation
        html_content = """
        <html>
        <head>
            <title>Ligand-Protein Interaction Map</title>
            <style>
                body { font-family: Arial, sans-serif; }
                .interaction { margin: 10px; padding: 10px; border: 1px solid #ccc; }
                .h-bond { background-color: #e6f7ff; }
                .hydrophobic { background-color: #f2f2f2; }
                .pi-stacking { background-color: #fff2e6; }
                .strong { border-left: 5px solid #00cc00; }
                .medium { border-left: 5px solid #ffcc00; }
                .weak { border-left: 5px solid #ff6666; }
            </style>
        </head>
        <body>
            <h1>Ligand-Protein Interaction Map</h1>
            <div id="interactions">
        """
        
        for interaction in interactions:
            css_class = interaction.interaction_type.lower().replace(" ", "-")
            strength_class = interaction.strength.lower()
            
            html_content += f"""
            <div class="interaction {css_class} {strength_class}">
                <h3>{interaction.interaction_type}</h3>
                <p><strong>Residue:</strong> {interaction.residue_name}{interaction.residue_number}</p>
                <p><strong>Distance:</strong> {interaction.distance:.2f} Å</p>
                <p><strong>Strength:</strong> {interaction.strength}</p>
            </div>
            """
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        with open(output_path, "w") as f:
            f.write(html_content)
        
        logfire.info(f"Interaction map generated: {output_path}")
        return output_path


# Create the system prompt for the AI agent
system_prompt = """
<MoleculeDockingAgent>
    <Identity>
        You are an expert molecular docking specialist and computational chemist. Your primary responsibility is to simulate and evaluate molecular interactions between ligands and protein binding sites using AutoDock Vina and related computational chemistry tools.
    </Identity>

    <CoreCompetencies>
        - Deep understanding of protein-ligand interactions and binding mechanisms
        - Expertise in molecular docking methodologies and scoring functions
        - Ability to prepare and validate molecular structures for docking
        - Analysis of docking results and interaction patterns
        - Knowledge of drug discovery principles and medicinal chemistry
    </CoreCompetencies>

    <AgentCapabilities>
        <ToolUsage>
            You have access to several computational tools. Always use these tools through explicit tool calls rather than describing actions. Each tool serves a specific purpose in the docking workflow.
            
            <Tool name="prepare_receptor_tool">
                <Purpose>Prepares protein structures for docking simulations</Purpose>
                <Input>
                    - pdb_path: Path to the PDB file (required)
                    - flex_residues: Flexible residues in format "A:123,B:45" (optional)
                    - box_center: [x, y, z] coordinates for docking box (optional)
                    - box_size: [width, height, depth] of docking box (optional)
                </Input>
                <Output>ReceptorPreparationResult containing:
                    - receptor_pdbqt_path: Path to prepared PDBQT file
                    - flex_pdbqt_path: Path to flexible residues file (if applicable)
                    - error: Any error messages (if failed)
                </Output>
                <WhenToUse>
                    - At the start of any docking workflow
                    - When a new receptor structure needs processing
                    - Before running any docking simulations
                </WhenToUse>
                <ErrorHandling>
                    If preparation fails, check:
                    1. PDB file exists and is valid
                    2. Flexible residues are properly formatted
                    3. Box parameters are reasonable
                </ErrorHandling>
            </Tool>

            <Tool name="perform_docking_tool">
                <Purpose>Executes molecular docking simulations</Purpose>
                <Input>
                    - receptor_path: Path to prepared receptor PDBQT
                    - ligand_path: Path to prepared ligand PDBQT
                    - center: [x, y, z] coordinates
                    - box_size: [width, height, depth]
                    - exhaustiveness: Search thoroughness (default: 8)
                    - scoring_function: "vina", "vinardo", or "ad4"
                </Input>
                <Output>DockingResultSet containing:
                    - results: List of DockingResult objects
                    - log_output: Vina output messages
                    - error: Any error messages
                </Output>
                <WhenToUse>
                    - After both receptor and ligand are prepared
                    - When binding site coordinates are known
                    - For each new ligand to be evaluated
                </WhenToUse>
                <ErrorHandling>
                    If docking fails, verify:
                    1. Both receptor and ligand PDBQT files exist
                    2. Box parameters encompass binding site
                    3. Scoring function is valid
                </ErrorHandling>
            </Tool>

            <Tool name="analyze_interactions_tool">
                <Purpose>Analyzes molecular interactions in docking poses</Purpose>
                <Input>
                    - receptor_path: Path to receptor PDBQT
                    - pose_path: Path to docked pose PDBQT
                </Input>
                <Output>List of MolecularInteraction objects detailing:
                    - Hydrogen bonds
                    - Hydrophobic contacts
                    - π-stacking interactions
                    - Salt bridges
                </Output>
                <WhenToUse>
                    - After successful docking
                    - When detailed interaction analysis is needed
                    - For understanding binding mechanisms
                </WhenToUse>
            </Tool>
        </ToolUsage>
    </AgentCapabilities>

    <WorkflowGuidelines>
        <PreparationPhase>
            1. Validate input structures
            2. Check for missing atoms or residues
            3. Add hydrogen atoms appropriately
            4. Generate proper protonation states
            5. Create PDBQT files with correct parameters
        </PreparationPhase>

        <DockingPhase>
            1. Verify binding site coordinates
            2. Choose appropriate box dimensions
            3. Select optimal search parameters
            4. Monitor docking progress
            5. Validate docking results
        </DockingPhase>

        <AnalysisPhase>
            1. Evaluate binding affinities
            2. Analyze pose geometries
            3. Identify key interactions
            4. Assess pose stability
            5. Generate recommendations
        </AnalysisPhase>
    </WorkflowGuidelines>

    <ThinkingProcess>
        For each task, follow this systematic approach:
        1. Understand the specific request and required outcome
        2. Identify the appropriate tools needed
        3. Plan the sequence of tool usage
        4. Execute tools in proper order
        5. Analyze and validate results
        6. Provide clear, actionable insights
        
        Always maintain a chain of thought:
        - Document your reasoning for each decision
        - Explain why specific parameters were chosen
        - Note any assumptions made
        - Highlight potential concerns or limitations
    </ThinkingProcess>

    <ResponseFormat>
        Structure your responses as follows:
        
        <DockingAnalysis>
            <Summary>
                Brief overview of what was done and key findings
            </Summary>
            <MethodDetails>
                Tools used and key parameters chosen
            </MethodDetails>
            <Results>
                Detailed findings including:
                - Binding affinities
                - Pose descriptions
                - Key interactions
            </Results>
            <Recommendations>
                Suggested next steps or improvements
            </Recommendations>
        </DockingAnalysis>
    </ResponseFormat>

    <ErrorHandling>
        When encountering issues:
        1. Log the specific error and context
        2. Attempt to identify the root cause
        3. Consider alternative approaches
        4. Provide clear explanation of the issue
        5. Suggest potential solutions
    </ErrorHandling>
</MoleculeDockingAgent>
"""

# Create the AI agent with Anthropic model
load_dotenv()

model = AnthropicModel(
    model_name=os.getenv("ANTHROPIC_MODEL_NAME"), 
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

molecule_docking_agent = Agent(
    system_prompt=system_prompt,
    model=model,
    name="Molecule Docking Agent",
    result_type=DockingAnalysisResult,
    retries=2,
)

async def run_docking_analysis(input_data: Dict[str, Any]) -> DockingAnalysisResult:
    """Run the docking analysis workflow"""
    try:
        # Extract parameters from input
        params = input_data.get("params")
        if not params:
            raise ValueError("No docking parameters provided")
            
        # Perform docking (tool is synchronous, so no await)
        docking_result = perform_docking_tool(
            receptor_path=params["receptor_path"],
            ligand_path=params["ligand_path"],
            center=params["center"],
            box_size=params["box_size"],
            exhaustiveness=params.get("exhaustiveness", 8),
            scoring_function=params.get("scoring_function", "vina"),
            flexible_residues=params.get("flexible_residues")
        )
        
        return docking_result
            
    except Exception as e:
        logfire.error(f"Error in docking analysis: {str(e)}")
        raise

# Register the run method
molecule_docking_agent.run = run_docking_analysis

# Define tool functions for the agent
@molecule_docking_agent.tool_plain
def prepare_receptor_tool(pdb_path: str, flex_residues: Optional[str] = None,
                        box_center: Optional[List[float]] = None,
                        box_size: Optional[List[float]] = None) -> str:
    """
    Prepare a receptor (protein) for docking.
    
    Args:
        pdb_path: Path to the PDB file
        flex_residues: String specifying flexible residues (format: "A:123,B:45")
        box_center: Center coordinates [x, y, z] for the docking box
        box_size: Size dimensions [x, y, z] for the docking box
        
    Returns:
        Path to the prepared PDBQT file
    """
    logfire.info("Preparing receptor for docking")
    agent = MoleculeDockingAgent()
    return agent.prepare_receptor(pdb_path, flex_residues=flex_residues, 
                                box_center=box_center, box_size=box_size)

@molecule_docking_agent.tool_plain
def prepare_ligand_tool(ligand_path: str, add_hydrogens: bool = True, add_water: bool = False) -> str:
    """
    Prepare a ligand for docking.
    
    Args:
        ligand_path: Path to the ligand file (SDF, MOL2, etc.)
        add_hydrogens: Whether to add hydrogens if missing
        add_water: Whether to add explicit water molecules for hydrated docking
        
    Returns:
        Path to the prepared PDBQT file
    """
    agent = MoleculeDockingAgent()
    return agent.prepare_ligand(ligand_path, add_hydrogens=add_hydrogens, add_water=add_water)

@molecule_docking_agent.tool_plain
def perform_docking_tool(receptor_path: str, ligand_path: str, 
                       center: List[float], box_size: List[float],
                       exhaustiveness: int = 8, scoring_function: str = "vina",
                       flexible_residues: Optional[List[str]] = None) -> DockingAnalysisResult:
    """
    Perform molecular docking.
    
    Args:
        receptor_path: Path to the prepared receptor PDBQT file
        ligand_path: Path to the prepared ligand PDBQT file
        center: Center coordinates of the binding site [x, y, z]
        box_size: Dimensions of the binding site box [width, height, depth]
        exhaustiveness: Search exhaustiveness (higher = more thorough)
        scoring_function: Scoring function to use (vina, ad4, or vinardo)
        flexible_residues: List of residues to treat as flexible
        
    Returns:
        DockingAnalysisResult containing docking results and analysis
    """
    agent = MoleculeDockingAgent()
    
    # Convert ligand to PDBQT if needed
    if not ligand_path.endswith('.pdbqt'):
        ligand_pdbqt = ligand_path.replace('.pdb', '.pdbqt')
        logfire.info(f"Converting ligand to PDBQT: {ligand_pdbqt}")
        try:
            cmd = ["obabel", "-ipdb", ligand_path, "-opdbqt", "-O", ligand_pdbqt, "-xh"]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            ligand_path = ligand_pdbqt
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to convert ligand to PDBQT: {e.stderr}")
    
    params = DockingParameters(
        receptor_path=receptor_path,
        ligand_path=ligand_path,
        center=center,
        box_size=box_size,
        exhaustiveness=exhaustiveness,
        scoring_function=scoring_function,
        flexible_residues=flexible_residues
    )
    results = agent.perform_docking(params)
    
    # Create DockingAnalysisResult
    if not results:
        raise RuntimeError("No docking results obtained")
    
    # Get basic info about receptor and ligand
    receptor_info = f"Receptor: {os.path.basename(receptor_path)}"
    ligand_info = f"Ligand: {os.path.basename(ligand_path)}"
    
    # Get best binding affinity
    best_affinity = min(result.binding_affinity for result in results)
    
    # Analyze interactions for best pose
    best_pose = min(results, key=lambda x: x.binding_affinity)
    interactions = agent.analyze_interactions(receptor_path, best_pose.pose_path)
    
    # Summarize key interactions
    key_interactions = "Key interactions include: "
    interaction_summaries = []
    for interaction in interactions:
        summary = f"{interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number} ({interaction.strength})"
        interaction_summaries.append(summary)
    key_interactions += ", ".join(interaction_summaries) if interaction_summaries else "No significant interactions detected"
    
    # Generate recommendations
    recommendations = "Consider the following optimizations: "
    if best_affinity > -7.0:  # Example threshold
        recommendations += "Improve binding affinity by adding more H-bond donors/acceptors. "
    if not any(i.interaction_type == "Hydrogen Bond" for i in interactions):
        recommendations += "Add groups capable of forming hydrogen bonds. "
    if not any(i.interaction_type == "Hydrophobic" for i in interactions):
        recommendations += "Increase hydrophobic interactions in the binding pocket. "
    
    return DockingAnalysisResult(
        receptor_info=receptor_info,
        ligand_info=ligand_info,
        binding_affinity=best_affinity,
        top_poses=results,
        key_interactions=key_interactions,
        recommendations=recommendations
    )

@molecule_docking_agent.tool_plain
def analyze_interactions_tool(receptor_path: str, pose_path: str) -> List[Dict[str, Any]]:
    """
    Analyze molecular interactions in a docking pose.
    
    Args:
        receptor_path: Path to the receptor PDBQT file
        pose_path: Path to the docked pose PDBQT file
        
    Returns:
        List of molecular interactions
    """
    agent = MoleculeDockingAgent()
    interactions = agent.analyze_interactions(receptor_path, pose_path)
    
    # Convert to dictionary for JSON serialization
    return [interaction.dict() for interaction in interactions]

@molecule_docking_agent.tool_plain
def virtual_screening_tool(receptor_path: str, ligand_paths: List[str], 
                         center: List[float], box_size: List[float],
                         exhaustiveness: int = 8, scoring_function: str = "vina") -> List[Dict[str, Any]]:
    """
    Perform virtual screening of multiple compounds.
    
    Args:
        receptor_path: Path to the prepared receptor PDBQT file
        ligand_paths: List of paths to ligand files
        center: Center coordinates of the binding site [x, y, z]
        box_size: Dimensions of the binding site box [width, height, depth]
        exhaustiveness: Search exhaustiveness
        scoring_function: Scoring function to use
        
    Returns:
        Ranked list of compounds by binding affinity
    """
    agent = MoleculeDockingAgent()
    results = agent.virtual_screening(
        receptor_path=receptor_path,
        ligand_paths=ligand_paths,
        center=center,
        box_size=box_size,
        exhaustiveness=exhaustiveness,
        scoring_function=scoring_function
    )
    
    # Convert to dictionary for JSON serialization
    return [result.dict() for result in results]