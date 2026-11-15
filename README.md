# Power BI portfolio — interactive demo projects

Three end-to-end Power BI projects built on **fictional companies and generated data**, by **Adams Dalqiel Yao** (Power BI developer · data modeling).
Each project contains the data generator, the Power BI project files (PBIP: TMDL semantic model + PBIR report), the `.pbix` and a technical README.

| Project | What it shows | Live demo |
|---|---|---|
| [A — Procurement cost (AviNord)](A-approvisionnement-v2/) | Star schema, fiscal 13×4-week calendar, calculation group, **price / volume / mix variance bridge** | [Open](https://app.powerbi.com/view?r=eyJrIjoiOWNhYzY5ZGItM2QwYS00MTcxLWJhMTMtZDM0YzU4MTdhMmViIiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9) |
| [B — Multi-plant performance (Bellerive)](B-performance-usines/) | **Microsoft Fabric**: lakehouse, PySpark notebook, Delta tables, Direct Lake; OEE, downtime Pareto, MTBF / MTTR | [Open](https://app.powerbi.com/view?r=eyJrIjoiYjMzNmFhNTktZTAxNC00NWQzLTg0NDYtMDg1YWNmOTUyZDQ3IiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9) |
| [C — Small-business financial dashboard (Lumen)](C-etats-financiers-pme/) | Dynamic income statement (one DAX measure for every line), EBITDA bridge, 13-week cash flow forecast | [Open](https://app.powerbi.com/view?r=eyJrIjoiOWQzMTYzNzktZjI5MC00NmU2LTkxMmEtYzJkMTQ4ZWYwNjNmIiwidCI6IjAyYmVjMmI0LWEzMTMtNDM3YS1hMTg1LWFjM2JiMGJkMmIyYiJ9) |

## How the projects are built
- `scripts/generer_donnees.py` — generates realistic fictional data with a fixed seed (same numbers every run), with "stories" hidden in the data for the report to reveal.
- `scripts/generer_pbip.py` — generates the whole Power BI project as code: TMDL semantic model (tables, relationships, DAX measures, calculation groups) and PBIR report pages, theme and logo.
- Open the `.pbip` (or the `.pbix`) in Power BI Desktop and refresh.

Project B also includes the Fabric notebook (`fabric/NB_Bellerive_Transformation.ipynb`) and the DAX measures script (`fabric/mesures.dax`).

> Technical READMEs are written in French; the case studies are available in English on the portfolio website.

**All companies, people and figures are fictional.**
