import os
import sys
import argparse
import glob
import time
from pprint import pprint
from dotenv import load_dotenv

# Import our Molecule Docking Agent
from core.agents.molecule_docking_agent import MoleculeDockingAgent, DockingParameters, molecule_docking_agent

def parse_config_file(config_path):
    """Parse a Vina configuration file"""
    config = {}
    
    with open(config_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            parts = line.split('=', 1)
            if len(parts) != 2:
                continue
                
            key = parts[0].strip()
            value = parts[1].strip()
            
            # Try to convert to appropriate type
            try:
                if '.' in value:
                    config[key] = float(value)
                else:
                    config[key] = int(value)
            except ValueError:
                config[key] = value
    
    return config

def run_from_config(args):
    """Run docking using a config file - simplified version that skips preparation"""
    print("\n== Running Docking from Config File ==")
    
    # Parse config file
    print(f"Parsing config file: {args.config}")
    config = parse_config_file(args.config)
    
    # Extract docking parameters
    receptor_path = config.get('receptor')
    ligand_path = config.get('ligand')
    
    center = [
        config.get('center_x', 0.0),
        config.get('center_y', 0.0),
        config.get('center_z', 0.0)
    ]
    
    box_size = [
        config.get('size_x', 20.0),
        config.get('size_y', 20.0),
        config.get('size_z', 20.0)
    ]
    
    exhaustiveness = config.get('exhaustiveness', 8)
    num_modes = config.get('num_modes', 9)
    energy_range = config.get('energy_range', 3.0)
    
    print(f"Config parameters:")
    print(f"  Receptor: {receptor_path}")
    print(f"  Ligand: {ligand_path}")
    print(f"  Center: {center}")
    print(f"  Box size: {box_size}")
    print(f"  Exhaustiveness: {exhaustiveness}")
    print(f"  Number of modes: {num_modes}")
    print(f"  Energy range: {energy_range}")
    
    # Initialize the agent
    agent = MoleculeDockingAgent()
    
    # Create output directory if needed
    if args.output:
        os.makedirs(args.output, exist_ok=True)
    
    start_time = time.time()
    
    # SKIP preparation steps and use files directly
    print("\nUsing provided PDBQT files directly...")
    prepared_receptor = receptor_path
    prepared_ligand = ligand_path
    
    # Set up docking parameters
    docking_output = os.path.join(args.output, "docked.pdbqt") if args.output else None
    
    params = DockingParameters(
        receptor_path=prepared_receptor,
        ligand_path=prepared_ligand,
        center=center,
        box_size=box_size,
        exhaustiveness=exhaustiveness,
        num_modes=num_modes,
        energy_range=energy_range,
        scoring_function=args.scoring,
        output_path=docking_output
    )
    
    # Step 4: Perform docking
    print("\nPerforming docking...")
    
    try:
        docking_results = agent.perform_docking(params)
        
        # Print results - WITH ADDED ERROR HANDLING
        print("\nDocking Results:")
        print("=" * 60)
        
        if docking_results is None or len(docking_results) == 0:
            print("No docking results returned.")
        else:
            for i, result in enumerate(docking_results):
                print(f"Pose {i+1}:")
                print(f"  Binding Affinity: {result.binding_affinity:.2f} kcal/mol")
                if result.rmsd_lb is not None:
                    print(f"  RMSD (lower bound): {result.rmsd_lb:.2f} Å")
                if result.rmsd_ub is not None:
                    print(f"  RMSD (upper bound): {result.rmsd_ub:.2f} Å")
                print()
        
            # Step 5: Analyze best pose
            if docking_results:
                print("\nAnalyzing interactions for best pose...")
                best_pose = docking_results[0].pose_path
                
                # Check if the pose file exists
                if not os.path.exists(best_pose):
                    print(f"Warning: Pose file {best_pose} not found.")
                    if os.path.exists(docking_output):
                        print(f"Using output file {docking_output} instead.")
                        best_pose = docking_output
                    else:
                        print("No pose file available for analysis.")
                        raise FileNotFoundError("No pose file available for analysis")
                
                interactions = agent.analyze_interactions(prepared_receptor, best_pose)
                
                # Make sure output directory exists for JSON
                if args.output:
                    os.makedirs(args.output, exist_ok=True)
                    
                    try:
                        import json
                        json_path = os.path.join(args.output, "docking_results.json")
                        with open(json_path, 'w') as f:
                            json_data = [result.dict() for result in docking_results]
                            json.dump(json_data, f, indent=4)
                        print(f"\nDocking results saved to {json_path}")
                    except Exception as e:
                        print(f"Error saving JSON results: {e}")
                
                print("\nKey Interactions:")
                print("=" * 60)
                for interaction in interactions:
                    print(f"{interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number}")
                    print(f"  Distance: {interaction.distance:.2f} Å")
                    print(f"  Strength: {interaction.strength}")
                    print()
                
                # Step 6: Generate visualization
                if args.visualize:
                    print("\nGenerating visualization...")
                    viz_path = agent.generate_visualization(prepared_receptor, best_pose)
                    print(f"Visualization script generated: {viz_path}")
                    
                    interaction_map = agent.generate_interaction_map(best_pose, interactions)
                    print(f"Interaction map generated: {interaction_map}")
    except Exception as e:
        print(f"Docking error: {e}")
        print("\nTIP: Make sure you have installed vina with 'pip install vina'")
        print("If you see errors about Python bindings, try 'pip install openbabel'")
    
    elapsed_time = time.time() - start_time
    print(f"\nDocking completed in {elapsed_time:.2f} seconds")

def run_basic_docking(args):
    """Run a basic docking experiment"""
    print("\n== Running Basic Docking ==")
    
    # Initialize the agent
    agent = MoleculeDockingAgent()
    
    # Create output directory if needed
    if args.output:
        os.makedirs(args.output, exist_ok=True)
    
    start_time = time.time()
    
    # Step 1: Prepare receptor
    print("\nPreparing receptor...")
    receptor_output = os.path.join(args.output, "receptor.pdbqt") if args.output else None
    prepared_receptor = agent.prepare_receptor(
        args.receptor, 
        output_path=receptor_output,
        box_center=args.center,
        box_size=args.box_size,
        generate_gpf=True
    )
    print(f"Prepared receptor: {prepared_receptor}")
    
    # Step 2: Prepare ligand
    print("\nPreparing ligand...")
    ligand_output = os.path.join(args.output, "ligand.pdbqt") if args.output else None
    prepared_ligand = agent.prepare_ligand(
        args.ligand, 
        output_path=ligand_output,
        add_hydrogens=True
    )
    print(f"Prepared ligand: {prepared_ligand}")
    
    # Step 3: Set up docking parameters
    docking_output = os.path.join(args.output, "docked.pdbqt") if args.output else None
    
    params = DockingParameters(
        receptor_path=prepared_receptor,
        ligand_path=prepared_ligand,
        center=args.center,
        box_size=args.box_size,
        exhaustiveness=args.exhaustiveness,
        scoring_function=args.scoring,
        output_path=docking_output
    )
    
    # Step 4: Perform docking
    print("\nPerforming docking...")
    docking_results = agent.perform_docking(params)
    
    # Print results
    print("\nDocking Results:")
    print("=" * 60)
    for i, result in enumerate(docking_results):
        print(f"Pose {i+1}:")
        print(f"  Binding Affinity: {result.binding_affinity:.2f} kcal/mol")
        if result.rmsd_lb is not None:
            print(f"  RMSD (lower bound): {result.rmsd_lb:.2f} Å")
        if result.rmsd_ub is not None:
            print(f"  RMSD (upper bound): {result.rmsd_ub:.2f} Å")
        print()
    
    # Step 5: Analyze best pose
    if docking_results:
        print("\nAnalyzing interactions for best pose...")
        best_pose = docking_results[0].pose_path
        interactions = agent.analyze_interactions(prepared_receptor, best_pose)
        
        print("\nKey Interactions:")
        print("=" * 60)
        for interaction in interactions:
            print(f"{interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number}")
            print(f"  Distance: {interaction.distance:.2f} Å")
            print(f"  Strength: {interaction.strength}")
            print()
        
        # Step 6: Generate visualization
        if args.visualize:
            print("\nGenerating visualization...")
            viz_path = agent.generate_visualization(prepared_receptor, best_pose)
            print(f"Visualization script generated: {viz_path}")
            
            interaction_map = agent.generate_interaction_map(best_pose, interactions)
            print(f"Interaction map generated: {interaction_map}")
    
    elapsed_time = time.time() - start_time
    print(f"\nDocking completed in {elapsed_time:.2f} seconds")

def run_flexible_docking(args):
    """Run a flexible docking experiment"""
    print("\n== Running Flexible Docking ==")
    
    # Initialize the agent
    agent = MoleculeDockingAgent()
    
    # Create output directory if needed
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        
    start_time = time.time()
    
    # Step 1: Prepare receptor with flexible residues
    print("\nPreparing receptor with flexible residues...")
    receptor_output = os.path.join(args.output, "receptor") if args.output else None
    prepared_receptor = agent.prepare_receptor(
        args.receptor, 
        output_path=receptor_output,
        flex_residues=args.flex,
        box_center=args.center,
        box_size=args.box_size,
        generate_gpf=True
    )
    print(f"Prepared receptor: {prepared_receptor}")
    
    # Step 2: Prepare ligand
    print("\nPreparing ligand...")
    ligand_output = os.path.join(args.output, "ligand.pdbqt") if args.output else None
    prepared_ligand = agent.prepare_ligand(
        args.ligand, 
        output_path=ligand_output,
        add_hydrogens=True
    )
    print(f"Prepared ligand: {prepared_ligand}")
    
    # Step 3: Set up docking parameters (with flexible residues)
    docking_output = os.path.join(args.output, "docked.pdbqt") if args.output else None
    
    # Parse flexible residues string to list
    flex_list = args.flex.split(",") if args.flex else None
    
    params = DockingParameters(
        receptor_path=prepared_receptor,
        ligand_path=prepared_ligand,
        center=args.center,
        box_size=args.box_size,
        exhaustiveness=args.exhaustiveness,
        scoring_function=args.scoring,
        flexible_residues=flex_list,
        output_path=docking_output
    )
    
    # Step 4: Perform docking
    print("\nPerforming flexible docking...")
    docking_results = agent.perform_docking(params)
    
    # Print results
    print("\nDocking Results:")
    print("=" * 60)
    for i, result in enumerate(docking_results):
        print(f"Pose {i+1}:")
        print(f"  Binding Affinity: {result.binding_affinity:.2f} kcal/mol")
        if result.rmsd_lb is not None:
            print(f"  RMSD (lower bound): {result.rmsd_lb:.2f} Å")
        if result.rmsd_ub is not None:
            print(f"  RMSD (upper bound): {result.rmsd_ub:.2f} Å")
        print()
    
    # Step 5: Analyze best pose
    if docking_results:
        print("\nAnalyzing interactions for best pose...")
        best_pose = docking_results[0].pose_path
        
        # For flexible docking, we should use the receptor_rigid.pdbqt file for analysis
        rigid_receptor = prepared_receptor.replace(".pdbqt", "_rigid.pdbqt")
        interactions = agent.analyze_interactions(rigid_receptor, best_pose)
        
        print("\nKey Interactions:")
        print("=" * 60)
        for interaction in interactions:
            print(f"{interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number}")
            print(f"  Distance: {interaction.distance:.2f} Å")
            print(f"  Strength: {interaction.strength}")
            print()
    
    elapsed_time = time.time() - start_time
    print(f"\nFlexible docking completed in {elapsed_time:.2f} seconds")

def run_virtual_screening(args):
    """Run a virtual screening experiment"""
    print("\n== Running Virtual Screening ==")
    
    # Initialize the agent
    agent = MoleculeDockingAgent()
    
    # Create output directory if needed
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        
    start_time = time.time()
    
    # Step 1: Prepare receptor
    print("\nPreparing receptor...")
    receptor_output = os.path.join(args.output, "receptor.pdbqt") if args.output else None
    prepared_receptor = agent.prepare_receptor(
        args.receptor, 
        output_path=receptor_output,
        box_center=args.center,
        box_size=args.box_size,
        generate_gpf=True
    )
    print(f"Prepared receptor: {prepared_receptor}")
    
    # Step 2: Gather ligand files
    if os.path.isdir(args.ligands):
        # Get all ligand files in directory
        ligand_patterns = ["*.sdf", "*.mol2", "*.pdb", "*.pdbqt"]
        ligand_files = []
        for pattern in ligand_patterns:
            ligand_files.extend(glob.glob(os.path.join(args.ligands, pattern)))
        
        # Limit to max number if specified
        if args.max_ligands and len(ligand_files) > args.max_ligands:
            ligand_files = ligand_files[:args.max_ligands]
    else:
        # Single ligand file specified
        ligand_files = [args.ligands]
    
    print(f"Found {len(ligand_files)} ligand files for screening")
    
    # Step 3: Perform virtual screening
    vs_output = os.path.join(args.output, "vs_results") if args.output else None
    
    print("\nPerforming virtual screening...")
    vs_results = agent.virtual_screening(
        receptor_path=prepared_receptor,
        ligand_paths=ligand_files,
        center=args.center,
        box_size=args.box_size,
        exhaustiveness=args.exhaustiveness,
        scoring_function=args.scoring,
        output_dir=vs_output
    )
    
    # Print results
    print("\nVirtual Screening Results:")
    print("=" * 60)
    print(f"Ranked list of {len(vs_results)} compounds by binding affinity:")
    print()
    
    for i, result in enumerate(vs_results):
        print(f"Rank {i+1}: {result.ligand_name}")
        print(f"  Binding Affinity: {result.binding_affinity:.2f} kcal/mol")
        print()
    
    # Analyze top hits
    if vs_results and args.analyze_top > 0:
        top_n = min(args.analyze_top, len(vs_results))
        print(f"\nAnalyzing top {top_n} compounds...")
        
        for i in range(top_n):
            result = vs_results[i]
            print(f"\nCompound {i+1}: {result.ligand_name}")
            print("-" * 40)
            
            interactions = agent.analyze_interactions(prepared_receptor, result.pose_path)
            
            print("Key Interactions:")
            for interaction in interactions:
                print(f"- {interaction.interaction_type} with {interaction.residue_name}{interaction.residue_number}")
                print(f"  Distance: {interaction.distance:.2f} Å, Strength: {interaction.strength}")
            
            # Generate visualization for top hit only
            if i == 0 and args.visualize:
                print("\nGenerating visualization for top hit...")
                viz_path = agent.generate_visualization(prepared_receptor, result.pose_path)
                print(f"Visualization script generated: {viz_path}")
    
    elapsed_time = time.time() - start_time
    print(f"\nVirtual screening completed in {elapsed_time:.2f} seconds")

def run_ai_agent(args):
    """Run the AI-based docking agent with natural language prompt"""
    print("\n== Running AI Docking Agent ==")
    
    # Load environment variables
    load_dotenv()
    
    # Build the prompt
    prompt = f"""
I want to dock the ligand in {args.ligand} into the protein receptor in {args.receptor}.
The binding site is centered at coordinates {args.center} with dimensions {args.box_size}.
Please use the {args.scoring} scoring function with an exhaustiveness of {args.exhaustiveness}.
"""
    
    if args.flex:
        prompt += f"\nTreat the residues {args.flex} as flexible during docking."
    
    prompt += """
Please perform the docking and analyze:
1. The binding affinity and pose
2. Key molecular interactions
3. Recommendations for improving the binding
"""
    
    print("\nSending prompt to AI agent:")
    print("-" * 60)
    print(prompt)
    print("-" * 60)
    
    try:
        # Run the AI agent
        print("Running AI agent (this may take some time)...")
        result = molecule_docking_agent.run(prompt)
        
        # Print the results
        print("\nDocking Analysis Results:")
        print("=" * 60)
        print(f"Receptor Information: {result.receptor_info}")
        print(f"Ligand Information: {result.ligand_info}")
        print(f"Binding Affinity: {result.binding_affinity} kcal/mol")
        
        print("\nTop Poses:")
        for i, pose in enumerate(result.top_poses):
            print(f"Pose {i+1}: Affinity {pose['binding_affinity']:.2f} kcal/mol")
        
        print("\nKey Interactions:")
        print(result.key_interactions)
        
        print("\nRecommendations:")
        print(result.recommendations)
        
    except Exception as e:
        print(f"Error running AI agent: {str(e)}")
        return False
    
    return True

def main():
    """Main function to parse arguments and run docking"""
    parser = argparse.ArgumentParser(description="Test the Molecule Docking Agent")
    
    # Mode selection
    parser.add_argument('--mode', type=str, required=True, 
                      choices=['basic', 'flexible', 'virtual_screening', 'ai', 'config'],
                      help='Docking mode to run')
    
    # Config file option (for 'config' mode)
    parser.add_argument('--config', type=str, help='Path to config file (for config mode)')
    
    # Input files
    parser.add_argument('--receptor', type=str, help='Path to receptor PDB file')
    parser.add_argument('--ligand', type=str, help='Path to ligand file for single docking')
    parser.add_argument('--ligands', type=str, help='Path to directory with ligand files for virtual screening')
    
    # Docking parameters
    parser.add_argument('--center', type=float, nargs=3, default=[15.190, 53.903, 16.917],
                      help='Center coordinates [x, y, z] for binding site')
    parser.add_argument('--box_size', type=float, nargs=3, default=[20.0, 20.0, 20.0],
                      help='Box dimensions [x, y, z] for binding site')
    parser.add_argument('--exhaustiveness', type=int, default=8,
                      help='Exhaustiveness of the docking search')
    parser.add_argument('--scoring', type=str, default='vina',
                      choices=['vina', 'ad4', 'vinardo'],
                      help='Scoring function to use')
    
    # Flexible docking
    parser.add_argument('--flex', type=str, help='Flexible residues (format: "A:315,B:124")')
    
    # Virtual screening
    parser.add_argument('--max_ligands', type=int, default=None,
                      help='Maximum number of ligands to screen')
    parser.add_argument('--analyze_top', type=int, default=3,
                      help='Number of top hits to analyze')
    
    # Output options
    parser.add_argument('--output', type=str, default='./docking_results',
                      help='Output directory')
    parser.add_argument('--visualize', action='store_true', 
                      help='Generate visualization scripts')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.mode == 'config':
        if not args.config:
            parser.error("--config is required for config mode")
    elif args.mode != 'ai':
        if not args.receptor:
            parser.error("--receptor is required")
            
        if args.mode in ['basic', 'flexible'] and not args.ligand:
            parser.error("--ligand is required for basic and flexible docking")
            
        if args.mode == 'virtual_screening' and not args.ligands:
            parser.error("--ligands is required for virtual screening")
            
        if args.mode == 'flexible' and not args.flex:
            parser.error("--flex is required for flexible docking")
    
    # Run the selected docking mode
    try:
        if args.mode == 'basic':
            run_basic_docking(args)
        elif args.mode == 'flexible':
            run_flexible_docking(args)
        elif args.mode == 'virtual_screening':
            run_virtual_screening(args)
        elif args.mode == 'ai':
            run_ai_agent(args)
        elif args.mode == 'config':
            run_from_config(args)
        
        return 0
        
    except Exception as e:
        print(f"Error during docking: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())