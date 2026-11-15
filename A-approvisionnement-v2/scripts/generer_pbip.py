"""
Génère le projet Power BI (format PBIP : modèle TMDL + rapport PBIR) du projet A.
Ouvrir ensuite ../AviNord-Appro.pbip dans Power BI Desktop, puis Actualiser.

Usage : python generer_pbip.py
"""
import hashlib, json, shutil, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = (ROOT / "data").resolve()
NAME = "AviNord-Appro"
SM = ROOT / f"{NAME}.SemanticModel"
RP = ROOT / f"{NAME}.Report"
# On ne supprime que les définitions : le dossier .pbi (cache des données actualisées) est conservé
for d in (SM / "definition", RP / "definition", RP / "StaticResources"):
    if d.exists():
        shutil.rmtree(d)

def q(n):  # nom TMDL toujours entre apostrophes
    return "'" + n.replace("'", "''") + "'"

def write(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")

def wjson(p: Path, obj):
    write(p, json.dumps(obj, ensure_ascii=False, indent=2))

def uid(s):
    return hashlib.md5(s.encode()).hexdigest()[:20]

def indent(code, n):
    return "\n".join(("\t" * n + l) if l.strip() else "" for l in code.strip("\n").split("\n"))

# =============================================================================
# 1. MODÈLE SÉMANTIQUE (TMDL)
# =============================================================================
TYPES_M = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date"}

def csv_m(fichier, cols):
    types = ", ".join(f'{{"{c}", {TYPES_M[t]}}}' for c, t, *_ in cols)
    return f'''let
    Source = Csv.Document(File.Contents(DossierDonnees & "{fichier}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Entetes = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Types = Table.TransformColumnTypes(Entetes, {{{types}}}, "en-US")
in
    Types'''

def column_tmdl(c, t, hidden=False, fmt=None, sort_by=None, key=False, summarize="none"):
    lines = [f"\tcolumn {q(c)}", f"\t\tdataType: {t}"]
    if fmt: lines.append(f"\t\tformatString: {fmt}")
    if hidden: lines.append("\t\tisHidden")
    if key: lines.append("\t\tisKey")
    lines.append(f"\t\tsummarizeBy: {summarize}")
    lines.append(f"\t\tsourceColumn: {c}")
    if sort_by: lines.append(f"\t\tsortByColumn: {q(sort_by)}")
    return "\n".join(lines)

def table_tmdl(name, cols, m, hidden=False, extra="", data_category=None):
    """cols: list of (name, dataType, options dict)"""
    head = [f"table {q(name)}"]
    if hidden: head.append("\tisHidden")
    if data_category: head.append(f"\tdataCategory: {data_category}")
    parts = ["\n".join(head)]
    for c, t, opt in cols:
        parts.append(column_tmdl(c, t, **opt))
    if extra:
        parts.append(extra)
    parts.append(f"\tpartition {q(name)} = m\n\t\tmode: import\n\t\tsource =\n{indent(m, 4)}")
    return "\n\n".join(parts) + "\n"

H = {"hidden": True}
N = {}
DATE_FMT = {"fmt": "yyyy-mm-dd"}
tables = {}

# --- DimDate -----------------------------------------------------------------
dimdate_cols = [
    ("Date", "dateTime", {"fmt": "yyyy-mm-dd", "key": True}),
    ("Exercice", "int64", {"fmt": "0"}),
    ("NoPeriode", "int64", H),
    ("Periode", "string", {"sort_by": "NoPeriode"}),
    ("ExercicePeriode", "string", {"sort_by": "CleExercicePeriode"}),
    ("CleExercicePeriode", "int64", H),
    ("SemaineExercice", "int64", {"fmt": "0"}),
    ("SemainePeriode", "int64", {"fmt": "0"}),
    ("JourPeriode", "int64", {"fmt": "0"}),
    ("DebutPeriode", "dateTime", DATE_FMT),
    ("FinPeriode", "dateTime", DATE_FMT),
    ("JourSemaine", "int64", H),
    ("NomJour", "string", {"sort_by": "JourSemaine"}),
    ("AnneeCivile", "int64", {"fmt": "0"}),
    ("MoisCivil", "int64", {"fmt": "0"}),
]
tables["DimDate"] = table_tmdl("DimDate", dimdate_cols,
                               csv_m("DimDate.csv", dimdate_cols), data_category="Time")

def simple_dim(name, fichier, cols):
    tables[name] = table_tmdl(name, cols, csv_m(fichier, cols))

simple_dim("DimProducteur", "DimProducteur.csv", [
    ("ProducteurID", "int64", H), ("Producteur", "string", N), ("Region", "string", H),
    ("DistanceKm", "int64", {"fmt": "0", "summarize": "none"}), ("TailleFerme", "string", N)])
simple_dim("DimRegion", "DimRegion.csv", [("RegionID", "int64", H), ("Region", "string", {"sort_by": "RegionID"})])
simple_dim("DimTypePoulet", "DimTypePoulet.csv", [
    ("TypePouletID", "int64", H), ("TypePoulet", "string", {"sort_by": "TypePouletID"}),
    ("PoidsCibleKg", "double", {"fmt": "0.00"}), ("PrimeBaseKg", "double", H)])
simple_dim("DimTransporteur", "DimTransporteur.csv", [("TransporteurID", "int64", H), ("Transporteur", "string", N)])
simple_dim("DimCauseCondamnation", "DimCauseCondamnation.csv", [("CauseID", "int64", H), ("Cause", "string", {"sort_by": "CauseID"})])
simple_dim("DimComposante", "DimComposante.csv", [
    ("Composante", "string", {"sort_by": "Ordre"}), ("Groupe", "string", N), ("Ordre", "int64", H)])

# --- Faits -------------------------------------------------------------------
LOT_COLS_ALL = [
    ("LotID", "int64"), ("NoLot", "string"), ("DateAbattage", "dateTime"), ("ProducteurID", "int64"),
    ("TypePouletID", "int64"), ("TransporteurID", "int64"), ("TetesRecues", "int64"), ("MortsEnCage", "int64"),
    ("KgVifsRecus", "double"), ("KgMortsEnCage", "double"), ("KgCondamnes", "double"), ("KgPayes", "double"),
    ("MontantPrixBase", "double"), ("MontantAjustement", "double"), ("MontantBonification", "double"),
    ("MontantChargement", "double"), ("MontantTransport", "double")]
MONTANTS = [c for c, _ in LOT_COLS_ALL if c.startswith("Montant")]

lots_bruts_m = csv_m("FaitReceptionLot.csv", LOT_COLS_ALL)

lot_cols = [
    ("LotID", "int64", H), ("NoLot", "string", N), ("DateAbattage", "dateTime", DATE_FMT),
    ("ProducteurID", "int64", H), ("TypePouletID", "int64", H), ("TransporteurID", "int64", H),
    ("TetesRecues", "int64", H), ("MortsEnCage", "int64", H), ("KgVifsRecus", "double", H),
    ("KgMortsEnCage", "double", H), ("KgCondamnes", "double", H), ("KgPayes", "double", H)]
tables["FaitReceptionLot"] = table_tmdl("FaitReceptionLot", lot_cols, f'''let
    Source = LotsBruts,
    SansMontants = Table.RemoveColumns(Source, {{{", ".join(f'"{c}"' for c in MONTANTS)}}})
in
    SansMontants''')

ren_lot = ", ".join(f'{{"{c}", "{lbl}"}}' for c, lbl in zip(MONTANTS, ["Prix de base", "Ajustement", "Bonification", "Chargement", "Transport"]))
tables["FaitCout"] = table_tmdl("FaitCout", [
    ("LotID", "int64", H), ("Composante", "string", H), ("Montant", "double", H)], f'''let
    Source = LotsBruts,
    Colonnes = Table.SelectColumns(Source, {{"LotID", {", ".join(f'"{c}"' for c in MONTANTS)}}}),
    Long = Table.UnpivotOtherColumns(Colonnes, {{"LotID"}}, "Composante", "Montant"),
    Noms = Table.TransformColumns(Long, {{"Composante", each Record.FieldOrDefault([{", ".join(f'{c} = "{l}"' for c, l in zip(MONTANTS, ["Prix de base", "Ajustement", "Bonification", "Chargement", "Transport"]))}], _, _), type text}}),
    Types = Table.TransformColumnTypes(Noms, {{{{"Montant", type number}}}})
in
    Types''')

cond_cols = [("LotID", "int64", H), ("CauseID", "int64", H), ("KgCondamnes", "double", H)]
tables["FaitCondamnation"] = table_tmdl("FaitCondamnation", cond_cols, csv_m("FaitCondamnation.csv", cond_cols))

BUD_COLS = [("Exercice", "int64"), ("NoPeriode", "int64"), ("CleExercicePeriode", "int64"), ("TypePouletID", "int64"),
            ("Region", "string"), ("KgPayesBudget", "double"), ("MontantPrixBaseBudget", "double"),
            ("MontantAjustementBudget", "double"), ("MontantBonificationBudget", "double"),
            ("MontantChargementBudget", "double"), ("MontantTransportBudget", "double")]
BUD_MONT = [c for c, _ in BUD_COLS if c.startswith("Montant")]
bud_valeurs = ["KgPayesBudget"] + BUD_MONT
budget_jour_m = f'''let
    Budget = {csv_m("FaitBudgetPeriode.csv", BUD_COLS).replace(chr(10), chr(10) + "    ").replace("let", "let", 1)},
    Dates = Table.SelectColumns(DimDate, {{"Date", "CleExercicePeriode"}}),
    Joint = Table.NestedJoin(Budget, {{"CleExercicePeriode"}}, Dates, {{"CleExercicePeriode"}}, "D", JoinKind.Inner),
    Jours = Table.ExpandTableColumn(Joint, "D", {{"Date"}}),
    ParJour = Table.TransformColumns(Jours, List.Transform({{{", ".join(f'"{c}"' for c in bud_valeurs)}}}, (c) => {{c, each _ / 28, type number}}))
in
    ParJour'''

tables["FaitBudgetVolume"] = table_tmdl("FaitBudgetVolume", [
    ("Date", "dateTime", H), ("TypePouletID", "int64", H), ("Region", "string", H), ("KgPayesBudget", "double", H)], '''let
    Source = BudgetJour,
    Colonnes = Table.SelectColumns(Source, {"Date", "TypePouletID", "Region", "KgPayesBudget"})
in
    Colonnes''')

tables["FaitBudgetCout"] = table_tmdl("FaitBudgetCout", [
    ("Date", "dateTime", H), ("TypePouletID", "int64", H), ("Region", "string", H),
    ("Composante", "string", H), ("Montant", "double", H)], f'''let
    Source = BudgetJour,
    Colonnes = Table.SelectColumns(Source, {{"Date", "TypePouletID", "Region", {", ".join(f'"{c}"' for c in BUD_MONT)}}}),
    Long = Table.UnpivotOtherColumns(Colonnes, {{"Date", "TypePouletID", "Region"}}, "Composante", "Montant"),
    Noms = Table.TransformColumns(Long, {{"Composante", each Record.FieldOrDefault([{", ".join(f'{c} = "{l}"' for c, l in zip(BUD_MONT, ["Prix de base", "Ajustement", "Bonification", "Chargement", "Transport"]))}], _, _), type text}}),
    Types = Table.TransformColumnTypes(Noms, {{{{"Montant", type number}}}})
in
    Types''')

# --- Tables de paramètres (déconnectées) ---------------------------------------
tables["Référence"] = table_tmdl("Référence", [
    ("Référence", "string", {"sort_by": "Ordre"}), ("Ordre", "int64", H)], '''let
    Source = #table(type table [Référence = text, Ordre = Int64.Type], {{"Budget", 1}, {"Année précédente", 2}})
in
    Source''')
tables["Étapes du pont"] = table_tmdl("Étapes du pont", [
    ("Étape", "string", {"sort_by": "Ordre"}), ("Ordre", "int64", H)], '''let
    Source = #table(type table [Étape = text, Ordre = Int64.Type], {{"Effet volume", 1}, {"Effet mix", 2}, {"Effet prix", 3}})
in
    Source''')

# --- Mesures ---------------------------------------------------------------------
CUR = r'#,0 \$;-#,0 \$'
KG = "#,0"
PCT = "0.00 %"
PKG = r'0.000 \$'
measures = [
    # (nom, dossier, format, dax)
    ("Dernière date réelle", "0. Paramètres", "yyyy-mm-dd", "CALCULATE(MAX(FaitReceptionLot[DateAbattage]), REMOVEFILTERS())"),
    ("Référence choisie", "0. Paramètres", None, "SELECTEDVALUE('Référence'[Référence], \"Budget\")"),
    ("Mise à jour", "0. Paramètres", None, "\"Données au \" & FORMAT([Dernière date réelle], \"d mmmm yyyy\")"),

    ("Kg payés", "1. Réel", KG, "SUM(FaitReceptionLot[KgPayes])"),
    ("Coût total", "1. Réel", CUR, "SUM(FaitCout[Montant])"),
    ("$/kg", "1. Réel", PKG, "DIVIDE([Coût total], [Kg payés])"),
    ("Nb lots", "1. Réel", "#,0", "COUNTROWS(FaitReceptionLot)"),
    ("Têtes reçues", "1. Réel", "#,0", "SUM(FaitReceptionLot[TetesRecues])"),
    ("Morts en cage", "1. Réel", "#,0", "SUM(FaitReceptionLot[MortsEnCage])"),
    ("% Morts en cage", "1. Réel", PCT, "DIVIDE([Morts en cage], [Têtes reçues])"),
    ("Poids moyen vif (kg)", "1. Réel", "0.000", "DIVIDE(SUM(FaitReceptionLot[KgVifsRecus]), [Têtes reçues] - [Morts en cage])"),
    ("Kg condamnés", "1. Réel", KG, "SUM(FaitCondamnation[KgCondamnes])"),
    ("% Condamnation", "1. Réel", PCT, "DIVIDE(SUM(FaitReceptionLot[KgCondamnes]), SUM(FaitReceptionLot[KgVifsRecus]))"),

    ("Kg budget", "2. Référence", KG, """VAR _fin = [Dernière date réelle]
RETURN CALCULATE(SUM(FaitBudgetVolume[KgPayesBudget]), KEEPFILTERS(DimDate[Date] <= _fin))"""),
    ("Coût budget", "2. Référence", CUR, """VAR _fin = [Dernière date réelle]
RETURN CALCULATE(SUM(FaitBudgetCout[Montant]), KEEPFILTERS(DimDate[Date] <= _fin))"""),
    ("Kg AP", "2. Référence", KG, """VAR _fin = [Dernière date réelle]
VAR _dates = FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _fin)
VAR _datesAP = SELECTCOLUMNS(_dates, "Date", DimDate[Date] - 364)   -- 364 j = 13 x 28 : même jour fiscal
RETURN CALCULATE([Kg payés], REMOVEFILTERS(DimDate), TREATAS(_datesAP, DimDate[Date]))"""),
    ("Coût AP", "2. Référence", CUR, """VAR _fin = [Dernière date réelle]
VAR _dates = FILTER(VALUES(DimDate[Date]), DimDate[Date] <= _fin)
VAR _datesAP = SELECTCOLUMNS(_dates, "Date", DimDate[Date] - 364)
RETURN CALCULATE([Coût total], REMOVEFILTERS(DimDate), TREATAS(_datesAP, DimDate[Date]))"""),
    ("Kg référence", "2. Référence", KG, "IF([Référence choisie] = \"Budget\", [Kg budget], [Kg AP])"),
    ("Coût référence", "2. Référence", CUR, "IF([Référence choisie] = \"Budget\", [Coût budget], [Coût AP])"),
    ("$/kg référence", "2. Référence", PKG, "DIVIDE([Coût référence], [Kg référence])"),

    ("Écart total", "3. Écarts", CUR, "[Coût total] - [Coût référence]"),
    ("Écart total %", "3. Écarts", PCT, "DIVIDE([Écart total], [Coût référence])"),
    ("Écart $/kg", "3. Écarts", PKG, "[$/kg] - [$/kg référence]"),
    ("Coût réel au prix de référence", "3. Écarts", CUR, """SUMX(
    CROSSJOIN(VALUES(DimTypePoulet[TypePoulet]), VALUES(DimRegion[Region])),
    [Kg payés] * [$/kg référence]
)"""),
    ("Effet volume", "3. Écarts", CUR, "([Kg payés] - [Kg référence]) * [$/kg référence]"),
    ("Effet mix", "3. Écarts", CUR, "[Coût réel au prix de référence] - [Kg payés] * [$/kg référence]"),
    ("Effet prix", "3. Écarts", CUR, "[Coût total] - [Coût réel au prix de référence]"),
    ("Contrôle (doit être 0)", "3. Écarts", CUR, "[Écart total] - ([Effet volume] + [Effet mix] + [Effet prix])"),
    ("Pont des écarts", "3. Écarts", CUR, """SWITCH(
    SELECTEDVALUE('Étapes du pont'[Étape]),
    "Effet volume", [Effet volume],
    "Effet mix", [Effet mix],
    "Effet prix", [Effet prix]
)"""),
]

def measure_tmdl(name, folder, fmt, dax):
    if "\n" in dax:
        head = f"\tmeasure {q(name)} =\n{indent(dax, 3)}"
    else:
        head = f"\tmeasure {q(name)} = {dax}"
    props = []
    if fmt: props.append(f"\t\tformatString: {fmt}")
    props.append(f"\t\tdisplayFolder: {folder}")
    return head + "\n" + "\n".join(props)

mes_tmdl = "\n\n".join(measure_tmdl(*m) for m in measures)
tables["_Mesures"] = table_tmdl("_Mesures", [("Colonne", "string", H)], '''let
    Source = #table(type table [Colonne = text], {})
in
    Source''', extra=mes_tmdl)

# --- Groupe de calcul ---------------------------------------------------------------
cg = f"""table {q('Vue temporelle')}

\tcalculationGroup

\t\tcalculationItem {q('Période sélectionnée')} = SELECTEDMEASURE()
\t\t\tordinal: 0

\t\tcalculationItem {q("Cumul de l'exercice")} =
{indent('''VAR _ex = MAX(DimDate[Exercice])
VAR _fin = MAX(DimDate[Date])
RETURN CALCULATE(SELECTEDMEASURE(), REMOVEFILTERS(DimDate), DimDate[Exercice] = _ex, DimDate[Date] <= _fin)''', 4)}
\t\t\tordinal: 1

\tcolumn Vue
\t\tdataType: string
\t\tsummarizeBy: none
\t\tsourceColumn: Name
\t\tsortByColumn: Ordinal

\tcolumn Ordinal
\t\tdataType: int64
\t\tisHidden
\t\tsummarizeBy: none
\t\tsourceColumn: Ordinal

\tpartition {q('Vue temporelle')} = calculationGroup
"""
tables["Vue temporelle"] = cg

# --- Relations ----------------------------------------------------------------------
rels = [
    ("FaitReceptionLot", "DateAbattage", "DimDate", "Date"),
    ("FaitReceptionLot", "ProducteurID", "DimProducteur", "ProducteurID"),
    ("DimProducteur", "Region", "DimRegion", "Region"),
    ("FaitReceptionLot", "TypePouletID", "DimTypePoulet", "TypePouletID"),
    ("FaitReceptionLot", "TransporteurID", "DimTransporteur", "TransporteurID"),
    ("FaitCout", "LotID", "FaitReceptionLot", "LotID"),
    ("FaitCout", "Composante", "DimComposante", "Composante"),
    ("FaitCondamnation", "LotID", "FaitReceptionLot", "LotID"),
    ("FaitCondamnation", "CauseID", "DimCauseCondamnation", "CauseID"),
    ("FaitBudgetVolume", "Date", "DimDate", "Date"),
    ("FaitBudgetVolume", "TypePouletID", "DimTypePoulet", "TypePouletID"),
    ("FaitBudgetVolume", "Region", "DimRegion", "Region"),
    ("FaitBudgetCout", "Date", "DimDate", "Date"),
    ("FaitBudgetCout", "TypePouletID", "DimTypePoulet", "TypePouletID"),
    ("FaitBudgetCout", "Region", "DimRegion", "Region"),
    ("FaitBudgetCout", "Composante", "DimComposante", "Composante"),
]
rel_txt = "\n\n".join(
    f"relationship {uuid.uuid5(uuid.NAMESPACE_DNS, f'{a}.{b}-{c}.{d}')}\n\tfromColumn: {q(a)}.{q(b)}\n\ttoColumn: {q(c)}.{q(d)}"
    for a, b, c, d in rels) + "\n"

expr_txt = f'''expression DossierDonnees = "{str(DATA)}\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
\tannotation PBI_ResultType = Text

expression LotsBruts =
{indent(lots_bruts_m, 2)}
\tannotation PBI_ResultType = Table

expression BudgetJour =
{indent(budget_jour_m, 2)}
\tannotation PBI_ResultType = Table
'''

D = SM / "definition"
write(D / "database.tmdl", "database\n\tcompatibilityLevel: 1601\n")
write(D / "model.tmdl", """model Model
\tculture: fr-CA
\tdefaultPowerBIDataSourceVersion: powerBI_V3
\tdiscourageImplicitMeasures
\tsourceQueryCulture: fr-CA

annotation __PBI_TimeIntelligenceEnabled = 0
""")
write(D / "expressions.tmdl", expr_txt)
write(D / "relationships.tmdl", rel_txt)
for n, t in tables.items():
    write(D / "tables" / f"{n}.tmdl", t)
wjson(SM / "definition.pbism", {"version": "4.0", "settings": {}})

# =============================================================================
# 2. RAPPORT (PBIR)
# =============================================================================
VIS_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.14.0/schema.json"
lit = lambda v: {"expr": {"Literal": {"Value": v}}}
BLEU, ORANGE, GRIS = "#1F3A5F", "#E07A1F", "#8A8F98"

def col(t, c, active=False):
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": t}}, "Property": c}},
         "queryRef": f"{t}.{c}", "nativeQueryRef": c}
    if active: p["active"] = True
    return p

