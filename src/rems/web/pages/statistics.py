import streamlit as st
import plotly.express as px
import pandas as pd
from rems.models.session import get_session
from rems.models.database import Evaluation, EvaluationResult
from rems.models.database import Interaction
import datetime
import numpy as np
import joblib
from datetime import datetime, timedelta
import uuid
import sklearn

import plotly.io as pio
pio.templates.default = "plotly_white"

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
        print("resultats evaluations:", evaluations)
        data = []
        i=0
        for e in evaluations :
            metrics= e.metrics or {}
            i+=1
            #print(f"Evaluation {e.id} - overall_score: {e.overall_score}, retrieval_score: {e.retrieval_score}, generation_score: {e.generation_score}, metrics: {metrics}")
            st.write("Evaluation:", e.id, "results:", e.results)
            print("Evaluation:", e.overall_score, e.retrieval_score, e.generation_score, e.results)
            if i>10:
                break
            if not e.results:
                continue
            for result in e.results :
                interaction = result.interaction
                # if interaction is None :
                #     continue
                i+=1
                st.write(len(e.results))
                print(f"faithfulness: {metrics.get('avg_faithfulness')}, retrieval_score: {e.retrieval_score}, answer_relevancy: {e.metrics.get('avg_answer_relevancy')}, context_precision: {e.metrics.get('avg_context_precision')}, longueur_reponse: {longueur_reponse_utile(interaction.response)}")
                st.write(f"faithfulness: {metrics.get('avg_faithfulness')}, retrieval_score: {e.retrieval_score}, answer_relevancy: {e.metrics.get('avg_answer_relevancy')}, context_precision: {e.metrics.get('avg_context_precision')}, longueur_reponse: {longueur_reponse_utile(interaction.response)}")
                if i>10:
                    break
            row = {
                            "evaluation_id": e.id,
                            "created_at": e.created_at,
                            "overall_score": e.overall_score,
                            "retrieval_score": e.retrieval_score,
                            "generation_score": e.generation_score,

                            # #métriques détaillées
                            "faithfulness": metrics.get("avg_faithfulness"),
                            "answer_relevancy": metrics.get("avg_answer_relevancy"),
                            "context_precision": metrics.get("avg_context_precision"),
                            "context_relevancy": metrics.get("avg_context_relevancy"),
                            "Taux d'hallucination": metrics.get("hallucination_rate"),

                            # "longueur_query": len(interaction.query),
                            # "longueur_response": longueur_reponse_utile(interaction.response),
                            # "nb_documents_retrieves": len(interaction.retrieved_documents)
        
        }
            data.append(row)
            

    return pd.DataFrame(data)


# def load_data():
#     with get_session() as session:
#         results = session.query(EvaluationResult).all()
#         data = []
#         i=0
#         #st.write("results:", len(results))
#         print("interactions:", session.query(EvaluationResult).count())
#         print("resultats:", results)
#         print("metrics:", )
#         for r in results:
#             interaction = r.interaction
#             if interaction is None:
#                 continue
#             i+=1
#             #st.write("Evaluation:", r.evaluation_id, "results:", len(r.interaction.results))
            
#             print(f"faithfulness: {r.faithfulness}, retrieval_score: {interaction.retrieval_score}, answer_relevancy: {r.answer_relevancy}, context_precision: {r.context_precision}, longueur_reponse: {longueur_reponse_utile(interaction.response)}")
#             if i>2:
#                 break
#             row = {
#                 "evaluation_id": r.evaluation_id,
#                 "interaction_id": r.interaction_id,

#                 # Scores RAGAS individuels
#                 "faithfulness": r.faithfulness,
#                 "answer_relevancy": r.answer_relevancy,
#                 "context_precision": r.context_precision,
#                 "context_relevancy": r.context_relevancy,
#                 "overall_score": r.overall_score,
#                 "has_hallucination": r.has_hallucination,

#                 # Variables qualitatives du prompt et de la réponse
#                 "longueur_query": len(interaction.query),
#                 "longueur_response": longueur_reponse_utile(interaction.response),
#                 "nb_documents_retrieves": len(interaction.retrieved_documents),
#             }

#             data.append(row)

#     return pd.DataFrame(data)

#uv run python -c "from rems.web.pages.statistics  import load_data; print(load_data())"

