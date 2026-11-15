# Projet A — Approvisionnement v2 (démo portfolio)

**Entreprise fictive** : AviNord, transformateur de volaille au Québec.
**Objectif** : la version publique et propre de l'étude de cas n° 1. Mêmes questions métier, mais avec un modèle en étoile irréprochable, des données 100 % fictives et une démo interactive.

> Toutes les données sont générées par `scripts/generer_donnees.py` (graine fixe : on obtient toujours les mêmes chiffres). Aucune donnée réelle.

🔎 **[Démo interactive en ligne](https://app.powerbi.com/view?r=eyJrIjoiOWNhYzY5ZGItM2QwYS00MTcxLWJhMTMtZDM0YzU4MTdhMmViIiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9)**

## ⚡ Version prête à ouvrir

Le projet complet (modèle + 4 pages) est généré par `scripts/generer_pbip.py` au format **PBIP** :
1. Double-cliquer sur **`AviNord-Appro.pbip`** : Power BI Desktop l'ouvre.
2. Cliquer sur **Actualiser** pour charger les CSV.
3. Si le dossier des données a bougé : *Transformer les données → Modifier les paramètres → DossierDonnees*.
4. **Fichier → Enregistrer sous → .pbix** pour obtenir un fichier classique à publier.

Les sections ci-dessous expliquent ce que contient le projet (et servent de support pour l'étude de cas).

---

## 1. Les données (`data/`)

| Fichier | Rôle | Grain | Lignes |
|---|---|---|---|
| `FaitReceptionLot.csv` | Faits — réception des lots | 1 ligne par lot | ~6 350 |
| `FaitCondamnation.csv` | Faits — kg condamnés par cause | lot × cause | ~37 800 |
| `FaitBudgetPeriode.csv` | Budget de la finance | période × type × région | 234 |
| `DimDate.csv` | Calendrier fiscal 13 × 4 semaines | jour | 1 092 |
| `DimProducteur.csv` | Producteurs (42) | producteur | 42 |
| `DimRegion.csv` | Québec / Ontario-Est | région | 2 |
| `DimTypePoulet.csv` | À griller, lourd, de grain | type | 3 |
| `DimTransporteur.csv` | Transporteurs (8) | transporteur | 8 |
| `DimCauseCondamnation.csv` | Causes de condamnation | cause | 6 |
| `DimComposante.csv` | Composantes du coût | composante | 5 |

**Calendrier** : exercices FY24 à FY26, 13 périodes de 28 jours (dimanche → samedi).
**Dernière donnée réelle** : 12 novembre 2026, 12ᵉ jour de la période 12. C'est voulu : la démo montre la comparaison **à date égale** en cours de période.

**L'histoire cachée dans les données** (ce que la démo doit faire ressortir) :
- FY26 est **sous le budget d'environ 1,4 M$**… mais c'est un **trompe-l'œil** :
  - effet **volume** ≈ −5,2 M$ (on a acheté moins de kilos que prévu) ;
  - effet **prix** ≈ +3,3 M$ (le $/kg a monté plus que budgété) ;
  - effet **mix** ≈ +0,4 M$ (davantage d'achats en Ontario-Est, plus cher à cause du transport).
- Sans la décomposition, la direction croirait que tout va bien. C'est exactement l'argument de vente.

---

## 2. Le modèle (schéma en étoile)

```
                         DimDate ─────────────┬──────────────┐
                            │                 │              │
DimProducteur ─┐            │                 │              │
   │           ├──► FaitReceptionLot ──► FaitCout ◄── DimComposante ──► FaitBudgetCout
DimRegion ─────┤            │      └───► FaitCondamnation ◄── DimCauseCondamnation
   │      DimTypePoulet ────┤                                               ▲
   │      DimTransporteur ──┘                                               │
   └──────────────────────────────► FaitBudgetVolume / FaitBudgetCout ◄─────┘
                                     (aussi reliés à DimDate et DimTypePoulet)
```

### Relations (toutes 1 → plusieurs, filtrage simple)

| De (côté 1) | Vers (côté plusieurs) | Clé |
|---|---|---|
| DimDate | FaitReceptionLot | Date → DateAbattage |
| DimProducteur | FaitReceptionLot | ProducteurID |
| DimRegion | DimProducteur | Region |
| DimTypePoulet | FaitReceptionLot | TypePouletID |
| DimTransporteur | FaitReceptionLot | TransporteurID |
| FaitReceptionLot | FaitCout | LotID |
| DimComposante | FaitCout | Composante |
| FaitReceptionLot | FaitCondamnation | LotID |
| DimCauseCondamnation | FaitCondamnation | CauseID |
| DimDate | FaitBudgetVolume, FaitBudgetCout | Date |
| DimTypePoulet | FaitBudgetVolume, FaitBudgetCout | TypePouletID |
| DimRegion | FaitBudgetVolume, FaitBudgetCout | Region |
| DimComposante | FaitBudgetCout | Composante |

### Réglages à faire dans Power BI Desktop
- **Fichier → Options → Données actuelles → Chargement des données** : décocher **Date/heure automatique**.
- **Marquer `DimDate` comme table de dates** (colonne `Date`).
- Trier `Periode` par `NoPeriode`, `ExercicePeriode` par `CleExercicePeriode`, `Composante` par `Ordre`.
- Masquer toutes les colonnes clés (ID) et les colonnes des tables de faits qui ont une mesure.
- Créer une table vide **`_Mesures`** pour ranger toutes les mesures, avec des dossiers d'affichage.

---

## 3. Power Query — les deux transformations clés

### 3.1 `FaitCout` : passer les montants en format long
Les 5 colonnes de montant deviennent 2 colonnes (`Composante`, `Montant`). On a ainsi **une seule mesure de coût**, que `DimComposante` découpe automatiquement. Pas de mesure dupliquée par composante.

```m
let
    Source = FaitReceptionLot,
    Colonnes = Table.SelectColumns(Source, {"LotID", "MontantPrixBase", "MontantAjustement",
                                            "MontantBonification", "MontantChargement", "MontantTransport"}),
    Long = Table.UnpivotOtherColumns(Colonnes, {"LotID"}, "Composante", "Montant"),
    Noms = Table.ReplaceValue(Long, each [Composante], each
        Record.Field([MontantPrixBase = "Prix de base", MontantAjustement = "Ajustement",
                      MontantBonification = "Bonification", MontantChargement = "Chargement",
                      MontantTransport = "Transport"], [Composante]),
        Replacer.ReplaceValue, {"Composante"}),
    Types = Table.TransformColumnTypes(Noms, {{"LotID", Int64.Type}, {"Montant", Currency.Type}})
in
    Types
```
Dans `FaitReceptionLot`, supprimer ensuite les 5 colonnes de montant (elles vivent dans `FaitCout`).

### 3.2 Budget : ventiler la période au jour
La finance donne un budget **par période**. On le répartit sur les 28 jours de la période. Les comparaisons « à date égale » deviennent alors un simple filtre de dates, sans calcul de prorata dans le DAX.

```m
// Requête intermédiaire « BudgetJour » (désactiver son chargement)
let
    Budget = FaitBudgetPeriode,
    Dates = Table.SelectColumns(DimDate, {"Date", "CleExercicePeriode"}),
    Joint = Table.NestedJoin(Budget, {"CleExercicePeriode"}, Dates, {"CleExercicePeriode"}, "D", JoinKind.Inner),
    Jours = Table.ExpandTableColumn(Joint, "D", {"Date"}),
    Cols = {"KgPayesBudget", "MontantPrixBaseBudget", "MontantAjustementBudget",
            "MontantBonificationBudget", "MontantChargementBudget", "MontantTransportBudget"},
    ParJour = Table.TransformColumns(Jours, List.Transform(Cols, (c) => {c, each _ / 28, type number}))
in
    ParJour

// Requête « FaitBudgetVolume »
let
    S = Table.SelectColumns(BudgetJour, {"Date", "TypePouletID", "Region", "KgPayesBudget"})
in
    S

// Requête « FaitBudgetCout »
let
    S = Table.SelectColumns(BudgetJour, {"Date", "TypePouletID", "Region", "MontantPrixBaseBudget",
        "MontantAjustementBudget", "MontantBonificationBudget", "MontantChargementBudget", "MontantTransportBudget"}),
    Long = Table.UnpivotOtherColumns(S, {"Date", "TypePouletID", "Region"}, "Composante", "Montant"),
    Noms = Table.ReplaceValue(Long, each [Composante], each
        Record.Field([MontantPrixBaseBudget = "Prix de base", MontantAjustementBudget = "Ajustement",
                      MontantBonificationBudget = "Bonification", MontantChargementBudget = "Chargement",
                      MontantTransportBudget = "Transport"], [Composante]),
        Replacer.ReplaceValue, {"Composante"}),
    Types = Table.TransformColumnTypes(Noms, {{"Date", type date}, {"Montant", Currency.Type}})
in
    Types
```

---

## 4. DAX

### 4.1 Tables de paramètres (Modélisation → Nouvelle table)

```dax
Référence = DATATABLE("Référence", STRING, "Ordre", INTEGER, {{"Budget", 1}, {"Année précédente", 2}})

Étapes du pont = DATATABLE("Étape", STRING, "Ordre", INTEGER,
    {{"Effet volume", 1}, {"Effet mix", 2}, {"Effet prix", 3}})
```
Ces deux tables ne sont reliées à rien (tables déconnectées).

### 4.2 Mesures de base — dossier `1. Réel`

```dax
Dernière date réelle = CALCULATE(MAX(FaitReceptionLot[DateAbattage]), REMOVEFILTERS())

Kg payés = SUM(FaitReceptionLot[KgPayes])
Coût total = SUM(FaitCout[Montant])
$/kg = DIVIDE([Coût total], [Kg payés])

Nb lots = COUNTROWS(FaitReceptionLot)
Têtes reçues = SUM(FaitReceptionLot[TetesRecues])
Morts en cage = SUM(FaitReceptionLot[MortsEnCage])
% Morts en cage = DIVIDE([Morts en cage], [Têtes reçues])
Poids moyen vif (kg) = DIVIDE(SUM(FaitReceptionLot[KgVifsRecus]), [Têtes reçues] - [Morts en cage])
Kg condamnés = SUM(FaitCondamnation[KgCondamnes])
% Condamnation = DIVIDE([Kg condamnés], SUM(FaitReceptionLot[KgVifsRecus]))
```

### 4.3 Budget et année précédente, à date égale — dossier `2. Référence`

```dax
Kg budget =
VAR _fin = [Dernière date réelle]
RETURN CALCULATE(SUM(FaitBudgetVolume[KgPayesBudget]), KEEPFILTERS(DimDate[Date] <= _fin))

Coût budget =
VAR _fin = [Dernière date réelle]
RETURN CALCULATE(SUM(FaitBudgetCout[Montant]), KEEPFILTERS(DimDate[Date] <= _fin))

Kg AP =
VAR _fin = [Dernière date réelle]
VAR _dates = FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _fin)
VAR _datesAP = SELECTCOLUMNS(_dates, "Date", DimDate[Date] - 364)   -- 364 j = 13 × 28 : même jour fiscal
RETURN CALCULATE([Kg payés], REMOVEFILTERS(DimDate), TREATAS(_datesAP, DimDate[Date]))

Coût AP =
VAR _fin = [Dernière date réelle]
VAR _dates = FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _fin)
VAR _datesAP = SELECTCOLUMNS(_dates, "Date", DimDate[Date] - 364)
RETURN CALCULATE([Coût total], REMOVEFILTERS(DimDate), TREATAS(_datesAP, DimDate[Date]))

Référence choisie = SELECTEDVALUE('Référence'[Référence], "Budget")

Kg référence = IF([Référence choisie] = "Budget", [Kg budget], [Kg AP])
Coût référence = IF([Référence choisie] = "Budget", [Coût budget], [Coût AP])
$/kg référence = DIVIDE([Coût référence], [Kg référence])
```

### 4.4 Décomposition des écarts — dossier `3. Écarts`

Convention : **positif = le coût augmente (défavorable)**.

```dax
Écart total = [Coût total] - [Coût référence]

Coût réel au prix de référence =
SUMX(
    CROSSJOIN(VALUES(DimTypePoulet[TypePoulet]), VALUES(DimRegion[Region])),
    [Kg payés] * [$/kg référence]
)

Effet volume = ([Kg payés] - [Kg référence]) * [$/kg référence]
Effet mix    = [Coût réel au prix de référence] - [Kg payés] * [$/kg référence]
Effet prix   = [Coût total] - [Coût réel au prix de référence]

Contrôle (doit être 0) = [Écart total] - ([Effet volume] + [Effet mix] + [Effet prix])
```

Pourquoi ça marche :
- le **mix** compare ce qu'on aurait payé avec la répartition réelle (type × région), mais aux prix de référence, à ce qu'on aurait payé avec la répartition de référence ;
- les trois effets s'additionnent **exactement** à l'écart total ;
- comme le coût est en format long, mettre `DimComposante[Composante]` en lignes donne **automatiquement** les écarts par composante (prix de base, transport…). Il n'y a pas une mesure par composante.

```dax
Pont des écarts =
SWITCH(
    SELECTEDVALUE('Étapes du pont'[Étape]),
    "Effet volume", [Effet volume],
    "Effet mix",    [Effet mix],
    "Effet prix",   [Effet prix]
)
```
À utiliser dans un **graphique en cascade** : catégorie = `Étapes du pont[Étape]`. La barre « Total » que la cascade ajoute seule est égale à l'écart total. On ne met pas les coûts complets (environ 200 M$) dans la cascade : à côté, les effets de quelques millions seraient invisibles.

### 4.5 Groupe de calcul « Période d'analyse »

Créé dans la **vue Modèle → Groupes de calcul** (Power BI Desktop récent) ou avec Tabular Editor.

| Élément | Expression |
|---|---|
| Période sélectionnée | `SELECTEDMEASURE()` |
| Cumul de l'exercice | voir ci-dessous |

```dax
-- Cumul de l'exercice
VAR _ex  = MAX(DimDate[Exercice])
VAR _fin = MAX(DimDate[Date])
RETURN CALCULATE(SELECTEDMEASURE(), REMOVEFILTERS(DimDate), DimDate[Exercice] = _ex, DimDate[Date] <= _fin)
```
Un seul segment transforme **toutes** les mesures (réel, budget, AP, écarts) en cumul de l'exercice. Dans l'ancien rapport, il fallait dupliquer chaque mesure.

---

## 5. Les pages du rapport

1. **Vue d'ensemble** : cartes KPI (coût total, $/kg, kg payés, écart vs référence), courbe réel vs référence par période, segments Référence / Période d'analyse / Type / Région.
2. **Pont des écarts** : cascade référence → volume → mix → prix → réel ; matrice composantes × effets ; écarts par type et par région.
3. **Opérations** : têtes, poids moyen, % morts en cage, % condamnation par cause, classement des producteurs.
4. **Détail par lot** (extraction / drill-through depuis les autres pages).

Design : une seule palette (deux couleurs + gris), logo AviNord fictif, date de dernière mise à jour sur chaque page, page « À propos » qui explique le modèle (capture du schéma).

---

## 6. Publication
1. Publier dans **ton espace de travail personnel** (pas celui de l'employeur).
2. **Fichier → Incorporer le rapport → Publier sur le web** : le lien public servira sur le site et sur NovyPro.
3. Faire 3 captures propres (vue d'ensemble, pont, opérations) et une courte vidéo de démo (60–90 s).
4. Déposer sur GitHub : `scripts/`, `data/`, ce README et le `.pbix`.
