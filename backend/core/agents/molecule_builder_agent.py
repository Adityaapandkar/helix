import os
import sys
import traceback
import json
import random
import tempfile
import datetime
import uuid
import subprocess
from typing import List, Dict, Optional, Union, Any
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from dotenv import load_dotenv
import logfire

# Load environment variables first
load_dotenv()

# Configure logfire
os.environ['LOGFIRE_IGNORE_NO_CONFIG'] = '1'  # Suppress warning
logfire.configure(
    send_to_logfire=True, 
    scrubbing=False, 
    service_name="helix", 
    token=os.getenv("LOGFIRE_API_KEY")
)

# Initialize RDKit availability flag
RDKIT_AVAILABLE = False

try:
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem import rdMolDescriptors
    from rdkit.Chem import Descriptors
    from rdkit.Chem import Crippen
    
    # Test RDKit functionality
    test_mol = Chem.MolFromSmiles('CC')
    if test_mol is not None:
        RDKIT_AVAILABLE = True
        logfire.info("RDKit successfully initialized")
    else:
        logfire.error("RDKit molecule creation test failed")
except ImportError as e:
    logfire.error(f"RDKit import error: {str(e)}")
    logfire.error(f"Traceback:\n{traceback.format_exc()}")
except Exception as e:
    logfire.error(f"Unexpected error initializing RDKit: {str(e)}")
    logfire.error(f"Traceback:\n{traceback.format_exc()}")

# Print debug info
logfire.info(f"Python path: {sys.path}")
logfire.info(f"RDKit available: {RDKIT_AVAILABLE}")

# Define molecule properties model
class MoleculeProperties(BaseModel):
    molecular_weight: Optional[float] = None
    logp: Optional[float] = None
    num_hba: Optional[int] = None  # Hydrogen bond acceptors
    num_hbd: Optional[int] = None  # Hydrogen bond donors
    tpsa: Optional[float] = None   # Topological polar surface area
    rotatable_bonds: Optional[int] = None
    rings: Optional[int] = None
    heavy_atoms: Optional[int] = None

# Define result type
class MoleculeBuilderResult(BaseModel):
    smiles: str
    molecule_path: str
    molecule_format: str
    properties: MoleculeProperties
    description: str
    terminate: bool = False
    termination_reason: Optional[str] = None

# Define a model for the chain of thought logging
class ChainOfThoughtLog(BaseModel):
    session_id: str
    timestamp: str
    function: str
    input_params: Dict[str, Any]
    reasoning_steps: List[str]
    decisions: List[Dict[str, Any]]
    output: Dict[str, Any]

# Global storage for chain of thought records
cot_logs = []

# Chain of thought logger initialization
def init_cot_logger():
    global cot_logs
    cot_logs = []
    
    # Create a file for the session if it doesn't exist
    session_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now().isoformat()
    
    # Log the initial session info
    log_entry = {
        "session_id": session_id,
        "started_at": timestamp,
        "logs": []
    }
    
    # Return session info
    return session_id, timestamp

# Function to log chain of thought
def log_chain_of_thought(session_id, function_name, inputs, reasoning=None, decisions=None, output=None):
    global cot_logs
    
    timestamp = datetime.datetime.now().isoformat()
    
    log_entry = {
        "timestamp": timestamp,
        "function": function_name,
        "input_params": inputs,
        "reasoning_steps": reasoning or [],
        "decisions": decisions or [],
        "output": output or {}
    }
    
    cot_logs.append(log_entry)
    
    # Write to file each time to ensure data is saved even if process crashes
    save_cot_logs(session_id)
    
    return log_entry

def pydantic_encoder(obj):
    """JSON encoder for Pydantic models."""
    if isinstance(obj, BaseModel):
        return obj.dict()
    # Let the default encoder raise the TypeError for other types
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

# Function to save logs to JSON file
def save_cot_logs(session_id):
    global cot_logs
    
    # Save logs within the project's output directory
    output_log_dir = os.path.join(os.getcwd(), "helix_output", "logs")
    os.makedirs(output_log_dir, exist_ok=True) # Ensure the directory exists
    log_file_path = os.path.join(output_log_dir, f"molecule_builder_cot_{session_id}.json")
    
    log_data = {
        "session_id": session_id,
        "last_updated": datetime.datetime.now().isoformat(),
        "logs": cot_logs
    }
    
    try:
        with open(log_file_path, 'w') as f:
            # Use the custom encoder for Pydantic models
            json.dump(log_data, f, indent=2, default=pydantic_encoder)
        logfire.info(f"Chain of thought logs saved to {log_file_path}")
    except TypeError as te:
        # Catch potential TypeErrors during serialization and log details
        logfire.error(f"Error serializing chain of thought logs: {str(te)}")
        logfire.error(f"Problematic data structure (sample): {str(log_data)[:500]}...") # Log a sample of the data
    except Exception as e:
        logfire.error(f"Error saving chain of thought logs: {str(e)}")

