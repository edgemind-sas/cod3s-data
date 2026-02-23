# Installation sur Windows

Guide d'installation du framework **cod3s-data** et du pipeline **gemini-pipeline** sur un poste Windows, avec lancement de l'Observatory (interface web de visualisation).

---

## 1. Prerequis

### Option A : uv (recommande — installe Python automatiquement)

`uv` est un gestionnaire de paquets Python qui peut telecharger et gerer ses propres versions de Python. **Meme si le PC a deja un Python 3.10 ou plus ancien, `uv` installera automatiquement Python 3.12+** sans toucher a l'installation existante.

Installer `uv` dans PowerShell :

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

Fermer et rouvrir le terminal, puis verifier :

```powershell
uv --version
```

> `uv` installera Python 3.12+ automatiquement lors du premier `uv sync` (car le projet exige `requires-python = ">=3.12"`). Aucune installation manuelle de Python n'est necessaire.

### Option B : Python manuel (si uv n'est pas disponible)

Si l'installation de `uv` n'est pas possible, installer Python manuellement :

1. Telecharger Python 3.12+ depuis <https://www.python.org/downloads/>
2. Lancer l'installateur et **cocher "Add python.exe to PATH"** avant de cliquer sur "Install Now"
3. Verifier dans un terminal PowerShell :

```powershell
python --version
# Python 3.12.x ou 3.13.x
```

> La procedure pip (section 4b) sera utilisee pour installer les dependances.

---

## 2. Recuperer les sources

Telecharger les archives ZIP des deux projets et les extraire **cote a cote** dans un meme dossier :

```
C:\COD3S\
├── cod3s-data\          ← le framework
└── gemini-pipeline\     ← le pipeline Gemini 3D
```

> Les noms de dossiers doivent etre exactement `cod3s-data` et `gemini-pipeline` (sans suffixe `-main` ou autre). Si le ZIP extrait un sous-dossier (ex: `cod3s-data-main\`), le renommer.

---

## 3. Adapter le chemin de dependance locale

Le fichier `gemini-pipeline\pyproject.toml` contient un chemin absolu Linux qu'il faut remplacer.

Ouvrir `C:\COD3S\gemini-pipeline\pyproject.toml` dans un editeur de texte et remplacer la section :

```toml
[tool.uv.sources]
cod3s-data = { path = "/home/gurvan/Dev/COD3S/cod3s-data", editable = true }
```

par :

```toml
[tool.uv.sources]
cod3s-data = { path = "../cod3s-data", editable = true }
```

Sauvegarder le fichier.

---

## 4a. Installer les dependances (avec uv)

### Installer cod3s-data

```powershell
cd C:\COD3S\cod3s-data
uv sync --extra observatory
```

### Installer gemini-pipeline

```powershell
cd C:\COD3S\gemini-pipeline
uv sync
```

### Verifier

```powershell
cd C:\COD3S\gemini-pipeline
uv run cod3s-data --version
```

---

## 4b. Installer les dependances (avec pip, sans uv)

### Creer un environnement virtuel

```powershell
cd C:\COD3S
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Si l'execution de scripts est bloquee, lancer d'abord :
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

### Installer les deux projets

```powershell
pip install -e "cod3s-data[observatory]"
pip install -e gemini-pipeline
```

### Verifier

```powershell
cod3s-data --version
```

> **Important** : avec pip, il faut activer le venv (`.\.venv\Scripts\Activate.ps1`) a chaque nouveau terminal avant de lancer les commandes.

---

## 5. Fichiers de donnees

Copier les fichiers CSV dans le dossier `data` du pipeline :

```
C:\COD3S\gemini-pipeline\
└── data\
    ├── egm.csv          (~60 Mo)
    └── vision5D.csv     (~77 Mo)
```

Creer le dossier `data` s'il n'existe pas :

```powershell
mkdir C:\COD3S\gemini-pipeline\data
```

---

## 6. Lancer le pipeline avec l'Observatory

### Avec uv

```powershell
cd C:\COD3S\gemini-pipeline
uv run cod3s-data run pipeline.yaml --observatory
```

### Avec pip (venv active)

```powershell
cd C:\COD3S\gemini-pipeline
cod3s-data run pipeline.yaml --observatory
```

Ouvrir un navigateur a l'adresse :

```
http://127.0.0.1:8765
```

L'onglet **Topology** affiche le graphe du pipeline en temps reel avec les animations de flux de donnees.

### Options utiles

| Option | Description |
|--------|-------------|
| `--observatory-port 9000` | Changer le port (defaut : 8765) |
| `--log-level DEBUG` | Logs detailles dans le terminal |
| `--interactive` | Attend que l'Observatory soit pret avant de demarrer |

Pour arreter le pipeline : `Ctrl+C` dans le terminal.

---

## 7. Depannage

### "uv : le terme 'uv' n'est pas reconnu"

Fermer et rouvrir le terminal apres l'installation de `uv`. Si le probleme persiste, ajouter manuellement le chemin d'installation a la variable `PATH` :

```powershell
$env:PATH += ";$env:USERPROFILE\.local\bin"
```

### "L'execution de scripts est desactivee sur ce systeme"

Autoriser l'execution de scripts PowerShell :

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Le navigateur affiche une page blanche ou une erreur de connexion

- Verifier que le pipeline tourne bien dans le terminal (pas d'erreur)
- Verifier le port : `http://127.0.0.1:8765`
- Si le pare-feu Windows affiche une alerte, autoriser Python / uvicorn sur le reseau prive

### Erreur "No module named 'cod3s_data'"

- **Avec uv** : s'assurer de lancer `uv run cod3s-data ...` (pas juste `cod3s-data`)
- **Avec pip** : verifier que le venv est active (le prompt doit afficher `(.venv)`)

### Erreur d'encodage sur les fichiers CSV

Si les noms de colonnes avec accents posent probleme, s'assurer que le terminal utilise UTF-8 :

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001
```

### L'Observatory ne se met pas a jour apres un rebuild frontend

Faire un hard-refresh dans le navigateur avec `Ctrl+Shift+R` pour vider le cache.
