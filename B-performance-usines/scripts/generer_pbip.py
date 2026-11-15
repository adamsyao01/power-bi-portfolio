"""
Génère la COPIE PUBLIQUE (mode Import) du projet B — Performance multi-usines.
Ouvrir ensuite ../Bellerive-Performance.pbip dans Power BI Desktop, puis Actualiser.

Usage : python generer_pbip.py
"""
import hashlib, json, shutil, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = (ROOT / "data" / "or").resolve()
NAME = "Bellerive-Performance"
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
TYPES_M = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date", "dateTimeFull": "type datetime"}

def csv_m(fichier, cols):
    types = ", ".join(f'{{"{c}", {TYPES_M["dateTimeFull" if c == "Debut" else t]}}}' for c, t, *_ in cols)
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


# --- Modèle du projet B ---
H = {"hidden": True}
N = {}
DATE_FMT = {"fmt": "yyyy-mm-dd"}
tables = {}

def dim(name, cols, **kw):
    tables[name] = table_tmdl(name, cols, csv_m(f"{name}.csv", cols), **kw)

dim("dim_date", [
    ("Date", "dateTime", {"fmt": "yyyy-mm-dd", "key": True}),
    ("Annee", "int64", {"fmt": "0"}),
    ("NoMois", "int64", H),
    ("Mois", "string", {"sort_by": "NoMois"}),
    ("AnneeMois", "string", {"sort_by": "CleAnneeMois"}),
    ("CleAnneeMois", "int64", H),
    ("SemaineISO", "int64", {"fmt": "0"}),
    ("JourSemaine", "int64", H),
], data_category="Time")
dim("dim_usine", [("CodeUsine", "string", N), ("Usine", "string", N), ("Region", "string", N),
                  ("CourrielDirecteur", "string", H)])
dim("dim_ligne", [("CodeLigne", "string", N), ("CodeUsine", "string", H), ("Ligne", "string", N),
                  ("TypeLigne", "string", N), ("CadenceIdealeUnitesMin", "double", {"fmt": "0"})])
dim("dim_produit", [("CodeProduit", "string", H), ("Produit", "string", N), ("Famille", "string", N)])
dim("dim_code_arret", [("CodeArret", "string", N), ("Arret", "string", N), ("Categorie", "string", N),
                       ("Planifie", "string", H)])
dim("dim_quart", [("Quart", "string", {"sort_by": "OrdreQuart"}), ("OrdreQuart", "int64", H), ("HeureDebut", "string", N)])

fp_cols = [("Date", "dateTime", H), ("CodeUsine", "string", H), ("CodeLigne", "string", H), ("Quart", "string", H),
           ("CodeProduit", "string", H), ("MinutesOuvertes", "double", H), ("UnitesProduites", "double", H),
           ("UnitesRejetees", "double", H), ("MinutesArretPlanifie", "double", H), ("MinutesArretNonPlanifie", "double", H),
           ("NbArretsNonPlanifies", "double", H), ("TempsRequisMin", "double", H), ("TempsFonctionnementMin", "double", H),
           ("UnitesTheoriques", "double", H), ("UnitesBonnes", "double", H)]
dim("fact_production", fp_cols)
dim("fact_arret", [("CodeUsine", "string", H), ("CodeLigne", "string", H), ("Date", "dateTime", H), ("Quart", "string", H),
                   ("Debut", "dateTime", {"fmt": "yyyy-mm-dd hh:nn"}), ("DureeMin", "double", H), ("CodeArret", "string", H)])