system_prompt = """
<MoleculeBuilderAgent>
    <Identity>
        You are an expert medicinal chemist and molecular designer specializing in computer-aided drug design (CADD). Your primary responsibility is to design and optimize drug-like molecules for specific protein targets, with a focus on generating structures suitable for molecular docking.
    </Identity>

    <CoreCompetencies>
        - Deep understanding of medicinal chemistry principles
        - Expertise in structure-based drug design
        - Knowledge of pharmacophore modeling
        - Proficiency in molecular property prediction
        - Understanding of protein-ligand interactions
        - Experience with fragment-based drug design
    </CoreCompetencies>

    <AgentCapabilities>
        <ToolUsage>
            You have access to several molecular design and analysis tools. Always use these tools through explicit tool calls rather than describing actions. Each tool serves a specific purpose in the molecule design workflow.

            <Tool name="prepare_ligand_for_docking_tool">
                <Purpose>Designs and prepares ligands optimized for specific binding sites</Purpose>
                <Input>
                    - binding_site_info: Dictionary containing site properties
                    - output_dir: Directory for output files (optional)
                    - previous_results: List of previous attempts (optional)
                    - iteration: Current iteration number (optional)
                    - max_iterations: Maximum allowed iterations (optional)
                </Input>
                <Output>MoleculeBuilderResult containing:
                    - smiles: SMILES string of designed molecule
                    - molecule_path: Path to molecule file
                    - pdbqt_path: Path to docking-ready PDBQT file
                    - properties: Calculated molecular properties
                    - description: Design rationale
                    - error: Any error messages
                    - terminate: Boolean flag to stop iterations
                </Output>
                <WhenToUse>
                    - When designing new ligands for docking
                    - During iterative optimization
                    - When preparing compounds for virtual screening
                </WhenToUse>
                <ErrorHandling>
                    If preparation fails, check:
                    1. Binding site information is complete
                    2. SMILES string is valid
                    3. RDKit is available
                    4. Open Babel conversion succeeds
                </ErrorHandling>
            </Tool>

            <Tool name="calculate_properties_tool">
                <Purpose>Calculates physicochemical properties of molecules</Purpose>
                <Input>
                    - molecule_input: SMILES string or file path
                </Input>
                <Output>MoleculeProperties containing:
                    - molecular_weight
                    - logP
                    - hydrogen bond donors/acceptors
                    - TPSA
                    - rotatable bonds
                    - ring count
                </Output>
                <WhenToUse>
                    - After generating new molecules
                    - When evaluating drug-likeness
                    - During property optimization
                </WhenToUse>
            </Tool>

            <Tool name="generate_3d_conformation_tool">
                <Purpose>Generates 3D conformations of molecules</Purpose>
                <Input>
                    - molecule_input: SMILES or file path
                    - output_format: Desired format (pdb/sdf/pdbqt)
                </Input>
                <Output>
                    - Path to 3D structure file
                    - Error message if generation fails
                </Output>
                <WhenToUse>
                    - Before docking
                    - When 3D structure is needed
                    - For conformational analysis
                </WhenToUse>
            </Tool>
        </ToolUsage>
    </AgentCapabilities>

    <DesignGuidelines>
        <DrugLikeness>
            <LipinskiRules>
                - Molecular weight ≤ 500 Da
                - LogP ≤ 5
                - Hydrogen bond donors ≤ 5
                - Hydrogen bond acceptors ≤ 10
                - Violations allowed: ≤ 1
            </LipinskiRules>

            <VeberRules>
                - Rotatable bonds ≤ 10
                - TPSA ≤ 140 Å²
                - Essential for oral bioavailability
            </VeberRules>

            <AdditionalConsiderations>
                - Synthetic accessibility
                - Metabolic stability
                - Toxicophore avoidance
                - Solubility requirements
            </AdditionalConsiderations>
        </DrugLikeness>

        <BindingSiteAdaptation>
            <SpatialConsiderations>
                - Match pocket volume and shape
                - Respect binding site boundaries
                - Consider protein flexibility
            </SpatialConsiderations>

            <InteractionMapping>
                - Map H-bond donors/acceptors
                - Identify hydrophobic regions
                - Consider π-stacking opportunities
                - Plan salt bridge formations
                - Account for water networks
            </InteractionMapping>
        </BindingSiteAdaptation>

        <OptimizationStrategies>
            <Structure>
                - Core scaffold selection
                - Fragment growing
                - Linker design
                - Substituent placement
            </Structure>

            <Properties>
                - Balance potency vs properties
                - Consider ADME implications
                - Maintain synthetic feasibility
                - Optimize stability
            </Properties>
        </OptimizationStrategies>
    </DesignGuidelines>

    <ThinkingProcess>
        For each design task:
        1. Analyze binding site characteristics
        2. Identify key interaction opportunities
        3. Select appropriate scaffold
        4. Place functional groups strategically
        5. Optimize properties iteratively
        6. Validate design decisions

        Document your reasoning:
        - Explain scaffold choice
        - Justify functional group placement
        - Discuss property trade-offs
        - Note potential risks/limitations
    </ThinkingProcess>

    <ResponseFormat>
        Structure your responses as follows:

        <MoleculeDesign>
            <Summary>
                Brief overview of designed molecule
            </Summary>
            <Rationale>
                Explanation of design decisions
            </Rationale>
            <Properties>
                Analysis of physicochemical properties
            </Properties>
            <PredictedInteractions>
                Expected binding interactions
            </PredictedInteractions>
            <Recommendations>
                Suggestions for optimization
            </Recommendations>
        </MoleculeDesign>
    </ResponseFormat>

    <IterationBehavior>
        Consider terminating iterations when:
        1. Optimal properties achieved
        2. No further improvement likely
        3. Maximum iterations reached
        4. Critical error encountered
        5. Design objectives met

        Before terminating:
        - Document reasoning
        - Summarize progress
        - Suggest alternatives
    </IterationBehavior>

    <ErrorHandling>
        When encountering issues:
        1. Log specific error details
        2. Identify failure point
        3. Consider fallback options
        4. Document limitations
        5. Suggest workarounds
    </ErrorHandling>
</MoleculeBuilderAgent>
"""

