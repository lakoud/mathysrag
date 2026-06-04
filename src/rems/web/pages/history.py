"""History page - View past evaluations and trends."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml

from rems.config import settings
from rems.web.client import REMSClient




def render():
    """Render the history page."""
    st.title("📜 Historique des évaluations")

    # Get all evaluations
    evaluations = get_all_evaluations()

    if not evaluations:
        st.warning("Aucune évaluation disponible.")
        return

    # Trend chart
    st.subheader("Évolution des scores")
    render_trend_chart(evaluations)

    st.divider()

    # Evaluation list
    st.subheader("Liste des évaluations")
    render_evaluation_list(evaluations)

    # Selected evaluation details
    if "selected_evaluation_id" in st.session_state:
        st.divider()
        render_evaluation_details(st.session_state.selected_evaluation_id)


def get_all_evaluations() -> list[dict]:
    """Get all evaluations from the API."""
    client = REMSClient()
    return client.get_evaluations(limit=100)


def get_evaluation_by_id(evaluation_id: str) -> dict | None:
    """Get a specific evaluation by ID from the API."""
    client = REMSClient()
    return client.get_evaluation_details(evaluation_id)


def render_trend_chart(evaluations: list[dict]):
    """Render the score trend chart."""
    # Prepare data
    data = []
    for eval in reversed(evaluations):  # Chronological order
        date_val = eval.get("evaluation_date")
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val)
            
        data.append({
            "Date": date_val,
            "Score Global": (eval.get("overall_score") or 0) * 100,
            "Retrieval": (eval.get("retrieval_score") or 0) * 100,
            "Génération": (eval.get("generation_score") or 0) * 100,
        })

    df = pd.DataFrame(data)

    if len(df) > 1:
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["Score Global"],
            name="Score Global",
            line=dict(color="#3498db", width=3),
            mode="lines+markers",
        ))

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["Retrieval"],
            name="Retrieval",
            line=dict(color="#2ecc71", width=2, dash="dash"),
            mode="lines+markers",
        ))

        fig.add_trace(go.Scatter(
            x=df["Date"],
            y=df["Génération"],
            name="Génération",
            line=dict(color="#9b59b6", width=2, dash="dash"),
            mode="lines+markers",
        ))

        # Add threshold line
        fig.add_hline(
            y=75,
            line_dash="dot",
            line_color="orange",
            annotation_text="Seuil acceptable (75%)",
        )

        fig.update_layout(
            height=350,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(range=[0, 100], title="Score (%)"),
            xaxis=dict(title="Date"),
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas assez de données pour afficher les tendances. Au moins 2 évaluations sont nécessaires.")


def render_evaluation_list(evaluations: list[dict]):
    """Render the list of evaluations."""
    # Create dataframe for display
    data = []
    for eval in evaluations:
        metrics = eval.get("metrics") or {}
        date_val = eval.get("evaluation_date")
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val)
            
        data.append({
            "id": eval.get("evaluation_id"),
            "Date": date_val.strftime("%d/%m/%Y %H:%M") if date_val else "-",
            "Nom": eval.get("name") or "-",
            "Interactions": eval.get("interaction_count", 0),
            "Score Global": f"{(eval.get('overall_score') or 0):.1%}",
            "Retrieval": f"{(eval.get('retrieval_score') or 0):.1%}",
            "Génération": f"{(eval.get('generation_score') or 0):.1%}",
            "Hallucinations": f"{(metrics.get('hallucination_rate', 0)):.1%}",
            "Recommandations": len(eval.get("recommendations") or []),
        })

    df = pd.DataFrame(data)

    # Display as interactive table
    for idx, row in df.iterrows():
        col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])

        with col1:
            st.markdown(f"**{row['Date']}** - {row['Nom']}")
        with col2:
            st.text(f"📊 {row['Score Global']}")
        with col3:
            st.text(f"🔍 {row['Retrieval']}")
        with col4:
            st.text(f"🤖 {row['Génération']}")
        with col5:
            st.text(f"👁 {row['Interactions']} int.")
        with col6:
            if st.button("Voir détails", key=f"detail_{row['id']}"):
                st.session_state.selected_evaluation_id = row["id"]
                st.rerun()


def render_evaluation_details(evaluation_id: str):
    """Render detailed view of a specific evaluation."""
    evaluation = get_evaluation_by_id(evaluation_id)

    if not evaluation:
        st.error("Évaluation non trouvée.")
        return

    date_val = evaluation.get("evaluation_date")
    if isinstance(date_val, str):
        try:
            date_str = datetime.fromisoformat(date_val.replace("Z", "+00:00")).strftime('%d/%m/%Y %H:%M')
        except ValueError:
            date_str = date_val
    elif date_val:
        date_str = date_val.strftime('%d/%m/%Y %H:%M')
    else:
        date_str = "-"

    st.subheader(f"Détails - {date_str}")

    # Close button
    if st.button("✖ Fermer"):
        del st.session_state.selected_evaluation_id
        st.rerun()

    # Tabs for different sections
    tab1, tab2, tab3 = st.tabs(["📈 Métriques", "💡 Recommandations", "📥 Exports"])

    with tab1:
        render_metrics_tab(evaluation)

    with tab2:
        render_recommendations_tab(evaluation)

    with tab3:
        render_exports_tab(evaluation)


def render_metrics_tab(evaluation: dict):
    """Render the metrics tab."""
    metrics = evaluation.get("metrics") or {}

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Score Global", f"{(evaluation.get('overall_score') or 0):.1%}")
    with col2:
        st.metric("Retrieval", f"{(evaluation.get('retrieval_score') or 0):.1%}")
    with col3:
        st.metric("Génération", f"{(evaluation.get('generation_score') or 0):.1%}")
    with col4:
        hall_rate = metrics.get("hallucination_rate", 0)
        st.metric(
            "Hallucinations",
            f"{hall_rate:.1%}",
            delta=f"{metrics.get('total_hallucinations', 0)} cas",
            delta_color="inverse" if hall_rate > 0.1 else "normal"
        )

    st.markdown("---")

    # Detailed metrics
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Métriques Retrieval**")
        st.json({
            "Context Precision": metrics.get("avg_context_precision"),
            "Context Relevancy": metrics.get("avg_context_relevancy"),
        })

    with col2:
        st.markdown("**Métriques Génération**")
        st.json({
            "Faithfulness": metrics.get("avg_faithfulness"),
            "Answer Relevancy": metrics.get("avg_answer_relevancy"),
        })

    # Score distribution
    if metrics.get("score_distribution"):
        st.markdown("**Distribution des scores**")
        dist = metrics["score_distribution"]
        fig = px.pie(
            names=list(dist.keys()),
            values=list(dist.values()),
            color=list(dist.keys()),
            color_discrete_map={
                "excellent": "#28a745",
                "good": "#20c997",
                "acceptable": "#ffc107",
                "poor": "#fd7e14",
                "critical": "#dc3545",
            },
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)


def render_recommendations_tab(evaluation: dict):
    """Render the recommendations tab."""
    recommendations = evaluation.get("recommendations") or []

    if not recommendations:
        st.success("Aucune recommandation - Le système fonctionne correctement !")
        return

    # Group by priority
    priority_order = ["critical", "high", "medium", "low"]
    priority_labels = {
        "critical": ("🔴 Critique", "error"),
        "high": ("🟠 Haute", "warning"),
        "medium": ("🟡 Moyenne", "info"),
        "low": ("🟢 Basse", "success"),
    }

    for priority in priority_order:
        recs = [r for r in recommendations if r.get("priority") == priority]
        if recs:
            label, msg_type = priority_labels[priority]
            st.markdown(f"### {label} ({len(recs)})")

            for rec in recs:
                with st.expander(f"[{rec.get('component', '').upper()}] {rec.get('suggestion', '')[:100]}..."):
                    st.markdown(f"**Problème détecté:**\n{rec.get('issue')}")
                    st.markdown(f"**Suggestion:**\n{rec.get('suggestion')}")

                    if rec.get("parameter_adjustments"):
                        st.markdown("**Paramètres à ajuster:**")
                        st.json(rec.get("parameter_adjustments"))


def render_exports_tab(evaluation: dict):
    """Render the exports tab."""
    st.markdown("### Télécharger les exports")

    col1, col2 = st.columns(2)

    with col1:
        # Generate YAML content
        yaml_content = generate_yaml_export(evaluation)
        date_val = evaluation.get("evaluation_date")
        if isinstance(date_val, str):
            date_val = datetime.fromisoformat(date_val)
        
        st.download_button(
            label="📄 Télécharger YAML",
            data=yaml_content,
            file_name=f"recommendations_{date_val.strftime('%Y%m%d') if date_val else 'export'}.yaml",
            mime="text/yaml",
        )

    with col2:
        # Check if PDF/HTML reports exist
        st.markdown("**Rapports complets**")
        
        client = REMSClient()
        eval_id = evaluation.get("evaluation_id")
        
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            if st.button("📄 HTML", key=f"hist_html_{eval_id}"):
                with st.spinner("Génération..."):
                    content = client.get_report(eval_id, "html")
                    if content:
                        st.download_button(
                            "Télécharger HTML", 
                            content, 
                            file_name=f"report_{eval_id[:8]}.html", 
                            mime="text/html",
                            key=f"dl_hist_html_{eval_id}"
                        )
                    else:
                        st.error("Erreur")
        
        with r_col2:
            if st.button("📕 PDF", key=f"hist_pdf_{eval_id}"):
                with st.spinner("Génération..."):
                    content = client.get_report(eval_id, "pdf")
                    if content:
                        st.download_button(
                            "Télécharger PDF", 
                            content, 
                            file_name=f"report_{eval_id[:8]}.pdf", 
                            mime="application/pdf",
                            key=f"dl_hist_pdf_{eval_id}"
                        )
                    else:
                        st.warning("Indisponible")

    # Show YAML preview
    st.markdown("### Aperçu du fichier YAML")
    st.code(yaml_content, language="yaml")


def generate_yaml_export(evaluation: dict) -> str:
    """Generate YAML export for an evaluation."""
    metrics = evaluation.get("metrics") or {}
    
    date_val = evaluation.get("evaluation_date")
    if isinstance(date_val, str):
        date_val = datetime.fromisoformat(date_val)

    data = {
        "evaluation_id": evaluation.get("evaluation_id"),
        "evaluation_date": date_val.isoformat() if date_val else None,
        "overall_score": round(evaluation.get("overall_score") or 0, 3),
        "quality_level": evaluation.get("quality_level", "unknown"),
        "scores": {
            "retrieval": round(evaluation.get("retrieval_score") or 0, 3),
            "generation": round(evaluation.get("generation_score") or 0, 3),
        },
        "metrics": {
            "avg_context_precision": metrics.get("avg_context_precision"),
            "avg_context_relevancy": metrics.get("avg_context_relevancy"),
            "avg_faithfulness": metrics.get("avg_faithfulness"),
            "avg_answer_relevancy": metrics.get("avg_answer_relevancy"),
            "hallucination_rate": metrics.get("hallucination_rate"),
            "total_hallucinations": metrics.get("total_hallucinations", 0),
        },
        "recommendations": [
            {
                "component": rec.get("component"),
                "priority": rec.get("priority"),
                "issue": rec.get("issue"),
                "suggestion": rec.get("suggestion"),
                "parameter_adjustments": rec.get("parameter_adjustments"),
            }
            for rec in (evaluation.get("recommendations") or [])
        ],
    }

    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_quality_level(score: float) -> str:
    """Determine quality level from score."""
    if score >= 0.90:
        return "excellent"
    elif score >= 0.75:
        return "good"
    elif score >= 0.60:
        return "acceptable"
    elif score >= 0.40:
        return "poor"
    else:
        return "critical"
