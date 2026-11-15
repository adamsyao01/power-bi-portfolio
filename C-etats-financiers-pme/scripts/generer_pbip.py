"""
Génère la projet C — Tableau de bord financier de PME (mode Import).
Ouvrir ensuite ../Lumen-Finances.pbip dans Power BI Desktop, puis Actualiser.

Usage : python generer_pbip.py
"""
import hashlib, json, shutil, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = (ROOT / "data").resolve()
NAME = "Lumen-Finances"
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


# --- Modèle du projet C ---
H = {"hidden": True}
N = {}
DATE_FMT = {"fmt": "yyyy-mm-dd"}
tables = {}

def tbl(name, cols, **kw):
    tables[name] = table_tmdl(name, cols, csv_m(f"{name}.csv", cols), **kw)

tbl("DimDate", [
    ("Date", "dateTime", {"fmt": "yyyy-mm-dd", "key": True}),
    ("AnneeFiscale", "int64", H),
    ("Exercice", "string", {"sort_by": "AnneeFiscale"}),
    ("MoisFiscal", "int64", H),
    ("Mois", "string", {"sort_by": "MoisFiscal"}),
    ("MoisAnnee", "string", {"sort_by": "CleMois"}),
    ("CleMois", "int64", H),
    ("DebutSemaine", "dateTime", {"fmt": "d mmm yyyy"}),
    ("AnneeCivile", "int64", {"fmt": "0"}),
    ("MoisCivil", "int64", H),
], data_category="Time")
tbl("DimCompte", [("NoCompte", "int64", {"fmt": "0"}), ("Compte", "string", N),
                  ("Categorie", "string", {"sort_by": "OrdreCategorie"}), ("SousCategorie", "string", N),
                  ("OrdreCategorie", "int64", H), ("Signe", "int64", H),
                  ("CompteAffiche", "string", {"sort_by": "NoCompte"})])
tbl("StructurePL", [("Ordre", "int64", H), ("LignePL", "string", {"sort_by": "Ordre"}), ("TypeLigne", "string", H)])
tbl("FaitGL", [("Date", "dateTime", H), ("NoCompte", "int64", H), ("Montant", "double", H), ("MontantSigne", "double", H)])
tbl("FaitBudget", [("Date", "dateTime", H), ("NoCompte", "int64", H), ("Montant", "double", H), ("MontantSigne", "double", H)])
tbl("FaitTresorerie", [("DebutSemaine", "dateTime", H), ("CategorieFlux", "string", N), ("Montant", "double", H),
                       ("TypeDonnee", "string", N)])

CUR = r'#,0 \$;(#,0 \$);-'
PCT = "0.0 %;-0.0 %;-"
ECART = r'+#,0 \$;-#,0 \$;-'
FIN = "_FIN = EOMONTH(CALCULATE(MAX(FaitGL[Date]), REMOVEFILTERS()), 0)"

def pl(base):
    return f"""VAR _o = SELECTEDVALUE(StructurePL[Ordre])
VAR _t = SELECTEDVALUE(StructurePL[TypeLigne])
RETURN
    SWITCH(
        _t,
        "Détail", CALCULATE({base}, DimCompte[OrdreCategorie] = _o),
        "Sous-total", CALCULATE({base}, DimCompte[OrdreCategorie] < _o)
    )"""

