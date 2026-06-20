"""
File: merge_gedcom_jsons.py
Summary: Merges two parsed GEDCOM JSON files into a single master JSON file 
         so they can be run through the overlay engine simultaneously for 
         consensus matching.
"""

import json
import os

def merge_json_trees(file1, file2, output_file):
    print(f"Loading Tree 1: {file1}")
    with open(file1, 'r', encoding='utf-8') as f1:
        tree1 = json.load(f1)
        
    # Tag every couple so we know they came from Tree 1
    for couple in tree1:
        couple['source_tree'] = 'Tree_1'

    print(f"Loading Tree 2: {file2}")
    with open(file2, 'r', encoding='utf-8') as f2:
        tree2 = json.load(f2)
        
    # Tag every couple so we know they came from Tree 2
    for couple in tree2:
        couple['source_tree'] = 'Tree_2'

    # Smash them together into one giant list
    combined_trees = tree1 + tree2

    print(f"Saving combined dataset to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as out:
        json.dump(combined_trees, out, indent=4)

    print(f"\nSUCCESS!")
    print(f"  -> Merged {len(tree1):,} couples from Tree 1")
    print(f"  -> Merged {len(tree2):,} couples from Tree 2")
    print(f"  -> Total couples in master JSON: {len(combined_trees):,}")

if __name__ == '__main__':
    # Define the paths to your two input JSONs and the final output JSON
    base_dir = r"E:\Users\Andy\PycharmProjects\Genealogy\gedcom_sources"
    
    # You will need to generate these two files using your normal GEDCOM parser first!
    file_1_path = os.path.join(base_dir, "tree1_couples.json")
    file_2_path = os.path.join(base_dir, "tree2_couples.json")
    
    # This is the file your GedcomNameOverlay_V2.py script will read
    output_path = os.path.join(base_dir, "gedcom_couples.json")
    
    merge_json_trees(file_1_path, file_2_path, output_path)