"""
Génère les données FICTIVES du projet A « Approvisionnement v2 ».
Entreprise fictive : AviNord (transformateur de volaille, Québec).
Aucune donnée réelle : tout est simulé avec une graine fixe (résultats reproductibles).

Usage : python generer_donnees.py   → écrit les CSV dans ../data/
"""
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(2026)
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Calendrier fiscal : 13 périodes de 4 semaines (dimanche → samedi)
# ---------------------------------------------------------------------------
FY_START = {2024: date(2023, 12, 31), 2025: date(2024, 12, 29), 2026: date(2025, 12, 28)}
DERNIERE_DATE_REELLE = date(2026, 11, 12)  # le « hier » de la démo : période 12 en cours

rows = []
for fy, start in FY_START.items():
    for i in range(364):
        d = start + timedelta(days=i)
        p = i // 28 + 1
        rows.append({
            "Date": d,
            "Exercice": fy,
            "NoPeriode": p,
            "Periode": f"P{p:02d}",
            "ExercicePeriode": f"FY{fy % 100}-P{p:02d}",
            "CleExercicePeriode": fy * 100 + p,
            "SemaineExercice": i // 7 + 1,
            "SemainePeriode": (i % 28) // 7 + 1,
            "JourPeriode": i % 28 + 1,
            "DebutPeriode": start + timedelta(days=(p - 1) * 28),
            "FinPeriode": start + timedelta(days=(p - 1) * 28 + 27),
            "JourSemaine": d.isoweekday() % 7 + 1,  # 1 = dimanche
            "NomJour": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"][d.weekday()],
            "AnneeCivile": d.year,
            "MoisCivil": d.month,
        })