model = AnthropicModel(
    model_name=os.getenv("ANTHROPIC_MODEL_NAME"), 
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# Initialize chain of thought session
session_id, timestamp = init_cot_logger()

# Custom callback to capture chain of thought from the agent responses
def capture_chain_of_thought(response_object, function_name, inputs):
    # Extract reasoning from response if possible
    # Since we can't rely on a built-in reasoning field, we'll extract from the raw message
    reasoning_steps = []
    decisions = []
    
    # Try to infer reasoning from the response
    response_str = str(response_object)
    if "thinking" in response_str.lower() or "considering" in response_str.lower():
        # Simple approach: treat paragraphs or sentences as reasoning steps
        lines = [line.strip() for line in response_str.split('.') if line.strip()]
        reasoning_steps = lines[:min(len(lines), 5)]  # Limit to first 5 sentences to avoid noise
    
    # Log the chain of thought with what we have
    output = response_object.dict() if hasattr(response_object, "dict") else {"result": str(response_object)}
    log_chain_of_thought(
        session_id=session_id,
        function_name=function_name,
        inputs=inputs,
        reasoning=reasoning_steps,
        decisions=decisions,
        output=output
    )
    
    return response_object

molecule_builder_agent = Agent(
    system_prompt=system_prompt,
    model=model,
    name="Molecule Builder Agent",
    result_type=MoleculeBuilderResult,
    retries=2
)

# Helper function to ensure output directory exists
def ensure_output_dir(output_dir=None):
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), "molecule_files")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

# Generate a simple molecule if RDKit is not available
def generate_simple_molecule(name="default"):
    """Create a simple molecule file when RDKit is not available"""
    # Create a PDB file for a water molecule as fallback
    water_pdb = f"""HEADER    WATER
COMPND    HOH
ATOM      1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O
ATOM      2  H1  HOH A   1       0.000   0.000   1.000  1.00  0.00           H
ATOM      3  H2  HOH A   1       0.000   1.000   0.000  1.00  0.00           H
END
"""
    output_dir = ensure_output_dir()
    output_path = os.path.join(output_dir, f"{name}.pdb")
    with open(output_path, "w") as f:
        f.write(water_pdb)
    return output_path

# Handle file saving with appropriate format
def save_molecule_file(mol, output_path, file_format="pdb"):
    """Save molecule to a file with specified format"""
    if not RDKIT_AVAILABLE:
        # Return the simple water molecule as fallback
        return generate_simple_molecule(os.path.basename(output_path).split('.')[0])
        
    # Ensure correct file extension
    if not output_path.endswith(f".{file_format}"):
        output_path = f"{output_path}.{file_format}"
    
    # Save based on format
    if file_format == "pdb":
        Chem.MolToPDBFile(mol, output_path)
    elif file_format == "sdf":
        writer = Chem.SDWriter(output_path)
        writer.write(mol)
        writer.close()
    elif file_format == "mol":
        Chem.MolToMolFile(mol, output_path)
    elif file_format == "pdbqt":
        # For PDBQT, first save as PDB then convert using Open Babel
        temp_pdb = f"{output_path.replace('.pdbqt', '.pdb')}"
        Chem.MolToPDBFile(mol, temp_pdb)
        try:
            cmd = f"obabel -ipdb {temp_pdb} -opdbqt -O {output_path} -p 7.4 -xh"
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            logfire.info(f"Converted to PDBQT format: {output_path}")
        except Exception as e:
            logfire.error(f"Error converting to PDBQT: {str(e)}")
            # Return the PDB file if conversion fails
            return temp_pdb
    else:
        logfire.warning(f"Unsupported format: {file_format}, saving as PDB instead")
        Chem.MolToPDBFile(mol, output_path.replace(f".{file_format}", ".pdb"))
        return output_path.replace(f".{file_format}", ".pdb")
        
    return output_path

# Calculate molecule properties
def calculate_molecular_properties(mol):
    """Calculate molecular properties using RDKit."""
    if not RDKIT_AVAILABLE or mol is None:
        return {
            "molecular_weight": None,
            "logp": None,
            "num_hba": None,
            "num_hbd": None,
            "tpsa": None,
            "rotatable_bonds": None,
            "rings": None,
            "heavy_atoms": None
        }
    
    try:
        props = {}
        # Calculate individual descriptors using correct methods
        props["molecular_weight"] = Descriptors.ExactMolWt(mol)
        props["logp"] = Crippen.MolLogP(mol)
        props["num_hba"] = rdMolDescriptors.CalcNumHBA(mol)
        props["num_hbd"] = rdMolDescriptors.CalcNumHBD(mol)
        props["tpsa"] = Descriptors.TPSA(mol)
        props["rotatable_bonds"] = rdMolDescriptors.CalcNumRotatableBonds(mol)
        props["rings"] = rdMolDescriptors.CalcNumRings(mol)
        props["heavy_atoms"] = mol.GetNumHeavyAtoms()
        
        return props
    except Exception as e:
        logfire.error(f"Error calculating molecular properties: {str(e)}")
        return {
            "molecular_weight": None,
            "logp": None,
            "num_hba": None,
            "num_hbd": None,
            "tpsa": None,
            "rotatable_bonds": None,
            "rings": None,
            "heavy_atoms": None
        }