def color(c):
    return {"solid": {"color": lit(f"'{c}'")}}

def series_colors(pairs):
    """pairs: [(nom de mesure, couleur)] → couleurs fixes par série"""
    return [{"properties": {"fill": color(c)}, "selector": {"metadata": f"_Mesures.{m}"}} for m, c in pairs]

DATA_LABELS = [{"properties": {"show": lit("true"), "labelDisplayUnits": lit("1000000D"), "labelPrecision": lit("1L")}}]

def mes(m, label=None):
    p = {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "_Mesures"}}, "Property": m}},
         "queryRef": f"_Mesures.{m}", "nativeQueryRef": m}
    if label: p["displayName"] = label
    return p

def title(text):
    return {"title": [{"properties": {"show": lit("true"), "text": lit(f"'{text}'"),
                                      "fontColor": {"solid": {"color": lit(f"'{BLEU}'")}}, "bold": lit("true")}}]}

pages = []

class Page:
    def __init__(self, name, display):
        self.name, self.display, self.visuals = name, display, []
        pages.append(self)
    def add(self, vtype, x, y, w, h, query=None, objects=None, vco=None, extra=None):
        vid = uid(f"{self.name}-{len(self.visuals)}")
        objects = dict(objects or {})
        if vtype in ("clusteredColumnChart", "clusteredBarChart", "lineChart", "waterfallChart", "scatterChart"):
            # titres d'axes masqués : le titre du visuel suffit
            objects.setdefault("categoryAxis", [{"properties": {"showAxisTitle": lit("false")}}])
            objects.setdefault("valueAxis", [{"properties": {"showAxisTitle": lit("false")}}])
        if vtype in ("pivotTable", "tableEx"):
            objects.setdefault("grid", [{"properties": {"rowPadding": lit("1D")}}])
        objects = objects or None
        v = {"visualType": vtype}
        if query: v["query"] = {"queryState": query}
        if objects: v["objects"] = objects
        if vco: v["visualContainerObjects"] = vco
        if extra: v.update(extra)
        v["drillFilterOtherVisuals"] = True
        z = len(self.visuals) * 1000
        self.visuals.append({"$schema": VIS_SCHEMA, "name": vid,
                             "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
                             "visual": v})

