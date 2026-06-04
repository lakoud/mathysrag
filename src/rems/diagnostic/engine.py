"""Diagnostic Engine - Analyzes evaluation results to identify root causes."""

from dataclasses import dataclass
from enum import Enum

import structlog

from rems.config import settings
from rems.schemas import EvaluationMetrics, EvaluationSummary
import numpy as np
from sklearn.linear_model import LinearRegression



def detect_trend(values, seuil=-0.03):
# values : score des 4 dernières évaluation
# seuil : seuil à partir du quel on considère que c'est un dégradation
#entraine un model sur les au moins 4 dernières valeurs pour déterminer la tendance au fil du temps de la monotonie des performances

    if len(values) < 4:
        return None

    X = np.arange(len(values)).reshape(-1, 1)
    y = np.array(values)

    model = LinearRegression().fit(X, y)
    slope = model.coef_[0]

    return slope


def detect_anomaly(history, last_value, seuil=-2):
    if len(history) < 4:
        return None

    mean = np.mean(history)
    std = np.std(history)
    z_score = (last_value - mean) / std if std > 0 else 0

    q1 = np.percentile(history, 25)
    q3 = np.percentile(history, 75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr

    anomaly = (z_score < seuil) or (last_value < lower_bound)

    return anomaly, z_score, lower_bound

def classify_quality(score: float, thresholds: list[float]) -> int:
    for i, t in enumerate(thresholds):
        if score < t:
            return i
    return len(thresholds)


logger = structlog.get_logger()


class Component(str, Enum):
    """RAG pipeline components."""

    RETRIEVER = "retriever"
    GENERATOR = "generator"
    INDEXING = "indexing"


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DiagnosedIssue:
    """A diagnosed issue with its root cause analysis."""

    component: Component
    symptom: str
    probable_causes: list[str]
    severity: Severity
    metric_name: str
    metric_value: float
    threshold: float


# Diagnostic rules: maps symptoms to probable causes
DIAGNOSTIC_RULES = {
    "very_low_context_precision": {
        "component": Component.RETRIEVER,
        "causes": [
            "Seuil de similarité trop bas (documents non pertinents inclus)",
            "Top-K trop élevé (trop de documents récupérés)",
            "Qualité des embeddings insuffisante pour le domaine réglementaire",
        ],
    },
    "low_context_precision": {
        "component": Component.RETRIEVER,
        "causes": [
            "Seuil de similarité trop bas (documents non pertinents inclus)",
            "Top-K trop élevé (trop de documents récupérés)",
            "Qualité des embeddings insuffisante pour le domaine réglementaire",
        ],
    },

    "very_low_context_relevancy": {
        "component": Component.RETRIEVER,
        "causes": [
            "Query mal formulée ou trop vague",
            "Chunking inadapté (chunks trop grands ou trop petits)",
            "Embeddings non optimisés pour le vocabulaire juridique",
        ],
    },

    "low_context_relevancy": {
        "component": Component.RETRIEVER,
        "causes": [
            "Query mal formulée ou trop vague",
            "Chunking inadapté (chunks trop grands ou trop petits)",
            "Embeddings non optimisés pour le vocabulaire juridique",
        ],
    },
    "low_faithfulness": {
        "component": Component.GENERATOR,
        "causes": [
            "Température du LLM trop élevée (génération trop créative)",
            "Prompt système insuffisamment contraignant",
            "Contexte fourni insuffisant (top-K trop faible)",
            "Absence d'instruction explicite de ne pas inventer",
        ],
    },

    "very_low_faithfulness": {
        "component": Component.GENERATOR,
        "causes": [
            "Température du LLM trop élevée (génération trop créative)",
            "Prompt système insuffisamment contraignant",
            "Contexte fourni insuffisant (top-K trop faible)",
            "Absence d'instruction explicite de ne pas inventer",
        ],
    },
    "low_answer_relevancy": {
        "component": Component.GENERATOR,
        "causes": [
            "Prompt ne guidant pas assez vers une réponse directe",
            "LLM trop verbeux ou hors sujet",
            "Mauvaise compréhension de la question par le LLM",
        ],
    },

    "very_low_answer_relevancy": {
        "component": Component.GENERATOR,
        "causes": [
            "Prompt ne guidant pas assez vers une réponse directe",
            "LLM trop verbeux ou hors sujet",
            "Mauvaise compréhension de la question par le LLM",
        ],
    },

    "high_hallucination_rate": {
        "component": Component.GENERATOR,
        "causes": [
            "Absence de guardrails dans le prompt système",
            "Température LLM trop élevée",
            "Contexte insuffisant pour répondre (retriever défaillant)",
            "LLM non adapté au domaine réglementaire",
        ],
    },
    "degradation_trend": {
        "component": Component.GENERATOR,
        "causes":[
            "Dégradation progessive des performances",
            "Corpus viellissant ou drift du modèle"
        ],

    },
    "anomaly_detected": {
        "component":Component.GENERATOR,
        "causes":[
            "Chute soudaine des performances",
            "Mise à jour cassante",
            "Corpus corrompu"
        ],
    },
    
    "quality_class_faithfulness_0": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité faible "],
        "causes" : [
            " Performances très en dessous des seuils de qualité",
        ]
    },
    "quality_class_faithfulness_1": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité médiocre "],
        "causes" : [
            " Performances en dessous des seuils de qualité",
        ]
    },
    "quality_class_faithfulness_2": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité acceptable "],
        "causes" : [
            " Performances de bonne qualité",
        ]
    },
    "quality_class_answer_relevancy_0": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité faible "],
        "causes" : [
            " Performances dans la plage de qualité faible",
        ]
    },
    "quality_class_answer_relevancy_1": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité médiocre "],
        "causes" : [
            " Performances dans la plage de qualité médiocre",
        ]
    },
    "quality_class_answer_relevancy_2": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité acceptable "],
        "causes" : [
            " Performances dans la plage de qualité acceptable",
        ]
    },

    "quality_class_context_precision_0": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité très faible "],
        "causes" : [
            " Performances dans la plage de qualité très faible",
        ]
    },
    "quality_class_context_precision_1": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité faible "],
        "causes" : [
            " Performances dans la plage de qualité faible",
        ]
    },
    "quality_class_context_precision_2": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité médiocre "],
        "causes" : [
            " Performances dans la plage de qualité médiocre",
        ]
    },
    "quality_class_context_precision_3": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Excellente qualité "],
        "causes" : [
            " Performances dans la plage de qualité excellente",
        ]
    },
    "quality_class_context_relevancy_0": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité faible "],
        "causes" : [
            " Performances dans la plage de qualité faible",
        ]
    },
    "quality_class_context_relevancy_1": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité moyennement faible "],
        "causes" : [
            " Performances dans la plage de qualité en dessous de médiocre",
        ]
    },
    "quality_class_context_relevancy_2": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité médiocre "],
        "causes" : [
            " Performances dans la plage de qualité au dessus de médiocre",
        ]
    },
    "quality_class_context_relevancy_3": {
        "component": Component.GENERATOR,
        "niveau de qualité": ["Qualité acceptable "],
        "causes" : [
            " Performances dans la plage de bonne qualité",
        ]
    },
}



