# Hallmark Report — protein-inspect feature extraction
Run on 20 structures.

| PDB | Description | All checks matched? | Time (s) |
|-----|-------------|---------------------|----------|
| 1adc | Alcohol dehydrogenase (NAD analog PAD, Zn) | 2/2 ✓ | 0.07 |
| 1aon | GroEL chaperonin (large, multi-domain, 14-mer asymmetric unit subset) | 1/1 ✓ | 2.33 |
| 1asy | Aspartyl-tRNA synthetase + tRNA | 1/1 ✓ | 0.07 |
| 1atp | PKA catalytic subunit (kinase, ATP, divalent metal) | 2/2 ✓ | 0.03 |
| 1bl8 | KcsA potassium channel (TM tetramer) | 2/2 ✓ | 0.03 |
| 1cdw | TBP-DNA complex | 1/1 ✓ | 0.01 |
| 1fxd | Ferredoxin (4Fe-4S cluster) | 1/1 ✓ | 0.01 |
| 1hsg | HIV-1 protease (Asp25-Asp25' dimer dyad) | 3/3 ✓ | 0.02 |
| 1igy | IgG immunoglobulin (multi-chain, glycosylated) | 3/3 ✓ | 0.07 |
| 1mbn | Myoglobin (heme monomer) | 2/2 ✓ | 0.01 |
| 1tim | Triosephosphate isomerase (TIM barrel dimer) | 2/2 ✓ | 0.02 |
| 1ubq | Ubiquitin (small β-grasp monomer) | 2/2 ✓ | 0.01 |
| 2omf | OmpF porin (β-barrel membrane) | 1/1 ✓ | 0.02 |
| 2rh1 | β2-adrenergic receptor (GPCR, 7TM) | 1/1 ✓ | 0.02 |
| 2zju | Ls-AChBP pentamer + imidacloprid | 4/4 ✓ | 0.06 |
| 4hhb | Hemoglobin α2β2 heterotetramer (heme) | 3/3 ✓ | 0.03 |
| 5cha | Chymotrypsin (Ser-His-Asp triad, post-cleavage chains) | 1/1 ✓ | 0.02 |
| 5pep | Pepsin (aspartyl protease, intra-chain Asp dyad) | 0/1 ✗ | 0.02 |
| 6lu7 | SARS-CoV-2 main protease (Cys-His dyad, dimer + inhibitor) | 1/1 ✓ | 0.17 |
| 7rsa | Ribonuclease A (small, 4 disulfides) | 2/2 ✓ | 0.01 |

**Overall: 35/36 expectations matched (97%)**

## Per-entry detail

### 1adc — Alcohol dehydrogenase (NAD analog PAD, Zn)
- ✓ `cofactor` expected `['NAD', 'NAI', 'NAJ', 'PAD']` → got `['PAD']`
- ✓ `metals` expected `['ZN']` → got `['ZN']`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 2, 'oligomer': 'dimer', 'homo_or_hetero': 'homo', 'symmetry': 'C2', 'unique_sequences': 1}, 'fold': {'length': 374, 'ss_fractions': {'helix': 0.40641711229946526, 'sheet': 0.5775401069518716, 'loop': 0.016042780748663103}}, 'n_metals': 1, 'metals': ['ZN'], 'n_cofactors': 1, 'cofactors': [['PAD', 'redox_2e']], 'disulfide_types': [], 'active_site_patterns': ['catalytic_triad', 'catalytic_triad', 'catalytic_triad', 'catalytic_triad', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop'], 'bio_ligands': ['EOH'], 'artifacts': {'unclassified': ['EOH']}, 'membrane_likely': False}`

### 1aon — GroEL chaperonin (large, multi-domain, 14-mer asymmetric unit subset)
- ✓ `multi_domain` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 21, 'oligomer': 'higher_order', 'homo_or_hetero': 'hetero', 'symmetry': None, 'unique_sequences': 2}, 'fold': {'length': 524, 'ss_fractions': {'helix': 0.6641221374045801, 'sheet': 0.32633587786259544, 'loop': 0.009541984732824428}}, 'n_metals': 1, 'metals': ['MG'], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad'], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 1asy — Aspartyl-tRNA synthetase + tRNA
- ✓ `macromolecule` expected `['protein_rna', 'mixed']` → got `protein_rna`
- summary excerpt: `{'macromolecule_type': 'protein_rna', 'assembly': {'n_chains': 2, 'oligomer': 'dimer', 'homo_or_hetero': 'homo', 'symmetry': 'C2', 'unique_sequences': 1}, 'fold': {'length': 490, 'ss_fractions': {'helix': 0.4857142857142857, 'sheet': 0.4857142857142857, 'loop': 0.02857142857142857}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['cys_his_dyad', 'cys_his_dyad', 'asp_dyad', 'phosphate_binding_loop', 'phosphate_binding_loop'], 'bio_ligands': ['1MG', '5MC', '5MU', 'H2U', 'PSU'], 'artifacts': {'unclassified': ['1MG', '5MC', '5MU', 'H2U', 'PSU']}, 'membrane_likely': False}`