def textbox(pg, x, y, w, h, text, size="20pt", color=BLEU, bold=True):
    pg.add("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": text, "textStyle": {"fontSize": size, "color": color,
                                                     **({"fontWeight": "bold"} if bold else {})}}]}]}}]})

def richtext(pg, x, y, w, h, lignes):
    """lignes : liste de (texte, style) avec style ∈ titre | texte | puce | vide"""
    styles = {"titre": {"fontSize": "13pt", "color": BLEU, "fontWeight": "bold"},
              "texte": {"fontSize": "10.5pt", "color": "#1F2A37"},
              "puce": {"fontSize": "10.5pt", "color": "#1F2A37"},
              "formule": {"fontSize": "10pt", "color": ORANGE, "fontWeight": "bold"},
              "vide": {"fontSize": "6pt", "color": "#1F2A37"}}
    paras = []
    for txt, st in lignes:
        val = ("•  " + txt) if st == "puce" else (txt if txt else " ")
        paras.append({"textRuns": [{"value": val, "textStyle": styles[st]}]})
    pg.add("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": paras}}]})

def image(pg, x, y, w, h, ressource):
    pg.add("image", x, y, w, h, objects={"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
        "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": ressource}}}}}],
        "imageScaling": [{"properties": {"imageScalingType": lit("'Fit'")}}]})

