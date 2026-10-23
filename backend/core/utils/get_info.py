from Bio.SeqUtils.ProtParam import ProteinAnalysis
from Bio.SeqUtils.ProtParamData import kd  # Kyte-Doolittle hydrophobicity scale

def extract_protein_info(sequence):
    """
    Extracts comprehensive information from a protein sequence using BioPython's ProteinAnalysis.

    Parameters:
    sequence (str): The protein sequence (e.g., "MAEPRQEF...").

    Returns:
    dict: A dictionary containing physicochemical properties and profiles of the protein.
    """
    # Initialize ProteinAnalysis with the sequence
    analysis = ProteinAnalysis(sequence)

    # Basic sequence properties
    length = len(sequence)
    aa_counts = analysis.count_amino_acids()  # Dictionary of amino acid counts
    aa_percent = analysis.amino_acids_percent  # Dictionary of amino acid percentages
    mol_weight = analysis.molecular_weight()  # Molecular weight in Daltons
    aromaticity = analysis.aromaticity()  # Fraction of aromatic amino acids (F, W, Y)
    instability_index = analysis.instability_index()  # Stability in a test tube
    pI = analysis.isoelectric_point()  # pH where net charge is zero
    secondary_structure = analysis.secondary_structure_fraction()  # Tuple: (helix, turn, sheet)
    gravy = analysis.gravy()  # Grand average of hydropathy
    flexibility = analysis.flexibility()  # List of flexibility values
    charge_at_pH7 = analysis.charge_at_pH(7.0)  # Net charge at pH 7.0
    molar_extinction = analysis.molar_extinction_coefficient()  # Tuple: (with disulfide, without)
    hydrophobicity = analysis.protein_scale(window=9, param_dict=kd)  # Hydrophobicity profile

    # Define amino acid categories
    hydrophobic = ['A', 'V', 'I', 'L', 'M', 'F', 'W', 'P']  # Non-polar
    polar_uncharged = ['G', 'S', 'T', 'C', 'Y', 'N', 'Q']  # Polar, no charge
    positive = ['K', 'R', 'H']  # Positively charged
    negative = ['D', 'E']  # Negatively charged

    # Helper function to compute fraction of a category
    def get_fraction(aa_list):
        return sum(aa_percent[aa] for aa in aa_list if aa in aa_percent)

    # Calculate category fractions
    hydrophobic_fraction = get_fraction(hydrophobic)
    polar_fraction = get_fraction(polar_uncharged)
    positive_fraction = get_fraction(positive)
    negative_fraction = get_fraction(negative)

    # Organize all information into a dictionary
    info = {
        "sequence_length": length,
        "amino_acid_counts": aa_counts,
        "amino_acid_percent": aa_percent,
        "molecular_weight": mol_weight,
        "aromaticity": aromaticity,
        "instability_index": instability_index,
        "isoelectric_point": pI,
        "secondary_structure_fraction": {
            "helix": secondary_structure[0],
            "turn": secondary_structure[1],
            "sheet": secondary_structure[2]
        },
        "gravy": gravy,
        "flexibility_profile": flexibility,
        "charge_at_pH7": charge_at_pH7,
        "molar_extinction_coefficient": {
            "with_disulfide_bonds": molar_extinction[0],
            "without_disulfide_bonds": molar_extinction[1]
        },
        "hydrophobic_fraction": hydrophobic_fraction,
        "polar_uncharged_fraction": polar_fraction,
        "positive_fraction": positive_fraction,
        "negative_fraction": negative_fraction,
        "hydrophobicity_profile": hydrophobicity
    }

    return info

# Example usage
if __name__ == "__main__":
    sequence = "MAEPRQEFEVMEDHAGTYGLGDRKDQGGYTMHQDQEGDTDAGLKESPLQTPTEDGSEEPGSETSDAKSTPTAEDVTAPLVDEGAPGKQAAAQPHTEIPEGTTAEEAGIGDTPSLEDEAAGHVTQARMVSKSKDGTGSDDKKAKGADGKTKIATPRGAAPPGQKGQANATRIPAKTPPAPKTPPSSGEPPKSGDRSGYSSPGSPGTPGSRSRTPSLPTPPTREPKKVAVVRTPPKSPSSAKSRLQTAPVPMPDLKNVKSKIGSTENLKHQPGGGKVQIINKKLDLSNVQSKCGSKDNIKHVPGGGSVQIVYKPVDLSKVTSKCGSLGNIHHKPGGGQVEVKSEKLDFKDRVQSKIGSLDNITHVPGGGNKKIETHKLTFRENAKAKTDHGAEIVYKSPVVSGDTSPRHLSNVSSTGSIDMVDSPQLATLADEVSASLAKQGL"
    info = extract_protein_info(sequence)
    print(info)