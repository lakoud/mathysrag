"""Dashboard page - Overview of the latest evaluation."""

from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from rems.web.client import REMSClient


def render():
    """Render the dashboard page."""
    st.title("📊 Dashboard")
    st.markdown("Vue d'ensemble de la dernière évaluation")

    # Get the latest evaluation
    latest_eval = get_latest_evaluation()

    if latest_eval is None:
        st.warning("Aucune évaluation disponible. Lancez une première évaluation.")
        return

    # Header with evaluation info
    col1, col2, col3 = st.columns(3)
    with col1:
        # Check if created_at is a string or datetime
        date_val = latest_eval.get("evaluation_date")
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val)
        st.metric("Date d'évaluation", date_val.strftime("%d/%m/%Y") if date_val else "-")
    with col2:
        st.metric("Interactions analysées", latest_eval.get("interaction_count", 0))
    with col3:
        quality_level = latest_eval.get("quality_level", "unknown")
        st.metric("Niveau de qualité", quality_level.upper())

    st.divider()

    # Main score card
    render_score_overview(latest_eval)

    st.divider()

    # Component scores
    st.subheader("Scores par composant")
    render_component_scores(latest_eval)

    st.divider()

    # Diagnostics
    st.subheader("🔍 Diagnostics du système")
    render_diagnostics(latest_eval["evaluation_id"])

    st.divider()

    # Detailed metrics
    st.subheader("Métriques détaillées")
    render_detailed_metrics(latest_eval)
    
    st.divider()

    # Recommendations summary
    st.subheader("💡 Recommandations prioritaires")
    render_recommendations_summary(latest_eval)

    st.divider()

    # Reports
    st.subheader("📄 Rapport d'évaluation")
    render_report_download(latest_eval["evaluation_id"])


def get_latest_evaluation() -> dict | None:
    """Get the most recent evaluation from the API."""
    client = REMSClient()
    evaluations = client.get_evaluations(limit=1)
    if evaluations:
        # Fetch full details for the latest evaluation
        return client.get_evaluation_details(evaluations[0]["evaluation_id"])
    return None


def get_quality_level(score: float) -> str:
    """Determine quality level from score."""
    # This is now handled by the API, but keeping the logic for safety or local use if needed
    if score >= 0.90:
        return "excellent"
    elif score >= 0.75:
        return "bon"
    elif score >= 0.60:
        return "acceptable"
    elif score >= 0.40:
        return "faible"
    else:
        return "critique"


def get_quality_color(score: float) -> str:
    """Get color for quality level."""
    if score >= 0.90:
        return "#28a745"
    elif score >= 0.75:
        return "#20c997"
    elif score >= 0.60:
        return "#ffc107"
    elif score >= 0.40:
        return "#fd7e14"
    else:
        return "#dc3545"


def render_score_overview(evaluation: dict):
    """Render the main score overview."""
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        score = evaluation.get("overall_score") or 0
        color = get_quality_color(score)

        # Create gauge chart
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score * 100,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Score Global", 'font': {'size': 24}},
            number={'suffix': "%", 'font': {'size': 48}},
            gauge={
                'axis': {'range': [0, 100], 'tickwidth': 1},
                'bar': {'color': color},
                'bgcolor': "white",
                'borderwidth': 2,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 40], 'color': '#ffebee'},
                    {'range': [40, 60], 'color': '#fff3e0'},
                    {'range': [60, 75], 'color': '#fffde7'},
                    {'range': [75, 90], 'color': '#e8f5e9'},
                    {'range': [90, 100], 'color': '#c8e6c9'},
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 75
                }
            }
        ))

        fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20))
        st.plotly_chart(fig, use_container_width=True)


def render_component_scores(evaluation: dict):
    """Render component score cards."""
    col1, col2 = st.columns(2)

    with col1:
        retrieval_score = evaluation.get("retrieval_score") or 0
        delta = None  # TODO: Calculate delta from previous evaluation

        st.metric(
            "🔍 Retrieval",
            f"{retrieval_score:.1%}",
            delta=delta,
            help="Qualité de la récupération des documents (context precision + relevancy)"
        )

        # Progress bar
        st.progress(retrieval_score)

    with col2:
        generation_score = evaluation.get("generation_score") or 0

        st.metric(
            "🤖 Génération",
            f"{generation_score:.1%}",
            delta=None,
            help="Qualité de la génération (faithfulness + answer relevancy)"
        )

        st.progress(generation_score)