measures = [
    ("Dernière date réelle", "0. Paramètres", "yyyy-mm-dd", "EOMONTH(CALCULATE(MAX(FaitGL[Date]), REMOVEFILTERS()), 0)"),
    ("Mise à jour", "0. Paramètres", None, "\"Réel au \" & FORMAT([Dernière date réelle], \"d mmmm yyyy\")"),

    # Bases signées : revenus +, charges −
    ("Réel", "1. Bases", CUR, "SUM(FaitGL[MontantSigne])"),
    ("Budget", "1. Bases", CUR, f"VAR {FIN}\nRETURN CALCULATE(SUM(FaitBudget[MontantSigne]), KEEPFILTERS(DimDate[Date] <= _FIN))"),
    ("Réel année précédente", "1. Bases", CUR,
     f"VAR {FIN}\nRETURN CALCULATE(CALCULATE([Réel], SAMEPERIODLASTYEAR(DimDate[Date])), KEEPFILTERS(DimDate[Date] <= _FIN))"),
    ("Écart vs budget (fav. +)", "1. Bases", ECART, "[Réel] - [Budget]"),
    ("Montant réel", "1. Bases", CUR, "SUM(FaitGL[Montant])"),
    ("Montant budget", "1. Bases", CUR, f"VAR {FIN}\nRETURN CALCULATE(SUM(FaitBudget[Montant]), KEEPFILTERS(DimDate[Date] <= _FIN))"),

    # État des résultats
    ("PL Réel", "2. État des résultats", CUR, pl("[Réel]")),
    ("PL Budget", "2. État des résultats", CUR, pl("[Budget]")),
    ("PL Année précédente", "2. État des résultats", CUR, pl("[Réel année précédente]")),
    ("PL Écart vs budget", "2. État des résultats", ECART, "[PL Réel] - [PL Budget]"),
    ("PL Écart vs budget %", "2. État des résultats", PCT, "DIVIDE([PL Écart vs budget], ABS([PL Budget]))"),
    ("PL Écart vs année préc.", "2. État des résultats", ECART, "[PL Réel] - [PL Année précédente]"),
    ("PL % des revenus", "2. État des résultats", PCT,
     "DIVIDE([PL Réel], CALCULATE([Réel], DimCompte[OrdreCategorie] = 1))"),

    # Indicateurs clés
    ("Revenus", "3. Indicateurs", CUR, "CALCULATE([Réel], DimCompte[OrdreCategorie] = 1)"),
    ("Revenus budget", "3. Indicateurs", CUR, "CALCULATE([Budget], DimCompte[OrdreCategorie] = 1)"),
    ("Écart revenus vs budget %", "3. Indicateurs", PCT, "DIVIDE([Revenus] - [Revenus budget], [Revenus budget])"),
    ("Marge brute", "3. Indicateurs", CUR, "CALCULATE([Réel], DimCompte[OrdreCategorie] < 3)"),
    ("Marge brute %", "3. Indicateurs", PCT, "DIVIDE([Marge brute], [Revenus])"),
    ("Marge brute % budget", "3. Indicateurs", PCT,
     "DIVIDE(CALCULATE([Budget], DimCompte[OrdreCategorie] < 3), [Revenus budget])"),
    ("BAIIA", "3. Indicateurs", CUR, "CALCULATE([Réel], DimCompte[OrdreCategorie] < 6)"),
    ("BAIIA budget", "3. Indicateurs", CUR, "CALCULATE([Budget], DimCompte[OrdreCategorie] < 6)"),
    ("Écart BAIIA vs budget", "3. Indicateurs", ECART, "[BAIIA] - [BAIIA budget]"),
    ("Pont du BAIIA", "3. Indicateurs", ECART,
     "IF(MAX(DimCompte[OrdreCategorie]) < 6, [Écart vs budget (fav. +)])"),
    ("BAIIA %", "3. Indicateurs", PCT, "DIVIDE([BAIIA], [Revenus])"),
    ("Bénéfice net", "3. Indicateurs", CUR, "CALCULATE([Réel], DimCompte[OrdreCategorie] < 12)"),

    # Trésorerie
    ("Solde initial", "4. Trésorerie", CUR, "1385000"),
    ("Seuil de sécurité", "4. Trésorerie", CUR, "150000"),
    ("Flux net", "4. Trésorerie", CUR, "SUM(FaitTresorerie[Montant])"),
    ("Encaissements", "4. Trésorerie", CUR, "CALCULATE([Flux net], FaitTresorerie[Montant] > 0)"),
    ("Décaissements", "4. Trésorerie", CUR, "-CALCULATE([Flux net], FaitTresorerie[Montant] < 0)"),
    ("Flux réels", "4. Trésorerie", CUR, "CALCULATE([Flux net], FaitTresorerie[TypeDonnee] = \"Réel\")"),
    ("Flux prévus", "4. Trésorerie", CUR, "CALCULATE([Flux net], FaitTresorerie[TypeDonnee] = \"Prévision\")"),
    ("Dernière semaine réelle", "4. Trésorerie", "d mmm yyyy",
     "CALCULATE(MAX(FaitTresorerie[DebutSemaine]), FaitTresorerie[TypeDonnee] = \"Réel\", REMOVEFILTERS())"),
    ("Solde de trésorerie", "4. Trésorerie", CUR, """IF(
    NOT ISEMPTY(FaitTresorerie),
    VAR _d = MAX(DimDate[Date])
    RETURN [Solde initial] + CALCULATE([Flux net], REMOVEFILTERS(DimDate), DimDate[Date] <= _d)
)"""),
    ("Solde réel", "4. Trésorerie", CUR, "IF(MIN(DimDate[DebutSemaine]) <= [Dernière semaine réelle], [Solde de trésorerie])"),
    ("Solde prévu", "4. Trésorerie", CUR, "IF(MAX(DimDate[DebutSemaine]) >= [Dernière semaine réelle], [Solde de trésorerie])"),
    ("Seuil", "4. Trésorerie", CUR, "IF(NOT ISEMPTY(FaitTresorerie), [Seuil de sécurité])"),
    ("Solde actuel", "4. Trésorerie", CUR, """VAR _s = [Dernière semaine réelle]
RETURN [Solde initial] + CALCULATE([Flux net], REMOVEFILTERS(), FaitTresorerie[DebutSemaine] <= _s)"""),
    ("Solde minimum prévu", "4. Trésorerie", CUR, """MINX(
    CALCULATETABLE(VALUES(FaitTresorerie[DebutSemaine]), FaitTresorerie[TypeDonnee] = "Prévision", REMOVEFILTERS()),
    VAR _w = FaitTresorerie[DebutSemaine]
    RETURN [Solde initial] + CALCULATE([Flux net], REMOVEFILTERS(), FaitTresorerie[DebutSemaine] <= _w)
)"""),
    ("Semaine du point bas", "4. Trésorerie", None, """VAR _sem =
    ADDCOLUMNS(
        CALCULATETABLE(VALUES(FaitTresorerie[DebutSemaine]), FaitTresorerie[TypeDonnee] = "Prévision", REMOVEFILTERS()),
        "@solde", VAR _w = FaitTresorerie[DebutSemaine]
                  RETURN CALCULATE([Flux net], REMOVEFILTERS(), FaitTresorerie[DebutSemaine] <= _w)
    )
VAR _bas = TOPN(1, _sem, [@solde], ASC)
RETURN FORMAT(MAXX(_bas, FaitTresorerie[DebutSemaine]), "d mmm yyyy")"""),
    ("Manque vs seuil", "4. Trésorerie", CUR, "MAX(0, [Seuil de sécurité] - [Solde minimum prévu])"),
]