# --- Mesures (identiques à fabric/mesures.dax) ------------------------------------
PCT, PCT1, N0 = "0.0 %", "0.0 %", "#,0"
PLANIF_FAUX = 'dim_code_arret[Planifie] = "False"'
measures = [
    ("Mise à jour", "0. Paramètres", None, "\"Données au \" & FORMAT(MAX(fact_production[Date]), \"d mmmm yyyy\")"),
    ("Temps requis (min)", "1. Temps et volumes", N0, "SUM(fact_production[TempsRequisMin])"),
    ("Temps de fonctionnement (min)", "1. Temps et volumes", N0, "SUM(fact_production[TempsFonctionnementMin])"),
    ("Unités produites", "1. Temps et volumes", N0, "SUM(fact_production[UnitesProduites])"),
    ("Unités bonnes", "1. Temps et volumes", N0, "SUM(fact_production[UnitesBonnes])"),
    ("Unités rejetées", "1. Temps et volumes", N0, "SUM(fact_production[UnitesRejetees])"),
    ("Unités théoriques", "1. Temps et volumes", N0, "SUM(fact_production[UnitesTheoriques])"),
    ("Disponibilité", "2. TRS", PCT, "DIVIDE([Temps de fonctionnement (min)], [Temps requis (min)])"),
    ("Performance", "2. TRS", PCT, "DIVIDE([Unités produites], [Unités théoriques])"),
    ("Qualité", "2. TRS", PCT, "DIVIDE([Unités bonnes], [Unités produites])"),
    ("TRS", "2. TRS", PCT, "[Disponibilité] * [Performance] * [Qualité]"),
    ("TRS cible", "2. TRS", PCT, "0.85"),
    ("Écart TRS vs cible", "2. TRS", "+0.0 %;-0.0 %", "[TRS] - [TRS cible]"),
    ("TRS mois précédent", "2. TRS", PCT, "CALCULATE([TRS], DATEADD(dim_date[Date], -1, MONTH))"),
    ("Variation TRS vs mois précédent", "2. TRS", "+0.0 %;-0.0 %",
     "IF(NOT ISBLANK([TRS mois précédent]), [TRS] - [TRS mois précédent])"),
    ("% rebuts", "2. TRS", "0.00 %", "DIVIDE([Unités rejetées], [Unités produites])"),
    ("Minutes d'arrêt", "3. Arrêts", N0, "SUM(fact_arret[DureeMin])"),
    ("Minutes d'arrêt non planifié", "3. Arrêts", N0, f"CALCULATE([Minutes d'arrêt], {PLANIF_FAUX})"),
    ("Heures d'arrêt non planifié", "3. Arrêts", N0, "[Minutes d'arrêt non planifié] / 60"),
    ("Nb arrêts non planifiés", "3. Arrêts", N0, f"CALCULATE(COUNTROWS(fact_arret), {PLANIF_FAUX})"),
    ("Durée moyenne d'arrêt (min)", "3. Arrêts", "0.0", "DIVIDE([Minutes d'arrêt non planifié], [Nb arrêts non planifiés])"),
    ("% du temps d'arrêt", "3. Arrêts", PCT1,
     "DIVIDE([Minutes d'arrêt non planifié], CALCULATE([Minutes d'arrêt non planifié], ALLSELECTED(dim_code_arret)))"),
    ("Nb pannes", "3. Arrêts", N0, "CALCULATE(COUNTROWS(fact_arret), dim_code_arret[Categorie] = \"Panne mécanique\")"),
    ("MTBF (h)", "3. Arrêts", "0.0", "DIVIDE([Temps de fonctionnement (min)], [Nb pannes]) / 60"),
    ("MTTR (min)", "3. Arrêts", "0.0",
     "DIVIDE(CALCULATE([Minutes d'arrêt], dim_code_arret[Categorie] = \"Panne mécanique\"), [Nb pannes])"),
]

def measure_tmdl(name, folder, fmt, dax):
    head = f"\tmeasure {q(name)} = {dax}" if "\n" not in dax else f"\tmeasure {q(name)} =\n{indent(dax, 3)}"
    props = ([f"\t\tformatString: {fmt}"] if fmt else []) + [f"\t\tdisplayFolder: {folder}"]
    return head + "\n" + "\n".join(props)

tables["_Mesures"] = table_tmdl("_Mesures", [("Colonne", "string", H)], '''let
    Source = #table(type table [Colonne = text], {})
in
    Source''', extra="\n\n".join(measure_tmdl(*m) for m in measures))

