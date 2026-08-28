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

## 3a. Installer les dependances (avec uv)

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

## 3b. Installer les dependances (avec pip, sans uv)

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

## 4. Choisir un exemple et ses donnees

Il n'y a pas de pipeline a la racine de `gemini-pipeline`. Chaque exemple vit
dans son propre dossier sous `examples\`, avec son `pipeline.yaml`, son
`README.md` et son dossier `data\` :

```powershell
dir C:\COD3S\gemini-pipeline\examples
```

```
C:\COD3S\gemini-pipeline\examples\<exemple>\
├── pipeline.yaml     ← le pipeline a lancer
├── README.md         ← ce dont cet exemple a besoin
└── data\             ← ses donnees
```

Certains exemples embarquent des donnees de demonstration et tournent tels
quels. D'autres attendent des CSV que vous fournissez : leur `README.md` dit
lesquels et dans quel sous-dossier de `data\` les poser. Lire ce fichier
avant de lancer quoi que ce soit.

Creer un sous-dossier manquant :

```powershell
mkdir C:\COD3S\gemini-pipeline\examples\<exemple>\data
```

---

## 5. Lancer un exemple avec l'Observatory

Se placer **dans le dossier de l'exemple** : les chemins de son `pipeline.yaml`
sont relatifs a ce dossier, donc le lancer d'ailleurs ne trouvera pas les
donnees.

### Avec uv

```powershell
cd C:\COD3S\gemini-pipeline\examples\<exemple>
uv run cod3s-data run pipeline.yaml --observatory
```

### Avec pip (venv active)

```powershell
cd C:\COD3S\gemini-pipeline\examples\<exemple>
cod3s-data run pipeline.yaml --observatory
```

Ouvrir un navigateur a l'adresse :

```
http://127.0.0.1:8765
```

L'onglet **Topology** affiche le graphe du pipeline en temps reel avec les
animations de flux de donnees.

### Options utiles

| Option | Description |
|--------|-------------|
| `--observatory-port 9000` | Changer le port (defaut : 8765) |
| `--log-level DEBUG` | Logs detailles dans le terminal |
| `--interactive` | Attend que l'Observatory soit pret avant de demarrer |

Pour arreter le pipeline : `Ctrl+C` dans le terminal.

---

## 6. Depannage

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

### "Error: Configuration file not found: pipeline.yaml"

Vous n'etes pas dans le dossier de l'exemple. Faire `cd` dans
`C:\COD3S\gemini-pipeline\examples\<exemple>` avant de lancer la commande.

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