def render_detailed_metrics(evaluation: dict):
    """Render detailed metrics table."""
    metrics = evaluation.get("metrics") or {}

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Retrieval**")
        metrics_data = {
            "Context Precision": metrics.get("avg_context_precision"),
            "Context Relevancy": metrics.get("avg_context_relevancy"),
        }
        for name, value in metrics_data.items():
            if value is not None:
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.text(name)
                with col_b:
                    st.text(f"{value:.1%}")

    with col2:
        st.markdown("**Génération**")
        metrics_data = {
            "Faithfulness": metrics.get("avg_faithfulness"),
            "Answer Relevancy": metrics.get("avg_answer_relevancy"),
            "Taux d'hallucination": metrics.get("hallucination_rate"),
        }
        for name, value in metrics_data.items():
            if value is not None:
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.text(name)
                with col_b:
                    color = "red" if name == "Taux d'hallucination" and value > 0.1 else "inherit"
                    st.markdown(f"<span style='color:{color}'>{value:.1%}</span>", unsafe_allow_html=True)

    # Score distribution chart
    if metrics.get("score_distribution"):
        st.markdown("**Distribution des scores**")
        dist = metrics["score_distribution"]

        fig = px.bar(
            x=list(dist.keys()),
            y=list(dist.values()),
            color=list(dist.keys()),
            color_discrete_map={
                "excellent": "#28a745",
                "good": "#20c997",
                "acceptable": "#ffc107",
                "poor": "#fd7e14",
                "critical": "#dc3545",
            },
            labels={"x": "Niveau", "y": "Nombre d'interactions"},
        )
        fig.update_layout(showlegend=False, height=250)
        st.plotly_chart(fig, use_container_width=True)


def render_recommendations_summary(evaluation: dict):
    """Render a summary of top recommendations."""
    recommendations = evaluation.get("recommendations") or []

    if not recommendations:
        st.success("Aucune recommandation - Le système fonctionne correctement !")
        return

    # Count by priority
    critical = [r for r in recommendations if r.get("priority") == "critical"]
    high = [r for r in recommendations if r.get("priority") == "high"]

    if critical:
        st.error(f"⚠️ {len(critical)} recommandation(s) critique(s)")
        for rec in critical[:2]:
            with st.expander(f"🔴 [{rec.get('component', '').upper()}] {rec.get('suggestion', '')[:80]}..."):
                st.markdown(f"**Problème:** {rec.get('issue')}")
                st.markdown(f"**Suggestion:** {rec.get('suggestion')}")

    if high:
        st.warning(f"⚡ {len(high)} recommandation(s) haute priorité")
        for rec in high[:2]:
            with st.expander(f"🟠 [{rec.get('component', '').upper()}] {rec.get('suggestion', '')[:80]}..."):
                st.markdown(f"**Problème:** {rec.get('issue')}")
                st.markdown(f"**Suggestion:** {rec.get('suggestion')}")


def render_diagnostics(evaluation_id: str):
    """Render diagnostic issues for the current evaluation."""
    client = REMSClient()
    # For the dashboard, we show all diagnostics related to this evaluation's timeframe if possible, 
    # but the API allows filtering. Let's just get the latest ones.
    diagnostics = client.get_diagnostics(limit=20)
    
    # Filter for this evaluation_id if the API returns it
    eval_diagnostics = [d for d in diagnostics if d.get("evaluation_id") == evaluation_id]
    
    if not eval_diagnostics:
        st.info("Aucune anomalie détectée par le moteur de diagnostic.")
        return

    for diag in eval_diagnostics:
        severity = diag.get("severity", "info")
        icon = "🔴" if severity == "critical" else "🟠" if severity == "high" else "🟡"
        
        with st.expander(f"{icon} [{diag.get('component', '').upper()}] {diag.get('symptom')}"):
            st.markdown(f"**Métrique:** {diag.get('metric_name')} = `{diag.get('metric_value'):.2f}` (seuil: {diag.get('threshold'):.2f})")
            st.markdown("**Causes probables :**")
            for cause in diag.get("probable_causes", []):
                st.markdown(f"- {cause}")


def render_report_download(evaluation_id: str):
    """Render download buttons for reports."""
    client = REMSClient()
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Générer Rapport HTML"):
            with st.spinner("Génération du rapport HTML..."):
                report_content = client.get_report(evaluation_id, "html")
                if report_content:
                    st.download_button(
                        label="💾 Télécharger HTML",
                        data=report_content,
                        file_name=f"report_{evaluation_id[:8]}.html",
                        mime="text/html",
                        key="dl_html"
                    )
                else:
                    st.error("Erreur lors de la génération du rapport.")

    with col2:
        if st.button("📥 Générer Rapport PDF"):
            with st.spinner("Génération du rapport PDF..."):
                report_content = client.get_report(evaluation_id, "pdf")
                if report_content:
                    st.download_button(
                        label="💾 Télécharger PDF",
                        data=report_content,
                        file_name=f"report_{evaluation_id[:8]}.pdf",
                        mime="application/pdf",
                        key="dl_pdf"
                    )
                else:
                    st.warning("Génération PDF indisponible ou erreur. Vérifiez WeasyPrint sur le serveur.")
