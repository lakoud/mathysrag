"""API Client for the REMS dashboard."""

import httpx
import structlog
from typing import List, Dict, Any, Optional
from rems.config import settings

logger = structlog.get_logger()

class REMSClient:
    """Client for interacting with the REMS FastAPI backend."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.rems_api_base_url
        self.timeout = 30.0  # Default timeout in seconds

    def get_evaluations(self, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """Get recent evaluation summaries."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get("/evaluations", params={"limit": limit, "skip": skip})
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error fetching evaluations from API", error=str(e))
            return []

    def get_evaluation_details(self, evaluation_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific evaluation."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get(f"/evaluations/{evaluation_id}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error fetching evaluation details from API", evaluation_id=evaluation_id, error=str(e))
            return None

    def trigger_evaluation(self, 
                           name: Optional[str] = None, 
                           interactions: Optional[List[Dict[str, Any]]] = None,
                           limit: Optional[int] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None,
                           store_results: bool = True) -> Dict[str, Any]:
        """Trigger a new evaluation asynchronously."""
        payload = {
            "name": name,
            "interactions": interactions,
            "limit": limit,
            "start_date": start_date,
            "end_date": end_date,
            "store_results": store_results
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.post("/evaluate", json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error triggering evaluation via API", error=str(e))
            return {"status": "error", "message": str(e)}

    def collect_interactions(self, 
                             start_date: Optional[str] = None, 
                             end_date: Optional[str] = None, 
                             limit: Optional[int] = None,
                             store: bool = True) -> Dict[str, Any]:
        """Collect interactions from the chatbot API via REMS API."""
        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "store": store
        }
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.post("/collect", json=payload)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error collecting interactions via API", error=str(e))
            return {"status": "error", "message": str(e)}

    def get_diagnostics(self, 
                        severity: Optional[str] = None, 
                        component: Optional[str] = None,
                        start_date: Optional[str] = None,
                        end_date: Optional[str] = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
        """Get diagnosed issues from the API."""
        params = {
            "severity": severity,
            "component": component,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit
        }
        params = {k: v for k, v in params.items() if v is not None}
        
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get("/diagnostics", params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error fetching diagnostics from API", error=str(e))
            return []

    def get_recommendations(self, 
                            severity: Optional[str] = None, 
                            component: Optional[str] = None,
                            evaluation_id: Optional[str] = None,
                            start_date: Optional[str] = None,
                            end_date: Optional[str] = None,
                            limit: int = 50) -> List[Dict[str, Any]]:
        """Get persisted recommendations from the API."""
        params = {
            "severity": severity,
            "component": component,
            "evaluation_id": evaluation_id,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit
        }
        params = {k: v for k, v in params.items() if v is not None}
        
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                response = client.get("/recommendations", params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error("Error fetching recommendations from API", error=str(e))
            return []

    def get_report(self, evaluation_id: str, report_format: str = "html") -> Optional[bytes]:
        """Download an evaluation report."""
        try:
            with httpx.Client(base_url=self.base_url, timeout=60.0) as client:  # Longer timeout for report generation
                response = client.get(f"/reports/{evaluation_id}", params={"format": report_format})
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error("Error downloading report from API", evaluation_id=evaluation_id, error=str(e))
            return None
