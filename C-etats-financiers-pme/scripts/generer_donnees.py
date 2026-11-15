"""
Projet C — « États financiers de PME » : données FICTIVES d'une PME québécoise.
Entreprise fictive : Biscuiterie Lumen inc. (environ 19 M$ de ventes), exercice du 1er avril au 31 mars.

Sorties (../data/) :
  DimDate, DimCompte, StructurePL, FaitGL (réel mensuel par compte), FaitBudget, FaitTresorerie (hebdomadaire).

Histoires cachées :
  1. Exercice 2027 (en cours) : ventes AU-DESSUS du budget (+3 %), mais BAIIA SOUS le budget,
     à cause de la hausse des matières premières (beurre, farine) et d'un dépassement en marketing.
  2. Les ventes à l'export progressent fortement.
  3. Trésorerie : la prévision sur 13 semaines passe SOUS le seuil de sécurité en décembre
     (achat d'une ligne d'emballage + stocks des Fêtes + encaissements décalés en janvier).
"""
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(7)
OUT = Path(__file__).resolve().parent.parent / "data"
OUT.mkdir(exist_ok=True)
NOMS_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]

def fy(d):  # exercice se terminant le 31 mars
    return d.year + 1 if d.month >= 4 else d.year

# ---------------------------------------------------------------------------
# Calendrier (1er avril 2024 → 31 mars 2027)
# ---------------------------------------------------------------------------
jours = pd.date_range("2024-04-01", "2027-03-31")
dd = pd.DataFrame({"Date": jours})
dd["AnneeFiscale"] = dd.Date.map(lambda d: fy(d))
dd["Exercice"] = "Ex. " + (dd.AnneeFiscale - 1).astype(str) + "-" + (dd.AnneeFiscale % 100).astype(str).str.zfill(2)
dd["MoisFiscal"] = (dd.Date.dt.month - 4) % 12 + 1
dd["Mois"] = dd.Date.dt.month.map(lambda m: NOMS_MOIS[m - 1])
dd["MoisAnnee"] = dd.Date.dt.strftime("%Y-%m")
dd["CleMois"] = dd.Date.dt.year * 100 + dd.Date.dt.month
dd["DebutSemaine"] = dd.Date - pd.to_timedelta(dd.Date.dt.weekday, unit="D")
dd["AnneeCivile"] = dd.Date.dt.year
dd["MoisCivil"] = dd.Date.dt.month
dd.to_csv(OUT / "DimDate.csv", index=False, date_format="%Y-%m-%d", encoding="utf-8")

# ---------------------------------------------------------------------------
# Plan comptable et structure de l'état des résultats
# ---------------------------------------------------------------------------
CAT = {  # catégorie → (ordre dans l'état des résultats, signe)
    "Revenus": (1, 1), "Coût des ventes": (2, -1), "Frais de vente": (4, -1), "Frais d'administration": (5, -1),
    "Amortissement": (7, -1), "Frais financiers": (9, -1), "Impôts sur le résultat": (11, -1)}