@molecule_builder_agent.tool_plain
async def modify_molecule_via_smarts(
    input_smiles: str,
    reaction_smarts: str,
    max_replacements: int = 1
) -> Dict[str, Any]:
    """
    Modifies a molecule using a specified SMARTS reaction.

    Args:
        input_smiles: SMILES string of the molecule to modify.
        reaction_smarts: A reaction SMARTS string defining the transformation
                         (e.g., '[cH:1]>>[c:1](C)' to replace aromatic H with methyl).
                         Ensure reactants are mapped with :N syntax.
        max_replacements: Maximum number of matches to modify (default: 1).

    Returns:
        Dictionary with 'success' flag, 'modified_smiles', 'description', 'properties', 'error' (if any).
    """
    logfire.info(f"Attempting modification: SMILES='{input_smiles}', Reaction='{reaction_smarts}'")
    if not RDKIT_AVAILABLE:
        return {"success": False, "modified_smiles": input_smiles, "description": "RDKit not available", "properties": {}, "error": "RDKit not available"}

    try:
        # Validate and prepare reaction
        rxn = AllChem.ReactionFromSmarts(reaction_smarts)
        if rxn is None or rxn.GetNumReactantTemplates() == 0:
            raise ValueError("Invalid or empty reaction SMARTS")

        # Validate and prepare reactant molecule
        mol = Chem.MolFromSmiles(input_smiles)
        if mol is None:
            raise ValueError(f"Invalid input SMILES: {input_smiles}")
        Chem.SanitizeMol(mol)
        original_smiles = Chem.MolToSmiles(mol) # Canonical SMILES

        # Run the reaction
        reactants = (mol,) # Reaction needs a tuple of reactants
        product_sets = rxn.RunReactants(reactants, maxProducts=max_replacements) # Control max modifications

        if not product_sets:
            # Reaction didn't yield any products (e.g., reactant pattern not found)
            description = f"Reaction '{reaction_smarts}' did not apply to '{original_smiles}'"
            logfire.warning(description)
            props = calculate_molecular_properties(mol)
            return {"success": False, "modified_smiles": original_smiles, "description": description, "properties": props, "error": "Reaction did not apply"}

        # Process products - take the first product of the first successful reaction set
        # RunReactants returns a tuple of tuples of product molecules.
        # We typically expect one product per set for simple modifications.
        modified_mol = product_sets[0][0] # Get the first product from the first set

        if modified_mol is None:
             raise ValueError("Reaction produced an invalid molecule.")

        # Post-process the modified molecule
        final_smiles = original_smiles
        properties = {}
        description = "Modification failed during post-processing"
        success = False

        try:
            Chem.SanitizeMol(modified_mol)
            # Generate 3D coords
            modified_mol = Chem.AddHs(modified_mol, addCoords=True)
            embed_params = AllChem.ETKDGv3() # Use modern embedder
            embed_params.randomSeed = 0xf00d # for reproducibility if needed
            if AllChem.EmbedMolecule(modified_mol, embed_params) == -1: # Check embed success
                 logfire.warning("Could not embed molecule, using non-optimized 3D coords.")
                 # Still try to optimize
                 AllChem.MMFFOptimizeMolecule(modified_mol) # Optimize geometry even if embed failed initially
            else:
                 AllChem.MMFFOptimizeMolecule(modified_mol) # Optimize geometry

            final_smiles = Chem.MolToSmiles(modified_mol)
            properties = calculate_molecular_properties(modified_mol)
            description = f"Successfully applied reaction: '{reaction_smarts}'"
            success = True
            logfire.info(f"Modification successful: '{original_smiles}' -> '{final_smiles}'")

        except Exception as post_process_error:
            logfire.error(f"Post-processing failed for modified molecule: {post_process_error}")
            final_smiles = original_smiles # Revert SMILES
            properties = calculate_molecular_properties(mol) # Properties of original
            description = f"Modification applied, but post-processing failed: {post_process_error}"
            success = False # Mark as failed if post-processing breaks

        return {
            "success": success,
            "modified_smiles": final_smiles,
            "description": description,
            "properties": properties,
            "error": None if success else description # Provide error description on failure
        }

    except Exception as e:
        error_msg = f"Error in modify_molecule_via_smarts: {str(e)}"
        logfire.error(error_msg)
        mol_fallback = Chem.MolFromSmiles(input_smiles) # Try to get original mol props
        props_fallback = calculate_molecular_properties(mol_fallback) if mol_fallback else {}
        return {
            "success": False,
            "modified_smiles": input_smiles, # Return original SMILES on failure
            "description": f"Modification failed: {str(e)}",
            "properties": props_fallback,
            "error": str(e)
        }

