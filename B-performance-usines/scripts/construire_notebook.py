"""Construit le notebook Fabric (PySpark) ../fabric/NB_Bellerive_Transformation.ipynb"""
import json
from pathlib import Path

cells = []
def md(s): cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n")})
def py(s): cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n")})

md("""
# Aliments Bellerive — de l'export MES aux tables Delta (bronze → argent → or)

**Données 100 % fictives.** Ce notebook lit les fichiers bruts des 3 usines déposés dans `Files/raw/` du lakehouse,
les nettoie (formats de date, séparateurs, virgules décimales, doublons, espaces), calcule les temps du TRS par quart
et écrit un **schéma en étoile** en tables Delta, prêt pour un modèle sémantique **Direct Lake**.

| Couche | Contenu |
|---|---|
| Bronze | fichiers CSV bruts, tels qu'exportés par chaque usine (`Files/raw/`) |
| Argent | données normalisées, typées, dédoublonnées (DataFrames intermédiaires) |
| Or | `dim_*` et `fact_*` en Delta (tables du lakehouse) |
""")

py("""
from pyspark.sql import functions as F

RAW = "Files/raw"

def lire(chemin, sep=","):
    return (spark.read.option("header", True).option("sep", sep)
            .option("encoding", "UTF-8").csv(f"{RAW}/{chemin}"))

def ecrire(df, nom):
    (df.write.mode("overwrite").format("delta")
       .option("overwriteSchema", "true").saveAsTable(nom))
    print(f"{nom:<22} {df.count():>8,} lignes")
""")

md("## 1. Référentiels")
py("""
usines = lire("reference/usines.csv")
lignes = (lire("reference/lignes.csv")
          .withColumn("CadenceIdealeUnitesMin", F.col("CadenceIdealeUnitesMin").cast("double")))
produits = lire("reference/produits.csv")
codes = lire("reference/codes_arret.csv").withColumn("Planifie", F.col("Planifie").cast("boolean"))
""")

md("""
## 2. Production — normaliser les 3 formats d'export
- **LAV** : format de référence
- **DRU** : `;` comme séparateur, dates `JJ/MM/AAAA`, doublons d'export
- **SAG** : colonnes en anglais, espaces parasites dans le code de ligne
""")
py("""
COLS_PROD = ["Date", "CodeUsine", "CodeLigne", "Quart", "CodeProduit",
             "MinutesOuvertes", "UnitesProduites", "UnitesRejetees"]

p_lav = lire("production/production_LAV.csv").withColumn("Date", F.to_date("Date", "yyyy-MM-dd"))

p_dru = (lire("production/production_DRU.csv", sep=";")
         .withColumn("Date", F.to_date("Date", "dd/MM/yyyy"))
         .dropDuplicates())

p_sag = (lire("production/production_SAG.csv")
         .select(F.to_date("date", "yyyy-MM-dd").alias("Date"),
                 F.col("plant").alias("CodeUsine"),
                 F.trim("line").alias("CodeLigne"),
                 F.col("shift").alias("Quart"),
                 F.col("product").alias("CodeProduit"),
                 F.col("open_minutes").alias("MinutesOuvertes"),
                 F.col("units_produced").alias("UnitesProduites"),
                 F.col("units_rejected").alias("UnitesRejetees")))

production = (p_lav.select(COLS_PROD).unionByName(p_dru.select(COLS_PROD)).unionByName(p_sag.select(COLS_PROD))
              .withColumn("MinutesOuvertes", F.col("MinutesOuvertes").cast("int"))
              .withColumn("UnitesProduites", F.col("UnitesProduites").cast("long"))
              .withColumn("UnitesRejetees", F.col("UnitesRejetees").cast("long")))

print("Doublons retirés à DRU :", lire("production/production_DRU.csv", sep=";").count() - p_dru.count())
""")

md("## 3. Arrêts — même travail de normalisation")
py("""
COLS_ARR = ["CodeUsine", "CodeLigne", "Date", "Quart", "Debut", "DureeMin", "CodeArret"]

a_lav = (lire("arrets/arrets_LAV.csv")
         .withColumn("Date", F.to_date("Date", "yyyy-MM-dd"))
         .withColumn("Debut", F.to_timestamp("Debut", "yyyy-MM-dd HH:mm:ss")))

a_dru = (lire("arrets/arrets_DRU.csv", sep=";")
         .withColumn("Date", F.to_date("Date", "dd/MM/yyyy"))
         .withColumn("Debut", F.to_timestamp("Debut", "dd/MM/yyyy HH:mm"))
         .withColumn("DureeMin", F.regexp_replace("DureeMin", ",", ".")))     # virgule décimale

a_sag = (lire("arrets/arrets_SAG.csv")
         .select(F.col("plant").alias("CodeUsine"), F.trim("line").alias("CodeLigne"),
                 F.to_date("date", "yyyy-MM-dd").alias("Date"), F.col("shift").alias("Quart"),
                 F.to_timestamp("start_time", "yyyy-MM-dd HH:mm:ss").alias("Debut"),
                 F.col("duration_min").alias("DureeMin"), F.col("stop_code").alias("CodeArret")))

arrets = (a_lav.select(COLS_ARR).unionByName(a_dru.select(COLS_ARR)).unionByName(a_sag.select(COLS_ARR))
          .withColumn("DureeMin", F.col("DureeMin").cast("double")))
""")

