"""Dessine le schéma du modèle en étoile (SVG) utilisé sur la page « À propos »."""
from pathlib import Path

W, H, BW, BH = 900, 420, 176, 42
NAVY, ORANGE, GRIS, LIGNE = "#1F3A5F", "#E07A1F", "#8A8F98", "#B8C2CC"

# (nom, x, y, type) — type : fait | budget | dim
N = {
    "DimRegion":            (30, 30, "dim"),
    "DimProducteur":        (30, 110, "dim"),
    "DimTypePoulet":        (30, 190, "dim"),
    "DimTransporteur":      (30, 270, "dim"),
    "DimDate":              (290, 30, "dim"),
    "FaitReceptionLot":     (290, 150, "fait"),
    "FaitCondamnation":     (290, 260, "fait"),
    "DimCauseCondamnation": (290, 350, "dim"),
    "FaitCout":             (520, 150, "fait"),
    "DimComposante":        (520, 260, "dim"),
    "FaitBudgetVolume":     (712, 150, "budget"),
    "FaitBudgetCout":       (712, 260, "budget"),
}
# Les liens du budget vers DimDate / DimTypePoulet / DimRegion sont indiqués en légende
# (des traits longs rendraient le schéma illisible).
LIENS = [
    ("DimDate", "FaitReceptionLot"), ("DimRegion", "DimProducteur"),
    ("DimProducteur", "FaitReceptionLot"), ("DimTypePoulet", "FaitReceptionLot"),
    ("DimTransporteur", "FaitReceptionLot"), ("FaitReceptionLot", "FaitCout"),
    ("FaitReceptionLot", "FaitCondamnation"), ("DimCauseCondamnation", "FaitCondamnation"),
    ("DimComposante", "FaitCout"), ("DimComposante", "FaitBudgetCout"),
]

def centre(n):
    x, y, _ = N[n]
    return x + BW / 2, y + BH / 2

def svg():
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H + 40}" viewBox="0 0 {W} {H + 40}">',
           f'<rect width="{W}" height="{H + 40}" fill="#FFFFFF"/>',
           # cadre du budget
           f'<rect x="700" y="112" width="196" height="210" rx="12" fill="#FFF7EF" stroke="{ORANGE}" stroke-dasharray="5 4"/>',
           f'<text x="798" y="134" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="12" font-weight="600" fill="{ORANGE}">BUDGET (ventilé au jour)</text>',
           f'<text x="798" y="232" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="10.5" fill="{GRIS}">reliées aussi à DimDate,</text>',
           f'<text x="798" y="246" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="10.5" fill="{GRIS}">DimTypePoulet et DimRegion</text>']
    for a, b in LIENS:
        (x1, y1), (x2, y2) = centre(a), centre(b)
        coul = ORANGE if "Budget" in a + b else NAVY
        out.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{coul}" stroke-width="1.6"/>')
    for n, (x, y, t) in N.items():
        fill, txt, stroke = {"fait": (NAVY, "#FFFFFF", NAVY), "budget": ("#FFFFFF", ORANGE, ORANGE),
                             "dim": ("#FFFFFF", NAVY, NAVY)}[t]
        out.append(f'<rect x="{x}" y="{y}" width="{BW}" height="{BH}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        out.append(f'<text x="{x + BW / 2}" y="{y + BH / 2 + 5}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
                   f'font-size="13" font-weight="600" fill="{txt}">{n}</text>')
    ly = H + 14
    legend = [(NAVY, NAVY, "Table de faits"), ("#FFFFFF", ORANGE, "Budget (ventilé au jour)"), ("#FFFFFF", NAVY, "Dimension")]
    lx = 20
    for fill, stroke, lab in legend:
        out.append(f'<rect x="{lx}" y="{ly}" width="18" height="14" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        out.append(f'<text x="{lx + 26}" y="{ly + 12}" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="{GRIS}">{lab}</text>')
        lx += 210
    out.append(f'<text x="{W - 20}" y="{ly + 12}" text-anchor="end" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="{GRIS}">'
               'Toutes les relations : 1 → plusieurs, filtrage simple</text>')
    out.append("</svg>")
    return "\n".join(out)

if __name__ == "__main__":
    p = Path(__file__).parent / "ressources" / "AviNord-modele.svg"
    p.write_text(svg(), encoding="utf-8")
    print("OK", p)
