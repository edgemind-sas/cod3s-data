# Spécifications Fonctionnelles - Framework COD3S Data

**Version** : 1.0
**Date** : 2026-01-06
**Statut** : Draft initial

---

## Table des matières

1. [Vision et Objectifs](#1-vision-et-objectifs)
2. [Concepts Métier](#2-concepts-métier)
3. [Modèle de Données](#3-modèle-de-données)
4. [Acteurs du Système](#4-acteurs-du-système)
5. [Fonctionnalités Principales](#5-fonctionnalités-principales)
6. [Règles Métier](#6-règles-métier)
7. [Flux Fonctionnels](#7-flux-fonctionnels)
8. [Cas d'Usage Détaillés](#8-cas-dusage-détaillés)
9. [Contraintes et Exigences](#9-contraintes-et-exigences)
10. [Comportements et Edge Cases](#10-comportements-et-edge-cases)
11. [Glossaire](#11-glossaire)

---

## 1. Vision et Objectifs

### 1.1 Vision

COD3S Data est un framework de gestion de flux de données temporelles permettant la collecte, le routage, le traitement et le stockage de mesures horodatées provenant de sources diverses (capteurs IoT, systèmes industriels, applications métier, etc.).

Le framework doit permettre de construire des architectures distribuées résilientes où les données circulent de manière découplée entre producteurs et consommateurs, avec possibilité de transformation, filtrage et persistance.

### 1.2 Objectifs Fonctionnels

**OF-001** : Permettre l'émission de données temporelles par des sources multiples
**OF-002** : Acheminer les données vers des destinations multiples de manière découplée
**OF-003** : Filtrer les données selon des critères métadonnées
**OF-004** : Transformer et enrichir les données en transit
**OF-005** : Persister les données dans des systèmes de stockage adaptés
**OF-006** : Générer des alertes basées sur des règles métier
**OF-007** : Simuler des flux de données pour tests et développement
**OF-008** : Garantir la traçabilité temporelle de toutes les mesures

### 1.3 Objectifs Non-Fonctionnels

**ONF-001** : Scalabilité horizontale pour traiter des volumes croissants
**ONF-002** : Faible latence pour traitement temps réel
**ONF-003** : Découplage fort entre composants
**ONF-004** : Extensibilité par ajout de nouveaux composants
**ONF-005** : Testabilité avec possibilité d'environnements isolés
**ONF-006** : Observabilité des flux de données

---

## 2. Concepts Métier

### 2.1 Message Temporel

Un **message temporel** est l'unité atomique d'information transitant dans le système. Il représente une mesure ou un événement survenu à un instant précis.

**Propriétés conceptuelles :**
- **Identifiant de mesure** : Nom qualifiant le type de donnée (ex: "temperature_salle_101")
- **Horodatage** : Moment précis de la mesure (avec fuseau horaire)
- **Valeur** : Donnée mesurée (nombre, texte, booléen, structure complexe)
- **Métadonnées** : Informations contextuelles (source, localisation, unité, qualité, etc.)

### 2.2 Canal de Communication

Un **canal** est un espace logique thématique où transitent des messages partageant un contexte commun.

**Caractéristiques :**
- Identifié par un nom unique dans le système
- Permet le découplage entre émetteurs et récepteurs
- Peut avoir plusieurs émetteurs et plusieurs récepteurs simultanés
- Ne modifie pas les messages qui y transitent

**Exemples de canaux :**
- `capteurs.temperature` : températures de tous capteurs
- `alarmes.critiques` : alertes nécessitant intervention
- `production.ligne_a` : mesures ligne de production A

### 2.3 Source de Données

Une **source de données** est une entité qui produit des messages temporels et les émet vers un canal.

**Comportements :**
- Crée des messages avec horodatage
- Peut ajouter des métadonnées fixes à tous ses messages
- Émet vers un ou plusieurs canaux
- Peut produire en mode ponctuel ou continu

### 2.4 Destination de Données

Une **destination** est une entité qui reçoit et traite des messages temporels depuis un canal.

**Comportements :**
- S'abonne à un ou plusieurs canaux
- Peut filtrer les messages reçus selon critères métadonnées
- Traite les messages reçus (affichage, stockage, transformation, etc.)
- Peut définir un traitement personnalisé par message

### 2.5 Courtier de Messages

Le **courtier** (broker) est le mécanisme central assurant l'acheminement des messages entre sources et destinations via les canaux.

**Responsabilités fonctionnelles :**
- Gérer les abonnements des destinations aux canaux
- Acheminer chaque message reçu vers toutes les destinations abonnées au canal
- Maintenir un historique récent des messages par canal
- Notifier les destinations des nouveaux messages

**Modes de fonctionnement :**
- **Mode local** : Courtier interne au processus, adapté aux tests et applications mono-processus
- **Mode distribué** : Courtier externe partagé entre processus/machines, adapté à la production

### 2.6 Transformation de Données

Une **transformation** est une opération qui consomme des messages d'un canal et produit de nouveaux messages vers un autre canal.

**Caractéristiques :**
- Agit comme destination ET source simultanément
- Applique une logique métier (calcul, enrichissement, agrégation)
- Peut filtrer les messages en entrée
- Peut produire 0, 1 ou N messages en sortie pour chaque message en entrée

---

## 3. Modèle de Données

### 3.1 Structure d'un Message

```
Message
├── identifiant_mesure : Texte (obligatoire)
│   └── Nom qualifiant le type de donnée
│       Exemples : "temperature", "pression_hydraulique", "compteur_pieces"
│
├── horodatage : DateHeure (obligatoire)
│   └── Instant de la mesure avec fuseau horaire
│       Format : ISO 8601 avec timezone (préférence UTC)
│       Exemples : "2024-01-15T14:30:25+00:00"
│
├── valeur : Toute donnée (obligatoire)
│   └── Donnée mesurée, type variable selon contexte
│       Exemples : 23.5, "OK", true, {"x": 10, "y": 20}
│
└── métadonnées : Dictionnaire clé-valeur (obligatoire, peut être vide)
    └── Informations contextuelles de la mesure
        Structure : {clé_texte: valeur_texte}
        Exemples :
        - {"capteur_id": "TH001", "salle": "production", "unite": "celsius"}
        - {"machine": "tour_cnc_3", "operateur": "jdupont"}
```

### 3.2 Règles de Validation

**RV-001** : L'identifiant de mesure ne peut être vide
**RV-002** : L'horodatage doit être une date/heure valide avec timezone
**RV-003** : La valeur doit être présente (peut être null si sémantiquement pertinent)
**RV-004** : Les métadonnées doivent être un dictionnaire avec clés et valeurs textuelles
**RV-005** : Les clés de métadonnées ne peuvent contenir d'espaces ni caractères spéciaux (alphanumérique + underscore)
**RV-006** : Un message est immutable une fois créé

### 3.3 Représentation Sérialisée

Pour transit et stockage, un message doit pouvoir être sérialisé dans un format standard (JSON recommandé).

**Exemple de sérialisation JSON :**
```json
{
  "key": "temperature",
  "timestamp": "2024-01-15T14:30:25+00:00",
  "value": 23.5,
  "tags": {
    "sensor_id": "TH001",
    "location": "warehouse_A",
    "unit": "celsius"
  }
}
```

---

## 4. Acteurs du Système

### 4.1 Acteur : Source de Données Simple

**Description** : Entité émettant des messages vers un canal spécifique.

**Capacités :**
- Créer un message avec identifiant, horodatage, valeur et métadonnées
- Émettre le message vers un canal désigné
- Ajouter automatiquement des métadonnées fixes à chaque message (optionnel)

**Paramètres de configuration :**
- Canal de destination
- Métadonnées fixes (optionnel)

### 4.2 Acteur : Source de Données par Lot

**Description** : Entité émettant une série de messages issus d'un ensemble structuré (tableau de données avec horodatages).

**Capacités :**
- Ingérer un ensemble de données tabulaires (lignes/colonnes) avec index temporel
- Convertir chaque ligne en message temporel
- Émettre les messages selon différentes stratégies temporelles

**Modes d'émission :**

1. **Mode BATCH (lot immédiat)**
   - Tous les messages émis instantanément
   - Usage : import historique, tests rapides

2. **Mode REALTIME (temps réel simulé)**
   - Messages émis avec délais correspondant aux écarts temporels originaux
   - Si message 1 à t=0s, message 2 à t=10s, message 3 à t=15s
   - Émission : instant T, puis T+10s, puis T+5s
   - Usage : simulation réaliste, rejeu de scénarios

3. **Mode TRANSPOSE (temps transposé)**
   - Messages émis avec timestamps actuels mais écarts temporels préservés
   - Si message 1 à t=0s, message 2 à t=10s
   - Émission : maintenant avec timestamp actuel, puis 10s plus tard avec timestamp actuel+10s
   - Usage : rejeu adapté au temps présent

**Paramètres de configuration :**
- Canal de destination
- Ensemble de données tabulaires
- Identifiant de mesure pour les messages
- Métadonnées fixes (optionnel)
- Mode d'émission (BATCH/REALTIME/TRANSPOSE)

### 4.3 Acteur : Destination Simple

**Description** : Entité recevant et traitant des messages depuis un canal.

**Capacités :**
- S'abonner à un canal
- Recevoir les messages du canal
- Filtrer les messages selon critères métadonnées (optionnel)
- Exécuter un traitement pour chaque message reçu

**Paramètres de configuration :**
- Canal(aux) d'écoute
- Filtres sur métadonnées (optionnel)
- Traitement à exécuter (fonction/méthode)

**Règles de filtrage :**
- Les filtres sont des paires clé-valeur sur les métadonnées
- Un message passe le filtre si TOUTES les paires clé-valeur du filtre correspondent aux métadonnées du message
- Si aucun filtre défini, tous les messages sont traités

**Exemple de filtrage :**
```
Filtre : {"location": "warehouse_A", "sensor_type": "temperature"}

Message 1 : {"location": "warehouse_A", "sensor_type": "temperature"} → PASSE
Message 2 : {"location": "warehouse_B", "sensor_type": "temperature"} → BLOQUÉ
Message 3 : {"location": "warehouse_A", "sensor_type": "humidity"} → BLOQUÉ
Message 4 : {"location": "warehouse_A", "sensor_type": "temperature", "unit": "celsius"} → PASSE
```

### 4.4 Acteur : Transformation avec Seuil

**Description** : Transformation spécialisée surveillant une métrique et générant des alertes en cas de dépassement de seuil.

**Capacités :**
- S'abonner à un canal source (données à surveiller)
- Filtrer messages selon critères (optionnel)
- Vérifier si la valeur du message dépasse un seuil configuré
- Si dépassement : émettre un message d'alerte vers un canal de destination

**Paramètres de configuration :**
- Canal d'écoute (source des mesures)
- Canal de destination (alertes)
- Champ à vérifier (identifiant de mesure attendu)
- Seuil limite
- Filtres sur métadonnées (optionnel)

**Règle métier :**
- Le message source est traité SI il passe les filtres métadonnées
- Si `valeur_message > seuil_limite`, créer message d'alerte
- Le message d'alerte contient les informations du message source + indication de dépassement

**Exemple :**
```
Configuration :
- Canal écoute : "capteurs.temperature"
- Canal alerte : "alarmes.temperature"
- Champ : "temperature"
- Seuil : 30.0
- Filtre : {"location": "entrepot_A"}

Message reçu :
- key: "temperature"
- value: 32.5
- tags: {"location": "entrepot_A", "sensor_id": "TH001"}

Action : Message d'alerte émis vers "alarmes.temperature"
```

### 4.5 Acteur : Destination Persistante

**Description** : Destination stockant les messages dans un système de persistance externe (base de données time-series).

**Capacités :**
- Recevoir messages depuis canal(aux)
- Convertir message vers format de stockage cible
- Écrire dans système de persistance externe
- Gérer métadonnées dynamiques et champs multiples

**Paramètres de configuration :**
- Canal(aux) d'écoute
- Configuration connexion système de stockage (URL, authentification, espace de noms)
- Nom de la mesure pour le stockage
- Filtres métadonnées (optionnel)

**Règles de conversion :**
- L'horodatage du message devient le timestamp de stockage
- Les métadonnées deviennent les tags/dimensions indexés
- La valeur devient le champ mesuré
- L'identifiant de mesure peut servir de nom de série

### 4.6 Acteur : Générateur de Données Synthétiques

**Description** : Utilitaire générant des séries temporelles artificielles pour tests et simulations.

**Capacités :**
- Générer séries temporelles avec caractéristiques statistiques contrôlées
- Créer données suivant processus stochastiques (bruit gaussien, tendances, variations)
- Produire ensemble de données tabulaires utilisable par Source par Lot

**Paramètres de configuration :**
- Nombre de points de données
- Intervalle temporel entre points
- Valeur moyenne cible
- Niveau de bruit (écart-type)
- Type de processus (gaussien, sinusoïdal, etc.)

**Sortie :**
- Ensemble tabulaire avec index temporel et valeurs générées

---

## 5. Fonctionnalités Principales

### F-001 : Émission de Message Simple

**Description** : Permettre à une source d'émettre un message temporel vers un canal.

**Flux nominal :**
1. Source crée un message avec identifiant, horodatage, valeur, métadonnées
2. Source désigne le canal de destination
3. Courtier reçoit le message et le canal
4. Courtier identifie toutes les destinations abonnées au canal
5. Courtier transmet le message à chaque destination
6. Chaque destination traite le message selon sa logique

**Préconditions :**
- Le canal existe (ou est créé implicitement)
- Le message est valide selon règles de validation

**Postconditions :**
- Le message est acheminé à toutes les destinations actives
- Le message est ajouté à l'historique du canal

### F-002 : Abonnement à un Canal

**Description** : Permettre à une destination de s'abonner à un canal pour recevoir les messages.

**Flux nominal :**
1. Destination demande l'abonnement à un canal spécifique
2. Courtier enregistre l'abonnement
3. À chaque nouveau message sur ce canal, le courtier notifie la destination

**Préconditions :**
- Le canal existe ou peut être créé
- La destination fournit une méthode de traitement des messages

**Postconditions :**
- La destination reçoit tous les nouveaux messages du canal
- L'abonnement reste actif jusqu'à désabonnement explicite

### F-003 : Filtrage par Métadonnées

**Description** : Permettre à une destination de filtrer les messages reçus selon critères métadonnées.

**Flux nominal :**
1. Destination s'abonne à un canal avec filtres métadonnées
2. Courtier achemine tous les messages du canal vers la destination
3. Destination vérifie chaque message reçu contre les filtres
4. Si message passe filtres : traitement exécuté
5. Si message échoue filtres : message ignoré

**Préconditions :**
- Destination abonnée à un canal
- Filtres définis comme paires clé-valeur

**Postconditions :**
- Seuls les messages correspondant aux filtres sont traités

**Alternative :** Le filtrage peut être effectué par le courtier avant transmission (optimisation).

### F-004 : Production par Lot

**Description** : Permettre l'émission d'une série de messages depuis un ensemble tabulaire selon stratégies temporelles.

**Flux nominal :**
1. Source par lot reçoit un ensemble tabulaire avec index temporel et colonnes de valeurs
2. Source identifie canal destination et mode d'émission
3. Pour chaque ligne de l'ensemble :
   - Création d'un message avec identifiant, horodatage (depuis index), valeur
   - Selon mode BATCH : émission immédiate
   - Selon mode REALTIME : calcul du délai depuis message précédent, attente, puis émission
   - Selon mode TRANSPOSE : calcul nouveau timestamp (actuel + delta), émission immédiate
4. Tous messages émis vers canal

**Préconditions :**
- Ensemble tabulaire valide avec index temporel
- Mode d'émission spécifié

**Postconditions :**
- Tous les messages de l'ensemble sont émis selon le mode choisi

### F-005 : Surveillance et Alerte sur Seuil

**Description** : Surveiller des mesures et générer alertes en cas de dépassement de seuil.

**Flux nominal :**
1. Transformation seuil s'abonne au canal source avec filtres
2. Pour chaque message reçu passant les filtres :
   - Vérification : valeur > seuil ?
   - Si OUI :
     - Création message d'alerte
     - Émission vers canal d'alertes
   - Si NON : aucune action
3. Destinations abonnées au canal d'alertes reçoivent les alertes

**Préconditions :**
- Seuil défini
- Canaux source et destination configurés

**Postconditions :**
- Alerte émise pour chaque dépassement de seuil

### F-006 : Persistance des Messages

**Description** : Stocker les messages dans un système de persistance externe pour historisation et analyse.

**Flux nominal :**
1. Destination persistante s'abonne à canal(aux)
2. Pour chaque message reçu :
   - Conversion du message vers format de stockage
   - Écriture dans système de persistance
   - Confirmation de stockage (ou gestion d'erreur)

**Préconditions :**
- Connexion au système de persistance établie
- Autorisations suffisantes pour écriture

**Postconditions :**
- Message stocké de manière permanente
- Message interrogeable via système de persistance

### F-007 : Consultation de l'Historique

**Description** : Permettre la consultation des N derniers messages d'un canal.

**Flux nominal :**
1. Demandeur interroge le courtier pour les N derniers messages d'un canal
2. Courtier retourne les N derniers messages stockés pour ce canal (ou moins si historique insuffisant)

**Préconditions :**
- Canal existe
- N est un entier positif

**Postconditions :**
- Liste des messages retournée (éventuellement vide)

### F-008 : Désabonnement

**Description** : Permettre à une destination de se désabonner d'un canal.

**Flux nominal :**
1. Destination demande désabonnement du canal
2. Courtier retire l'abonnement de ses registres
3. Destination ne reçoit plus de messages du canal

**Préconditions :**
- Destination était abonnée au canal

**Postconditions :**
- Destination ne reçoit plus de notifications pour ce canal

### F-009 : Génération de Données Synthétiques

**Description** : Générer des séries temporelles artificielles pour tests.

**Flux nominal :**
1. Générateur configuré avec paramètres (nombre de points, intervalle, statistiques)
2. Générateur calcule série temporelle selon modèle stochastique
3. Générateur retourne ensemble tabulaire avec index temporel

**Préconditions :**
- Paramètres de génération valides

**Postconditions :**
- Ensemble tabulaire prêt pour injection via Source par Lot

---

## 6. Règles Métier

### RM-001 : Horodatage Obligatoire
Tout message DOIT posséder un horodatage valide avec fuseau horaire.
**Justification** : Garantir la traçabilité temporelle.

### RM-002 : Immutabilité des Messages
Un message une fois créé NE PEUT PAS être modifié.
**Justification** : Garantir l'intégrité des données et la reproductibilité.

### RM-003 : Découplage Source-Destination
Une source NE CONNAÎT PAS les destinations de ses messages. Une destination NE CONNAÎT PAS les sources.
**Justification** : Permettre l'évolution indépendante des composants.

### RM-004 : Canaux Thématiques
Les messages d'un même canal DOIVENT partager un contexte métier commun.
**Justification** : Faciliter le routage et la compréhension.

### RM-005 : Filtrage Inclusif
Un filtre métadonnées avec plusieurs critères applique un ET logique (tous critères doivent correspondre).
**Justification** : Comportement prévisible et expressif.

### RM-006 : Dépassement de Seuil Strictement Supérieur
Une alerte est déclenchée si valeur STRICTEMENT SUPÉRIEURE au seuil (>, pas >=).
**Justification** : Éviter les alertes sur valeurs limites exactes.

### RM-007 : Conservation Horodatage Original
En mode BATCH et REALTIME, l'horodatage du message est celui de la donnée source originale.
En mode TRANSPOSE, l'horodatage est recalculé au moment de l'émission en préservant les deltas.
**Justification** : Respecter la sémantique temporelle selon le mode.

### RM-008 : Métadonnées Textuelles
Toutes les clés et valeurs des métadonnées DOIVENT être des chaînes de caractères.
**Justification** : Simplifier la compatibilité inter-systèmes.

### RM-009 : Historique Limité
Le courtier conserve un historique limité par canal (taille configurable).
**Justification** : Éviter la croissance mémoire infinie.

### RM-010 : Traitement Asynchrone
Le traitement d'un message par une destination NE DOIT PAS bloquer l'émission de messages suivants.
**Justification** : Garantir la fluidité du système.

---

## 7. Flux Fonctionnels

### Flux 1 : Émission et Réception Simple

```
[Source]
   |
   | 1. Créer Message(key="temp", timestamp=T, value=23.5, tags={"loc":"A"})
   |
   v
[Courtier] (canal="capteurs.temperature")
   |
   | 2. Identifier destinations abonnées au canal
   |
   +---> [Destination 1] (filtre: tous)
   |         | 3a. Traiter message (ex: afficher)
   |
   +---> [Destination 2] (filtre: {"loc":"A"})
             | 3b. Vérifier filtre -> OK
             | 4b. Traiter message (ex: stocker)
```

### Flux 2 : Transformation avec Alerte

```
[Source Capteur]
   | Message(key="temp", value=31.0, tags={"zone":"entrepot"})
   v
[Courtier] (canal="capteurs.temperature")
   |
   v
[Transformation Seuil] (seuil=30.0, filtre={"zone":"entrepot"})
   | 1. Recevoir message
   | 2. Vérifier filtre -> OK
   | 3. Comparer valeur > seuil -> 31.0 > 30.0 -> OUI
   | 4. Créer Message Alerte(key="alerte_temp", value=31.0, tags={...})
   |
   v
[Courtier] (canal="alarmes.temperature")
   |
   v
[Destination Alertes]
   | 5. Notifier opérateur
```

### Flux 3 : Production par Lot en Mode REALTIME

```
[Ensemble Tabulaire]
Index Temporel     | Valeur
2024-01-01 10:00  | 20.0
2024-01-01 10:05  | 21.5  (delta = 5 min)
2024-01-01 10:12  | 22.0  (delta = 7 min)

[Source par Lot] (mode=REALTIME)
   | T=0s : Émettre Message(timestamp=2024-01-01 10:00, value=20.0)
   | Attendre 5 minutes (300s)
   | T=300s : Émettre Message(timestamp=2024-01-01 10:05, value=21.5)
   | Attendre 7 minutes (420s)
   | T=720s : Émettre Message(timestamp=2024-01-01 10:12, value=22.0)
   v
[Courtier]
   v
[Destinations] (reçoivent messages avec timing original préservé)
```

### Flux 4 : Persistance Multi-Canal

```
[Source Température] -> [Courtier] (canal="capteurs.temperature")
                            |
[Source Humidité] ----> [Courtier] (canal="capteurs.humidite")
                            |
                            +---> [Destination Persistante]
                                    | (abonnée aux deux canaux)
                                    v
                                  [Base Time-Series]
                                    | - Série "temperature"
                                    | - Série "humidite"
```

---

## 8. Cas d'Usage Détaillés

### CU-001 : Monitoring Temps Réel de Capteurs IoT

**Contexte** : Une usine dispose de 50 capteurs de température répartis dans différentes zones.

**Objectif** : Collecter les mesures toutes les 30 secondes et afficher en temps réel.

**Acteurs** :
- 50 Sources (une par capteur)
- 1 Courtier distribué
- 1 Destination affichage temps réel

**Flux** :
1. Chaque capteur émet un message toutes les 30s vers canal "capteurs.temperature"
2. Messages contiennent métadonnées {"zone": "A/B/C", "capteur_id": "TH001-TH050"}
3. Destination affichage abonnée au canal sans filtre
4. Destination met à jour interface graphique en temps réel

**Résultats attendus** :
- Latence < 1 seconde entre émission et affichage
- Tous les messages reçus et affichés
- Pas de perte de données

### CU-002 : Alerte Seuil Critique avec Notification

**Contexte** : Surveillance température d'une chambre froide. Seuil critique : 5°C.

**Objectif** : Déclencher alerte immédiate si température > 5°C.

**Acteurs** :
- Source capteur température
- Transformation seuil
- Destination notification (email/SMS)

**Flux** :
1. Capteur émet message temperature=6.2°C vers "capteurs.chambre_froide"
2. Transformation seuil (seuil=5.0) abonnée au canal
3. Détection dépassement : 6.2 > 5.0
4. Émission alerte vers canal "alarmes.chambre_froide"
5. Destination notification reçoit alerte et envoie email

**Résultats attendus** :
- Alerte déclenchée dans les 2 secondes suivant le dépassement
- Email reçu par opérateur
- Pas de fausses alertes si température <= 5°C

### CU-003 : Historisation de Données Industrielles

**Contexte** : Ligne de production avec mesures toutes les 10 secondes (débit, pression, vitesse).

**Objectif** : Stocker toutes les mesures dans base time-series pour analyse ultérieure.

**Acteurs** :
- Multiples sources (débitmètre, pressostat, tachymètre)
- Destination persistante base time-series

**Flux** :
1. Chaque appareil émet vers canal spécifique ("production.debit", "production.pression", etc.)
2. Destination persistante abonnée aux 3 canaux
3. Chaque message converti et stocké dans base avec tags {"ligne": "A", "appareil": "..."}

**Résultats attendus** :
- Toutes les mesures stockées sans perte
- Requêtes possibles par période, par ligne, par appareil
- Rétention configurable (ex: 1 an)

### CU-004 : Rejeu de Scénario pour Tests

**Contexte** : Développement d'un algorithme de détection d'anomalies.

**Objectif** : Rejouer des données historiques avec timing réel pour tester l'algorithme.

**Acteurs** :
- Source par lot (données historiques)
- Destination algorithme de détection

**Flux** :
1. Chargement fichier CSV avec 1000 lignes de mesures historiques
2. Source par lot configurée en mode REALTIME
3. Émission vers canal "test.replay"
4. Algorithme abonné au canal traite en temps réel
5. Vérification des détections d'anomalies

**Résultats attendus** :
- Timing entre messages respecté (comme données originales)
- Algorithme traite comme en situation réelle
- Possibilité de répéter le test

### CU-005 : Pipeline de Transformation Multi-Étapes

**Contexte** : Données brutes de capteurs nécessitent calibration puis filtrage.

**Objectif** : Créer pipeline : données brutes -> calibration -> filtrage -> stockage.

**Acteurs** :
- Source capteurs
- Transformation calibration
- Transformation filtrage (passe-bas)
- Destination persistante

**Flux** :
1. Source émet vers "donnees.brutes"
2. Transformation calibration abonnée à "donnees.brutes", applique formule, émet vers "donnees.calibrees"
3. Transformation filtrage abonnée à "donnees.calibrees", lisse valeurs, émet vers "donnees.filtrees"
4. Destination persistante abonnée à "donnees.filtrees", stocke

**Résultats attendus** :
- Chaque étape indépendante et testable
- Possibilité d'ajouter/retirer étapes sans tout casser
- Données finales correctement calibrées et filtrées

### CU-006 : Agrégation Temporelle

**Contexte** : Mesures haute fréquence (1/seconde), besoin de moyennes par minute.

**Objectif** : Calculer moyennes glissantes et émettre résultats.

**Acteurs** :
- Source haute fréquence
- Transformation agrégation
- Destination stockage agrégats

**Flux** :
1. Source émet 60 messages/minute vers "mesures.haute_freq"
2. Transformation agrégation accumule messages pendant 60s
3. Calcul moyenne chaque minute
4. Émission message agrégé vers "mesures.moyennes_minute"
5. Stockage des moyennes

**Résultats attendus** :
- Réduction volume de données (60 -> 1 message/minute)
- Préservation information statistique essentielle
- Latence acceptable (< 1 minute)

### CU-007 : Routage Multi-Zone Géographique

**Contexte** : Système multi-sites (Paris, Lyon, Marseille). Chaque site a opérateur local.

**Objectif** : Router alertes vers opérateur du site concerné uniquement.

**Acteurs** :
- Sources capteurs (tags incluent {"site": "Paris/Lyon/Marseille"})
- Transformations seuils par site
- Destinations notifications par site

**Flux** :
1. Capteur site Paris émet avec tag {"site": "Paris"}
2. Transformation seuil Paris avec filtre {"site": "Paris"}
3. Si alerte : émission vers "alarmes.paris"
4. Destination notification Paris abonnée à "alarmes.paris" uniquement

**Résultats attendus** :
- Opérateur Paris ne reçoit que alertes Paris
- Isolation totale entre sites
- Évolutivité (ajout nouveau site facile)

### CU-008 : Simulation pour Formation

**Contexte** : Formation opérateurs sur nouveau système de supervision.

**Objectif** : Générer données réalistes sans capteurs physiques.

**Acteurs** :
- Générateur données synthétiques
- Source par lot
- Système de supervision (destinations multiples)

**Flux** :
1. Générateur crée séries temporelles avec bruit gaussien, tendances, pics anomalies
2. Source par lot en mode REALTIME émet vers canaux système
3. Système de supervision traite comme données réelles
4. Formateurs créent scénarios (incidents, dérives)

**Résultats attendus** :
- Données indiscernables de vraies mesures
- Contrôle total des scénarios pédagogiques
- Environnement sûr sans impact production

---

## 9. Contraintes et Exigences

### 9.1 Exigences de Performance

**EP-001** : Latence bout-en-bout < 100ms en mode local pour 90% des messages
**EP-002** : Latence bout-en-bout < 1s en mode distribué pour 90% des messages
**EP-003** : Débit minimum 10 000 messages/seconde par instance en mode local
**EP-004** : Débit minimum 1 000 messages/seconde par instance en mode distribué
**EP-005** : Mémoire historique configurable (défaut : 100 derniers messages par canal)

### 9.2 Exigences de Fiabilité

**EF-001** : Pas de perte de messages en mode local si processus actif
**EF-002** : En mode distribué, durabilité selon garanties du courtier externe
**EF-003** : Échec de traitement d'une destination NE DOIT PAS affecter les autres
**EF-004** : Reprise sur erreur : tentative de reconnexion automatique (courtier distribué)

### 9.3 Exigences de Scalabilité

**ES-001** : Support minimum 1000 canaux simultanés
**ES-002** : Support minimum 100 sources émettrices simultanées
**ES-003** : Support minimum 100 destinations simultanées
**ES-004** : Possibilité d'ajouter sources/destinations à chaud (sans redémarrage)

### 9.4 Exigences de Compatibilité

**EC-001** : Messages sérialisables en JSON
**EC-002** : Horodatages conformes ISO 8601
**EC-003** : Support fuseaux horaires standard (préférence UTC)
**EC-004** : Métadonnées compatibles ASCII + caractères internationaux (UTF-8)

### 9.5 Exigences de Testabilité

**ET-001** : Mode local permettant tests unitaires isolés
**ET-002** : Possibilité d'injecter courtier simulé (mock)
**ET-003** : Générateur données synthétiques avec reproductibilité (seed aléatoire)
**ET-004** : Logs détaillés pour debugging (niveau configurable)

### 9.6 Exigences de Sécurité

**ESec-001** : En mode distribué, support authentification courtier externe
**ESec-002** : Validation systématique des messages reçus (format, types)
**ESec-003** : Isolation des erreurs (exception dans destination ne propage pas)
**ESec-004** : Pas d'injection de code via métadonnées (sanitization)

### 9.7 Exigences d'Observabilité

**EO-001** : Logs structurés (niveau DEBUG, INFO, WARNING, ERROR)
**EO-002** : Métriques exposées : nombre messages émis/reçus par canal
**EO-003** : Métriques : latence moyenne/P95/P99 par canal
**EO-004** : Détection destinations inactives (heartbeat)

---

## 10. Comportements et Edge Cases

### 10.1 Gestion des Erreurs

**Erreur E-001 : Message Invalide**
- **Situation** : Source tente d'émettre message sans horodatage ou identifiant vide
- **Comportement attendu** : Rejet immédiat avec exception explicite, aucune émission
- **Log** : WARNING avec détails de validation échouée

**Erreur E-002 : Canal Inexistant**
- **Situation** : Destination s'abonne à canal qui n'a jamais reçu de messages
- **Comportement attendu** : Création implicite du canal, abonnement réussi
- **Log** : INFO "Nouveau canal créé"

**Erreur E-003 : Échec Traitement Destination**
- **Situation** : Destination lève exception durant traitement message
- **Comportement attendu** : Exception capturée, log ERROR, message marqué non traité, autres destinations non affectées
- **Log** : ERROR avec traceback complet

**Erreur E-004 : Courtier Distribué Indisponible**
- **Situation** : Courtier externe déconnecté
- **Comportement attendu** :
  - Tentatives reconnexion automatique (backoff exponentiel)
  - Messages en attente bufferisés (limite configurable)
  - Si buffer plein : exception explicite
- **Log** : WARNING reconnexion, ERROR si buffer plein

**Erreur E-005 : Sérialisation Échouée**
- **Situation** : Valeur de message non-sérialisable en JSON
- **Comportement attendu** : Exception explicite avant émission
- **Log** : ERROR avec type de valeur problématique

### 10.2 Cas Limites

**CL-001 : Message avec Métadonnées Vides**
- **Situation** : Message avec `tags={}`
- **Comportement** : Accepté, message valide, passe tous les filtres vides

**CL-002 : Filtre Vide**
- **Situation** : Destination avec `filtres={}`
- **Comportement** : Tous les messages passent (équivalent pas de filtre)

**CL-003 : Valeur null**
- **Situation** : Message avec `value=null`
- **Comportement** : Accepté si sémantiquement pertinent (ex: capteur hors ligne)

**CL-004 : Horodatage Futur**
- **Situation** : Message avec timestamp dans le futur
- **Comportement** : Accepté (pas de validation temporelle), c'est à l'application de gérer

**CL-005 : Horodatage Très Ancien**
- **Situation** : Message avec timestamp de 1970
- **Comportement** : Accepté, géré normalement

**CL-006 : Canal avec Caractères Spéciaux**
- **Situation** : Nom canal "capteurs/température/zone-A"
- **Comportement** : Accepté si compatible avec système de courtier, sinon exception explicite

**CL-007 : Dépassement Seuil Exact**
- **Situation** : Valeur exactement égale au seuil (30.0 == 30.0)
- **Comportement** : PAS d'alerte (règle : strictement supérieur)

**CL-008 : Production Lot Vide**
- **Situation** : Source par lot avec ensemble tabulaire 0 lignes
- **Comportement** : Aucun message émis, log INFO "Aucune donnée à émettre"

**CL-009 : Historique Demandé > Disponible**
- **Situation** : Demande 100 derniers messages, seulement 10 disponibles
- **Comportement** : Retourne les 10 disponibles sans erreur

**CL-010 : Désabonnement Sans Abonnement**
- **Situation** : Destination demande désabonnement sans avoir été abonnée
- **Comportement** : Opération ignorée, log INFO "Déjà désabonné"

### 10.3 Comportements Concurrents

**CC-001 : Émissions Simultanées Même Canal**
- **Situation** : 10 sources émettent simultanément vers même canal
- **Comportement** : Tous messages traités, ordre d'arrivée non garanti, pas de perte

**CC-002 : Abonnement Pendant Émission**
- **Situation** : Destination s'abonne pendant qu'un message est en cours d'acheminement
- **Comportement** : Destination reçoit les messages émis APRÈS abonnement complet uniquement

**CC-003 : Modification Filtre à Chaud**
- **Situation** : Destination change ses filtres pendant réception de messages
- **Comportement** : Nouveaux filtres appliqués aux messages suivants, pas de rétroactivité

### 10.4 Comportements de Reprise

**CR-001 : Redémarrage Destination**
- **Situation** : Destination redémarre, messages émis pendant arrêt
- **Comportement** : Messages perdus pour cette destination (pas de buffer persistant par défaut)
- **Alternative** : En mode distribué avec groupe consommateur, messages peuvent être rejoués

**CR-002 : Redémarrage Source**
- **Situation** : Source redémarre
- **Comportement** : Source peut reprendre émissions, état à gérer par application

**CR-003 : Redémarrage Courtier Local**
- **Situation** : Processus avec courtier local redémarre
- **Comportement** : Historique perdu, canaux recréés vides

**CR-004 : Redémarrage Courtier Distribué**
- **Situation** : Courtier externe redémarre
- **Comportement** : Selon courtier, messages peuvent être persistés, abonnements restaurés

---

## 11. Glossaire

**Broker / Courtier** : Composant central gérant l'acheminement des messages entre sources et destinations via canaux.

**Canal** : Espace logique thématique où transitent des messages partageant un contexte commun. Équivalent à "topic" ou "queue".

**Consommateur / Destination** : Composant recevant et traitant des messages depuis un ou plusieurs canaux.

**Filtrage** : Mécanisme permettant à une destination de ne traiter qu'un sous-ensemble de messages selon critères métadonnées.

**Horodatage / Timestamp** : Instant précis (date + heure + fuseau horaire) auquel une mesure a été effectuée.

**Message Temporel** : Unité atomique d'information contenant identifiant, horodatage, valeur et métadonnées.

**Métadonnées / Tags** : Informations contextuelles sous forme de paires clé-valeur décrivant un message (source, localisation, unité, etc.).

**Mode BATCH** : Stratégie d'émission par lot où tous les messages sont émis instantanément.

**Mode REALTIME** : Stratégie d'émission par lot où les messages sont émis avec respect des délais temporels originaux.

**Mode TRANSPOSE** : Stratégie d'émission par lot où les messages sont émis avec timestamps recalculés au présent mais deltas préservés.

**Producteur / Source** : Composant créant et émettant des messages vers un ou plusieurs canaux.

**Sérialisation** : Conversion d'un message en format textuel/binaire pour transit ou stockage (typiquement JSON).

**Seuil** : Valeur limite configurée pour déclencher une action (généralement une alerte).

**Transformation** : Composant agissant comme destination ET source, appliquant une logique métier entre canaux.

**Time-series / Série Temporelle** : Séquence de mesures horodatées ordonnées chronologiquement.

---

## Questions Ouvertes pour Amélioration

**Question 1 - Gestion des erreurs de persistance** :
Que doit-il se passer si la destination persistante échoue à écrire en base (connexion perdue, disque plein) ?
- Option A : Buffer local temporaire avec rejeu automatique
- Option B : Log erreur et abandon du message
- Option C : Émission vers canal d'erreurs pour traitement spécial
- Autre ?

**Question 2 - Ordre des messages** :
Doit-on garantir l'ordre des messages d'une même source vers une destination ?
- Si OUI : quelle stratégie (numéro de séquence, lock source) ?
- Si NON : documenter explicitement dans contrat

**Question 3 - Acquittement** :
Les sources doivent-elles recevoir un acquittement de réception par les destinations ?
- Si OUI : quelle sémantique (au moins une fois, exactement une fois) ?
- Si NON : fire-and-forget pur ?

**Question 4 - Métriques avancées** :
Quelles métriques supplémentaires seraient utiles ?
- Taux de messages filtrés par destination ?
- Latence par transformation ?
- Taille moyenne des messages ?

**Question 5 - Retentions différenciées** :
L'historique par canal doit-il être configurable individuellement ou globalement ?

**Question 6 - Backpressure** :
Comment gérer une destination trop lente (accumulation messages) ?
- Abandon messages anciens ?
- Blocage émetteur ?
- Alerte système ?

**Question 7 - Schémas de données** :
Doit-on permettre de définir des schémas de validation par canal (ex: champ "temperature" doit être float entre -50 et 100) ?

**Question 8 - Agrégation** :
L'agrégation temporelle (CU-006) doit-elle être une fonctionnalité native ou un exemple de transformation personnalisée ?

---

**Fin du document**
**Prochaines étapes** : Révision itérative selon réponses aux questions ouvertes.