def render():
   
    st.title("Statistiques avancées")


    df = load_data()

    st.write(df.head())
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------

    # def fake_data(n=50, seed=42):

    #         np.random.seed(seed)

    #         data = []

    #         for _ in range(n):
    #             row = {
    #                 "evaluation_id": str(uuid.uuid4()),
    #                 "created_at": datetime.now() - timedelta(minutes=np.random.randint(0, 5000)),

    #                 # Scores globaux (entre 0 et 1)
    #                 "overall_score": np.round(np.random.uniform(0.4, 0.95), 3),
    #                 "retrieval_score": np.round(np.random.uniform(0.3, 0.95), 3),
    #                 "generation_score": np.round(np.random.uniform(0.4, 0.95), 3),

    #                 # Scores détaillés
    #                 "faithfulness": np.round(np.random.uniform(0.4, 0.95), 3),
    #                 "answer_relevancy": np.round(np.random.uniform(0.4, 0.95), 3),
    #                 "context_precision": np.round(np.random.uniform(0.3, 0.95), 3),
    #                 "context_relevancy": np.round(np.random.uniform(0.3, 0.95), 3),
    #                 "Taux d'hallucination": np.round(np.random.uniform(0.0, 0.3), 3),

    #                 # Features interaction
    #                 "longueur_query": np.random.randint(20, 200),
    #                 "longueur_reponse": np.random.randint(50, 500),
    #                 "nb_documents_retrieves": np.random.randint(1, 10),
    #             }

    #             data.append(row)

    #         return pd.DataFrame(data)
    
    
    
    # if df.empty:
    #     st.info("Aucune donnée réelle trouvée, utilisation de données factices pour tester les visualisations.")

        
    #     df = fake_data(50)
    #     print(df.head())





    # import csv
    # import os

    # def append_evaluation_to_csv(metrics, csv_path="src/rems/evaluation.csv"):
    #     file_exists = os.path.isfile(csv_path)

    #     with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
    #         writer = csv.DictWriter(f, fieldnames=metrics.keys())

    #         if not file_exists:
    #              st.write("Pas de fichier CSV trouvé.")

    #         writer.writerow(metrics)
    #         st.success("Métriques de l'évaluation ajoutées au fichier CSV.")
    #         st.write("Métriques ajoutées :")
    #         st.write(metrics)

    # with get_session() as session:
    #     evaluations = session.query(Evaluation).all()
    #     metrics_csv = {
    #         "faithfulness": round(evaluations[-1].metrics.get("avg_faithfulness"), 3) if evaluations else None,
    #         "retrieval_score": round(evaluations[-1].retrieval_score, 3) if evaluations else None,
    #         "answer_relevancy": round(evaluations[-1].metrics.get("avg_answer_relevancy"), 3) if evaluations else None,
    #         "context_precision": round(evaluations[-1].metrics.get("avg_context_precision"), 3) if evaluations else None,
    #     }
    # append_evaluation_to_csv(metrics_csv)