def slicer(pg, x, y, w, h, t, c, label, dropdown=True, single=False, default_in=None):
    obj = {"header": [{"properties": {"show": lit("false")}}]}  # le titre du visuel suffit
    if dropdown: obj["data"] = [{"properties": {"mode": lit("'Dropdown'")}}]
    if single: obj["selection"] = [{"properties": {"singleSelect": lit("true")}}]
    if default_in is not None:
        obj["general"] = [{"properties": {"filter": {"filter": {"Version": 2, "From": [{"Name": "s", "Entity": t, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": c}}],
                                            "Values": [[{"Literal": {"Value": default_in}}]]}}}]}}}}]
    pg.add("slicer", x, y, w, h, query={"Values": {"projections": [col(t, c, active=True)]}}, objects=obj,
           vco={"title": [{"properties": {"show": lit("true"), "text": lit(f"'{label}'"),
                                          "fontColor": color(GRIS), "fontSize": lit("10D")}}]})

def card(pg, x, y, w, h, m, label, units="1000000D", precision="2L"):
    lab = {"color": color(BLEU), "fontSize": lit("22D")}
    if units:
        lab["labelDisplayUnits"] = lit(units)
        lab["labelPrecision"] = lit(precision)
    pg.add("card", x, y, w, h, query={"Values": {"projections": [mes(m, label)]}},
           objects={"labels": [{"properties": lab}],
                    "categoryLabels": [{"properties": {"show": lit("true"), "color": color(GRIS)}}]},
           vco={"border": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#D9DDE3'")}}, "radius": lit("8D")}}]})

def bandeau(pg, sous_titre):
    image(pg, 14, 12, 125, 44, "AviNord-logo.svg")
    textbox(pg, 152, 6, 820, 52, "Approvisionnement en volaille vivante", size="18pt")
    textbox(pg, 152, 46, 820, 36, sous_titre, size="11pt", color=GRIS, bold=False)
    pg.add("card", 1010, 12, 250, 50, query={"Values": {"projections": [mes("Mise à jour")]}},
           objects={"labels": [{"properties": {"fontSize": lit("10D"), "color": {"solid": {"color": lit(f"'{GRIS}'")}}}}],
                    "categoryLabels": [{"properties": {"show": lit("false")}}]})

def filtres(pg, y=84):
    slicer(pg, 20, y, 150, 64, "DimDate", "Exercice", "Exercice", default_in="2026L")
    slicer(pg, 180, y, 150, 64, "DimDate", "Periode", "Période")
    slicer(pg, 340, y, 180, 64, "Référence", "Référence", "Comparer à", single=True)
    slicer(pg, 530, y, 200, 64, "Vue temporelle", "Vue", "Vue", single=True)
    slicer(pg, 740, y, 180, 64, "DimTypePoulet", "TypePoulet", "Type de poulet")
    slicer(pg, 930, y, 160, 64, "DimRegion", "Region", "Région")

# --- Page 1 : Vue d'ensemble -----------------------------------------------------------
p1 = Page(uid("p1"), "Vue d'ensemble")
bandeau(p1, "Coût d'approvisionnement : réel vs référence, à date égale")
filtres(p1)
for i, (m, l, u, pr) in enumerate([("Coût total", "Coût réel", "1000000D", "1L"),
                                    ("Coût référence", "Coût de référence", "1000000D", "1L"),
                                    ("Écart total", "Écart vs référence", "1000000D", "2L"),
                                    ("Écart total %", "Écart en %", None, None),
                                    ("$/kg", "$/kg réel", None, None)]):
    card(p1, 20 + i * 250, 160, 235, 95, m, l, units=u, precision=pr)
p1.add("clusteredColumnChart", 20, 270, 760, 410,
       query={"Category": {"projections": [col("DimDate", "ExercicePeriode", active=True)]},
              "Y": {"projections": [mes("Coût total", "Réel"), mes("Coût référence", "Référence")]}},
       objects={"dataPoint": series_colors([("Coût total", BLEU), ("Coût référence", "#B8C2CC")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Coût par période : réel vs référence"))
textbox(p1, 20, 682, 760, 30, "La dernière période est en cours : réel et référence sont comparés à date égale.",
        size="9pt", color=GRIS, bold=False)
p1.add("clusteredBarChart", 795, 270, 465, 440,
       query={"Category": {"projections": [col("DimComposante", "Composante", active=True)]},
              "Y": {"projections": [mes("Écart total", "Écart")]}},
       objects={"dataPoint": [{"properties": {"fill": color(ORANGE)}}],
                "labels": [{"properties": {"show": lit("true"), "labelDisplayUnits": lit("1000D"), "labelPrecision": lit("0L")}}]},
       vco=title("Écart par composante du coût (k$)"))

# --- Page 2 : Pont des écarts -----------------------------------------------------------------
p2 = Page(uid("p2"), "Pont des écarts")
bandeau(p2, "D'où vient l'écart ? Effet volume, effet mix, effet prix")
filtres(p2)
for i, (m, l) in enumerate([("Écart total", "Écart total"), ("Effet volume", "Effet volume"),
                             ("Effet mix", "Effet mix"), ("Effet prix", "Effet prix")]):
    card(p2, 20 + i * 312, 160, 300, 95, m, l)
p2.add("waterfallChart", 20, 270, 560, 440,
       query={"Category": {"projections": [col("Étapes du pont", "Étape", active=True)]},
              "Y": {"projections": [mes("Pont des écarts", "Écart")]}},
       objects={"sentimentColors": [{"properties": {
           "increaseFill": color("#C0392B"), "decreaseFill": color("#2E8B57"), "totalFill": color(BLEU)}}],
                "labels": DATA_LABELS},
       vco=title("Décomposition de l'écart vs référence"))
p2.add("pivotTable", 595, 270, 665, 200,
       query={"Rows": {"projections": [col("DimComposante", "Composante", active=True)]},
              "Values": {"projections": [mes("Effet volume"), mes("Effet mix"), mes("Effet prix"), mes("Écart total")]}},
       vco=title("Par composante du coût"))
p2.add("pivotTable", 595, 480, 665, 230,
       query={"Rows": {"projections": [col("DimRegion", "Region", active=True), col("DimTypePoulet", "TypePoulet", active=True)]},
              "Values": {"projections": [mes("Kg payés"), mes("Kg référence"), mes("$/kg"), mes("$/kg référence"), mes("Écart total")]}},
       vco=title("Par région et type de poulet"))

# --- Page 3 : Opérations ----------------------------------------------------------------------------
p3 = Page(uid("p3"), "Opérations")
bandeau(p3, "Réception des lots : volumes, mortalité et condamnations")
slicer(p3, 20, 84, 150, 64, "DimDate", "Exercice", "Exercice", default_in="2026L")
slicer(p3, 180, 84, 150, 64, "DimDate", "Periode", "Période")
slicer(p3, 340, 84, 180, 64, "DimTypePoulet", "TypePoulet", "Type de poulet")
slicer(p3, 530, 84, 160, 64, "DimRegion", "Region", "Région")
for i, (m, l, u, pr) in enumerate([("Nb lots", "Lots reçus", None, None), ("Têtes reçues", "Têtes reçues", "1000000D", "1L"),
                                    ("Poids moyen vif (kg)", "Poids moyen vif (kg)", None, None),
                                    ("% Morts en cage", "% morts en cage", None, None),
                                    ("% Condamnation", "% condamnation", None, None)]):
    card(p3, 20 + i * 250, 160, 235, 95, m, l, units=u, precision=pr)
p3.add("lineChart", 20, 270, 620, 220,
       query={"Category": {"projections": [col("DimDate", "ExercicePeriode", active=True)]},
              "Y": {"projections": [mes("% Morts en cage")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}]},
       vco=title("% morts en cage par période"))
p3.add("clusteredBarChart", 655, 270, 605, 220,
       query={"Category": {"projections": [col("DimCauseCondamnation", "Cause", active=True)]},
              "Y": {"projections": [mes("Kg condamnés")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}],
                "labels": [{"properties": {"show": lit("true"), "labelDisplayUnits": lit("1000D"), "labelPrecision": lit("0L")}}]},
       vco=title("Kg condamnés par cause"))
p3.add("tableEx", 20, 500, 640, 210,
       query={"Values": {"projections": [col("DimProducteur", "Producteur"), col("DimRegion", "Region"),
                                         mes("Nb lots"), mes("Kg payés"), mes("$/kg"),
                                         mes("% Morts en cage"), mes("% Condamnation")]}},
       vco=title("Producteurs"))
p3.add("scatterChart", 675, 500, 585, 210,
       query={"Category": {"projections": [col("DimProducteur", "Producteur", active=True)]},
              "Series": {"projections": [col("DimRegion", "Region")]},
              "X": {"projections": [mes("Kg payés")]},
              "Y": {"projections": [mes("$/kg")]}},
       # couleurs des séries : celles du thème (Québec = bleu marine, Ontario-Est = orange)
       objects={"legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Producteurs : volume acheté vs $/kg"))

# --- Page 4 : Détail par lot ---------------------------------------------------------------------------
p4 = Page(uid("p4"), "Détail par lot")
bandeau(p4, "Chaque lot reçu, avec son coût complet")
slicer(p4, 20, 84, 150, 64, "DimDate", "Exercice", "Exercice", default_in="2026L")
slicer(p4, 180, 84, 150, 64, "DimDate", "Periode", "Période")
slicer(p4, 340, 84, 220, 64, "DimProducteur", "Producteur", "Producteur")
p4.add("tableEx", 20, 160, 960, 550,
       query={"Values": {"projections": [col("FaitReceptionLot", "NoLot"), col("FaitReceptionLot", "DateAbattage"),
                                         col("DimProducteur", "Producteur"), col("DimTypePoulet", "TypePoulet"),
                                         col("DimTransporteur", "Transporteur"), mes("Têtes reçues"), mes("Kg payés"),
                                         mes("Coût total"), mes("$/kg"), mes("% Morts en cage")]}},
       vco=title("Lots"))
for i, (m, l, u, pr) in enumerate([("Nb lots", "Lots sélectionnés", None, None),
                                    ("Coût total", "Coût total", "1000000D", "2L"),
                                    ("$/kg", "$/kg moyen", None, None),
                                    ("% Condamnation", "% condamnation", None, None)]):
    card(p4, 995, 160 + i * 140, 265, 130, m, l, units=u, precision=pr)

# --- Page 5 : À propos -------------------------------------------------------------------------------------
p5 = Page(uid("p5"), "À propos")
bandeau(p5, "Démo portfolio : contexte, modèle de données et méthode")
richtext(p5, 20, 90, 440, 620, [
    ("Le contexte", "titre"),
    ("AviNord est un transformateur de volaille fictif au Québec. Le poulet vivant est son premier poste de coût. "
     "La direction voyait que le coût s'écartait du budget, sans savoir pourquoi.", "texte"),
    ("", "vide"),
    ("La question métier", "titre"),
    ("« On a payé plus (ou moins) que prévu : est-ce le volume, le prix au kilo, ou la provenance des achats ? »", "texte"),
    ("", "vide"),
    ("La méthode : décomposer l'écart", "titre"),
    ("Effet volume = (kg réels − kg référence) × $/kg référence", "formule"),
    ("Effet mix = coût réel au prix de référence − kg réels × $/kg référence", "formule"),
    ("Effet prix = coût réel − coût réel au prix de référence", "formule"),
    ("Les trois effets s'additionnent exactement à l'écart total, par type de poulet × région, "
     "et pour chaque composante du coût.", "texte"),
    ("", "vide"),
    ("Les données", "titre"),
    ("100 % fictives, générées par un script Python : environ 6 350 lots sur 3 exercices, "
     "42 producteurs, budget par période. Calendrier fiscal de 13 périodes de 4 semaines.", "texte"),
    ("", "vide"),
    ("Réalisé par", "titre"),
    ("Adams Dalqiel Michel Ange Yao · Consultant Power BI · modélisation de données", "texte"),
    ("Inspiré d'un projet réel en usine, reconstruit sans aucune donnée d'entreprise.", "texte"),
])
p5.add("image", 480, 90, 780, 400, objects={"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
    "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "AviNord-modele.svg"}}}}}],
    "imageScaling": [{"properties": {"imageScalingType": lit("'Fit'")}}]},
    vco={"title": [{"properties": {"show": lit("true"), "text": lit("'Le modèle en étoile'"),
                                   "fontColor": color(BLEU), "bold": lit("true")}}],
         "background": [{"properties": {"show": lit("true"), "color": color("#FFFFFF")}}],
         "border": [{"properties": {"show": lit("true"), "color": color("#E3E7EC"), "radius": lit("8D")}}]})
richtext(p5, 480, 505, 780, 205, [
    ("Les choix de modélisation", "titre"),
    ("Schéma en étoile, relations 1 → plusieurs à filtrage simple, date/heure automatique désactivée", "puce"),
    ("Une seule table de dates, sur le calendrier fiscal (comparaison à l'année précédente au même jour fiscal : −364 jours)", "puce"),
    ("Coûts en format long (Power Query) : une seule mesure de coût, découpée par composante", "puce"),
    ("Budget ventilé au jour : les comparaisons « à date égale » sont un simple filtre de dates", "puce"),
    ("Groupe de calcul « Vue temporelle » : chaque mesure passe en cumul de l'exercice sans être dupliquée", "puce"),
    ("Une trentaine de mesures DAX, rangées par dossier, avec une mesure de contrôle (écart non expliqué = 0)", "puce"),
])

# --- Écriture du rapport --------------------------------------------------------------------------------
R = RP / "definition"
wjson(RP / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
wjson(R / "version.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
wjson(R / "report.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {
        "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "SharedResources"},
        "customTheme": {"name": "AviNord-theme.json", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "RegisteredResources"}},
    "resourcePackages": [
        {"name": "SharedResources", "type": "SharedResources",
         "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
        {"name": "RegisteredResources", "type": "RegisteredResources",
         "items": [{"name": "AviNord-theme.json", "path": "AviNord-theme.json", "type": "CustomTheme"},
                   {"name": "AviNord-logo.svg", "path": "AviNord-logo.svg", "type": "Image"},
                   {"name": "AviNord-modele.svg", "path": "AviNord-modele.svg", "type": "Image"}]}],
    "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                 "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
THEMES = RP / "StaticResources" / "SharedResources" / "BaseThemes"
THEMES.mkdir(parents=True, exist_ok=True)
shutil.copy(Path(__file__).parent / "ressources" / "CY24SU10.json", THEMES / "CY24SU10.json")
REG = RP / "StaticResources" / "RegisteredResources"
REG.mkdir(parents=True, exist_ok=True)
for f in ("AviNord-theme.json", "AviNord-logo.svg", "AviNord-modele.svg"):
    shutil.copy(Path(__file__).parent / "ressources" / f, REG / f)
wjson(R / "pages" / "pages.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
for p in pages:
    wjson(R / "pages" / p.name / "page.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": p.name, "displayName": p.display, "displayOption": "FitToPage", "height": 720, "width": 1280})
    for v in p.visuals:
        wjson(R / "pages" / p.name / "visuals" / v["name"] / "visual.json", v)

wjson(ROOT / f"{NAME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                               "settings": {"enableAutoRecovery": True}})
write(ROOT / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
print("OK →", ROOT / f"{NAME}.pbip")
