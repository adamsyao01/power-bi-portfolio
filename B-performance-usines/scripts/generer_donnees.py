"""
Projet B — « Performance multi-usines » : génère des fichiers BRUTS fictifs, comme on les
recevrait d'un système de production (MES) dans 3 usines différentes.

Entreprise fictive : Aliments Bellerive (transformation alimentaire, Québec). Aucune donnée réelle.
Les 3 usines n'exportent PAS au même format (c'est voulu : le notebook Fabric doit nettoyer) :
  - LAV (Laval)          : dates AAAA-MM-JJ, séparateur « , », point décimal
  - DRU (Drummondville)  : dates JJ/MM/AAAA, séparateur « ; », virgule décimale, quelques doublons
  - SAG (Saguenay)       : dates AAAA-MM-JJ, noms de colonnes en anglais, espaces parasites

Usage : python generer_donnees.py   → écrit ../data/raw/...
"""
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
(OUT / "reference").mkdir(parents=True, exist_ok=True)
(OUT / "production").mkdir(parents=True, exist_ok=True)
(OUT / "arrets").mkdir(parents=True, exist_ok=True)

DEBUT, FIN = date(2025, 1, 1), date(2026, 10, 31)

# ---------------------------------------------------------------------------
# Référentiels
# ---------------------------------------------------------------------------
usines = pd.DataFrame([
    {"CodeUsine": "LAV", "Usine": "Laval",         "Region": "Montréal",               "CourrielDirecteur": "directeur.laval@bellerive-demo.ca"},
    {"CodeUsine": "DRU", "Usine": "Drummondville", "Region": "Centre-du-Québec",       "CourrielDirecteur": "directeur.drummondville@bellerive-demo.ca"},
    {"CodeUsine": "SAG", "Usine": "Saguenay",      "Region": "Saguenay–Lac-Saint-Jean", "CourrielDirecteur": "directeur.saguenay@bellerive-demo.ca"},
])
usines.to_csv(OUT / "reference" / "usines.csv", index=False, encoding="utf-8")

TYPES = ["Cuisson", "Tranchage", "Emballage sous vide", "Mise en barquette"]
lignes = []
for u in usines.CodeUsine:
    for i, t in enumerate(TYPES, start=1):
        lignes.append({"CodeLigne": f"{u}-L{i}", "CodeUsine": u, "Ligne": f"Ligne {i} — {t}", "TypeLigne": t,
                       "CadenceIdealeUnitesMin": {"Cuisson": 40, "Tranchage": 75, "Emballage sous vide": 55, "Mise en barquette": 60}[t]})
lignes = pd.DataFrame(lignes)
lignes.to_csv(OUT / "reference" / "lignes.csv", index=False, encoding="utf-8")

produits = pd.DataFrame([
    {"CodeProduit": "P100", "Produit": "Poitrine de poulet cuite tranchée", "Famille": "Volaille cuite"},
    {"CodeProduit": "P110", "Produit": "Lanières de poulet grillées",      "Famille": "Volaille cuite"},
    {"CodeProduit": "P200", "Produit": "Jambon fumé tranché",              "Famille": "Charcuterie"},
    {"CodeProduit": "P210", "Produit": "Dinde rôtie tranchée",             "Famille": "Charcuterie"},
    {"CodeProduit": "P300", "Produit": "Bol repas poulet-riz",             "Famille": "Prêt-à-manger"},
    {"CodeProduit": "P310", "Produit": "Salade-repas au poulet",           "Famille": "Prêt-à-manger"},
])
produits.to_csv(OUT / "reference" / "produits.csv", index=False, encoding="utf-8")