class DiagnosticEngine:
    """Analyzes evaluation results to identify root causes of issues."""

    def __init__(
        self,
        precision_threshold: float = 0.70,
        relevancy_threshold: float = 0.70,
        faithfulness_threshold: float = 0.75,
        answer_relevancy_threshold: float = 0.70,
        hallucination_rate_threshold: float = 0.10,
        quality_thresholds: dict[str, list[float]] = None
    ):
        """
        Initialize the diagnostic engine with thresholds.

        Args:
            precision_threshold: Minimum acceptable context precision
            relevancy_threshold: Minimum acceptable context relevancy
            faithfulness_threshold: Minimum acceptable faithfulness
            answer_relevancy_threshold: Minimum acceptable answer relevancy
            hallucination_rate_threshold: Maximum acceptable hallucination rate
            quality_thresholds: List of 5 thresholds derived from clustering
        """
        self.thresholds = {
            "context_precision": precision_threshold,
            "context_relevancy": relevancy_threshold,
            "faithfulness": faithfulness_threshold,
            "answer_relevancy": answer_relevancy_threshold,
            "hallucination_rate": hallucination_rate_threshold,
        }
        
        # clustering thresholds
        if quality_thresholds is None:
            quality_thresholds = {
                "faithfulness": [0.1406, 0.8818],
                "answer_relevancy": [0.1916, 0.7891],
                "context_precision": [0.0777,0.5212, 0.9324],
                "context_relevancy": [0.25, 0.625, 0.875],
            }
        self.quality_thresholds = quality_thresholds

    def diagnose(self, summary: EvaluationSummary,history: dict[str, list[float]]={"faithfulness": [0],"answer_relevancy": [0],"context_precision": [0]}) -> list[DiagnosedIssue]:
        """
        Analyze evaluation summary and diagnose issues.

        Args:
            summary: Evaluation summary with metrics

        Returns:
            List of diagnosed issues with root cause analysis
        """
        issues: list[DiagnosedIssue] = []
        metrics = summary.metrics

        # Check context precision
        if metrics.avg_context_precision is not None:
            if metrics.avg_context_precision < self.thresholds["context_precision"]:
                issues.append(self._create_issue(
                    rule_key="low_context_precision",
                    metric_name="context_precision",
                    metric_value=metrics.avg_context_precision,
                    threshold=self.thresholds["context_precision"],
                ))

        # Check context relevancy
        if metrics.avg_context_relevancy is not None:
            if metrics.avg_context_relevancy < self.thresholds["context_relevancy"]:
                issues.append(self._create_issue(
                    rule_key="low_context_relevancy",
                    metric_name="context_relevancy",
                    metric_value=metrics.avg_context_relevancy,
                    threshold=self.thresholds["context_relevancy"],
                ))

        # Check faithfulness
        if metrics.avg_faithfulness is not None:
            if metrics.avg_faithfulness < self.thresholds["faithfulness"]:
                issues.append(self._create_issue(
                    rule_key="low_faithfulness",
                    metric_name="faithfulness",
                    metric_value=metrics.avg_faithfulness,
                    threshold=self.thresholds["faithfulness"],
                ))

        # Check answer relevancy
        if metrics.avg_answer_relevancy is not None:
            if metrics.avg_answer_relevancy < self.thresholds["answer_relevancy"]:
                issues.append(self._create_issue(
                    rule_key="low_answer_relevancy",
                    metric_name="answer_relevancy",
                    metric_value=metrics.avg_answer_relevancy,
                    threshold=self.thresholds["answer_relevancy"],
                ))

        # Check hallucination rate
        if metrics.hallucination_rate is not None:
            if metrics.hallucination_rate > self.thresholds["hallucination_rate"]:
                issues.append(self._create_issue(
                    rule_key="high_hallucination_rate",
                    metric_name="hallucination_rate",
                    metric_value=metrics.hallucination_rate,
                    threshold=self.thresholds["hallucination_rate"],
                    is_upper_bound=True,
                ))

        # --- Trend detection (4 dernières valeurs)
        for metric_name in ["faithfulness", "answer_relevancy", "context_precision", "context_relevancy"]:
            if metric_name in history and len(history[metric_name]) >= 4:
                last_4 = history[metric_name][-4:]
                slope = detect_trend(last_4)

                if slope is not None and slope < -0.03:  # seuil configurable
                    issues.append(self._create_issue(
                        rule_key="degradation_trend",
                        metric_name=metric_name,
                        metric_value=slope,
                        threshold=-0.02
                    ))

        # --- Anomaly detection ---
        for metric_name in ["faithfulness", "answer_relevancy", "context_precision", "context_relevancy"]:
            if metric_name in history and len(history[metric_name]) >= 4:
                last_value = history[metric_name][-1]
                anomaly = detect_anomaly(history[metric_name][:-1], last_value)

                if anomaly is not None:
                    is_anomaly, z, lower_bound = anomaly
                    if is_anomaly:
                        issues.append(self._create_issue(
                            rule_key="anomaly_detected",
                            metric_name=metric_name,
                            metric_value=last_value,
                            threshold=lower_bound
                        ))

        # --- Quality classification ---
        if self.quality_thresholds:
            metric_map = {
                "faithfulness": metrics.avg_faithfulness,
                "answer_relevancy": metrics.avg_answer_relevancy,
                "context_precision": metrics.avg_context_precision,
                "context_relevancy": metrics.avg_context_relevancy,
            }
            for metric_name, value in metric_map.items():
                if value is None:
                    continue

                thresholds = self.quality_thresholds.get(metric_name)
                if thresholds is None:
                    continue

                quality_class = classify_quality(value, thresholds)
                rule_key = f"quality_class_{metric_name}_{quality_class}"

                issues.append(self._create_issue(
                    rule_key=rule_key,
                    metric_name=metric_name,
                    metric_value=value,
                    threshold=thresholds[quality_class] if quality_class < len(thresholds) else thresholds[-1],
                ))

        # Sort by severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }
        issues.sort(key=lambda x: severity_order[x.severity])

        logger.info(
            "Diagnostic complete",
            issues_found=len(issues),
            critical_count=len([i for i in issues if i.severity == Severity.CRITICAL]),
            high_count=len([i for i in issues if i.severity == Severity.HIGH]),
        )

        return issues

    def _create_issue(
        self,
        rule_key: str,
        metric_name: str,
        metric_value: float,
        threshold: float,
        is_upper_bound: bool = False,
        list_thresholds: bool = False,
    ) -> DiagnosedIssue:
        """Create a diagnosed issue from a rule."""
        rule = DIAGNOSTIC_RULES[rule_key]

        # Calculate severity based on how far from threshold
        if is_upper_bound:
            # For metrics where exceeding threshold is bad (e.g., hallucination rate)
            deviation = (metric_value - threshold) / threshold if threshold > 0 else metric_value
        else:
            # For metrics where being below threshold is bad
            deviation = (threshold - metric_value) / threshold if threshold > 0 else 1 - metric_value

        if deviation > 0.5:
            severity = Severity.CRITICAL
        elif deviation > 0.25:
            severity = Severity.HIGH
        elif deviation > 0.1:
            severity = Severity.MEDIUM
        else:
            severity = Severity.LOW

        if list_thresholds:
            quality_class = classify_quality(metric_value, self.quality_thresholds.get(metric_name))
            if quality_class == 0:
                severity = Severity.CRITICAL
            elif quality_class == 1:
                severity = Severity.HIGH
            elif quality_class == 2 and metric_name != "faithfulness" and metric_name != "answer_relevancy":
                severity = Severity.MEDIUM
            else:
                severity = Severity.LOW


        # Create symptom description

        if list_thresholds:
            if severity == Severity.CRITICAL:
                symptom = symptom = f"{metric_name} trop faible: {metric_value:.2%} (seuil: {threshold:.2%})"
            elif severity == Severity.HIGH:
                symptom = f"{metric_name} trop faible: {metric_value:.2%} (seuil: {threshold:.2%})"
            elif severity == Severity.MEDIUM:
                symptom = f"{metric_name}  faible: {metric_value:.2%} (seuil: {threshold:.2%})"
            else:
                symptom = f"{metric_name} acceptable: {metric_value:.2%} (dernierseuil: {threshold:.2%})"
                
        if not list_thresholds:
            if is_upper_bound:
                symptom = f"{metric_name} trop élevé: {metric_value:.2%} (seuil: {threshold:.2%})"
            else:
                symptom = f"{metric_name} trop faible: {metric_value:.2%} (seuil: {threshold:.2%})"

        return DiagnosedIssue(
            component=rule["component"],
            symptom=symptom,
            probable_causes=rule["causes"],
            severity=severity,
            metric_name=metric_name,
            metric_value=metric_value,
            threshold=threshold,
        )

    def get_component_health(self, summary: EvaluationSummary) -> dict[str, str]:
        """
        Get health status for each component.

        Returns:
            Dictionary mapping component name to health status
        """
        issues = self.diagnose(summary)

        # Count issues per component
        component_issues: dict[Component, list[DiagnosedIssue]] = {}
        for issue in issues:
            if issue.component not in component_issues:
                component_issues[issue.component] = []
            component_issues[issue.component].append(issue)

        # Determine health status
        health: dict[str, str] = {}

        for component in Component:
            comp_issues = component_issues.get(component, [])
            if not comp_issues:
                health[component.value] = "healthy"
            elif any(i.severity == Severity.CRITICAL for i in comp_issues):
                health[component.value] = "critical"
            elif any(i.severity == Severity.HIGH for i in comp_issues):
                health[component.value] = "degraded"
            else:
                health[component.value] = "warning"

        return health
