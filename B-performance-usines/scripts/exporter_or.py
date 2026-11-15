"""
Reproduit la couche « or » du notebook Fabric en local (pandas) et l'écrit en CSV dans ../data/or/.
Ces fichiers alimentent la COPIE PUBLIQUE du rapport (mode Import, sans RLS), publiable sur le web.
La logique est identique à celle du notebook NB_Bellerive_Transformation.
"""
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parent.parent / "data"
RAW, OR = BASE / "raw", BASE / "or"
OR.mkdir(exist_ok=True)
COLS_PROD = ["Date", "CodeUsine", "CodeLigne", "Quart", "CodeProduit", "MinutesOuvertes", "UnitesProduites", "UnitesRejetees"]
COLS_ARR = ["CodeUsine", "CodeLigne", "Date", "Quart", "Debut", "DureeMin", "CodeArret"]

usines = pd.read_csv(RAW / "reference/usines.csv")
lignes = pd.read_csv(RAW / "reference/lignes.csv")
produits = pd.read_csv(RAW / "reference/produits.csv")
codes = pd.read_csv(RAW / "reference/codes_arret.csv")

# --- production (3 formats) ---
p_lav = pd.read_csv(RAW / "production/production_LAV.csv", dtype=str)
p_lav["Date"] = pd.to_datetime(p_lav.Date, format="%Y-%m-%d")
p_dru = pd.read_csv(RAW / "production/production_DRU.csv", sep=";", dtype=str).drop_duplicates()
p_dru["Date"] = pd.to_datetime(p_dru.Date, format="%d/%m/%Y")
p_sag = pd.read_csv(RAW / "production/production_SAG.csv", dtype=str).rename(columns={
    "date": "Date", "plant": "CodeUsine", "line": "CodeLigne", "shift": "Quart", "product": "CodeProduit",
    "open_minutes": "MinutesOuvertes", "units_produced": "UnitesProduites", "units_rejected": "UnitesRejetees"})
p_sag["CodeLigne"] = p_sag.CodeLigne.str.strip()
p_sag["Date"] = pd.to_datetime(p_sag.Date, format="%Y-%m-%d")
prod = pd.concat([p_lav[COLS_PROD], p_dru[COLS_PROD], p_sag[COLS_PROD]], ignore_index=True)
for c in ["MinutesOuvertes", "UnitesProduites", "UnitesRejetees"]:
    prod[c] = prod[c].astype(int)

# --- arrêts (3 formats) ---
a_lav = pd.read_csv(RAW / "arrets/arrets_LAV.csv", dtype=str)
a_lav["Date"] = pd.to_datetime(a_lav.Date, format="%Y-%m-%d")
a_lav["Debut"] = pd.to_datetime(a_lav.Debut, format="%Y-%m-%d %H:%M:%S")
a_dru = pd.read_csv(RAW / "arrets/arrets_DRU.csv", sep=";", dtype=str)
a_dru["Date"] = pd.to_datetime(a_dru.Date, format="%d/%m/%Y")
a_dru["Debut"] = pd.to_datetime(a_dru.Debut, format="%d/%m/%Y %H:%M")
a_dru["DureeMin"] = a_dru.DureeMin.str.replace(",", ".")
a_sag = pd.read_csv(RAW / "arrets/arrets_SAG.csv", dtype=str).rename(columns={
    "plant": "CodeUsine", "line": "CodeLigne", "date": "Date", "shift": "Quart", "start_time": "Debut",
    "duration_min": "DureeMin", "stop_code": "CodeArret"})
a_sag["CodeLigne"] = a_sag.CodeLigne.str.strip()
a_sag["Date"] = pd.to_datetime(a_sag.Date, format="%Y-%m-%d")
a_sag["Debut"] = pd.to_datetime(a_sag.Debut, format="%Y-%m-%d %H:%M:%S")
arr = pd.concat([a_lav[COLS_ARR], a_dru[COLS_ARR], a_sag[COLS_ARR]], ignore_index=True)
arr["DureeMin"] = arr.DureeMin.astype(float)

# --- temps du TRS par quart ---
a = arr.merge(codes[["CodeArret", "Planifie"]], on="CodeArret", how="left")
aq = (a.assign(MinutesArretPlanifie=a.DureeMin.where(a.Planifie, 0),
               MinutesArretNonPlanifie=a.DureeMin.where(~a.Planifie, 0),
               NbArretsNonPlanifies=(~a.Planifie).astype(int))
       .groupby(["CodeLigne", "Date", "Quart"])[["MinutesArretPlanifie", "MinutesArretNonPlanifie", "NbArretsNonPlanifies"]]
       .sum().reset_index())
fp = (prod.merge(aq, on=["CodeLigne", "Date", "Quart"], how="left")
          .fillna({"MinutesArretPlanifie": 0, "MinutesArretNonPlanifie": 0, "NbArretsNonPlanifies": 0})
          .merge(lignes[["CodeLigne", "CadenceIdealeUnitesMin"]], on="CodeLigne", how="left"))
fp["TempsRequisMin"] = fp.MinutesOuvertes - fp.MinutesArretPlanifie
fp["TempsFonctionnementMin"] = fp.TempsRequisMin - fp.MinutesArretNonPlanifie
fp["UnitesTheoriques"] = fp.TempsFonctionnementMin * fp.CadenceIdealeUnitesMin
fp["UnitesBonnes"] = fp.UnitesProduites - fp.UnitesRejetees
fp = fp.drop(columns="CadenceIdealeUnitesMin")

# --- dimensions ---
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
dd = pd.DataFrame({"Date": pd.date_range(fp.Date.min(), fp.Date.max())})
dd["Annee"] = dd.Date.dt.year
dd["NoMois"] = dd.Date.dt.month
dd["Mois"] = dd.NoMois.map(lambda m: MOIS[m - 1])
dd["AnneeMois"] = dd.Date.dt.strftime("%Y-%m")
dd["CleAnneeMois"] = dd.Annee * 100 + dd.NoMois
dd["SemaineISO"] = dd.Date.dt.isocalendar().week.astype(int)
dd["JourSemaine"] = dd.Date.dt.dayofweek + 1
quarts = pd.DataFrame([("Jour", 1, "06:00"), ("Soir", 2, "14:00"), ("Nuit", 3, "22:00")],
                      columns=["Quart", "OrdreQuart", "HeureDebut"])

def ecrire(df, nom):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S" if c == "Debut" else "%Y-%m-%d")
    df.to_csv(OR / f"{nom}.csv", index=False, encoding="utf-8")
    print(f"{nom:<16} {len(df):>8,} lignes")

ecrire(usines, "dim_usine")
ecrire(lignes, "dim_ligne")
ecrire(produits, "dim_produit")
ecrire(codes, "dim_code_arret")
ecrire(quarts, "dim_quart")
ecrire(dd, "dim_date")
ecrire(fp, "fact_production")
ecrire(arr, "fact_arret")
