import os
import json
import sys
import asyncio
import logging
import re

# Add the parent directory to the path to find the core modules
sys.path.append(os.path.dirname(os.getcwd()))

# Import the necessary modules
from core.agents.molecule_builder_agent import prepare_ligand_for_docking
import logfire

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_molecule_builder")

async def main():
    """Main function to read config and build ligand"""
    # Define paths
    pdb_files_dir = os.path.abspath(os.getenv("PDB_FILES_DIR", "pdb_files"))
    vina_config_path = os.path.join(pdb_files_dir, "vina_config.txt")
    
    logger.info(f"Reading Vina config from {vina_config_path}")
    
    # Check if vina_config.txt exists
    if not os.path.exists(vina_config_path):
        logger.error(f"Vina config file not found at {vina_config_path}")
        return
    
    # Read vina_config.txt
    with open(vina_config_path, 'r') as f:
        config_text = f.read()
    
    logger.info("Successfully read Vina config")
    
    # Extract binding site information
    binding_site_info = {}
    
    # Use regex to extract all key-value pairs
    pattern = r'(\w+)\s*=\s*([^\s]+)'
    matches = re.findall(pattern, config_text)
    
    for key, value in matches:
        try:
            # Convert numeric values
            if key.startswith(('center_', 'size_')):
                binding_site_info[key] = float(value)
            else:
                binding_site_info[key] = value
        except ValueError:
            binding_site_info[key] = value
    
    # Check if we extracted the essential information
    essential_keys = ['center_x', 'center_y', 'center_z', 'size_x', 'size_y', 'size_z', 'receptor']
    missing_keys = [key for key in essential_keys if key not in binding_site_info]
    
    if missing_keys:
        logger.error(f"Missing essential information in vina_config.txt: {missing_keys}")
        return
    
    # Organize the binding site info in the expected format
    formatted_binding_site = {
        "center": {
            "x": binding_site_info['center_x'],
            "y": binding_site_info['center_y'],
            "z": binding_site_info['center_z']
        },
        "size": {
            "x": binding_site_info['size_x'],
            "y": binding_site_info['size_y'],
            "z": binding_site_info['size_z']
        },
        "protein_id": binding_site_info['receptor'].replace('.pdbqt', '')
    }
    
    logger.info("Extracted binding site information:")
    logger.info(json.dumps(formatted_binding_site, indent=2))
    
    # Generate ligand
    logger.info("Generating ligand...")
    
    try:
        # Call the prepare_ligand_for_docking function
        ligand_path = prepare_ligand_for_docking(formatted_binding_site, pdb_files_dir)
        
        logger.info(f"Ligand generated successfully at {ligand_path}")
        
        # Rename the ligand file to match the one in vina_config.txt if necessary
        expected_ligand_name = binding_site_info.get('ligand', 'ligand.pdbqt')
        expected_ligand_path = os.path.join(pdb_files_dir, expected_ligand_name)
        
        if ligand_path != expected_ligand_path:
            # Make a copy with the expected name
            import shutil
            shutil.copy(ligand_path, expected_ligand_path)
            logger.info(f"Ligand file copied to match vina_config.txt: {expected_ligand_path}")
        
        logger.info("Test completed successfully!")
        
    except Exception as e:
        logger.error(f"Error generating ligand: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())