comptes = [
    (4000, "Ventes — épiceries", "Revenus", "Ventes"),
    (4010, "Ventes — restauration", "Revenus", "Ventes"),
    (4020, "Ventes — export", "Revenus", "Ventes"),
    (4900, "Escomptes et ristournes", "Revenus", "Escomptes"),
    (5000, "Matières premières", "Coût des ventes", "Matières"),
    (5010, "Emballage", "Coût des ventes", "Matières"),
    (5100, "Main-d'œuvre directe", "Coût des ventes", "Main-d'œuvre"),
    (5200, "Frais généraux de fabrication", "Coût des ventes", "Frais de fabrication"),
    (6000, "Salaires — ventes", "Frais de vente", "Salaires"),
    (6010, "Marketing et promotion", "Frais de vente", "Marketing"),
    (6020, "Transport et livraison", "Frais de vente", "Transport"),
    (6500, "Salaires — administration", "Frais d'administration", "Salaires"),
    (6510, "Loyer", "Frais d'administration", "Locaux"),
    (6520, "Assurances", "Frais d'administration", "Locaux"),
    (6530, "Honoraires professionnels", "Frais d'administration", "Services"),
    (6540, "Informatique", "Frais d'administration", "Services"),
    (7000, "Amortissement", "Amortissement", "Amortissement"),
    (7500, "Intérêts sur la dette", "Frais financiers", "Intérêts"),
    (8000, "Impôts sur le résultat", "Impôts sur le résultat", "Impôts"),
]
dc = pd.DataFrame(comptes, columns=["NoCompte", "Compte", "Categorie", "SousCategorie"])
dc["OrdreCategorie"] = dc.Categorie.map(lambda c: CAT[c][0])
dc["Signe"] = dc.Categorie.map(lambda c: CAT[c][1])
dc.loc[dc.NoCompte == 4900, "Signe"] = -1          # escomptes : contre-revenu
dc["CompteAffiche"] = dc.NoCompte.astype(str) + " · " + dc.Compte
dc.to_csv(OUT / "DimCompte.csv", index=False, encoding="utf-8")

structure = pd.DataFrame([
    (1, "Revenus", "Détail"), (2, "Coût des ventes", "Détail"), (3, "Marge brute", "Sous-total"),
    (4, "Frais de vente", "Détail"), (5, "Frais d'administration", "Détail"), (6, "BAIIA", "Sous-total"),
    (7, "Amortissement", "Détail"), (8, "Bénéfice d'exploitation (BAII)", "Sous-total"),
    (9, "Frais financiers", "Détail"), (10, "Bénéfice avant impôts", "Sous-total"),
    (11, "Impôts sur le résultat", "Détail"), (12, "Bénéfice net", "Sous-total"),
], columns=["Ordre", "LignePL", "TypeLigne"])
structure.to_csv(OUT / "StructurePL.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# Montants mensuels : réel (FY2025 → oct. 2026) et budget (FY2026, FY2027)
# ---------------------------------------------------------------------------
SAISON = {4: .95, 5: .95, 6: .90, 7: .85, 8: .90, 9: 1.0, 10: 1.05, 11: 1.25, 12: 1.35, 1: .85, 2: .90, 3: 1.0}
BASE_VENTES = {2025: 1.40e6, 2026: 1.40e6 * 1.06, 2027: 1.40e6 * 1.06 * 1.09}   # réel
CROISS_BUDGET = {2026: 1.05, 2027: 1.06}

def montants_mois(annee_f, mois, budget=False):
    s = SAISON[mois]
    bruit = (lambda: 1.0) if budget else (lambda: rng.normal(1, 0.03))
    if budget:
        ventes = BASE_VENTES[annee_f - 1] * CROISS_BUDGET[annee_f] * s
    else:
        ventes = BASE_VENTES[annee_f] * s * bruit()
    export = {2025: .15, 2026: .17, 2027: .21}[annee_f] if not budget else {2026: .16, 2027: .18}[annee_f]
    resto = .23
    mp = .345 if (annee_f == 2027 and not budget) else (.305 if budget else .30)        # Histoire 1
    marketing = .041 if (annee_f == 2027 and not budget) else .03
    m = {
        4000: ventes * (1 - export - resto), 4010: ventes * resto, 4020: ventes * export,
        4900: ventes * .025,
        5000: ventes * mp * bruit(), 5010: ventes * .08 * bruit(), 5100: ventes * .12 * bruit(),
        5200: 90_000 * bruit(),
        6000: 70_000 * bruit(), 6010: ventes * marketing * bruit(), 6020: ventes * .05 * bruit(),
        6500: 85_000 * bruit(), 6510: 38_000, 6520: 6_000, 6530: 9_000 * bruit(), 6540: 7_000 * bruit(),
        7000: 42_000, 7500: 11_000,
    }
    rev = m[4000] + m[4010] + m[4020] - m[4900]
    charges = sum(v for k, v in m.items() if k >= 5000)
    m[8000] = max(rev - charges, 0) * .265
    return m

gl, bud = [], []
d = date(2024, 4, 1)
while d <= date(2027, 3, 1):
    af = fy(d)
    if d <= date(2026, 10, 1):
        for k, v in montants_mois(af, d.month).items():
            gl.append({"Date": d, "NoCompte": k, "Montant": round(v, 2)})
    if af in CROISS_BUDGET:
        for k, v in montants_mois(af, d.month, budget=True).items():
            bud.append({"Date": d, "NoCompte": k, "Montant": round(v, 2)})
    d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)

