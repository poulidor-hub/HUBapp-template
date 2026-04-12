import os
import ast
import re

# Dossiers et fichiers à ignorer (on ignore aussi notre propre fichier d'index !)
IGNORE_DIRS = {'.git', 'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build'}
IGNORE_FILES = {'package-lock.json', 'yarn.lock', 'AI_INDEX.md'}

def get_python_signatures(filepath):
    """Extrait les classes et les fonctions d'un fichier Python avec leurs numéros de ligne."""
    signatures = []
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            node = ast.parse(file.read())
            
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                signatures.append(f"  - [Ligne {item.lineno}] Fonction : def {item.name}()")
            elif isinstance(item, ast.ClassDef):
                signatures.append(f"  - [Ligne {item.lineno}] Classe : class {item.name}")
    except Exception as e:
        signatures.append(f"  - (Erreur de lecture du fichier)")
    return signatures

def get_react_components(filepath):
    """Extrait les composants React et leurs numéros de ligne."""
    components = []
    seen_components = set()
    
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                matches = re.findall(r'(?:const|function)\s+([A-Z][a-zA-Z0-9_]*)\s*(?:=|\()', line)
                for match in matches:
                    if match not in seen_components:
                        components.append(f"  - [Ligne {line_num}] Composant : {match}")
                        seen_components.add(match)
    except Exception:
        pass
    
    return components

def generate_index(root_path, output_filename="AI_INDEX.md"):
    """Supprime l'ancien index, puis parcourt le projet pour créer le nouveau."""
    
    # 1. Suppression de l'ancien fichier s'il existe
    if os.path.exists(output_filename):
        os.remove(output_filename)
        print(f"🗑️  Ancien fichier '{output_filename}' supprimé.")
        
    # 2. Création du nouveau fichier
    with open(output_filename, 'w', encoding='utf-8') as out_file:
        out_file.write("# Index du Projet pour Assistant IA\n\n")
        out_file.write("> **Note pour l'IA** : Ceci est la carte du projet. Les numéros de ligne sont indiqués entre crochets. Demande un extrait de code spécifique (ex: Lignes 20 à 50) si tu as besoin de plus de contexte.\n\n")
        
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            
            for file in files:
                if file in IGNORE_FILES:
                    continue
                
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, root_path)
                
                if file.endswith('.py'):
                    signatures = get_python_signatures(filepath)
                    if signatures:
                        out_file.write(f"### 📄 `{rel_path}`\n")
                        for sig in signatures:
                            out_file.write(f"{sig}\n")
                        out_file.write("\n")
                    
                elif file.endswith(('.jsx', '.tsx', '.js', '.ts')):
                    components = get_react_components(filepath)
                    if components:
                        out_file.write(f"### ⚛️ `{rel_path}`\n")
                        for comp in components:
                            out_file.write(f"{comp}\n")
                        out_file.write("\n")

if __name__ == "__main__":
    project_root = "." 
    print("🚀 Démarrage de la génération de l'index...")
    generate_index(project_root)
    print("✅ Terminé ! Le fichier AI_INDEX.md est à jour.")