### 1atp — PKA catalytic subunit (kinase, ATP, divalent metal)
- ✓ `free_nucleotide` expected `True` → got `True`
- ✓ `metals` expected `['MG', 'MN']` → got `['MN']`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 2, 'oligomer': 'dimer', 'homo_or_hetero': 'hetero', 'symmetry': None, 'unique_sequences': 2}, 'fold': {'length': 334, 'ss_fractions': {'helix': 0.5658682634730539, 'sheet': 0.41317365269461076, 'loop': 0.020958083832335328}}, 'n_metals': 1, 'metals': ['MN'], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['cys_his_dyad', 'asp_dyad', 'asp_dyad', 'phosphate_binding_loop', 'phosphate_binding_loop', 'phosphate_binding_loop'], 'bio_ligands': ['SEP', 'TPO'], 'artifacts': {'unclassified': ['SEP', 'TPO']}, 'membrane_likely': False}`

### 1bl8 — KcsA potassium channel (TM tetramer)
- ✓ `oligomer` expected `tetramer` → got `tetramer`
- ✓ `membrane_likely` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 4, 'oligomer': 'tetramer', 'homo_or_hetero': 'homo', 'symmetry': 'C4', 'unique_sequences': 1}, 'fold': {'length': 97, 'ss_fractions': {'helix': 0.7938144329896907, 'sheet': 0.13402061855670103, 'loop': 0.07216494845360824}}, 'n_metals': 1, 'metals': ['K'], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['asp_dyad', 'asp_dyad', 'asp_dyad', 'asp_dyad'], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': True}`

### 1cdw — TBP-DNA complex
- ✓ `macromolecule` expected `['protein_dna', 'mixed']` → got `protein_dna`
- summary excerpt: `{'macromolecule_type': 'protein_dna', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 179, 'ss_fractions': {'helix': 0.4581005586592179, 'sheet': 0.5195530726256983, 'loop': 0.0223463687150838}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 1fxd — Ferredoxin (4Fe-4S cluster)
- ✓ `iron_sulfur` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 57, 'ss_fractions': {'helix': 0.543859649122807, 'sheet': 0.43859649122807015, 'loop': 0.017543859649122806}}, 'n_metals': 1, 'metals': ['F3S'], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard'], 'active_site_patterns': [], 'bio_ligands': ['SCH'], 'artifacts': {'unclassified': ['SCH']}, 'membrane_likely': False}`