md("""
## 4. Temps du TRS par quart
- **Temps requis** = minutes ouvertes − arrêts planifiés
- **Temps de fonctionnement** = temps requis − arrêts non planifiés
- **Unités théoriques** = temps de fonctionnement × cadence idéale de la ligne
""")
py("""
arrets_quart = (arrets.join(codes.select("CodeArret", "Planifie"), "CodeArret", "left")
                .groupBy("CodeLigne", "Date", "Quart")
                .agg(F.sum(F.when(F.col("Planifie"), F.col("DureeMin")).otherwise(0)).alias("MinutesArretPlanifie"),
                     F.sum(F.when(~F.col("Planifie"), F.col("DureeMin")).otherwise(0)).alias("MinutesArretNonPlanifie"),
                     F.count(F.when(~F.col("Planifie"), True)).alias("NbArretsNonPlanifies")))

fact_production = (production
    .join(arrets_quart, ["CodeLigne", "Date", "Quart"], "left")
    .fillna(0, ["MinutesArretPlanifie", "MinutesArretNonPlanifie", "NbArretsNonPlanifies"])
    .join(lignes.select("CodeLigne", "CadenceIdealeUnitesMin"), "CodeLigne", "left")
    .withColumn("TempsRequisMin", F.col("MinutesOuvertes") - F.col("MinutesArretPlanifie"))
    .withColumn("TempsFonctionnementMin", F.col("TempsRequisMin") - F.col("MinutesArretNonPlanifie"))
    .withColumn("UnitesTheoriques", F.col("TempsFonctionnementMin") * F.col("CadenceIdealeUnitesMin"))
    .withColumn("UnitesBonnes", F.col("UnitesProduites") - F.col("UnitesRejetees"))
    .drop("CadenceIdealeUnitesMin"))
""")

md("## 5. Dimensions et écriture de la couche or (Delta)")
py("""
bornes = fact_production.agg(F.min("Date").alias("d0"), F.max("Date").alias("d1")).first()
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
mois_expr = F.element_at(F.array(*[F.lit(m) for m in MOIS]), F.month("Date"))

dim_date = (spark.sql(f"SELECT explode(sequence(to_date('{bornes.d0}'), to_date('{bornes.d1}'), interval 1 day)) AS Date")
    .withColumn("Annee", F.year("Date"))
    .withColumn("NoMois", F.month("Date"))
    .withColumn("Mois", mois_expr)
    .withColumn("AnneeMois", F.date_format("Date", "yyyy-MM"))
    .withColumn("CleAnneeMois", F.year("Date") * 100 + F.month("Date"))
    .withColumn("SemaineISO", F.weekofyear("Date"))
    .withColumn("JourSemaine", F.dayofweek("Date")))

dim_quart = spark.createDataFrame([("Jour", 1, "06:00"), ("Soir", 2, "14:00"), ("Nuit", 3, "22:00")],
                                  ["Quart", "OrdreQuart", "HeureDebut"])

ecrire(usines, "dim_usine")
ecrire(lignes, "dim_ligne")
ecrire(produits, "dim_produit")
ecrire(codes, "dim_code_arret")
ecrire(dim_quart, "dim_quart")
ecrire(dim_date, "dim_date")
ecrire(fact_production, "fact_production")
ecrire(arrets, "fact_arret")
""")

md("## 6. Contrôle rapide : TRS par usine")
py("""
display(spark.table("fact_production").groupBy("CodeUsine").agg(
    (F.sum("TempsFonctionnementMin") / F.sum("TempsRequisMin")).alias("Disponibilite"),
    (F.sum("UnitesProduites") / F.sum("UnitesTheoriques")).alias("Performance"),
    (F.sum("UnitesBonnes") / F.sum("UnitesProduites")).alias("Qualite"),
).withColumn("TRS", F.col("Disponibilite") * F.col("Performance") * F.col("Qualite")).orderBy("CodeUsine"))
""")

nb = {"cells": cells, "metadata": {"kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark", "language": "Python"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
for c in nb["cells"]:
    c["source"] = [l + "\n" for l in c["source"].split("\n")]
    c["source"][-1] = c["source"][-1].rstrip("\n")
out = Path(__file__).resolve().parent.parent / "fabric" / "NB_Bellerive_Transformation.ipynb"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print("OK", out)