signe = dc.set_index("NoCompte").Signe
for rows, nom in ((gl, "FaitGL"), (bud, "FaitBudget")):
    df = pd.DataFrame(rows)
    df["MontantSigne"] = (df.Montant * df.NoCompte.map(signe)).round(2)
    df.to_csv(OUT / f"{nom}.csv", index=False, encoding="utf-8")

# ---------------------------------------------------------------------------
# Trésorerie hebdomadaire : 26 semaines de réel + 13 semaines de prévision
# ---------------------------------------------------------------------------
DERNIERE_REELLE = date(2026, 11, 2)            # lundi de la dernière semaine réelle
semaines = [date(2026, 5, 4) + timedelta(weeks=i) for i in range(40)]
ventes_mois = {}
for r in gl + [b for b in bud if b["Date"] > date(2026, 10, 1)]:
    if r["NoCompte"] in (4000, 4010, 4020):
        ventes_mois[r["Date"]] = ventes_mois.get(r["Date"], 0) + r["Montant"]

def ventes_du_mois(dt):
    return ventes_mois.get(date(dt.year, dt.month, 1), 1.6e6)

tr = []
for i, s in enumerate(semaines):
    typ = "Réel" if s <= DERNIERE_REELLE else "Prévision"
    b = (lambda: rng.normal(1, 0.06)) if typ == "Réel" else (lambda: 1.0)
    # encaissements : ventes encaissées ~45 jours plus tard
    lag = s - timedelta(days=45)
    enc = ventes_du_mois(lag) / 4.33 * 0.975 * b()
    # fournisseurs : achats payés ~30 jours plus tard, stocks des Fêtes en octobre-novembre
    achat = s - timedelta(days=30)
    stock = 1.5 if achat.month in (10, 11) else 1.0
    four = -ventes_du_mois(achat) / 4.33 * 0.53 * stock * b()
    flux = [("Encaissements clients", enc), ("Fournisseurs", four)]
    if i % 2 == 0:
        flux.append(("Salaires", -165_000 * b()))
    if s.day <= 7:
        flux += [("Loyer et frais fixes", -62_000), ("Remboursement de prêt", -28_000)]
    if 22 <= s.day <= 28:
        flux.append(("Taxes et remises gouvernementales", -48_000 * b()))
    if s == date(2026, 6, 22):
        flux.append(("Dividendes versés", -400_000))
    if s == date(2026, 8, 17):
        flux.append(("Investissement — équipement", -350_000))
    if s == date(2026, 12, 7):
        flux.append(("Investissement — ligne d'emballage", -650_000))     # Histoire 3
    if s == date(2026, 12, 14):
        flux.append(("Taxes et remises gouvernementales", -120_000))       # acompte d'impôt
    for cat, mnt in flux:
        tr.append({"DebutSemaine": s, "CategorieFlux": cat, "Montant": round(mnt, 2), "TypeDonnee": typ})
pd.DataFrame(tr).to_csv(OUT / "FaitTresorerie.csv", index=False, encoding="utf-8")

print(f"OK — {len(gl):,} lignes GL, {len(bud):,} lignes budget, {len(tr):,} flux de trésorerie → {OUT}")
