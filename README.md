# REMS - RAG Evaluation & Monitoring System

Système d'évaluation et de monitoring pour chatbots RAG réglementaires. REMS est un module externe qui évalue les performances d'un chatbot RAG existant sans le modifier.

## Contexte

Dans le domaine réglementaire, les exigences sont strictes :
- **Exactitude absolue** : Une erreur sur un texte de loi peut avoir des conséquences juridiques
- **Traçabilité** : Chaque réponse doit être rattachée à ses sources
- **Détection des hallucinations** : Les informations inventées doivent être identifiées

REMS répond à ces besoins en fournissant une évaluation objective et continue des performances du chatbot.

## Fonctionnalités

- **Évaluation RAGAS** : Faithfulness, Context Precision, Answer Relevancy
- **Détection d'hallucinations** : Identification automatique des réponses non fidèles aux sources
- **Diagnostic automatique** : Analyse des causes racines avec recommandations actionnables
- **Interface web** : Dashboard Streamlit avec visualisation des métriques et tendances
- **Rapports** : Export PDF, HTML et YAML des recommandations
- **Scheduling** : Évaluations hebdomadaires automatisées via cron

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CHATBOT RAG EXISTANT                     │
│                        (API REST)                           │
└─────────────────────────┬───────────────────────────────────┘
                          │ query + response + retrieved_docs
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                         REMS                                │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ API         │  │ Data Store  │  │ Evaluators          │ │
│  │ Collector   │─▶│ PostgreSQL  │─▶│ (RAGAS)             │ │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘ │
│                                               │             │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────▼──────────┐ │
│  │ Report      │◀─│ Recommend.  │◀─│ Diagnostic          │ │
│  │ Generator   │  │ Engine      │  │ Engine              │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│         │                │                                  │
│         ▼                ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Web Interface (Streamlit)              │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Structure du Code

```
src/rems/
├── cli.py                 # Interface ligne de commande
├── config.py              # Configuration (variables d'environnement)
├── schemas.py             # Schémas Pydantic (DTOs)
├── models/                # Modèles SQLAlchemy
│   ├── database.py        # Définition des tables
│   └── session.py         # Gestion des sessions DB
├── collector/             # Collecte des interactions
│   └── api_collector.py   # Récupération via API ou fichier JSON
├── evaluators/            # Évaluateurs RAGAS
│   ├── retrieval_evaluator.py   # Context Precision
│   ├── generator_evaluator.py   # Faithfulness, Answer Relevancy
│   └── orchestrator.py          # Coordination des évaluateurs
├── diagnostic/            # Analyse des causes racines
│   └── engine.py          # Règles de diagnostic
├── recommendations/       # Génération des recommandations
│   └── engine.py          # Suggestions + export YAML
├── reports/               # Génération des rapports
│   ├── generator.py       # PDF/HTML via WeasyPrint
│   └── templates/         # Templates Jinja2
└── web/                   # Interface Streamlit
    ├── app.py             # Application principale
    └── pages/             # Pages du dashboard
        ├── dashboard.py   # Vue d'ensemble
        ├── history.py     # Historique + tendances
        └── evaluate.py    # Lancement d'évaluations
```

## Prérequis

