"""Evaluate page - Trigger new evaluations."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

import streamlit as st

from rems.config import settings
<<<<<<< HEAD
from rems.diagnostic import DiagnosticEngine
from rems.evaluators import EvaluationOrchestrator
from rems.models import init_db
from rems.recommendations import RecommendationEngine
from rems.reports import ReportGenerator
from rems.schemas import InteractionSchema
from rems.diagnostic.Exportation_statistique import Statistics_Report_Generator


from rems.config import settings
#st.write("DB utilisée :", settings.database_url)

# -----------------------------
        # Store Mock Evaluation (Fix ForeignKeyViolation)
        # -----------------------------
from rems.models.database import Evaluation
from rems.models.session import get_session

import pandas as pd
=======
from rems.web.client import REMSClient
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d


def render():
    """Render the evaluate page."""
    st.title("🚀 Nouvelle évaluation")
    st.markdown("Lancez une évaluation sur les interactions du chatbot")

    # Check configuration
    if not check_configuration():
        return

    # Data source selection
    st.subheader("Source des données")

    source = st.radio(
        "Choisissez la source des interactions :",
        options=["Fichier JSON", "API du chatbot"],
        horizontal=True,
    )

    if source == "Fichier JSON":
        render_file_upload()
    else:
        render_api_fetch()

#DataFrame Statistic report-----------------------------------------------------------------------

def longueur_reponse_utile(texte: str) -> int:
    """
    Retourne la longueur de la partie utile d'une réponse,
    en coupant tout ce qui vient après le premier '\n\n\n'.
    """

    if "*Références" in texte:
        texte_utile = texte.split("*Références")[0]
    else:
        texte_utile = texte  # si jamais il n'y a pas de partie inutile

    # 2) On nettoie les espaces superflus
    texte_utile = texte_utile.strip()

    # 3) On retourne la longueur
    return len(texte_utile)


def load_data():
    with get_session() as session:
        evaluations = session.query(Evaluation).all()
        data = []
        for e in evaluations :
            metrics= e.metrics or {}

            if not e.results:
                continue
            for result in e.results :
                interaction = result.interaction

            row = {
                            "evaluation_id": e.id,
                            "created_at": e.created_at,
                            "overall_score": e.overall_score,
                            "retrieval_score": e.retrieval_score,
                            "generation_score": e.generation_score,

                            #métriques détaillées
                            "faithfulness": e.metrics.get("avg_faithfulness"),
                            "answer_relevancy": e.metrics.get("avg_answer_relevancy"),
                            "context_precision": e.metrics.get("avg_context_precision"),
                            "context_relevancy": e.metrics.get("avg_context_relevancy"),
                            "Taux d'hallucination": e.metrics.get("hallucination_rate"),

                            "longueur_query": len(interaction.query),
                            "longueur_response": longueur_reponse_utile(interaction.response),
                            "nb_documents_retrieves": len(interaction.retrieved_documents)
        
        }
            data.append(row)
            

    return pd.DataFrame(data)
#---------------------------------------------------------------------------------



def check_configuration() -> bool:
    """Check if the system is properly configured."""
    issues = []

    if not settings.google_api_key:
        issues.append("❌ `REMS_GOOGLE_API_KEY` non configuré")

    if issues:
        st.error("Configuration incomplète")
        for issue in issues:
            st.markdown(issue)
        st.markdown("""
        Configurez les variables d'environnement dans le fichier `.env` :
        ```
        REMS_GOOGLE_API_KEY=your-google-api-key
        REMS_DATABASE_URL=postgresql://user:pass@localhost:5432/rems
        ```
        """)
        return False

    return True


def render_file_upload():
    """Render the file upload interface."""
    st.markdown("""
    Uploadez un fichier JSON contenant les interactions à évaluer.

    **Format attendu :**
    ```json
    {
        "interactions": [
            {
                "query": "Question de l'utilisateur",
                "response": "Réponse du chatbot",
                "retrieved_documents": [
                    {"content": "Contenu du document", "source": "source.pdf"}
                ]
            }
        ]
    }
    ```
    """)

    uploaded_file = st.file_uploader(
        "Choisir un fichier JSON",
        type=["json"],
        help="Fichier contenant les interactions à évaluer"
    )

    if uploaded_file is not None:
        try:
            data = json.load(uploaded_file)
            interactions_data = data.get("interactions", data if isinstance(data, list) else [])

            st.success(f"✅ {len(interactions_data)} interactions trouvées")

            # Preview
            with st.expander("Aperçu des données"):
                st.json(interactions_data[:3])

            # Evaluation options
            render_evaluation_options(interactions_data, source="file")

        except json.JSONDecodeError as e:
            st.error(f"Erreur de parsing JSON : {e}")


def render_api_fetch():
    """Render the API fetch interface."""
    st.markdown(f"""
    Récupérez les interactions depuis l'API du chatbot.

    **URL configurée :** `{settings.chatbot_api_url}`
    """)

    col1, col2 = st.columns(2)

    with col1:
        # Date range
        default_start = datetime.now() - timedelta(days=7)
        start_date = st.date_input("Date de début", value=default_start)

    with col2:
        end_date = st.date_input("Date de fin", value=datetime.now())

    limit = st.number_input(
        "Nombre maximum d'interactions",
        min_value=10,
        max_value=1000,
        value=100,
        step=10,
    )

    if st.button("🔍 Récupérer les interactions"):
        with st.spinner("Récupération des interactions..."):
            try:
                client = REMSClient()
                result = client.collect_interactions(
                    start_date=datetime.combine(start_date, datetime.min.time()).isoformat(),
                    end_date=datetime.combine(end_date, datetime.max.time()).isoformat(),
                    limit=limit,
                    store=False  # Don't store yet, just fetch for preview
                )

                if result.get("status") == "success":
                    # For preview we might need to actually fetch them or trust the API report
                    # Since /collect returns stats, we might need a separate preview endpoint or load from storage
                    # For now, let's assume API is used to trigger, and preview is optional or handled via file
                    st.info(f"✅ {result['imported']['interactions_count']} interactions identifiées sur l'API")
                    st.session_state.fetched_via_api = True
                    st.session_state.api_params = {
                        "start_date": datetime.combine(start_date, datetime.min.time()).isoformat(),
                        "end_date": datetime.combine(end_date, datetime.max.time()).isoformat(),
                        "limit": limit
                    }
                else:
                    st.warning("Aucune interaction trouvée ou erreur API")

            except Exception as e:
                st.error(f"Erreur lors de la récupération : {e}")

    # If we have fetched interactions
    if "fetched_interactions" in st.session_state or "fetched_via_api" in st.session_state:
        if "fetched_interactions" in st.session_state:
            interactions = st.session_state.fetched_interactions
            with st.expander("Aperçu des données"):
                preview = [
                    {"query": i.query[:100], "response": i.response[:100]}
                    for i in interactions[:5]
                ]
                st.json(preview)
            render_evaluation_options(interactions, source="file")
        else:
            st.success("Prêt à lancer l'évaluation sur les interactions récupérées via API")
            render_evaluation_options(None, source="api")


def render_evaluation_options(interactions_data, source: str):
    """Render evaluation options and trigger button."""
    st.divider()
    st.subheader("Options d'évaluation")

    col1, col2 = st.columns(2)

    with col1:
        eval_name = st.text_input(
            "Nom de l'évaluation",
            value=f"Évaluation {datetime.now().strftime('%d/%m/%Y')}",
        )

    with col2:
<<<<<<< HEAD
        generate_reports = st.checkbox("Générer les rapports PDF/HTML", value=True)
        statistics_report = st.checkbox("Inclure le rapport statistique avancé", value=True)
    
=======
        st.info("💡 L'évaluation sera exécutée en arrière-plan par l'API")

>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
    # Run evaluation button
    if st.button("▶️ Lancer l'évaluation", type="primary"):
        run_evaluation_v2(
            interactions_data=interactions_data,
            source=source,
            name=eval_name,
<<<<<<< HEAD
            generate_reports=generate_reports,
            statistics_report=statistics_report,
=======
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
        )


def run_evaluation_v2(
    interactions_data,
    source: str,
    name: str,
<<<<<<< HEAD
    generate_reports: bool,
    statistics_report: bool,
=======
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
):
    """Run the evaluation process via API (asynchronous)."""
    
    client = REMSClient()
    
    with st.spinner("Envoi de la demande d'évaluation..."):
        try:
            if source == "file":
                # interactions_data is already a list of dicts from json.load
                result = client.trigger_evaluation(
                    name=name,
                    interactions=interactions_data,
                    store_results=True
                )
            else:
                # Use stored API parameters
                api_params = st.session_state.get("api_params", {})
                result = client.trigger_evaluation(
                    name=name,
                    start_date=api_params.get("start_date"),
                    end_date=api_params.get("end_date"),
                    limit=api_params.get("limit"),
                    store_results=True
                )

            if result.get("status") == "accepted":
                st.success(f"✅ Évaluation planifiée avec succès !")
                st.info(f"ID de l'évaluation : `{result.get('evaluation_id')}`")
                st.markdown(f"L'évaluation tourne actuellement en arrière-plan. Vous pourrez consulter les résultats dans l'**Historique** d'ici quelques minutes.")
                
                if st.button("Aller à l'historique"):
                    st.switch_page("pages/2_history.py")
            else:
                st.error(f"Erreur lors de la planification : {result.get('message')}")

        except Exception as e:
            st.error(f"Erreur de communication avec l'API : {e}")

<<<<<<< HEAD
    total_steps = 5 if generate_reports else 4
    if generate_reports and statistics_report :
        total_steps = 6
    elif statistics_report or generate_reports:
        total_steps = 5
    else :
        total_steps = 4

    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # -----------------------------
        # Step 1: Setup LLM
        # -----------------------------
        status_text.text("🔧 Configuration du LLM...")
        progress_bar.progress(1 / total_steps)

        llm, embeddings = setup_llm()

        # -----------------------------
        # Step 2: Run Evaluation
        # -----------------------------
        status_text.text("📊 Évaluation en cours...")
        progress_bar.progress(2 / total_steps)

        orchestrator = EvaluationOrchestrator(llm=llm, embeddings=embeddings)
        summary = orchestrator.evaluate(
            interactions=interactions,
            name=name,
            store_results=True,
        )

        # -----------------------------
        # Step 3: Generate Recommendations
        # -----------------------------
        status_text.text("💡 Génération des recommandations...")
        progress_bar.progress(3 / total_steps)

        recommendation_engine = RecommendationEngine()
        recommendations = recommendation_engine.generate_recommendations(
            summary,
            store_in_db=True,
        )
        summary.recommendations = recommendations

        yaml_path = recommendation_engine.export_to_yaml(summary, recommendations)

        # -----------------------------
        # Step 4: Generate Reports
        # -----------------------------
        if generate_reports:
            status_text.text("📄 Génération des rapports...")
            progress_bar.progress(4 / total_steps)

            report_generator = ReportGenerator()
            output_files = report_generator.generate(summary, recommendations)
        # if statistics_report:
        #     status_text.text("📈 Génération du rapport statistique avancé...")
        #     progress_bar.progress(5 / total_steps)

        #     df=load_data()

        #     st.write("Données chargées pour le rapport :")
        #     st.write(df.head())

        #     stat_report_generator = Statistics_Report_Generator(df=df)
        #     stat_output_files = stat_report_generator.generate(summary,recommendations)

        # -----------------------------
        # Complete
        # -----------------------------
        progress_bar.progress(1.0)
        status_text.text("✅ Évaluation terminée !")

        st.success("Évaluation terminée avec succès !")

        # -----------------------------
        # Show Metrics
        # -----------------------------
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Score Global", f"{summary.overall_score:.1%}")
        with col2:
            st.metric("Retrieval", f"{summary.retrieval_score:.1%}")
        with col3:
            st.metric("Génération", f"{summary.generation_score:.1%}")
        with col4:
            st.metric("Qualité", summary.quality_level.upper())

        # -----------------------------
        # Recommendations Summary
        # -----------------------------
        if recommendations:
            critical = len([r for r in recommendations if r.priority == "critical"])
            high = len([r for r in recommendations if r.priority == "high"])

            if critical > 0:
                st.error(f"⚠️ {critical} recommandation(s) critique(s) détectée(s)")
            if high > 0:
                st.warning(f"⚡ {high} recommandation(s) haute priorité")

        st.info(f"📁 Fichier YAML : `{yaml_path}`")

        if generate_reports:
            st.info(f"📁 Rapports générés dans : `{settings.reports_dir}`")

        # Clear session cache
        if "fetched_interactions" in st.session_state:
            del st.session_state.fetched_interactions

    except Exception as e:
        st.error(f"Erreur lors de l'évaluation : {e}")
        st.exception(e)


def setup_llm():
    """Set up the LangChain LLM and Embeddings for evaluation."""
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    if not settings.google_api_key:
        return None, None

    llm = ChatGoogleGenerativeAI(
        model=settings.evaluation_model,
        google_api_key=settings.google_api_key,
        temperature=0.0,    # Deterministic JSON output → fewer OutputParserExceptions
        max_retries=6,      # More retries on transient timeouts
    )
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.google_api_key,
    )

    return llm, embeddings
=======
    # Clear session cache
    if "fetched_interactions" in st.session_state:
        del st.session_state.fetched_interactions
    if "fetched_via_api" in st.session_state:
        del st.session_state.fetched_via_api
>>>>>>> 6b10b543ba67f8dd50dd88634c0095970aa0719d