@molecule_builder_agent.tool_plain
async def build_molecule_from_smiles(smiles: str, output_format: str = "pdb", output_dir: Optional[str] = None) -> MoleculeBuilderResult:
    """
    Creates a molecule from a SMILES string and saves it to a file.
    
    Args:
        smiles: SMILES representation of the molecule
        output_format: File format (pdb, sdf, mol, pdbqt)
        output_dir: Directory to save the file (default: ./molecule_files)
        
    Returns:
        JSON string with path to the saved molecule file and its properties
    """
    # Log inputs for chain of thought
    function_name = "build_molecule_from_smiles"
    inputs = {"smiles": smiles, "output_format": output_format, "output_dir": output_dir}
    reasoning_steps = [f"Starting to build molecule from SMILES: {smiles}"]
    
    logfire.info(f"Building molecule from SMILES: {smiles}")
    
    output_dir = ensure_output_dir(output_dir)
    reasoning_steps.append(f"Using output directory: {output_dir}")
    
    # Generate a filename from the first 10 chars of SMILES if possible
    safe_name = ''.join(c if c.isalnum() else '_' for c in smiles[:10])
    output_path = os.path.join(output_dir, f"{safe_name}.{output_format}")
    reasoning_steps.append(f"Generated output path: {output_path}")
    
    result = None
    
    if RDKIT_AVAILABLE:
        try:
            reasoning_steps.append("RDKit is available, using it to build the molecule")
            
            # Create the molecule from SMILES
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                reasoning_steps.append(f"ERROR: Invalid SMILES string: {smiles}")
                raise ValueError(f"Invalid SMILES string: {smiles}")
            
            reasoning_steps.append("Successfully created molecule from SMILES")
            
            # Add hydrogen atoms
            mol = Chem.AddHs(mol)
            reasoning_steps.append("Added hydrogen atoms to the molecule")
            
            # Generate 3D coordinates
            AllChem.EmbedMolecule(mol, AllChem.ETKDG())
            reasoning_steps.append("Generated 3D coordinates using ETKDG method")
            
            # Optimize the structure
            AllChem.MMFFOptimizeMolecule(mol)
            reasoning_steps.append("Optimized molecular structure using MMFF")
            
            # Save to file
            file_path = save_molecule_file(mol, output_path, output_format)
            reasoning_steps.append(f"Saved molecule to file: {file_path}")
            
            # Calculate properties
            properties = calculate_molecular_properties(mol)
            reasoning_steps.append("Calculated molecular properties")
            
            result = {
                "smiles": smiles,
                "molecule_path": file_path,
                "molecule_format": output_format,
                "properties": properties,
                "description": f"Molecule built from SMILES: {smiles}"
            }
            
            reasoning_steps.append("Successfully completed molecule building process")
            
        except Exception as e:
            error_msg = f"Error building molecule: {str(e)}"
            reasoning_steps.append(f"ERROR: {error_msg}")
            logfire.error(error_msg)
            
            # Fallback to simple molecule
            reasoning_steps.append("Falling back to simple water molecule")
            file_path = generate_simple_molecule(safe_name)
            
            result = {
                "smiles": "O",  # Water
                "molecule_path": file_path,
                "molecule_format": "pdb",
                "properties": MoleculeProperties().dict(),
                "description": f"Fallback water molecule (error: {str(e)})"
            }
    else:
        # RDKit not available, use fallback
        reasoning_steps.append("RDKit not available, falling back to simple water molecule")
        file_path = generate_simple_molecule(safe_name)
        
        result = {
            "smiles": "O",  # Water
            "molecule_path": file_path,
            "molecule_format": "pdb",
            "properties": MoleculeProperties().dict(),
            "description": "Fallback water molecule (RDKit not available)"
        }
    
    # Log to chain of thought
    log_chain_of_thought(
        session_id=session_id,
        function_name=function_name,
        inputs=inputs,
        reasoning=reasoning_steps,
        decisions=[{"decision": f"Created molecule with format {output_format}"}],
        output=result
    )
    
    return MoleculeBuilderResult(**result)

@molecule_builder_agent.tool_plain
async def calculate_properties(molecule_input: str) -> str:
    """
    Calculates physicochemical properties of a molecule.
    
    Args:
        molecule_input: SMILES string or path to molecule file
        
    Returns:
        JSON string with molecular properties
    """
    # Log inputs for chain of thought
    function_name = "calculate_properties"
    inputs = {"molecule_input": molecule_input}
    reasoning_steps = [f"Starting property calculation for: {molecule_input}"]
    
    if not RDKIT_AVAILABLE:
        # Return dummy properties if RDKit is not available
        reasoning_steps.append("RDKit not available, returning dummy properties")
        
        dummy_props = MoleculeProperties().dict()
        
        # Log to chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Used dummy properties due to missing RDKit"}],
            output=dummy_props
        )
        
        return json.dumps(dummy_props)
    
    try:
        # Determine if input is a SMILES string or file path
        if os.path.exists(molecule_input):
            reasoning_steps.append(f"Input is a file path: {molecule_input}")
            
            # Read molecule from file
            file_ext = os.path.splitext(molecule_input)[1].lower()
            if file_ext == ".pdb":
                reasoning_steps.append("Detected PDB format")
                mol = Chem.MolFromPDBFile(molecule_input)
            elif file_ext == ".mol":
                reasoning_steps.append("Detected MOL format")
                mol = Chem.MolFromMolFile(molecule_input)
            elif file_ext == ".sdf":
                reasoning_steps.append("Detected SDF format")
                supplier = Chem.SDMolSupplier(molecule_input)
                mol = next(supplier) if supplier else None
            else:
                # Try to guess format
                reasoning_steps.append("Unrecognized format, attempting to guess")
                mol = Chem.MolFromPDBFile(molecule_input)
                if mol is None:
                    reasoning_steps.append("PDB format failed, trying MOL format")
                    mol = Chem.MolFromMolFile(molecule_input)
        else:
            # Assume input is SMILES
            reasoning_steps.append(f"Input appears to be a SMILES string: {molecule_input}")
            mol = Chem.MolFromSmiles(molecule_input)
        
        if mol is None:
            error_msg = f"Could not parse molecule from input: {molecule_input}"
            reasoning_steps.append(f"ERROR: {error_msg}")
            raise ValueError(error_msg)
        
        reasoning_steps.append("Successfully parsed molecule, calculating properties")
        
        # Calculate properties
        properties = calculate_molecular_properties(mol)
        
        # Add summary of key properties
        prop_dict = properties
        reasoning_steps.append(f"Calculated properties: MW={prop_dict['molecular_weight']:.2f}, " +
                               f"logP={prop_dict['logp']:.2f}, HBA={prop_dict['num_hba']}, " +
                               f"HBD={prop_dict['num_hbd']}")
        
        # Log to chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Successfully calculated molecular properties"}],
            output=prop_dict
        )
        
        return json.dumps(prop_dict)
        
    except Exception as e:
        error_msg = f"Error calculating properties: {str(e)}"
        reasoning_steps.append(f"ERROR: {error_msg}")
        logfire.error(error_msg)
        
        dummy_props = MoleculeProperties().dict()
        
        # Log to chain of thought with error
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Used dummy properties due to error"}],
            output=dummy_props
        )
        
        return json.dumps(dummy_props)

