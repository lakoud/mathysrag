"""API Collector - Fetches interactions from the chatbot API."""

from datetime import datetime

import httpx
import structlog

from rems.config import settings
from rems.models import Interaction, RetrievedDocument, get_session
from rems.schemas import DocumentSchema, InteractionSchema

logger = structlog.get_logger()


class APICollector:
    """Collects interactions from the chatbot API."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.api_url = api_url or settings.chatbot_api_url
        self.api_key = api_key or settings.chatbot_api_key
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.api_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def fetch_interactions(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int | None = None,
    ) -> list[InteractionSchema]:
        """
        Fetch interactions from the chatbot API.

        Args:
            start_date: Filter interactions after this date
            end_date: Filter interactions before this date
            limit: Maximum number of interactions to fetch

        Returns:
            List of interaction schemas
        """
        params: dict = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()
        if limit:
            params["limit"] = limit

        logger.info(
            "Fetching interactions from API",
            api_url=self.api_url,
            params=params,
        )

        response = self.client.get("/interactions", params=params)
        response.raise_for_status()

        data = response.json()
        interactions = []

        for item in data.get("interactions", data if isinstance(data, list) else []):
            interaction = self._parse_interaction(item)
            interactions.append(interaction)

        logger.info("Fetched interactions", count=len(interactions))
        return interactions

    def _parse_interaction(self, data: dict) -> InteractionSchema:
        """Parse raw API response into InteractionSchema."""
        documents = []
        for idx, doc in enumerate(data.get("retrieved_documents", [])):
            documents.append(
                DocumentSchema(
                    content=doc.get("content", ""),
                    source=doc.get("source"),
                    rank=doc.get("rank", idx),
                    score=doc.get("score"),
                    metadata=doc.get("metadata"),
                )
            )

        import uuid
        
        # Ensure the ID is a valid UUID or generate a new one (fixes DB crash on 'interaction_1')
        interaction_id_raw = data.get("id")
        try:
            interaction_id = str(uuid.UUID(str(interaction_id_raw))) if interaction_id_raw else str(uuid.uuid4())
        except ValueError:
            interaction_id = str(uuid.uuid4())

        return InteractionSchema(
            id=interaction_id,
            query=data["query"],
            response=data["response"],
            retrieved_documents=documents,
            session_id=data.get("session_id"),
            user_id=data.get("user_id"),
            metadata=data.get("metadata"),
            created_at=data.get("created_at"),
        )

    def store_interactions(self, interactions: list[InteractionSchema]) -> list[str]:
        """
        Store interactions in the database.

        Args:
            interactions: List of interactions to store

        Returns:
            List of stored interaction IDs
        """
        stored_ids = []

        with get_session() as session:
            for interaction_schema in interactions:
                # Create interaction record
                interaction = Interaction(
                    query=interaction_schema.query,
                    response=interaction_schema.response,
                    session_id=interaction_schema.session_id,
                    user_id=interaction_schema.user_id,
                    metadata_=interaction_schema.metadata,
                )

                # Add retrieved documents
                for doc in interaction_schema.retrieved_documents:
                    retrieved_doc = RetrievedDocument(
                        content=doc.content,
                        source=doc.source,
                        rank=doc.rank,
                        score=doc.score,
                        metadata_=doc.metadata,
                    )
                    interaction.retrieved_documents.append(retrieved_doc)

                session.add(interaction)
                session.flush()  # Get the ID
                stored_ids.append(interaction.id)

        logger.info("Stored interactions", count=len(stored_ids))
        return stored_ids

    def collect_and_store(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int | None = None,
    ) -> list[str]:
        """
        Fetch interactions from API and store them in the database.

        Returns:
            List of stored interaction IDs
        """
        interactions = self.fetch_interactions(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return self.store_interactions(interactions)

    def load_from_file(self, file_path: str) -> list[InteractionSchema]:
        """
        Load interactions from a JSON file (for offline/batch evaluation).

        Args:
            file_path: Path to JSON file containing interactions

        Returns:
            List of interaction schemas
        """
        import json
        from pathlib import Path

        path = Path(file_path)
        with path.open() as f:
            data = json.load(f)

        interactions = []
        items = data.get("interactions", data if isinstance(data, list) else [])

        for item in items:
            interaction = self._parse_interaction(item)
            interactions.append(interaction)

        logger.info("Loaded interactions from file", path=file_path, count=len(interactions))
        return interactions
