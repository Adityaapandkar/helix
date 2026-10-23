import requests

def fetch_uniprot_data(uniprot_id):
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return {
            "name": data["proteinDescription"]["recommendedName"]["fullName"]["value"],
            "organism": data["organism"]["scientificName"],
            "sequence": data["sequence"]["value"]
        }
    else:
        raise Exception(f"Couldn’t fetch UniProt data for {uniprot_id}. Check the ID, dude!")


# Usage
# uniprot_id = "P0DP23"

# protein_data = fetch_uniprot_data(uniprot_id)
# print(protein_data)
# print(f"Name: {protein_data['name']}")
# print(f"Organism: {protein_data['organism']}")
# print(f"Sequence: {protein_data['sequence']}")