@molecule_builder_agent.tool_plain
async def generate_3d_conformation(molecule_input: str, output_format: str = "pdb", 
                                 output_path: Optional[str] = None) -> str:
    """
    Generates a 3D conformation for a molecule.
    
    Args:
        molecule_input: SMILES string or path to molecule file
        output_format: File format for output (pdb, sdf, pdbqt)
        output_path: Path for saving the 3D structure (default: auto-generated)
        
    Returns:
        JSON string with path to the 3D conformation file
    """
    # Log inputs for chain of thought
    function_name = "generate_3d_conformation"
    inputs = {"molecule_input": molecule_input, "output_format": output_format, "output_path": output_path}
    reasoning_steps = [f"Starting 3D conformation generation for: {molecule_input}"]
    
    if not RDKIT_AVAILABLE:
        # Generate a simple molecule if RDKit is not available
        reasoning_steps.append("RDKit not available, generating simple molecule")
        
        if output_path is None:
            output_dir = ensure_output_dir()
            output_path = os.path.join(output_dir, f"conformation.{output_format}")
            reasoning_steps.append(f"Generated output path: {output_path}")
            
        simple_path = generate_simple_molecule(os.path.basename(output_path).split('.')[0])
        reasoning_steps.append(f"Generated simple molecule at {simple_path}")
        
        result = {
            "molecule_path": simple_path,
            "molecule_format": "pdb",
            "description": "Simple 3D structure (RDKit not available)"
        }
        
        # Log to chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Generated simple water molecule due to missing RDKit"}],
            output=result
        )
        
        return json.dumps(result)
    
    try:
        # Determine if input is a SMILES string or file path
        if os.path.exists(molecule_input):
            reasoning_steps.append(f"Input is a file path: {molecule_input}")
            
            # Read molecule from file
            file_ext = os.path.splitext(molecule_input)[1].lower()
            if file_ext == ".pdb":
                reasoning_steps.append("Detected PDB format")
                mol = Chem.MolFromPDBFile(molecule_input)
            elif file_ext == ".mol":
                reasoning_steps.append("Detected MOL format")
                mol = Chem.MolFromMolFile(molecule_input)
            elif file_ext == ".sdf":
                reasoning_steps.append("Detected SDF format")
                supplier = Chem.SDMolSupplier(molecule_input)
                mol = next(supplier) if supplier else None
            else:
                # Try to guess format
                reasoning_steps.append("Unrecognized format, attempting to guess")
                mol = Chem.MolFromPDBFile(molecule_input)
                if mol is None:
                    reasoning_steps.append("PDB format failed, trying MOL format")
                    mol = Chem.MolFromMolFile(molecule_input)
        else:
            # Assume input is SMILES
            reasoning_steps.append(f"Input appears to be a SMILES string: {molecule_input}")
            mol = Chem.MolFromSmiles(molecule_input)
        
        if mol is None:
            error_msg = f"Could not parse molecule from input: {molecule_input}"
            reasoning_steps.append(f"ERROR: {error_msg}")
            raise ValueError(error_msg)
        
        reasoning_steps.append("Successfully parsed molecule, generating 3D coordinates")
        
        # Generate 3D coordinates
        mol = Chem.AddHs(mol)
        reasoning_steps.append("Added hydrogen atoms")
        
        AllChem.EmbedMolecule(mol, AllChem.ETKDG())
        reasoning_steps.append("Embedded molecule using ETKDG method")
        
        AllChem.MMFFOptimizeMolecule(mol)
        reasoning_steps.append("Optimized structure using MMFF force field")
        
        # Save to file
        if output_path is None:
            output_dir = ensure_output_dir()
            if isinstance(molecule_input, str) and os.path.exists(molecule_input):
                base_name = os.path.splitext(os.path.basename(molecule_input))[0]
                reasoning_steps.append(f"Using base name from input file: {base_name}")
            else:
                # Generate name from first few characters of SMILES
                safe_chars = ''.join(c if c.isalnum() else '_' for c in molecule_input[:10])
                base_name = f"molecule_{safe_chars}"
                reasoning_steps.append(f"Generated base name from SMILES: {base_name}")
            
            output_path = os.path.join(output_dir, f"{base_name}_3d.{output_format}")
            reasoning_steps.append(f"Generated output path: {output_path}")
        
        file_path = save_molecule_file(mol, output_path, output_format)
        reasoning_steps.append(f"Saved 3D conformation to: {file_path}")
        
        result = {
            "molecule_path": file_path,
            "molecule_format": output_format,
            "description": "3D conformation generated"
        }
        
        # Log to chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": f"Generated 3D conformation in {output_format} format"}],
            output=result
        )
        
        return json.dumps(result)
        
    except Exception as e:
        error_msg = f"Error generating 3D conformation: {str(e)}"
        reasoning_steps.append(f"ERROR: {error_msg}")
        logfire.error(error_msg)
        
        # Generate a simple molecule as fallback
        reasoning_steps.append("Falling back to simple molecule")
        
        if output_path is None:
            output_dir = ensure_output_dir()
            output_path = os.path.join(output_dir, f"conformation.{output_format}")
            
        simple_path = generate_simple_molecule(os.path.basename(output_path).split('.')[0])
        reasoning_steps.append(f"Generated simple molecule at {simple_path}")
        
        result = {
            "molecule_path": simple_path,
            "molecule_format": "pdb",
            "description": f"Fallback simple 3D structure due to error: {str(e)}"
        }
        
        # Log to chain of thought with error
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Generated simple water molecule due to error"}],
            output=result
        )
        
        return json.dumps(result)