### 1hsg — HIV-1 protease (Asp25-Asp25' dimer dyad)
- ✓ `active_site_pattern` expected `asp_dyad` → got `True`
- ✓ `homo_or_hetero` expected `homo` → got `homo`
- ✓ `oligomer` expected `dimer` → got `dimer`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 2, 'oligomer': 'dimer', 'homo_or_hetero': 'homo', 'symmetry': 'C2', 'unique_sequences': 1}, 'fold': {'length': 99, 'ss_fractions': {'helix': 0.31313131313131315, 'sheet': 0.6868686868686869, 'loop': 0.0}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['asp_dyad'], 'bio_ligands': ['MK1'], 'artifacts': {'unclassified': ['MK1']}, 'membrane_likely': False}`

### 1igy — IgG immunoglobulin (multi-chain, glycosylated)
- ✓ `homo_or_hetero` expected `hetero` → got `hetero`
- ✓ `glycans` expected `True` → got `True`
- ✓ `interchain_disulfide` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 4, 'oligomer': 'tetramer', 'homo_or_hetero': 'hetero', 'symmetry': None, 'unique_sequences': 2}, 'fold': {'length': 213, 'ss_fractions': {'helix': 0.17370892018779344, 'sheet': 0.7981220657276995, 'loop': 0.028169014084507043}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard', 'standard', 'interchain', 'standard', 'standard', 'interchain', 'interchain', 'interchain', 'standard', 'standard', 'standard', 'standard', 'interchain', 'standard', 'standard', 'standard', 'standard'], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 1mbn — Myoglobin (heme monomer)
- ✓ `oligomer` expected `monomer` → got `monomer`
- ✓ `cofactor_class` expected `redox_heme` → got `{'redox_heme'}`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 153, 'ss_fractions': {'helix': 0.9215686274509803, 'sheet': 0.0718954248366013, 'loop': 0.006535947712418301}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 1, 'cofactors': [['HEM', 'redox_heme']], 'disulfide_types': [], 'active_site_patterns': [], 'bio_ligands': ['OH'], 'artifacts': {'unclassified': ['OH']}, 'membrane_likely': False}`

### 1tim — Triosephosphate isomerase (TIM barrel dimer)
- ✓ `oligomer` expected `dimer` → got `dimer`
- ✓ `homo_or_hetero` expected `homo` → got `homo`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 2, 'oligomer': 'dimer', 'homo_or_hetero': 'homo', 'symmetry': 'C2', 'unique_sequences': 1}, 'fold': {'length': 247, 'ss_fractions': {'helix': 0.6072874493927125, 'sheet': 0.3805668016194332, 'loop': 0.012145748987854251}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 1ubq — Ubiquitin (small β-grasp monomer)
- ✓ `oligomer` expected `monomer` → got `monomer`
- ✓ `macromolecule` expected `protein_only` → got `protein_only`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 76, 'ss_fractions': {'helix': 0.47368421052631576, 'sheet': 0.5263157894736842, 'loop': 0.0}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 2omf — OmpF porin (β-barrel membrane)
- ✓ `membrane_likely` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 340, 'ss_fractions': {'helix': 0.22941176470588234, 'sheet': 0.7382352941176471, 'loop': 0.03235294117647059}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {'detergent': ['C8E']}, 'membrane_likely': True}`

### 2rh1 — β2-adrenergic receptor (GPCR, 7TM)
- ✓ `membrane_likely` expected `True` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 442, 'ss_fractions': {'helix': 0.8665158371040724, 'sheet': 0.12895927601809956, 'loop': 0.004524886877828055}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard', 'standard'], 'active_site_patterns': [], 'bio_ligands': ['ACM', 'BU1', 'CAU', 'PLM'], 'artifacts': {'cryoprotectant': ['12P'], 'precipitant_salt': ['SO4'], 'unclassified': ['ACM', 'BU1', 'CAU', 'PLM']}, 'membrane_likely': True}`