- Python 3.12+
- PostgreSQL 14+
- [uv](https://github.com/astral-sh/uv) (gestionnaire de paquets Python)

## Installation

```bash
# Cloner le repository
git clone https://github.com/arielibaba/rag-evaluation-monitoring-system-for-regulatory.git
cd rag-evaluation-monitoring-system-for-regulatory

# Installer les dépendances
uv sync

# Configurer les variables d'environnement
cp .env.example .env
```

## Configuration

Éditez le fichier `.env` :

```env
# Base de données PostgreSQL
REMS_DATABASE_URL=postgresql://user:password@localhost:5432/rems

# API du chatbot à évaluer
REMS_CHATBOT_API_URL=http://localhost:8000
REMS_CHATBOT_API_KEY=your-api-key

# Google API pour l'évaluation LLM-as-judge (Gemini)
REMS_GOOGLE_API_KEY=your-google-api-key
REMS_EVALUATION_MODEL=gemini-2.0-flash

# Répertoires de sortie
REMS_REPORTS_DIR=./reports
REMS_RECOMMENDATIONS_FILE=./recommendations.yaml
```

### Création de la base de données

```bash
# Démarrer PostgreSQL (macOS avec Homebrew)
brew services start postgresql@16

# Créer la base de données
createdb rems

# Initialiser les tables
uv run rems init-db
```

## Utilisation

### Interface Web (Streamlit)

```bash
# Lancer le dashboard
uv run rems web

# Sur un port personnalisé
uv run rems web --port 8080
```

Accédez à **http://localhost:8501** pour :
- 📊 **Dashboard** : Score global, métriques par composant, gauge
- 📜 **Historique** : Évolution des scores, comparaison entre évaluations
- 🚀 **Nouvelle évaluation** : Lancer une évaluation via fichier ou API

### CLI

```bash
# Initialiser la base de données
uv run rems init-db

# Lancer une évaluation depuis un fichier JSON
uv run rems evaluate --file interactions.json --name "Eval Janvier"

# Lancer une évaluation depuis l'API du chatbot
uv run rems evaluate --start 2026-01-01 --end 2026-01-07 --limit 100

# Collecter des interactions sans évaluer
uv run rems collect --start 2026-01-01 --limit 100 --store

# Afficher l'aide
uv run rems --help
```

### Évaluation Hebdomadaire Automatique

```bash
# Éditer le crontab
crontab -e

# Ajouter cette ligne (exécution chaque lundi à 8h)
0 8 * * 1 /chemin/vers/projet/scripts/weekly_evaluation.sh
```

## Format des Données d'Entrée

Le fichier JSON d'interactions doit respecter ce format :

```json
{
  "interactions": [
    {
      "query": "Quelle est la procédure de déclaration fiscale ?",
      "response": "Selon l'article 12 du CGI, la déclaration doit être effectuée dans les 3 mois...",
      "retrieved_documents": [
        {
          "content": "Article 12 - Délais de déclaration. Les entreprises doivent...",
          "source": "code_general_impots.pdf",
          "score": 0.89
        }
      ]
    }
  ]
}
```

## Outputs

### Fichier YAML de recommandations

```yaml
evaluation_id: "abc123"
evaluation_date: "2026-01-10T08:00:00"
overall_score: 0.784
quality_level: good
scores:
  retrieval: 0.723
  generation: 0.817
metrics:
  avg_faithfulness: 0.775
  avg_answer_relevancy: 0.858
  avg_context_precision: 0.723
  hallucination_rate: 0.2
  total_hallucinations: 1
recommendations:
  - component: generator
    priority: high
    issue: "faithfulness trop faible: 45% (seuil: 70%)"
    suggestion: "Réduire la température du LLM"
    parameter_adjustments:
      generator.temperature:
        action: decrease
        suggested_value: 0.3
```

### Rapports PDF/HTML

Générés dans le dossier `reports/` avec :
- Score global avec gauge visuelle
- Métriques détaillées par composant (Retrieval, Génération)
- Distribution des scores (Excellent, Bon, Acceptable, Faible, Critique)
- Recommandations classées par priorité

## Métriques Évaluées

| Métrique | Description | Composant |
|----------|-------------|-----------|
| **Faithfulness** | Fidélité de la réponse aux documents sources | Generator |
| **Answer Relevancy** | Pertinence de la réponse par rapport à la question | Generator |
| **Context Precision** | Précision des documents récupérés | Retriever |
| **Hallucination Rate** | Taux de réponses non fidèles aux sources | Generator |

## Niveaux de Qualité

| Niveau | Score | Action |
|--------|-------|--------|
| Excellent | ≥ 90% | Aucune action requise |
| Bon | 75-89% | Améliorations mineures possibles |
| Acceptable | 60-74% | Améliorations recommandées |
| Faible | 40-59% | Actions correctives nécessaires |
| Critique | < 40% | Intervention urgente requise |

## Technologies

| Composant | Technologie |
|-----------|-------------|
| Évaluation RAG | RAGAS 0.4.x |
| LLM-as-judge | LangChain + Google Gemini |
| Base de données | PostgreSQL + SQLAlchemy |
| Interface web | Streamlit + Plotly |
| Génération PDF | WeasyPrint + Jinja2 |
| Configuration | Pydantic Settings |

## Développement

```bash
# Installer les dépendances de dev
uv sync --all-extras

# Lancer les tests
uv run pytest

# Linting
uv run ruff check src/

# Type checking
uv run mypy src/
```

## Licence

MIT