async def create_default_ligand(binding_site_info, output_dir=None):
    """Create a default ligand for testing"""
    try:
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "molecules")
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a simple molecule (benzene)
        smiles = "c1ccccc1"
        result = await build_molecule_from_smiles(smiles, "pdbqt", output_dir)
        return result.molecule_path
        
    except Exception as e:
        logfire.error(f"Error creating default ligand: {str(e)}")
        raise

async def prepare_ligand_for_docking(binding_site_info, output_dir=None):
    """
    Prepares a ligand file for docking based on binding site information.
    """
    try:
        # Initialize chain of thought logging
        session_id = str(uuid.uuid4())
        reasoning_steps = []
        decisions = []
        
        # Log input parameters
        input_params = {
            "binding_site_info": binding_site_info,
            "output_dir": output_dir
        }
        
        # Create a default ligand file
        reasoning_steps.append("Creating default ligand for binding site")
        ligand_path = await create_default_ligand(binding_site_info, output_dir)
        reasoning_steps.append(f"Default ligand created at: {ligand_path}")
        
        # Log the chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name="prepare_ligand_for_docking",
            inputs=input_params,
            reasoning=reasoning_steps,
            decisions=decisions,
            output={"ligand_path": ligand_path}
        )
        
        return ligand_path
        
    except Exception as e:
        logfire.error(f"Error preparing ligand for docking: {str(e)}")
        raise