def measure_tmdl(name, folder, fmt, dax):
    head = f"\tmeasure {q(name)} = {dax}" if "\n" not in dax else f"\tmeasure {q(name)} =\n{indent(dax, 3)}"
    props = ([f"\t\tformatString: {fmt}"] if fmt else []) + [f"\t\tdisplayFolder: {folder}"]
    return head + "\n" + "\n".join(props)

tables["_Mesures"] = table_tmdl("_Mesures", [("Colonne", "string", H)], '''let
    Source = #table(type table [Colonne = text], {})
in
    Source''', extra="\n\n".join(measure_tmdl(*m) for m in measures))

tables["Vue"] = f"""table {q('Vue')}

\tcalculationGroup

\t\tcalculationItem {q('Mois sélectionné')} = SELECTEDMEASURE()
\t\t\tordinal: 0

\t\tcalculationItem {q("Cumul de l'exercice")} = CALCULATE(SELECTEDMEASURE(), DATESYTD(DimDate[Date], "3-31"))
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

\tpartition {q('Vue')} = calculationGroup
"""

rels = [
    ("FaitGL", "Date", "DimDate", "Date"),
    ("FaitGL", "NoCompte", "DimCompte", "NoCompte"),
    ("FaitBudget", "Date", "DimDate", "Date"),
    ("FaitBudget", "NoCompte", "DimCompte", "NoCompte"),
    ("FaitTresorerie", "DebutSemaine", "DimDate", "Date"),
]
rel_txt = "\n\n".join(
    f"relationship {uuid.uuid5(uuid.NAMESPACE_DNS, f'C-{a}.{b}-{c}.{d}')}\n\tfromColumn: {q(a)}.{q(b)}\n\ttoColumn: {q(c)}.{q(d)}"
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
BLEU, ORANGE, GRIS = "#23395B", "#2A9D8F", "#8A8F98"

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


# --- Pages du projet C ---
def bandeau(pg, sous_titre):
    image(pg, 14, 12, 125, 44, "Lumen-logo.svg")
    textbox(pg, 152, 6, 820, 52, "Tableau de bord financier", size="18pt")
    textbox(pg, 152, 46, 820, 36, sous_titre, size="11pt", color=GRIS, bold=False)
    pg.add("card", 1010, 12, 250, 50, query={"Values": {"projections": [mes("Mise à jour")]}},
           objects={"labels": [{"properties": {"fontSize": lit("10D"), "color": color(GRIS)}}],
                    "categoryLabels": [{"properties": {"show": lit("false")}}]})

EX_DEFAUT = "'Ex. 2026-27'"
def filtres(pg, mois=True, vue=True, y=84):
    slicer(pg, 20, y, 170, 64, "DimDate", "Exercice", "Exercice", single=True, default_in=EX_DEFAUT)
    x = 200
    if mois:
        slicer(pg, x, y, 150, 64, "DimDate", "Mois", "Mois", single=True, default_in="'oct.'"); x += 160
    if vue:
        slicer(pg, x, y, 210, 64, "Vue", "Vue", "Vue", single=True, default_in="'Cumul de l''exercice'"); x += 220
    return x

PCT_LABELS = [{"properties": {"show": lit("true")}}]
NO_SUBTOTALS = [{"properties": {"rowSubtotals": lit("false"), "columnSubtotals": lit("false")}}]

# --- Page 1 : Sommaire ------------------------------------------------------------------------------
p1 = Page(uid("c1"), "Sommaire")
bandeau(p1, "Exercice en cours, depuis le 1er avril : réel vs budget")
filtres(p1, mois=False, vue=False)
textbox(p1, 200, 100, 700, 40, "Les montants couvrent l'exercice jusqu'au dernier mois réel ; le budget est comparé à date égale.",
        size="9pt", color=GRIS, bold=False)
for i, (m, l, u, pr) in enumerate([("Revenus", "Revenus", "1000000D", "2L"),
                                    ("Écart revenus vs budget %", "Revenus vs budget", None, None),
                                    ("Marge brute %", "Marge brute %", None, None),
                                    ("BAIIA", "BAIIA", "1000000D", "2L"),
                                    ("Écart BAIIA vs budget", "BAIIA vs budget", "1000D", "0L")]):
    card(p1, 20 + i * 250, 160, 235, 95, m, l, units=u, precision=pr)
p1.add("clusteredColumnChart", 20, 270, 620, 440,
       query={"Category": {"projections": [col("DimDate", "Mois", active=True)]},
              "Y": {"projections": [mes("Revenus", "Réel"), mes("Revenus budget", "Budget")]}},
       objects={"dataPoint": series_colors([("Revenus", BLEU), ("Revenus budget", "#B8C2CC")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Revenus mensuels : réel vs budget"))
p1.add("lineChart", 655, 270, 605, 215,
       query={"Category": {"projections": [col("DimDate", "Mois", active=True)]},
              "Y": {"projections": [mes("Marge brute %", "Réel"), mes("Marge brute % budget", "Budget")]}},
       objects={"dataPoint": series_colors([("Marge brute %", ORANGE), ("Marge brute % budget", "#8A8F98")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Marge brute % : réel vs budget"))
p1.add("clusteredColumnChart", 655, 495, 605, 215,
       query={"Category": {"projections": [col("DimDate", "Mois", active=True)]},
              "Y": {"projections": [mes("BAIIA", "Réel"), mes("BAIIA budget", "Budget")]}},
       objects={"dataPoint": series_colors([("BAIIA", BLEU), ("BAIIA budget", "#B8C2CC")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("BAIIA mensuel : réel vs budget"))

# --- Page 2 : État des résultats ------------------------------------------------------------------------
p2 = Page(uid("c2"), "État des résultats")
bandeau(p2, "État des résultats : réel, budget et année précédente")
filtres(p2)
p2.add("waterfallChart", 840, 160, 420, 470,
       query={"Category": {"projections": [col("DimCompte", "Categorie", active=True)]},
              "Y": {"projections": [mes("Pont du BAIIA", "Écart")]}},
       objects={"sentimentColors": [{"properties": {
           "increaseFill": color("#2A9D8F"), "decreaseFill": color("#E76F51"), "totalFill": color(BLEU)}}],
                "labels": [{"properties": {"show": lit("true"), "labelDisplayUnits": lit("1000D"), "labelPrecision": lit("0L")}}]},
       vco=title("Du BAIIA budgété au BAIIA réel : écarts (k$)"))
p2.add("pivotTable", 20, 160, 805, 470,
       query={"Rows": {"projections": [col("StructurePL", "LignePL", active=True)]},
              "Values": {"projections": [mes("PL Réel", "Réel"), mes("PL Budget", "Budget"),
                                         mes("PL Écart vs budget", "Écart vs budget"), mes("PL Écart vs budget %", "Écart %"),
                                         mes("PL Année précédente", "Année précédente"),
                                         mes("PL Écart vs année préc.", "Écart vs A-1"),
                                         mes("PL % des revenus", "% des revenus")]}},
       objects={"subTotals": NO_SUBTOTALS,
                "values": [{"properties": {"fontSize": lit("11D")}}],
                "rowHeaders": [{"properties": {"fontSize": lit("11D")}}],
                "columnHeaders": [{"properties": {"fontSize": lit("11D")}}]},
       vco=title("État des résultats"))
richtext(p2, 20, 640, 1240, 70, [
    ("Lecture : les charges sont entre parenthèses. Un écart positif est favorable (revenus plus élevés ou charges plus faibles "
     "que prévu), un écart négatif est défavorable. Les sous-totaux (marge brute, BAIIA, BAII, bénéfice) sont calculés par la "
     "structure de l'état des résultats, sans aucune ligne codée en dur dans le visuel.", "texte"),
])

# --- Page 3 : Analyse des écarts ------------------------------------------------------------------------------
p3 = Page(uid("c3"), "Analyse des écarts")
bandeau(p3, "Quels comptes expliquent l'écart au budget ?")
filtres(p3)
p3.add("clusteredBarChart", 20, 160, 620, 550,
       query={"Category": {"projections": [col("DimCompte", "CompteAffiche", active=True)]},
              "Y": {"projections": [mes("Écart vs budget (fav. +)", "Écart")]}},
       objects={"dataPoint": [{"properties": {"fill": color(BLEU)}}],
                "labels": [{"properties": {"show": lit("true"), "labelDisplayUnits": lit("1000D"), "labelPrecision": lit("0L")}}]},
       vco=title("Écart au budget par compte (k$, négatif = défavorable)"))
p3.visuals[-1]["visual"]["query"]["sortDefinition"] = {
    "sort": [{"field": mes("Écart vs budget (fav. +)")["field"], "direction": "Ascending"}], "isDefaultSort": False}
p3.add("pivotTable", 655, 160, 605, 550,
       query={"Rows": {"projections": [col("DimCompte", "Categorie", active=True), col("DimCompte", "Compte", active=True)]},
              "Values": {"projections": [mes("Réel"), mes("Budget"), mes("Écart vs budget (fav. +)", "Écart")]}},
       vco=title("Réel vs budget par catégorie et par compte (total = bénéfice net)"))

# --- Page 4 : Trésorerie ---------------------------------------------------------------------------------------
p4 = Page(uid("c4"), "Trésorerie")
bandeau(p4, "26 semaines de réel et prévision sur 13 semaines")
for i, (m, l, u, pr) in enumerate([("Solde actuel", "Solde actuel", "1000000D", "2L"),
                                    ("Solde minimum prévu", "Point bas prévu (13 sem.)", "1000D", "0L"),
                                    ("Semaine du point bas", "Semaine du point bas", None, None),
                                    ("Manque vs seuil", "Manque sous le seuil de 150 k$", "1000D", "0L")]):
    card(p4, 20 + i * 312, 90, 300, 95, m, l, units=u, precision=pr)
p4.add("lineChart", 20, 200, 1240, 260,
       query={"Category": {"projections": [col("DimDate", "DebutSemaine", active=True)]},
              "Y": {"projections": [mes("Solde réel", "Réel"), mes("Solde prévu", "Prévision"), mes("Seuil", "Seuil de sécurité")]}},
       objects={"dataPoint": series_colors([("Solde réel", BLEU), ("Solde prévu", ORANGE), ("Seuil", "#C0392B")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Solde de trésorerie hebdomadaire"))
p4.add("clusteredColumnChart", 20, 475, 760, 235,
       query={"Category": {"projections": [col("DimDate", "DebutSemaine", active=True)]},
              "Y": {"projections": [mes("Encaissements"), mes("Décaissements")]}},
       objects={"dataPoint": series_colors([("Encaissements", "#2A9D8F"), ("Décaissements", "#E76F51")]),
                "legend": [{"properties": {"show": lit("true"), "position": lit("'Top'")}}]},
       vco=title("Encaissements et décaissements par semaine"))
p4.add("pivotTable", 795, 475, 465, 235,
       query={"Rows": {"projections": [col("FaitTresorerie", "CategorieFlux", active=True)]},
              "Values": {"projections": [mes("Flux réels", "Réel (26 sem.)"), mes("Flux prévus", "Prévision (13 sem.)")]}},
       vco=title("Flux par catégorie"))

# --- Page 5 : À propos ----------------------------------------------------------------------------------------------
p5 = Page(uid("c5"), "À propos")
bandeau(p5, "Démo portfolio : contexte, modèle et méthode")
richtext(p5, 20, 90, 440, 620, [
    ("Le contexte", "titre"),
    ("Biscuiterie Lumen est une PME québécoise fictive (environ 19 M$ de ventes), avec un exercice "
     "du 1er avril au 31 mars. La direction et le comptable suivaient les résultats dans des chiffriers Excel, "
     "un mois après la fermeture.", "texte"),
    ("", "vide"),
    ("Ce que le tableau de bord apporte", "titre"),
    ("État des résultats réel vs budget vs année précédente, en un clic par mois ou en cumul", "puce"),
    ("Écarts expliqués compte par compte", "puce"),
    ("Prévision de trésorerie sur 13 semaines, avec alerte de seuil", "puce"),
    ("", "vide"),
    ("Ce que les données révèlent", "titre"),
    ("Les ventes dépassent le budget de 3 %, mais le BAIIA est inférieur d'environ 0,4 M$", "puce"),
    ("Cause : matières premières (beurre, farine) et dépassement en marketing", "puce"),
    ("Les ventes à l'export progressent fortement", "puce"),
    ("La trésorerie passe sous le seuil de sécurité de la mi-décembre à janvier (nouvelle ligne d'emballage, "
     "stocks des Fêtes, acompte d'impôt) : décaler l'achat ou prévoir la marge de crédit", "puce"),
    ("", "vide"),
    ("Réalisé par", "titre"),
    ("Adams Dalqiel Michel Ange Yao · Consultant Power BI · modélisation de données", "texte"),
    ("Données 100 % fictives, générées par script.", "texte"),
])
p5.add("image", 480, 90, 780, 330, objects={"general": [{"properties": {"imageUrl": {"expr": {"ResourcePackageItem": {
    "PackageName": "RegisteredResources", "PackageType": 1, "ItemName": "Lumen-modele.svg"}}}}}],
    "imageScaling": [{"properties": {"imageScalingType": lit("'Fit'")}}]},
    vco={"title": [{"properties": {"show": lit("true"), "text": lit("'Le modèle'"), "fontColor": color(BLEU), "bold": lit("true")}}],
         "background": [{"properties": {"show": lit("true"), "color": color("#FFFFFF")}}],
         "border": [{"properties": {"show": lit("true"), "color": color("#E3E7EC"), "radius": lit("8D")}}]})
richtext(p5, 480, 435, 780, 275, [
    ("Les choix de modélisation", "titre"),
    ("Plan comptable hiérarchique (compte → catégorie) et montants signés : revenus positifs, charges négatives", "puce"),
    ("Table « StructurePL » : les sous-totaux (marge brute, BAIIA, BAII, bénéfice) sont calculés par leur rang, "
     "en une seule mesure. Ajouter une ligne à l'état des résultats ne demande aucun nouveau DAX", "puce"),
    ("Calendrier fiscal d'avril à mars : cumul de l'exercice avec DATESYTD(…, \"3-31\")", "puce"),
    ("Budget et année précédente comparés à date égale (jusqu'au dernier mois fermé)", "puce"),
    ("Groupe de calcul « Vue » : mois ou cumul, pour toutes les mesures, sans duplication", "puce"),
    ("Trésorerie : solde cumulé hebdomadaire, point bas et manque vs seuil calculés dynamiquement", "puce"),
])

# --- Écriture du rapport --------------------------------------------------------------------------------
R = RP / "definition"
wjson(RP / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
wjson(R / "version.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
wjson(R / "report.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
    "themeCollection": {
        "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "SharedResources"},
        "customTheme": {"name": "Lumen-theme.json", "reportVersionAtImport": {"visual": "1.8.101", "report": "2.0.101", "page": "1.3.101"}, "type": "RegisteredResources"}},
    "resourcePackages": [
        {"name": "SharedResources", "type": "SharedResources",
         "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
        {"name": "RegisteredResources", "type": "RegisteredResources",
         "items": [{"name": "Lumen-theme.json", "path": "Lumen-theme.json", "type": "CustomTheme"},
                   {"name": "Lumen-logo.svg", "path": "Lumen-logo.svg", "type": "Image"},
                   {"name": "Lumen-modele.svg", "path": "Lumen-modele.svg", "type": "Image"}]}],
    "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                 "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                 "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True}})
THEMES = RP / "StaticResources" / "SharedResources" / "BaseThemes"
THEMES.mkdir(parents=True, exist_ok=True)
shutil.copy(Path(__file__).parent / "ressources" / "CY24SU10.json", THEMES / "CY24SU10.json")
REG = RP / "StaticResources" / "RegisteredResources"
REG.mkdir(parents=True, exist_ok=True)
for f in ("Lumen-theme.json", "Lumen-logo.svg", "Lumen-modele.svg"):
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
