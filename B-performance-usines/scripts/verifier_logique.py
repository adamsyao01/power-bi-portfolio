"""
Réplique en pandas la logique du notebook Fabric, pour la tester sans Spark
et connaître les chiffres attendus (TRS par usine, histoires cachées).
"""
from pathlib import Path
import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
COLS_PROD = ["Date", "CodeUsine", "CodeLigne", "Quart", "CodeProduit", "MinutesOuvertes", "UnitesProduites", "UnitesRejetees"]
COLS_ARR = ["CodeUsine", "CodeLigne", "Date", "Quart", "Debut", "DureeMin", "CodeArret"]

lignes = pd.read_csv(RAW / "reference/lignes.csv")
codes = pd.read_csv(RAW / "reference/codes_arret.csv")

p_lav = pd.read_csv(RAW / "production/production_LAV.csv", dtype=str)
p_lav["Date"] = pd.to_datetime(p_lav.Date, format="%Y-%m-%d")
p_dru_brut = pd.read_csv(RAW / "production/production_DRU.csv", sep=";", dtype=str)
p_dru = p_dru_brut.drop_duplicates().copy()
p_dru["Date"] = pd.to_datetime(p_dru.Date, format="%d/%m/%Y")
p_sag = pd.read_csv(RAW / "production/production_SAG.csv", dtype=str).rename(columns={
    "date": "Date", "plant": "CodeUsine", "line": "CodeLigne", "shift": "Quart", "product": "CodeProduit",
    "open_minutes": "MinutesOuvertes", "units_produced": "UnitesProduites", "units_rejected": "UnitesRejetees"})
p_sag["CodeLigne"] = p_sag.CodeLigne.str.strip()
p_sag["Date"] = pd.to_datetime(p_sag.Date, format="%Y-%m-%d")
prod = pd.concat([p_lav[COLS_PROD], p_dru[COLS_PROD], p_sag[COLS_PROD]])
for c in ["MinutesOuvertes", "UnitesProduites", "UnitesRejetees"]:
    prod[c] = prod[c].astype(int)

a_lav = pd.read_csv(RAW / "arrets/arrets_LAV.csv", dtype=str)
a_lav["Date"] = pd.to_datetime(a_lav.Date, format="%Y-%m-%d")
a_dru = pd.read_csv(RAW / "arrets/arrets_DRU.csv", sep=";", dtype=str)
a_dru["Date"] = pd.to_datetime(a_dru.Date, format="%d/%m/%Y")
a_dru["DureeMin"] = a_dru.DureeMin.str.replace(",", ".")
a_sag = pd.read_csv(RAW / "arrets/arrets_SAG.csv", dtype=str).rename(columns={
    "plant": "CodeUsine", "line": "CodeLigne", "date": "Date", "shift": "Quart", "start_time": "Debut",
    "duration_min": "DureeMin", "stop_code": "CodeArret"})
a_sag["CodeLigne"] = a_sag.CodeLigne.str.strip()
a_sag["Date"] = pd.to_datetime(a_sag.Date, format="%Y-%m-%d")
arr = pd.concat([a_lav[COLS_ARR], a_dru[COLS_ARR], a_sag[COLS_ARR]])
arr["DureeMin"] = arr.DureeMin.astype(float)
arr = arr.merge(codes[["CodeArret", "Planifie", "Categorie"]], on="CodeArret", how="left")

aq = arr.assign(P=arr.DureeMin.where(arr.Planifie, 0), NP=arr.DureeMin.where(~arr.Planifie, 0)) \
        .groupby(["CodeLigne", "Date", "Quart"])[["P", "NP"]].sum().reset_index()
f = prod.merge(aq, on=["CodeLigne", "Date", "Quart"], how="left").fillna({"P": 0, "NP": 0}) \
        .merge(lignes[["CodeLigne", "CadenceIdealeUnitesMin"]], on="CodeLigne")
f["TR"] = f.MinutesOuvertes - f.P
f["TF"] = f.TR - f.NP
f["UT"] = f.TF * f.CadenceIdealeUnitesMin
f["UB"] = f.UnitesProduites - f.UnitesRejetees

def trs(g):
    d, p, q = g.TF.sum() / g.TR.sum(), g.UnitesProduites.sum() / g.UT.sum(), g.UB.sum() / g.UnitesProduites.sum()
    return pd.Series({"Dispo": d, "Perf": p, "Qualite": q, "TRS": d * p * q})

print("Doublons retirés à DRU :", len(p_dru_brut) - len(p_dru), "| quarts :", len(f), "| arrêts :", len(arr))
print("Codes d'arrêt inconnus :", arr.Planifie.isna().sum())
print("\nTRS par usine\n", f.groupby("CodeUsine").apply(trs).round(4))
f["Periode"] = f.Date.dt.to_period("Q").astype(str)
print("\nSAG-L3 vs autres lignes SAG, par trimestre (disponibilité)\n",
      f[f.CodeUsine == "SAG"].assign(L3=lambda x: x.CodeLigne == "SAG-L3").groupby(["Periode", "L3"]).apply(lambda g: g.TF.sum() / g.TR.sum()).unstack().round(3))
print("\nQualité par quart à DRU\n", f[f.CodeUsine == "DRU"].groupby("Quart").apply(lambda g: g.UB.sum() / g.UnitesProduites.sum()).round(4))
print("\nMinutes d'arrêt non planifié par catégorie\n", arr[~arr.Planifie.astype(bool)].groupby("Categorie").DureeMin.sum().sort_values(ascending=False).round(0))