# Define the run method (New implementation)
async def run_molecule_builder(input_data: Dict[str, Any]) -> MoleculeBuilderResult:
    """
    Runs the molecule building workflow, driven by agent-specified modifications.
    """
    session_id = input_data.get("session_id", str(uuid.uuid4())) 
    function_name = "run_molecule_builder"
    inputs = input_data
    reasoning_steps = []
    decisions = []

    try:
        # Extract input parameters
        binding_site_info = input_data.get('binding_site_info', {})
        previous_results = input_data.get('previous_results', [])
        iteration = input_data.get('iteration', 0)
        max_iterations = input_data.get('max_iterations', 10)
        output_format = "pdb"
        output_dir = ensure_output_dir(input_data.get('output_dir'))

        logfire.info(f"--- Running Molecule Builder: Iteration {iteration} ---")
        reasoning_steps.append(f"Start Iteration {iteration}")

        final_smiles = ""
        description = ""
        terminate = False
        termination_reason = None

        # Initial molecule for first iteration
        if iteration == 0:
            final_smiles = "c1ccccc1"  # Start with benzene
            description = "Iteration 0: Starting with benzene as a foundational scaffold for optimization."
            reasoning_steps.append("Iteration 0: Using benzene as initial scaffold due to its versatility and potential for modification.")
            decisions.append({"decision": "Use initial scaffold", "smiles": final_smiles, "rationale": "Benzene provides a good starting point for aromatic interactions and further modifications."})
        else:
            reasoning_steps.append(f"Iteration {iteration}: Analyzing previous results and binding site characteristics.")
            
            if not previous_results:
                logfire.warning("No previous results found. Using initial scaffold.")
                final_smiles = "c1ccccc1"
                description = f"Iteration {iteration}: No previous results available. Starting fresh with benzene scaffold."
                decisions.append({"decision": "Use initial scaffold", "smiles": final_smiles, "rationale": "No previous results to build upon."})
            else:
                try:
                    # Sort results by binding affinity
                    sorted_results = sorted(previous_results, key=lambda r: r['docking'].binding_affinity)
                    best_prev = sorted_results[0]
                    prev_smiles = best_prev['molecule'].smiles
                    prev_affinity = best_prev['docking'].binding_affinity
                    
                    # Analyze binding site characteristics
                    pocket_volume = binding_site_info.get('volume', 0)
                    polar_area = binding_site_info.get('polar_area', 0)
                    apolar_area = binding_site_info.get('apolar_area', 0)
                    key_residues = binding_site_info.get('residues', [])
                    
                    # Analyze previous molecule properties
                    prev_props = best_prev['molecule'].properties
                    
                    # Agent analysis of the situation
                    analysis = {
                        "binding_site": {
                            "volume": pocket_volume,
                            "polarity_ratio": polar_area / (polar_area + apolar_area) if (polar_area + apolar_area) > 0 else 0.5,
                            "key_residues": key_residues
                        },
                        "current_molecule": {
                            "smiles": prev_smiles,
                            "affinity": prev_affinity,
                            "mw": prev_props.molecular_weight,
                            "logp": prev_props.logp,
                            "hbd": prev_props.num_hbd,
                            "hba": prev_props.num_hba,
                            "tpsa": prev_props.tpsa
                        },
                        "iteration_history": [
                            {
                                "iteration": r['iteration'],
                                "affinity": r['docking'].binding_affinity,
                                "smiles": r['molecule'].smiles
                            } for r in sorted_results
                        ]
                    }
                    
                    # Agent decision making based on analysis
                    reaction_strategy = ""
                    if analysis["binding_site"]["polarity_ratio"] > 0.6 and prev_props.num_hbd + prev_props.num_hba < 4:
                        # Add polar groups if binding site is predominantly polar
                        reaction_strategy = "[cH:1]>>[c:1](O)"  # Add hydroxyl
                        strategy_reason = "Adding polar group to improve interactions with polar binding site."
                    elif analysis["binding_site"]["polarity_ratio"] < 0.4 and prev_props.logp < 3:
                        # Add lipophilic groups if binding site is predominantly hydrophobic
                        reaction_strategy = "[cH:1]>>[c:1](C)"  # Add methyl
                        strategy_reason = "Adding hydrophobic group to improve interactions with apolar binding site."
                    else:
                        # Try scaffold hopping for more diverse exploration
                        reaction_strategy = "[c:1]1[cH:2][cH:3][cH:4][cH:5][cH:6]1>>[c:1]1[n:2][cH:3][cH:4][cH:5][cH:6]1"
                        strategy_reason = "Performing scaffold hop to explore new chemical space."
                    
                    reasoning_steps.append(f"Analysis: Binding site polarity ratio = {analysis['binding_site']['polarity_ratio']:.2f}")
                    reasoning_steps.append(f"Strategy: {strategy_reason}")
                    
                    # Apply the chosen modification
                    mod_result = await modify_molecule_via_smarts(
                        input_smiles=prev_smiles,
                        reaction_smarts=reaction_strategy
                    )
                    
                    if mod_result["success"]:
                        final_smiles = mod_result["modified_smiles"]
                        description = f"Iteration {iteration}: {strategy_reason} New SMILES: {final_smiles}"
                        decisions.append({
                            "decision": "Apply modification",
                            "strategy": strategy_reason,
                            "smiles": final_smiles
                        })
                    else:
                        final_smiles = prev_smiles
                        description = f"Iteration {iteration}: Modification failed ({mod_result['error']}). Maintaining previous structure."
                        decisions.append({
                            "decision": "Maintain previous structure",
                            "reason": f"Modification failed: {mod_result['error']}"
                        })
                    
                    # Intelligent termination criteria
                    if len(previous_results) >= 3:
                        recent_affinities = [r['docking'].binding_affinity for r in sorted_results[:3]]
                        affinity_improvements = [abs(recent_affinities[i] - recent_affinities[i+1]) for i in range(len(recent_affinities)-1)]
                        
                        # Check for diminishing returns
                        if all(imp < 0.5 for imp in affinity_improvements):  # Less than 0.5 kcal/mol improvement
                            terminate = True
                            termination_reason = "Optimization has reached convergence (diminishing returns in binding affinity improvements)."
                            final_smiles = prev_smiles  # Revert to best result
                            description = f"Iteration {iteration}: Terminating due to convergence. Final structure: {final_smiles}"
                            decisions.append({
                                "decision": "Terminate optimization",
                                "reason": "Convergence reached",
                                "final_smiles": final_smiles
                            })
                
                except Exception as e:
                    logfire.error(f"Error in molecule optimization: {str(e)}")
                    final_smiles = "c1ccccc1"
                    description = f"Iteration {iteration}: Error in optimization process. Reverting to base scaffold."
                    decisions.append({
                        "decision": "Use fallback scaffold",
                        "reason": f"Error: {str(e)}"
                    })

        # Build the final molecule
        logfire.info(f"Building molecule for SMILES: '{final_smiles}'")
        builder_output = await build_molecule_from_smiles(
            smiles=final_smiles,
            output_format=output_format,
            output_dir=output_dir
        )

        # Update result object
        builder_output.description = description
        builder_output.terminate = terminate
        builder_output.termination_reason = termination_reason

        # Check for max iterations
        if not builder_output.terminate and iteration + 1 >= max_iterations:
            builder_output.terminate = True
            builder_output.termination_reason = "Maximum iterations reached."
            reasoning_steps.append("Maximum iterations reached.")
            decisions.append({"decision": "Terminate due to max iterations"})

        # Log chain of thought
        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=decisions,
            output=builder_output.dict()
        )

        logfire.info(f"--- Molecule Builder Finished: Iteration {iteration} ---")
        return builder_output

    except Exception as e:
        logfire.error(f"Critical error in molecule builder: {str(e)}")
        reasoning_steps.append(f"Critical error: {str(e)}")
        fallback_result = await build_molecule_from_smiles("O", "pdb", output_dir)
        fallback_result.description = f"Critical error in builder run: {str(e)}"
        fallback_result.terminate = True
        fallback_result.termination_reason = f"Critical error: {str(e)}"

        log_chain_of_thought(
            session_id=session_id,
            function_name=function_name,
            inputs=inputs,
            reasoning=reasoning_steps,
            decisions=[{"decision": "Use fallback molecule", "reason": "Critical error"}],
            output=fallback_result.dict()
        )
        return fallback_result

# Register the new run method
molecule_builder_agent.run = run_molecule_builder