### 2zju — Ls-AChBP pentamer + imidacloprid
- ✓ `oligomer` expected `pentamer` → got `pentamer`
- ✓ `vicinal_disulfide` expected `True` → got `True`
- ✓ `aromatic_cage` expected `True` → got `True`
- ✓ `bio_ligand` expected `['IM4']` → got `['IM4']`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 5, 'oligomer': 'pentamer', 'homo_or_hetero': 'homo', 'symmetry': 'C5', 'unique_sequences': 1}, 'fold': {'length': 208, 'ss_fractions': {'helix': 0.25120772946859904, 'sheet': 0.7246376811594203, 'loop': 0.024154589371980676}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard', 'vicinal', 'standard', 'vicinal', 'standard', 'vicinal', 'standard', 'vicinal', 'standard', 'vicinal'], 'active_site_patterns': ['catalytic_triad', 'catalytic_triad', 'catalytic_triad', 'catalytic_triad', 'asp_dyad', 'aromatic_cage', 'aromatic_cage', 'aromatic_cage', 'aromatic_cage', 'aromatic_cage'], 'bio_ligands': ['IM4'], 'artifacts': {'unclassified': ['IM4']}, 'membrane_likely': False}`

### 4hhb — Hemoglobin α2β2 heterotetramer (heme)
- ✓ `oligomer` expected `tetramer` → got `tetramer`
- ✓ `homo_or_hetero` expected `hetero` → got `hetero`
- ✓ `cofactor_class` expected `redox_heme` → got `{'redox_heme'}`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 4, 'oligomer': 'tetramer', 'homo_or_hetero': 'hetero', 'symmetry': None, 'unique_sequences': 2}, 'fold': {'length': 141, 'ss_fractions': {'helix': 0.8439716312056738, 'sheet': 0.12056737588652482, 'loop': 0.03546099290780142}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 1, 'cofactors': [['HEM', 'redox_heme']], 'disulfide_types': [], 'active_site_patterns': ['cys_his_dyad', 'cys_his_dyad', 'asp_dyad', 'asp_dyad'], 'bio_ligands': [], 'artifacts': {'precipitant_salt': ['PO4']}, 'membrane_likely': False}`

### 5cha — Chymotrypsin (Ser-His-Asp triad, post-cleavage chains)
- ✓ `active_site_pattern` expected `catalytic_triad` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 4, 'oligomer': 'tetramer', 'homo_or_hetero': 'hetero', 'symmetry': None, 'unique_sequences': 2}, 'fold': {'length': 8, 'ss_fractions': {'helix': 0.0, 'sheet': 1.0, 'loop': 0.0}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['interchain', 'standard', 'interchain', 'standard', 'standard', 'interchain', 'standard', 'interchain', 'standard', 'standard'], 'active_site_patterns': ['catalytic_triad', 'catalytic_triad', 'asp_dyad', 'asp_dyad'], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 5pep — Pepsin (aspartyl protease, intra-chain Asp dyad)
- ✗ `active_site_pattern` expected `asp_dyad` → got `False`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 326, 'ss_fractions': {'helix': 0.39570552147239263, 'sheet': 0.5950920245398773, 'loop': 0.009202453987730062}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard', 'standard', 'standard'], 'active_site_patterns': [], 'bio_ligands': [], 'artifacts': {}, 'membrane_likely': False}`

### 6lu7 — SARS-CoV-2 main protease (Cys-His dyad, dimer + inhibitor)
- ✓ `active_site_pattern` expected `cys_his_dyad` → got `True`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 306, 'ss_fractions': {'helix': 0.4542483660130719, 'sheet': 0.5261437908496732, 'loop': 0.0196078431372549}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': [], 'active_site_patterns': ['cys_his_dyad'], 'bio_ligands': ['010', '02J', 'PJE'], 'artifacts': {'unclassified': ['010', '02J', 'PJE']}, 'membrane_likely': False}`

### 7rsa — Ribonuclease A (small, 4 disulfides)
- ✓ `oligomer` expected `monomer` → got `monomer`
- ✓ `disulfide_count_min` expected `3` → got `4`
- summary excerpt: `{'macromolecule_type': 'protein_only', 'assembly': {'n_chains': 1, 'oligomer': 'monomer', 'homo_or_hetero': 'monomer', 'symmetry': None, 'unique_sequences': 1}, 'fold': {'length': 124, 'ss_fractions': {'helix': 0.3064516129032258, 'sheet': 0.6693548387096774, 'loop': 0.024193548387096774}}, 'n_metals': 0, 'metals': [], 'n_cofactors': 0, 'cofactors': [], 'disulfide_types': ['standard', 'standard', 'standard', 'standard'], 'active_site_patterns': [], 'bio_ligands': ['TBU'], 'artifacts': {'unclassified': ['TBU']}, 'membrane_likely': False}`