dim_date = pd.DataFrame(rows)
dim_date.to_csv(OUT / "DimDate.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# 2. Dimensions
# ---------------------------------------------------------------------------
REGIONS = {"Québec": 28, "Ontario-Est": 14}
prod_rows, pid = [], 1
for region, n in REGIONS.items():
    code = "QC" if region == "Québec" else "ON"
    for k in range(1, n + 1):
        prod_rows.append({
            "ProducteurID": pid,
            "Producteur": f"Producteur {code}-{k:03d}",
            "Region": region,
            "DistanceKm": int(rng.integers(20, 160) if code == "QC" else rng.integers(180, 420)),
            "TailleFerme": rng.choice(["Petite", "Moyenne", "Grande"], p=[0.3, 0.45, 0.25]),
        })
        pid += 1
dim_region = pd.DataFrame([{"RegionID": 1, "Region": "Québec"}, {"RegionID": 2, "Region": "Ontario-Est"}])
dim_region.to_csv(OUT / "DimRegion.csv", index=False, encoding="utf-8-sig")
dim_prod = pd.DataFrame(prod_rows)
dim_prod.to_csv(OUT / "DimProducteur.csv", index=False, encoding="utf-8-sig")

dim_type = pd.DataFrame([
    {"TypePouletID": 1, "TypePoulet": "Poulet à griller", "PoidsCibleKg": 2.45, "PrimeBaseKg": 0.00},
    {"TypePouletID": 2, "TypePoulet": "Poulet lourd",     "PoidsCibleKg": 3.40, "PrimeBaseKg": 0.06},
    {"TypePouletID": 3, "TypePoulet": "Poulet de grain",  "PoidsCibleKg": 2.30, "PrimeBaseKg": 0.32},
])
dim_type.to_csv(OUT / "DimTypePoulet.csv", index=False, encoding="utf-8-sig")

dim_transp = pd.DataFrame([{"TransporteurID": i, "Transporteur": f"Transporteur T{i:02d}"} for i in range(1, 9)])
dim_transp.to_csv(OUT / "DimTransporteur.csv", index=False, encoding="utf-8-sig")

dim_cond = pd.DataFrame([
    {"CauseID": 1, "Cause": "Ascite"},
    {"CauseID": 2, "Cause": "Cellulite"},
    {"CauseID": 3, "Cause": "Septicémie"},
    {"CauseID": 4, "Cause": "Ecchymoses"},
    {"CauseID": 5, "Cause": "Dermatite"},
    {"CauseID": 6, "Cause": "Autre"},
])
dim_cond.to_csv(OUT / "DimCauseCondamnation.csv", index=False, encoding="utf-8-sig")

dim_comp = pd.DataFrame([
    {"Composante": "Prix de base",  "Groupe": "Prix du vivant", "Ordre": 1},
    {"Composante": "Ajustement",    "Groupe": "Prix du vivant", "Ordre": 2},
    {"Composante": "Bonification",  "Groupe": "Bonification",   "Ordre": 3},
    {"Composante": "Chargement",    "Groupe": "Logistique",     "Ordre": 4},
    {"Composante": "Transport",     "Groupe": "Logistique",     "Ordre": 5},
])
dim_comp.to_csv(OUT / "DimComposante.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# 3. Faits : réceptions de lots
# ---------------------------------------------------------------------------
# Part de l'Ontario-Est qui augmente avec le temps → effet mix visible en 2026
PART_ONTARIO = {2024: 0.24, 2025: 0.27, 2026: 0.36}
TYPE_MIX = [0.70, 0.18, 0.12]
PRIX_BASE = {2024: 2.18, 2025: 2.26, 2026: 2.37}       # $/kg, Québec, poulet à griller
ECART_PRIX_ON = -0.02                                   # l'Ontario-Est est un peu moins cher à la base…
TRANSPORT_KG = {"Québec": 0.035, "Ontario-Est": 0.095}  # …mais plus cher à transporter

lots, causes_rows, lot_id = [], [], 1
prod_by_region = {r: dim_prod[dim_prod.Region == r] for r in REGIONS}
for _, d in dim_date[dim_date.Date <= DERNIERE_DATE_REELLE].iterrows():
    if d.NomJour in ("samedi", "dimanche"):
        continue
    fy, i = d.Exercice, (d.Date - FY_START[d.Exercice]).days
    saison = 1 + 0.05 * np.sin(2 * np.pi * (i - 150) / 364)   # pic d'été
    n_lots = int(rng.integers(7, 11))
    for _ in range(n_lots):
        region = "Ontario-Est" if rng.random() < PART_ONTARIO[fy] else "Québec"
        p = prod_by_region[region].sample(1, random_state=int(rng.integers(1e9))).iloc[0]
        t = dim_type.iloc[rng.choice(3, p=TYPE_MIX)]
        tetes = int(rng.normal(16000, 3500) * saison)
        tetes = max(tetes, 6000)
        poids_moy = rng.normal(t.PoidsCibleKg, 0.12)
        mec = int(tetes * max(rng.normal(0.0035 + (0.0015 if region == "Ontario-Est" else 0), 0.0012), 0))
        kg_vifs = round((tetes - mec) * poids_moy, 1)
        kg_mec = round(mec * poids_moy, 1)
        taux_cond = max(rng.normal(0.008, 0.003), 0.001)
        kg_cond = round(kg_vifs * taux_cond, 1)
        kg_payes = round(kg_vifs - kg_cond, 1)

        prix_base = PRIX_BASE[fy] * saison ** 0.5 + t.PrimeBaseKg + (ECART_PRIX_ON if region == "Ontario-Est" else 0)
        prix_base = round(prix_base + rng.normal(0, 0.015), 4)
        ajust = round(rng.normal(-0.012, 0.008), 4)
        bonif = round(max(rng.normal(0.035 if p.TailleFerme == "Grande" else 0.025, 0.01), 0), 4)
        transport = round(TRANSPORT_KG[region] * (p.DistanceKm / (90 if region == "Québec" else 300)) ** 0.5
                          * rng.normal(1, 0.05), 4)
        chargement = round(rng.normal(780, 60), 2)  # $ fixes par lot (équipe d'attrapage)

        lots.append({
            "LotID": lot_id,
            "NoLot": f"L{d.Date:%y%m%d}-{lot_id % 1000:03d}",
            "DateAbattage": d.Date,
            "ProducteurID": int(p.ProducteurID),
            "TypePouletID": int(t.TypePouletID),
            "TransporteurID": int(rng.integers(1, 9)),
            "TetesRecues": tetes,
            "MortsEnCage": mec,
            "KgVifsRecus": kg_vifs,
            "KgMortsEnCage": kg_mec,
            "KgCondamnes": kg_cond,
            "KgPayes": kg_payes,
            "MontantPrixBase": round(kg_payes * prix_base, 2),
            "MontantAjustement": round(kg_payes * ajust, 2),
            "MontantBonification": round(kg_payes * bonif, 2),
            "MontantChargement": chargement,
            "MontantTransport": round(kg_payes * transport, 2),
        })
        # condamnations détaillées par cause
        reste = kg_cond
        poids_causes = rng.dirichlet([3, 2, 1.5, 2, 1, 0.5])
        for cid, w in enumerate(poids_causes, start=1):
            kg = round(kg_cond * w, 1)
            if kg > 0:
                causes_rows.append({"LotID": lot_id, "CauseID": cid, "KgCondamnes": kg})
        lot_id += 1

fact = pd.DataFrame(lots)
fact.to_csv(OUT / "FaitReceptionLot.csv", index=False, encoding="utf-8-sig")
pd.DataFrame(causes_rows).to_csv(OUT / "FaitCondamnation.csv", index=False, encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# 4. Budget : grain période × type de poulet × région (comme le fournit la finance)
# ---------------------------------------------------------------------------
fact_p = fact.merge(dim_date[["Date", "Exercice", "NoPeriode"]], left_on="DateAbattage", right_on="Date") \
             .merge(dim_prod[["ProducteurID", "Region"]], on="ProducteurID")
moy = fact_p.groupby(["Exercice", "TypePouletID", "Region"]).agg(
    kg=("KgPayes", "sum"),
    base=("MontantPrixBase", "sum"), aj=("MontantAjustement", "sum"), bo=("MontantBonification", "sum"),
    tr=("MontantTransport", "sum"), ch=("MontantChargement", "sum"), n=("LotID", "count"))

bud_rows = []
for fy in FY_START:
    ref = fy - 1 if fy - 1 in FY_START else fy           # budget bâti sur l'année précédente
    hausse = 1.03 if ref != fy else 1.0
    kg_total_ref = moy.loc[ref].kg.sum() / (13 if ref != 2026 else 11.4)  # kg moyens / période
    for (tid, region), r in moy.loc[ref].iterrows():
        part_type = TYPE_MIX[tid - 1]
        part_region = 0.25 if region == "Ontario-Est" else 0.75          # mix planifié
        for p in range(1, 14):
            kg = kg_total_ref * 1.02 * part_type * part_region * rng.normal(1, 0.02)
            bud_rows.append({
                "Exercice": fy, "NoPeriode": p, "CleExercicePeriode": fy * 100 + p,
                "TypePouletID": tid, "Region": region,
                "KgPayesBudget": round(kg, 0),
                "MontantPrixBaseBudget": round(kg * r.base / r.kg * hausse, 2),
                "MontantAjustementBudget": round(kg * r.aj / r.kg, 2),
                "MontantBonificationBudget": round(kg * r.bo / r.kg, 2),
                "MontantChargementBudget": round(kg * r.ch / r.kg, 2),
                "MontantTransportBudget": round(kg * r.tr / r.kg * hausse, 2),
            })
pd.DataFrame(bud_rows).to_csv(OUT / "FaitBudgetPeriode.csv", index=False, encoding="utf-8-sig")

print(f"OK — {len(fact):,} lots, {len(causes_rows):,} lignes de condamnation, {len(bud_rows)} lignes de budget → {OUT}")