#--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Claissification de la qualité
    st.subheader("Classification de la qualité des réponses")
    
    if df.empty:
        st.info("Aucune donnée disponible pour le moment. Lancez une évaluation pour voir les visualisations.")
    else:
        
        #rom rems.diagnostic.Classifieur_qualite import classify_qualite
    
        
        #df["qualite"]= df.apply(classify_qualite , axis=1)


        classifieur_qualite = joblib.load("src/rems/diagnostic/model_rf_v1.joblib")


        y_pred = classifieur_qualite.predict(df[["faithfulness","retrieval_score","answer_relevancy", "context_precision","longueur_reponse","longueur_query","nb_documents_retrieves"]])
        
        mapping = {0: "acceptable", 1: "hallucination", 2:"retrieval_failure", 3: "low_quality", 4:"off topic"}
        y_pred = [mapping.get(pred) for pred in y_pred]
        df=df.assign(qualite=y_pred)
        
        fig = px.pie(
        df,
        names="qualite",
        title="Répartition des erreurs de qualité",
        color="qualite",
        color_discrete_sequence=px.colors.qualitative.Set2,
        )
        st.plotly_chart(fig, use_container_width=True)

        
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["day"] = df["created_at"].dt.date
        df["week"] = df["created_at"].dt.to_period("W").astype(str)
        df["month"] = df["created_at"].dt.to_period("M").astype(str)

    #--------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    #Histogramme de distribution des scores


    st.subheader("Histogramme de distribution")

    # Si df est vide, on affiche un message et on arrête la visualisation
    if df.empty:
        st.info("Aucune donnée disponible pour le moment. Lancez une évaluation pour voir les visualisations.")
    else:
        # Liste des colonnes de métriques
        metric_columns = [
            "overall_score",
            "retrieval_score",
            "generation_score",
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_relevancy",
            "Taux d'hallucination",
            "longueur_query",
            "longueur_reponse",
            "nb_documents_retrieves",
        ]

        metric = st.selectbox("Choisir une métrique", metric_columns) # Affiche un menu déroulant pour choisir la métrique à visualiser
        bins = st.slider("Nombre de bins", min_value=5, max_value=100, value=20) 
        fig = px.histogram(
            df,
            x=metric,
            nbins=bins,
            title=f"Distribution de {metric}",
            opacity=0.75,
        )

        st.plotly_chart(fig, use_container_width=True)

    #--------------------------------------------------------------------------------------------------------------------------------------------------
    # Boxplot par période

    st.subheader("Boxplot par période")

    if df.empty:
        st.info("Aucune donnée disponible pour le moment. Lancez une évaluation pour voir les visualisations.")
    else:
        period = st.selectbox("Regrouper par", ["day", "week", "month"])

        metric_columns = [
            "overall_score",
            "retrieval_score",
            "generation_score",
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_relevancy",
            "Taux d'hallucination",
            "longueur_query",
            "longueur_reponse",
            "nb_documents_retrieves",
        ]

        metric = st.selectbox("Choisir une métrique", metric_columns, key="boxplot_metric")

        fig = px.box(
            df,
            x=period,
            y=metric,
            title=f"Distribution de {metric} par {period}",
            points="all",
        )

        st.plotly_chart(fig, use_container_width=True)


#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Scatter plot pour voir les corrélations entre deux métriques
    st.subheader("Scatter plot entre deux métriques")

    if df.empty:
        st.info("Aucune donnée disponible pour le moment. Lancez une évaluation pour voir les visualisations.")
    else:
        metric_columns = [
            "overall_score",
            "retrieval_score",
            "generation_score",
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_relevancy",
            "Taux d'hallucination",
            "longueur_query",
            "longueur_reponse",
            "nb_documents_retrieves",
        ]

        default_x = "overall_score"
        default_y = "faithfulness"



        col1, col2 = st.columns(2)
        with col1:
            x_metric = st.selectbox("Axe X", metric_columns,index=metric_columns.index(default_x), key="scatter_x")
        with col2:
            y_metric = st.selectbox("Axe Y", metric_columns,index=metric_columns.index(default_y), key="scatter_y")

        if x_metric == y_metric:
            st.warning("Veuillez choisir deux métriques différentes pour le scatter plot.")
            return

        fig = px.scatter(
            df,
            x=x_metric,
            y=y_metric,
            color_continuous_scale="Viridis",
            trendline="ols", #n'éccesite la bibliothèque statsmodels qui n'est pas dans le venv par défault
            title=f"{x_metric} vs {y_metric}",
            opacity=0.8,
            size_max=15,
        )

        fig.update_layout(
            title={
                "text": f"{x_metric} vs {y_metric}",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 22}
            }
        )

        st.plotly_chart(fig, use_container_width=True)

#---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
    # Heatmap de corrélation

    st.subheader("Heatmap de corrélation")

    if df.empty:
        st.info("Aucune donnée disponible pour le moment. Lancez une évaluation pour voir les visualisations.")
    else:
        metric_columns = [
            "overall_score",
            "retrieval_score",
            "generation_score",
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_relevancy",
            "Taux d'hallucination",
            "longueur_query",
            "longueur_reponse",
            "nb_documents_retrieves",
        ]

        method = st.radio("Méthode de corrélation", ["pearson", "spearman"], horizontal=True) # Affiche des boutons radio pour choisir la méthode de corrélation

        corr = df[metric_columns].corr(method=method).round(3) # la matrice de corrélation et arrondit à 3 décimales

        fig = px.imshow(
            corr,
            text_auto=True,
            color_continuous_scale="Viridis",
            title=f"Matrice de corrélation ({method})",
            aspect="auto",
        )
        fig.update_xaxes(side="bottom")
        fig.update_yaxes(autorange="reversed") 
        fig.update_layout(
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False),
        )

        st.plotly_chart(fig, use_container_width=True)