rels = [
    ("fact_production", "Date", "dim_date", "Date"),
    ("fact_production", "CodeLigne", "dim_ligne", "CodeLigne"),
    ("fact_production", "Quart", "dim_quart", "Quart"),
    ("fact_production", "CodeProduit", "dim_produit", "CodeProduit"),
    ("fact_arret", "Date", "dim_date", "Date"),
    ("fact_arret", "CodeLigne", "dim_ligne", "CodeLigne"),
    ("fact_arret", "Quart", "dim_quart", "Quart"),
    ("fact_arret", "CodeArret", "dim_code_arret", "CodeArret"),
    ("dim_ligne", "CodeUsine", "dim_usine", "CodeUsine"),
]
rel_txt = "\n\n".join(
    f"relationship {uuid.uuid5(uuid.NAMESPACE_DNS, f'B-{a}.{b}-{c}.{d}')}\n\tfromColumn: {q(a)}.{q(b)}\n\ttoColumn: {q(c)}.{q(d)}"
    for a, b, c, d in rels) + "\n"

expr_txt = f'''expression DossierDonnees = "{str(DATA)}\\" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
\tannotation PBI_ResultType = Text
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
BLEU, ORANGE, GRIS = "#1E4D3A", "#D9952B", "#8A8F98"

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
    def add(self, vtype, x, y, w, h, query=None, objects=None, vco=None, extra=None, sort_desc=None):
        vid = uid(f"{self.name}-{len(self.visuals)}")
        objects = dict(objects or {})
        if vtype in ("clusteredColumnChart", "clusteredBarChart", "columnChart", "lineChart", "waterfallChart", "scatterChart"):
            # titres d'axes masqués : le titre du visuel suffit
            objects.setdefault("categoryAxis", [{"properties": {"showAxisTitle": lit("false")}}])
            objects.setdefault("valueAxis", [{"properties": {"showAxisTitle": lit("false")}}])
        if vtype in ("pivotTable", "tableEx"):
            objects.setdefault("grid", [{"properties": {"rowPadding": lit("1D")}}])
        objects = objects or None
        v = {"visualType": vtype}
        if query:
            v["query"] = {"queryState": query}
            if sort_desc:  # tri décroissant sur une mesure
                v["query"]["sortDefinition"] = {"sort": [{"field": mes(sort_desc)["field"], "direction": "Descending"}],
                                                "isDefaultSort": False}
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


# --- Pages du projet B ---
def bandeau(pg, sous_titre):
    image(pg, 14, 12, 125, 44, "Bellerive-logo.svg")
    textbox(pg, 152, 6, 820, 52, "Performance des usines (TRS)", size="18pt")
    textbox(pg, 152, 46, 820, 36, sous_titre, size="11pt", color=GRIS, bold=False)
    pg.add("card", 1010, 12, 250, 50, query={"Values": {"projections": [mes("Mise à jour")]}},
           objects={"labels": [{"properties": {"fontSize": lit("10D"), "color": color(GRIS)}}],
                    "categoryLabels": [{"properties": {"show": lit("false")}}]})

def filtres(pg, y=84, usine=True, quart=True):
    slicer(pg, 20, y, 150, 64, "dim_date", "Annee", "Année")
    slicer(pg, 180, y, 150, 64, "dim_date", "Mois", "Mois")
    x = 340
    if usine:
        slicer(pg, x, y, 190, 64, "dim_usine", "Usine", "Usine"); x += 200
    if quart:
        slicer(pg, x, y, 150, 64, "dim_quart", "Quart", "Quart"); x += 160
    return x

PCT_LABELS = [{"properties": {"show": lit("true")}}]

# --- Page 1 : Vue groupe ----------------------------------------------------------------------------
p1 = Page(uid("b1"), "Vue groupe")
bandeau(p1, "Disponibilité × performance × qualité, par usine et par mois")
filtres(p1)
for i, (m, l) in enumerate([("TRS", "TRS"), ("Disponibilité", "Disponibilité"), ("Performance", "Performance"),
                             ("Qualité", "Qualité"), ("Écart TRS vs cible", "Écart vs cible 85 %")]):
    card(p1, 20 + i * 250, 160, 235, 95, m, l, units=None)
p1.add("lineChart", 20, 270, 760, 230,
       query={"Category": {"projections": [col("dim_date", "AnneeMois", active=True)]},
              "Y": {"projections": [mes("TRS"), mes("TRS cible", "Cible")]}},
       objects={"dataPoint": series_colors([("TRS", BLEU), ("TRS cible", ORANGE)]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("TRS mensuel vs cible"))
p1.add("clusteredBarChart", 795, 270, 465, 230,
       query={"Category": {"projections": [col("dim_usine", "Usine", active=True)]},
              "Y": {"projections": [mes("TRS")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}], "labels": PCT_LABELS},
       vco=title("TRS par usine"))
p1.add("pivotTable", 20, 515, 620, 195,
       query={"Rows": {"projections": [col("dim_usine", "Usine", active=True)]},
              "Values": {"projections": [mes("Disponibilité"), mes("Performance"), mes("Qualité"), mes("TRS"),
                                         mes("Variation TRS vs mois précédent", "vs mois préc."),
                                         mes("Heures d'arrêt non planifié", "Heures d'arrêt")]}},
       vco=title("Détail par usine"))
p1.add("clusteredColumnChart", 655, 515, 605, 195,
       query={"Category": {"projections": [col("dim_ligne", "CodeLigne", active=True)]},
              "Y": {"projections": [mes("TRS")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}]},
       vco=title("TRS par ligne (du plus faible au plus fort)"))
p1.visuals[-1]["visual"]["query"]["sortDefinition"] = {
    "sort": [{"field": mes("TRS")["field"], "direction": "Ascending"}], "isDefaultSort": False}

# --- Page 2 : Pertes ------------------------------------------------------------------------------------
p2 = Page(uid("b2"), "Pertes")
bandeau(p2, "Où part le temps ? Arrêts non planifiés par cause")
filtres(p2)
for i, (m, l, u) in enumerate([("Heures d'arrêt non planifié", "Heures d'arrêt non planifié", "1D"),
                                ("Nb arrêts non planifiés", "Arrêts non planifiés", "1D"),
                                ("Durée moyenne d'arrêt (min)", "Durée moyenne (min)", None),
                                ("MTBF (h)", "MTBF (h) — pannes", None), ("MTTR (min)", "MTTR (min) — pannes", None)]):
    card(p2, 20 + i * 250, 160, 235, 95, m, l, units=u, precision="0L")
p2.add("clusteredBarChart", 20, 270, 500, 440,
       query={"Category": {"projections": [col("dim_code_arret", "Categorie", active=True)]},
              "Y": {"projections": [mes("% du temps d'arrêt", "% du temps d'arrêt")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}], "labels": PCT_LABELS},
       vco=title("Répartition des arrêts non planifiés par catégorie"), sort_desc="% du temps d'arrêt")
p2.add("clusteredBarChart", 535, 270, 725, 220,
       query={"Category": {"projections": [col("dim_code_arret", "Arret", active=True)]},
              "Y": {"projections": [mes("Heures d'arrêt non planifié", "Heures")]}},
       objects={"dataPoint": [{"properties": {"fill": color(ORANGE)}}], "labels": PCT_LABELS},
       vco=title("Heures d'arrêt par cause détaillée"), sort_desc="Heures d'arrêt non planifié")
p2.add("pivotTable", 535, 505, 725, 205,
       query={"Rows": {"projections": [col("dim_code_arret", "Categorie", active=True)]},
              "Columns": {"projections": [col("dim_usine", "Usine", active=True)]},
              "Values": {"projections": [mes("Heures d'arrêt non planifié", "Heures")]}},
       vco=title("Heures d'arrêt par catégorie et par usine"))

# --- Page 3 : Analyse d'une ligne -------------------------------------------------------------------------
p3 = Page(uid("b3"), "Analyse d'une ligne")
bandeau(p3, "Zoom sur une ligne : disponibilité et pannes dans le temps")
slicer(p3, 20, 84, 190, 64, "dim_ligne", "CodeLigne", "Ligne", single=True, default_in="'SAG-L3'")
slicer(p3, 220, 84, 150, 64, "dim_date", "Annee", "Année")
for i, (m, l) in enumerate([("TRS", "TRS"), ("Disponibilité", "Disponibilité"), ("Nb pannes", "Pannes"),
                             ("MTBF (h)", "MTBF (h)"), ("MTTR (min)", "MTTR (min)")]):
    card(p3, 20 + i * 250, 160, 235, 95, m, l, units=None)
p3.add("lineChart", 20, 270, 1240, 215,
       query={"Category": {"projections": [col("dim_date", "AnneeMois", active=True)]},
              "Y": {"projections": [mes("Disponibilité")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}]},
       vco=title("Disponibilité mensuelle de la ligne"))
p3.add("columnChart", 20, 500, 760, 210,
       query={"Category": {"projections": [col("dim_date", "AnneeMois", active=True)]},
              "Y": {"projections": [mes("Heures d'arrêt non planifié", "Heures d'arrêt")]},
              "Series": {"projections": [col("dim_code_arret", "Categorie")]}},
       objects={"legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Heures d'arrêt par mois et par catégorie"))
p3.add("tableEx", 795, 500, 465, 210,
       query={"Values": {"projections": [col("dim_code_arret", "Arret"), mes("Nb arrêts non planifiés", "Arrêts"),
                                         mes("Heures d'arrêt non planifié", "Heures"), mes("Durée moyenne d'arrêt (min)", "Durée moy.")]}},
       vco=title("Causes d'arrêt de la ligne"), sort_desc="Heures d'arrêt non planifié")

# --- Page 4 : Qualité par quart ---------------------------------------------------------------------------
p4 = Page(uid("b4"), "Qualité par quart")
bandeau(p4, "Rebuts par usine et par quart de travail")
filtres(p4, quart=False)
for i, (m, l) in enumerate([("Qualité", "Qualité"), ("% rebuts", "% rebuts"), ("Unités rejetées", "Unités rejetées"),
                             ("Unités produites", "Unités produites")]):
    card(p4, 20 + i * 312, 160, 300, 95, m, l, units=("1000000D" if "Unités" in m else None), precision="1L")
p4.add("clusteredColumnChart", 20, 270, 620, 440,
       query={"Category": {"projections": [col("dim_usine", "Usine", active=True)]},
              "Y": {"projections": [mes("% rebuts")]},
              "Series": {"projections": [col("dim_quart", "Quart")]}},
       objects={"legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}], "labels": PCT_LABELS},
       vco=title("% rebuts par usine et par quart"))
p4.add("lineChart", 655, 270, 605, 230,
       query={"Category": {"projections": [col("dim_date", "AnneeMois", active=True)]},
              "Y": {"projections": [mes("% rebuts")]},
              "Series": {"projections": [col("dim_quart", "Quart")]}},
       objects={"legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("% rebuts mensuel par quart"))
p4.add("pivotTable", 655, 515, 605, 195,
       query={"Rows": {"projections": [col("dim_produit", "Famille", active=True), col("dim_produit", "Produit", active=True)]},
              "Values": {"projections": [mes("Unités produites"), mes("% rebuts"), mes("Qualité")]}},
       vco=title("Qualité par produit"))

# --- Page 5 : À propos --------------------------------------------------------------------------------------
p5 = Page(uid("b5"), "À propos")
bandeau(p5, "Démo portfolio : architecture Fabric, modèle et indicateurs")
richtext(p5, 20, 90, 440, 620, [
    ("Le contexte", "titre"),
    ("Aliments Bellerive est un transformateur alimentaire fictif : 3 usines au Québec, 4 lignes chacune, "
     "3 quarts par jour. La direction veut comparer la performance des usines sur une base commune.", "texte"),
    ("", "vide"),
    ("Le défi", "titre"),
    ("Chaque usine exporte ses données de production à sa façon : séparateurs, formats de date, "
     "langue des colonnes, doublons. Avant de calculer quoi que ce soit, il faut les harmoniser.", "texte"),
    ("", "vide"),
    ("L'indicateur : le TRS", "titre"),
    ("Disponibilité = temps de fonctionnement ÷ temps requis", "formule"),
    ("Performance = unités produites ÷ unités théoriques", "formule"),
    ("Qualité = unités bonnes ÷ unités produites", "formule"),
    ("TRS = disponibilité × performance × qualité (cible : 85 %)", "formule"),
    ("", "vide"),
    ("Ce que les données révèlent", "titre"),
    ("La ligne 3 de Saguenay perd 13 points de disponibilité depuis mars 2026 (convoyeur)", "puce"),
    ("Le quart de nuit de Drummondville produit deux fois plus de rebuts", "puce"),
    ("Les changements de format sont la 1re cause d'arrêt : une piste SMED", "puce"),
    ("", "vide"),
    ("Réalisé par", "titre"),
    ("Adams Dalqiel Michel Ange Yao · Consultant Power BI · modélisation de données", "texte"),
    ("Données 100 % fictives, générées par script.", "texte"),
])
p5.add("image", 480, 90, 780, 360, objects={"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
    "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "Bellerive-architecture.svg"}}}}}],
    "imageScaling": [{"properties": {"imageScalingType": lit("'Fit'")}}]},
    vco={"title": [{"properties": {"show": lit("true"), "text": lit("'Architecture'"), "fontColor": color(BLEU), "bold": lit("true")}}],
         "background": [{"properties": {"show": lit("true"), "color": color("#FFFFFF")}}],
         "border": [{"properties": {"show": lit("true"), "color": color("#E3E7EC"), "radius": lit("8D")}}]})
richtext(p5, 480, 465, 780, 245, [
    ("Les choix techniques", "titre"),
    ("Lakehouse Fabric : les fichiers bruts restent intacts (bronze), les tables propres sont en Delta (or)", "puce"),
    ("Notebook PySpark : harmonisation des 3 formats, dédoublonnage, calcul des temps du TRS par quart", "puce"),
    ("Modèle Direct Lake : Power BI lit directement les tables Delta, sans import ni copie", "puce"),
    ("Schéma en étoile : 2 tables de faits (production par quart, arrêts) et 6 dimensions partagées", "puce"),
    ("Sécurité par ligne prévue : chaque directeur d'usine ne voit que son usine", "puce"),
    ("Cette version publique est une copie en mode Import, sans sécurité par ligne", "puce"),
])

# --- Écriture du rapport --------------------------------------------------------------------------------
R = RP / "definition"
wjson(RP / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
wjson(R / "version.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
wjson(R / "report.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {
        "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "SharedResources"},
        "customTheme": {"name": "Bellerive-theme.json", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "RegisteredResources"}},
    "resourcePackages": [
        {"name": "SharedResources", "type": "SharedResources",
         "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
        {"name": "RegisteredResources", "type": "RegisteredResources",
         "items": [{"name": "Bellerive-theme.json", "path": "Bellerive-theme.json", "type": "CustomTheme"},
                   {"name": "Bellerive-logo.svg", "path": "Bellerive-logo.svg", "type": "Image"},
                   {"name": "Bellerive-architecture.svg", "path": "Bellerive-architecture.svg", "type": "Image"}]}],
    "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                 "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
THEMES = RP / "StaticResources" / "SharedResources" / "BaseThemes"
THEMES.mkdir(parents=True, exist_ok=True)
shutil.copy(Path(__file__).parent / "ressources" / "CY24SU10.json", THEMES / "CY24SU10.json")
REG = RP / "StaticResources" / "RegisteredResources"
REG.mkdir(parents=True, exist_ok=True)
for f in ("Bellerive-theme.json", "Bellerive-logo.svg", "Bellerive-architecture.svg"):
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
