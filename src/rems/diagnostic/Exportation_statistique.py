import numpy as np
import pandas as pd
from rems.web.pages.statistics import load_data
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
from sklearn.decomposition import PCA
from matplotlib import pyplot as plt
import base64
from io import BytesIO
import seaborn as sns
from datetime import datetime

import streamlit as st
from rems.models.database import Evaluation
from rems.models.session import get_session
from rems.models.database import Interaction

import structlog

from jinja2 import Environment, PackageLoader, select_autoescape
from rems.config import settings

logger = structlog.get_logger()



class Statistics_Report_Generator:
    def __init__(self, output_dir=None, df=None):
        self.output_dir = output_dir or settings.reports_dir
        self.env = Environment(
            loader=PackageLoader("rems.reports", "templates"),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self.pdf_available = self._check_pdf_stability()
        self.df = df
        

    
    
    def _check_pdf_stability(self) -> bool:
        """Run a 'canary' test in a subprocess to check if WeasyPrint crashes on Windows."""
        import subprocess
        import sys
        
        # Simple script to test weasyprint (careful with syntax for -c)
        check_script = "import sys\n" \
                      "try:\n" \
                      "    from weasyprint import HTML\n" \
                      "    HTML(string='<h1>Test</h1>').write_pdf(target=None)\n" \
                      "    print('OK')\n" \
                      "except Exception as e:\n" \
                      "    print(f'ERROR: {e}')\n" \
                      "    sys.exit(1)"
        
        try:
            # Run the script in a separate process to avoid crashing the main app
            result = subprocess.run(
                [sys.executable, "-c", check_script],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0 and "OK" in result.stdout:
                return True
            else:
                logger.warning(
                    "PDF generation disabled: WeasyPrint failed stability check",
                    returncode=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    tip="This is a safety measure to prevent the application from crashing. "
                        "On Windows, you likely need to install GTK+ (e.g. via 'gvsbuild' or a standalone installer)."
                )
                return False
        except Exception as e:
            logger.warning("PDF generation disabled: WeasyPrint stability check failed", error=str(e))
            return False
            


    #Corrélations--------------------------------------------------------------

    def _calculate_correlations(self, columns: list[str]):
        st.write(self.df.head())
        df_subset = self.df[columns].dropna()
        return {
            "pearson": df_subset.corr(method="pearson"),
            "spearman": df_subset.corr(method="spearman"),
        }


    #Régressions ---------------------------------------------------------------

    def _regression(self, features: list[str], target: str):
        X = self.df[features].dropna()
        y = self.df.loc[X.index, target]

        X_const = sm.add_constant(X)
        model = sm.OLS(y, X_const).fit()
        return {
            "model": model,
            "coefficients": model.summary2().tables[1],
            "p_values": model.pvalues,
            "r_squared": model.rsquared,
        }

    #ACP------------------------------------------------------------------------

    def _perform_pca(self, features: list[str]):
        X = self.df[features].dropna()
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        pca = PCA()
        pca.fit(X_scaled)
        features_pca = pca.transform(X_scaled)
        cumsum=np.cumsum(pca.explained_variance_ratio_)

        fig = plt.figure(figsize=(16, 9))
        x_values=range (1, pca.n_components_ + 1)
        plt.plot(x_values, cumsum, "o-")
        plt.xlabel("Composante principale")
        plt.ylabel("Taux de variance expliquée cumulée")
        plt.title("Taux de variance expliquée cumulée par les composantes principales")
        plt.grid(True,alpha=0.3)

        return {
            "fig": fig,
            "pca": pca,
            "features_pca": features_pca,
            "explained_variance_ratio": pca.explained_variance_ratio_,
            "cumulative_explained_variance": cumsum,
        }

    def fig_to_base64(fig):
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")


    # corr=calculate_correlations(df,["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"])
    # reg=regression(df,["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"],"overall_score")
    # pca_res=perform_pca(df,["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"])


    # figures = {
    #     "corr_pearson": fig_to_base64(fig_corr_pear.get_figure()),
    #     "corr_spearman": fig_to_base64(fig_corr_spear.get_figure()),
    #     "pca": fig_to_base64(fig_pca),
    # }


    def generate(self, df, formats=None):
        formats = formats or ["pdf", "html"]
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"statistics_report_{timestamp}"

        # 1. Calculs
        correlations = self._calculate_correlations(["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"])
        linreg = self._regression(["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"], "overall_score")
        pca_res = self._perform_pca(["faithfulness","answer_relevancy","context_precision","retrieval_score","longueur_reponse","longueur_query","nb_documents_retrieves"])

        fig_corr_pear=sns.heatmap(correlations["pearson"], annot=True, cmap="viridis", fmt=".3f", title="Matrice de corrélation (Pearson)")
        fig_corr_spear=sns.heatmap(correlations["spearman"], annot=True, cmap="viridis", fmt=".3f", title="Matrice de corrélation (Spearman)")
        fig_pca=pca_res["fig"]


        # 2. Figures
        figs = {
            "corr_pearson": fig_corr_pear.fig_to_base64(),
            "corr_spearman": fig_corr_spear.fig_to_base64(),
            "pca": fig_pca.fig_to_base64(),
        }

        # 3. Contexte
        context = {
            "title": "Rapport Statistiques Avancées",
            "generated_at": datetime.now(),
            "correlations": correlations,
            "regressions": linreg,
            "pca": pca_res,
            "figures": figs,
            "df_head": df.head(20).to_html(),
        }

        # 4. Export
        output_files = {}

        if "html" in formats:
            html_path = self.output_dir / f"{base_name}.html"
            self._generate_html(context, html_path)
            output_files["html"] = html_path

        if "pdf" in formats:
            pdf_path = self.output_dir / f"{base_name}.pdf"
            self._generate_pdf(context, pdf_path)
            output_files["pdf"] = pdf_path

        return output_files