codes = pd.DataFrame([
    {"CodeArret": "PL-01", "Arret": "Pause planifiée",            "Categorie": "Arrêt planifié",      "Planifie": True},
    {"CodeArret": "PL-02", "Arret": "Nettoyage planifié",         "Categorie": "Arrêt planifié",      "Planifie": True},
    {"CodeArret": "CF-01", "Arret": "Changement de format",       "Categorie": "Changement de format", "Planifie": False},
    {"CodeArret": "PM-01", "Arret": "Panne — trancheuse",         "Categorie": "Panne mécanique",     "Planifie": False},
    {"CodeArret": "PM-02", "Arret": "Panne — scelleuse",          "Categorie": "Panne mécanique",     "Planifie": False},
    {"CodeArret": "PM-04", "Arret": "Panne — convoyeur",          "Categorie": "Panne mécanique",     "Planifie": False},
    {"CodeArret": "MM-01", "Arret": "Manque de matière première", "Categorie": "Manque de matière",   "Planifie": False},
    {"CodeArret": "MM-02", "Arret": "Manque d'emballage",         "Categorie": "Manque de matière",   "Planifie": False},
    {"CodeArret": "QA-01", "Arret": "Retenue qualité",            "Categorie": "Qualité",             "Planifie": False},
    {"CodeArret": "PE-01", "Arret": "Manque de personnel",        "Categorie": "Main-d'œuvre",        "Planifie": False},
])
codes.to_csv(OUT / "reference" / "codes_arret.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# Production et arrêts, par quart
# ---------------------------------------------------------------------------
QUARTS = {"Jour": 6, "Soir": 14, "Nuit": 22}   # heure de début
PROD_PAR_TYPE = {"Cuisson": ["P100", "P110", "P210"], "Tranchage": ["P100", "P200", "P210"],
                 "Emballage sous vide": ["P100", "P110", "P200", "P210"], "Mise en barquette": ["P300", "P310"]}
NON_PLANIF = ["CF-01", "PM-01", "PM-02", "PM-04", "MM-01", "MM-02", "QA-01", "PE-01"]
POIDS_BASE = np.array([0.34, 0.12, 0.10, 0.08, 0.12, 0.08, 0.06, 0.10])

prod_rows, arret_rows = [], []
n_jours = (FIN - DEBUT).days + 1
for k in range(n_jours):
    d = DEBUT + timedelta(days=k)
    if d.weekday() == 6:          # pas de production le dimanche
        continue
    t_annee = k / 365
    for _, ln in lignes.iterrows():
        for quart, h0 in QUARTS.items():
            if d.weekday() == 5 and quart == "Nuit":   # pas de quart de nuit le samedi
                continue
            produit = rng.choice(PROD_PAR_TYPE[ln.TypeLigne])
            minutes_ouvertes = 480
            # arrêts planifiés
            evts = [("PL-01", 30)]
            if quart == "Nuit":
                evts.append(("PL-02", 45))
            # arrêts non planifiés : nombre et durée
            n = rng.poisson(2.6)
            poids = POIDS_BASE.copy()
            # Histoire 1 : le convoyeur de SAG-L3 se dégrade à partir de mars 2026
            degr = ln.CodeLigne == "SAG-L3" and d >= date(2026, 3, 1)
            if degr:
                n += rng.poisson(1.8)
                poids[NON_PLANIF.index("PM-04")] *= 6
            # Histoire 2 : les manques de personnel augmentent l'été à DRU
            if ln.CodeUsine == "DRU" and d.month in (6, 7, 8):
                poids[NON_PLANIF.index("PE-01")] *= 3
            poids /= poids.sum()
            for _ in range(n):
                code = NON_PLANIF[rng.choice(len(NON_PLANIF), p=poids)]
                duree = {"CF-01": rng.normal(28, 8), "PM-04": rng.normal(35 if degr else 18, 10)}.get(code, rng.gamma(2.2, 7))
                evts.append((code, int(max(3, round(duree)))))
            # sécurité : les arrêts ne dépassent pas 70 % du quart
            total = sum(m for _, m in evts)
            if total > 0.7 * minutes_ouvertes:
                f = 0.7 * minutes_ouvertes / total
                evts = [(c, max(1, int(m * f))) for c, m in evts]
            arrets_np = sum(m for c, m in evts if not c.startswith("PL"))
            planif = sum(m for c, m in evts if c.startswith("PL"))
            fonctionnement = minutes_ouvertes - planif - arrets_np
            # performance (vitesse) et qualité
            perf = np.clip(rng.normal(0.90 - (0.04 if quart == "Nuit" else 0) + 0.02 * t_annee, 0.04), 0.6, 0.99)
            unites = int(fonctionnement * ln.CadenceIdealeUnitesMin * perf)
            # Histoire 3 : plus de rebuts sur le quart de nuit à DRU
            taux_rebut = max(rng.normal(0.018 + (0.022 if ln.CodeUsine == "DRU" and quart == "Nuit" else 0), 0.006), 0.002)
            rejets = int(unites * taux_rebut)
            prod_rows.append({"Date": d, "CodeUsine": ln.CodeUsine, "CodeLigne": ln.CodeLigne, "Quart": quart,
                              "CodeProduit": produit, "MinutesOuvertes": minutes_ouvertes,
                              "UnitesProduites": unites, "UnitesRejetees": rejets})
            # horodatage des arrêts à l'intérieur du quart
            t = 15
            for code, m in evts:
                t += int(rng.integers(5, 40))
                debut = pd.Timestamp(d) + pd.Timedelta(hours=h0, minutes=t)
                arret_rows.append({"CodeUsine": ln.CodeUsine, "CodeLigne": ln.CodeLigne, "Date": d, "Quart": quart,
                                   "Debut": debut, "DureeMin": m, "CodeArret": code})
                t += m

prod = pd.DataFrame(prod_rows)
arr = pd.DataFrame(arret_rows)

# ---------------------------------------------------------------------------
# Écriture au format propre à chaque usine
# ---------------------------------------------------------------------------
for u in ["LAV", "DRU", "SAG"]:
    p = prod[prod.CodeUsine == u].copy()
    a = arr[arr.CodeUsine == u].copy()
    if u == "LAV":
        p.to_csv(OUT / "production" / "production_LAV.csv", index=False, encoding="utf-8")
        a.to_csv(OUT / "arrets" / "arrets_LAV.csv", index=False, encoding="utf-8")
    elif u == "DRU":
        p["Date"] = pd.to_datetime(p.Date).dt.strftime("%d/%m/%Y")
        a["Date"] = pd.to_datetime(a.Date).dt.strftime("%d/%m/%Y")
        a["Debut"] = a.Debut.dt.strftime("%d/%m/%Y %H:%M")
        a["DureeMin"] = a.DureeMin.astype(float).map(lambda v: f"{v:.1f}".replace(".", ","))
        dup = p.sample(frac=0.004, random_state=1)            # doublons d'export
        p = pd.concat([p, dup]).sort_values(["Date", "CodeLigne", "Quart"], kind="stable")
        p.to_csv(OUT / "production" / "production_DRU.csv", index=False, sep=";", encoding="utf-8")
        a.to_csv(OUT / "arrets" / "arrets_DRU.csv", index=False, sep=";", encoding="utf-8")
    else:
        p = p.rename(columns={"Date": "date", "CodeUsine": "plant", "CodeLigne": "line", "Quart": "shift",
                              "CodeProduit": "product", "MinutesOuvertes": "open_minutes",
                              "UnitesProduites": "units_produced", "UnitesRejetees": "units_rejected"})
        p["line"] = "  " + p["line"] + " "                     # espaces parasites
        a = a.rename(columns={"CodeUsine": "plant", "CodeLigne": "line", "Date": "date", "Quart": "shift",
                              "Debut": "start_time", "DureeMin": "duration_min", "CodeArret": "stop_code"})
        p.to_csv(OUT / "production" / "production_SAG.csv", index=False, encoding="utf-8")
        a.to_csv(OUT / "arrets" / "arrets_SAG.csv", index=False, encoding="utf-8")

print(f"OK — {len(prod):,} quarts, {len(arr):,} arrêts → {OUT}")
