import requests
import os

def fetch_alphafold_structure(uniprot_id):
    # Create a directory for PDB files if it doesn't exist
    pdb_dir = os.getenv("PDB_FILES_DIR", "pdb_files")
    os.makedirs(pdb_dir, exist_ok=True)

    url = f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v4.pdb"
    response = requests.get(url)
    if response.status_code == 200:
        pdb_file = os.path.join(pdb_dir, f"{uniprot_id}.pdb")
        with open(pdb_file, "w") as f:
            f.write(response.text)
        return pdb_file
    else:
        raise Exception(f"No AlphaFold structure for {uniprot_id}. Shit happens!")

# Usage
uniprot_id = "P0DP23"
pdb_file = fetch_alphafold_structure(uniprot_id)
print(f"Structure downloaded to {pdb_file}")
