# Projet C — Tableau de bord financier de PME

**Entreprise fictive** : Biscuiterie Lumen inc., PME québécoise d'environ 19 M$ de ventes, exercice du 1er avril au 31 mars.
**Objectif** : le besoin numéro un de toute PME, soit un état des résultats réel vs budget vs année précédente, l'analyse des écarts et une prévision de trésorerie sur 13 semaines.

🔎 **[Démo interactive en ligne](https://app.powerbi.com/view?r=eyJrIjoiOWQzMTYzNzktZjI5MC00NmU2LTkxMmEtYzJkMTQ4ZWYwNjNmIiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9)**

> Données 100 % fictives, générées par `scripts/generer_donnees.py`. Le projet Power BI (`Lumen-Finances.pbip`) est généré par `scripts/generer_pbip.py`.

## Ouvrir le projet
1. Double-clique sur **`Lumen-Finances.pbip`**, puis clique sur **Actualiser**.
2. Si le dossier a bougé : *Transformer les données → Modifier les paramètres → DossierDonnees*.

## Les données (`data/`)
| Fichier | Contenu |
|---|---|
| `FaitGL.csv` | réel mensuel par compte, d'avril 2024 à octobre 2026 |
| `FaitBudget.csv` | budget mensuel par compte (exercices 2025-26 et 2026-27) |
| `FaitTresorerie.csv` | flux hebdomadaires : 26 semaines réelles et 13 semaines de prévision |
| `DimCompte.csv` | plan comptable : compte → catégorie, avec le signe (revenus +, charges −) |
| `StructurePL.csv` | lignes de l'état des résultats et sous-totaux |
| `DimDate.csv` | calendrier fiscal d'avril à mars |

## Les histoires cachées dans les données (exercice 2026-27, d'avril à octobre)
| Indicateur | Réel | Budget |
|---|---|---|
| Revenus | 10,40 M$ | 10,12 M$ (**+2,7 %**) |
| Marge brute % | **38,0 %** | 42,0 % |
| BAIIA | **1,48 M$** | 1,91 M$ (**−0,44 M$**) |
| Marketing | 0,44 M$ | 0,31 M$ |

- **Les ventes dépassent le budget, mais la rentabilité recule** : les matières premières passent de 30 % à 34,5 % des ventes, et le marketing dépasse son budget.
- **L'export progresse** : 21 % des ventes, contre 15 % deux ans plus tôt.
- **Trésorerie** : le solde actuel est d'environ 1,2 M$, mais la prévision tombe autour de **60 k$ fin décembre** (sous le seuil dès la mi-décembre), sous le seuil de sécurité de 150 k$. En cause : une ligne d'emballage à 650 k$, les stocks des Fêtes et un acompte d'impôt.

## Les choix de modélisation
- **Montants signés** dans les faits : revenus positifs, charges négatives. Un sous-total n'est alors qu'une somme.
- **Table `StructurePL`** déconnectée : une seule mesure `PL Réel` calcule chaque ligne. Une ligne « Détail » prend sa catégorie, une ligne « Sous-total » prend toutes les catégories de rang inférieur.
- **Budget et année précédente comparés à date égale**, plafonnés au dernier mois fermé.
- **Groupe de calcul `Vue`** : *Mois sélectionné* ou *Cumul de l'exercice* (`DATESYTD(DimDate[Date], "3-31")`).
- **Trésorerie** : solde cumulé hebdomadaire, point bas et manque sous le seuil calculés dynamiquement.

## Pages
1. **Sommaire** : indicateurs clés et tendances réel vs budget.
2. **État des résultats** : réel, budget, écarts, année précédente, % des revenus.
3. **Analyse des écarts** : écart par compte, trié du plus défavorable au plus favorable.
4. **Trésorerie** : solde réel et prévu vs seuil, encaissements et décaissements, flux par catégorie.
5. **À propos**.
