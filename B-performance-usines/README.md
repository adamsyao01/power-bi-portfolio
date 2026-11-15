# Projet B — Performance multi-usines (Microsoft Fabric)

**Entreprise fictive** : Aliments Bellerive, transformation alimentaire, 3 usines au Québec (Laval, Drummondville, Saguenay), 4 lignes par usine.
**Objectif** : montrer une chaîne Fabric de bout en bout, avec des **données de production brutes**, un **lakehouse**, un **notebook PySpark**, des **tables Delta**, un modèle sémantique **Direct Lake** et la **sécurité par ligne** (chaque directeur d'usine ne voit que son usine).

> Données 100 % fictives, générées par `scripts/generer_donnees.py` (graine fixe).

🔎 **[Démo interactive en ligne](https://app.powerbi.com/view?r=eyJrIjoiYjMzNmFhNTktZTAxNC00NWQzLTg0NDYtMDg1YWNmOTUyZDQ3IiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9)** (copie publique en mode Import)

---

## 1. Les données brutes (`data/raw/`)

| Dossier | Fichiers | Particularité |
|---|---|---|
| `reference/` | usines, lignes, produits, codes_arret | référentiels |
| `production/` | 1 fichier par usine, 1 ligne par quart | **3 formats différents** (voir ci-dessous) |
| `arrets/` | 1 fichier par usine, 1 ligne par arrêt | idem |

Comme dans la vraie vie, chaque usine exporte à sa façon :
- **Laval** : format propre (référence) ;
- **Drummondville** : séparateur `;`, dates `JJ/MM/AAAA`, virgule décimale, **26 doublons** d'export ;
- **Saguenay** : colonnes en anglais, espaces parasites dans les codes de ligne.

Volume : environ 19 500 quarts et 77 000 arrêts, de janvier 2025 à octobre 2026.

**Les histoires cachées dans les données** (ce que le rapport doit révéler) :
1. **Le convoyeur de la ligne 3 à Saguenay se dégrade** à partir de mars 2026 : la disponibilité passe d'environ 88 % à 75 % (pannes PM-04 plus fréquentes et plus longues).
2. **Le quart de nuit à Drummondville produit plus de rebuts** : qualité de 96,0 %, contre 98,2 % de jour.
3. **Les changements de format sont la première cause d'arrêt** dans les 3 usines, devant les pannes. C'est une piste SMED pour la direction.

**Chiffres attendus** (calculés par `scripts/verifier_logique.py`, la même logique que le notebook en pandas) :

| Usine | Disponibilité | Performance | Qualité | **TRS** |
|---|---|---|---|---|
| Drummondville | 88,2 % | 90,7 % | 97,6 % | **78,1 %** |
| Laval | 88,2 % | 90,6 % | 98,2 % | **78,4 %** |
| Saguenay | 87,1 % | 90,7 % | 98,2 % | **77,6 %** |

---

## 2. L'architecture

```
Exports MES (CSV, 3 formats)
        │  téléversement
        ▼
Lakehouse LH_Bellerive ── Files/raw/ ............ BRONZE
        │  Notebook PySpark NB_Bellerive_Transformation
        │  (normalisation, dédoublonnage, typage, temps du TRS)
        ▼
Tables Delta dim_* / fact_* ....................... OR
        │  Direct Lake (pas d'import, pas de copie)
        ▼
Modèle sémantique SM_Bellerive_Performance (mesures TRS, RLS par usine)
        │
        ▼
Rapport Power BI « Performance des usines »
```

---

## 3. Mise en place dans Fabric (pas à pas)

### 3.1 Espace de travail et lakehouse
1. Sur app.powerbi.com : **Espaces de travail → Nouvel espace de travail** : `Portfolio - Bellerive`.
   Dans *Avancé*, choisis le mode de licence **Essai** (ta capacité Fabric).
2. Dans l'espace : **+ Nouvel élément → Lakehouse** : `LH_Bellerive`.

### 3.2 Téléverser les fichiers bruts
1. Dans le lakehouse, sur **Files** : **… → Charger → Charger un dossier**.
2. Sélectionne le dossier `data/raw` de ce projet. Tu dois obtenir `Files/raw/reference`, `Files/raw/production` et `Files/raw/arrets`.

### 3.3 Importer et lancer le notebook
1. Dans l'espace de travail : **Importer → Notebook → À partir de cet ordinateur**, puis choisis `fabric/NB_Bellerive_Transformation.ipynb`.
2. Ouvre-le. Dans le panneau de gauche, **ajoute le lakehouse `LH_Bellerive`** comme lakehouse par défaut.
3. **Exécuter tout**. La dernière cellule affiche le TRS par usine, qui doit correspondre au tableau ci-dessus.
4. Rafraîchis le lakehouse : 8 tables Delta apparaissent sous **Tables**.

### 3.4 Créer le modèle sémantique Direct Lake
1. Dans le lakehouse : **Nouveau modèle sémantique** : `SM_Bellerive_Performance`, en cochant les 8 tables.
2. Ouvre le modèle (**Ouvrir le modèle de données**, modification dans le navigateur).

**Relations à créer** (toutes 1 → plusieurs, filtrage simple) :

| De (plusieurs) | Vers (un) |
|---|---|
| fact_production[Date] | dim_date[Date] |
| fact_production[CodeLigne] | dim_ligne[CodeLigne] |
| fact_production[Quart] | dim_quart[Quart] |
| fact_production[CodeProduit] | dim_produit[CodeProduit] |
| fact_arret[Date] | dim_date[Date] |
| fact_arret[CodeLigne] | dim_ligne[CodeLigne] |
| fact_arret[Quart] | dim_quart[Quart] |
| fact_arret[CodeArret] | dim_code_arret[CodeArret] |
| dim_ligne[CodeUsine] | dim_usine[CodeUsine] |

Ensuite :
- marque `dim_date` comme **table de dates** ;
- trie `dim_date[Mois]` par `NoMois` et `dim_quart[Quart]` par `OrdreQuart` ;
- masque les colonnes de clé dans les tables de faits.

### 3.5 Les mesures (vue Requête DAX)
Ouvre la **vue Requête DAX**, colle `fabric/mesures.dax`, puis clique sur **Mettre à jour le modèle avec les modifications**. Les 24 mesures sont créées d'un coup dans `fact_production`. Le résultat de la requête affiche le TRS par usine, pour vérifier. Les dossiers d'affichage (`1. Temps`, `2. TRS`, `3. Arrêts`) se règlent ensuite dans le volet Propriétés.

### 3.6 La sécurité par ligne (RLS)
**Gérer les rôles → Nouveau rôle** :
- **`Directeur d'usine`** : sur la table `dim_usine`, ajoute le filtre DAX
  `[CourrielDirecteur] = USERPRINCIPALNAME()`.
  Le filtre descend `dim_usine → dim_ligne → faits`, donc chaque directeur ne voit que son usine.
- **`Direction`** : aucun filtre, accès à toutes les usines.

**Test** : *Afficher en tant que → Directeur d'usine + autre utilisateur* `directeur.saguenay@bellerive-demo.ca`. Seule l'usine de Saguenay doit rester visible.
Filme ce test : c'est l'argument le plus fort de la démo.

---

## 4. La version publique

**« Publier sur le web » ne fonctionne pas avec un modèle qui utilise la RLS**, et à ma connaissance pas non plus avec Direct Lake. La démo publique se fera donc en deux parties :
1. une **vidéo de 2 minutes** (lakehouse, notebook, modèle, test RLS « Afficher en tant que ») et des captures, pour montrer l'architecture Fabric ;
2. une **copie en mode Import** du rapport, sans RLS, publiée sur le web pour l'exploration interactive.

**Copie publique prête à l'emploi** : `scripts/exporter_or.py` écrit les tables « or » dans `data/or/` (même logique que le notebook), puis `scripts/generer_pbip.py` génère **`Bellerive-Performance.pbip`** : modèle Import, 25 mesures, 5 pages (Vue groupe, Pertes, Analyse d'une ligne, Qualité par quart, À propos). Ouvre-le, actualise, enregistre en .pbix, publie, puis *Publier sur le web*.

---

## 5. Pages du rapport (à construire à l'étape suivante)
1. **Vue groupe** : TRS, disponibilité, performance et qualité par usine ; tendance mensuelle vs cible de 85 %.
2. **Pertes** : Pareto des minutes d'arrêt par catégorie et par code ; MTBF / MTTR.
3. **Analyse d'une ligne** : disponibilité de SAG-L3 qui chute en 2026, pannes du convoyeur.
4. **Qualité par quart** : rebuts par usine × quart (le quart de nuit à Drummondville).
5. **À propos** : architecture Fabric, modèle, RLS.
