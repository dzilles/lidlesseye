import logging
import re
from pathlib import Path
from typing import Any

import instructor
import json
import yaml
from neo4j import GraphDatabase

from models import Edge, ExtractedGraph


LOGGER = logging.getLogger(__name__)
SAFE_CYPHER_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_ontology_profile(ontology_file: str, profile_name: str) -> dict[str, Any]:
    ontology_path = Path(ontology_file)
    if not ontology_path.is_absolute():
        ontology_path = Path(__file__).resolve().parent / ontology_path

    with ontology_path.open("r", encoding="utf-8") as handle:
        ontology = yaml.safe_load(handle) or {}

    profiles = ontology.get("profiles", {})
    if profile_name not in profiles:
        available = ", ".join(sorted(profiles)) or "<none>"
        raise ValueError(
            f"Ontology profile '{profile_name}' was not found in {ontology_path}. "
            f"Available profiles: {available}"
        )

    return profiles[profile_name]


def validate_cypher_identifier(value: str, identifier_type: str) -> str:
    if not SAFE_CYPHER_IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe {identifier_type} for Cypher insertion: {value!r}")
    return value


def resolve_local_path(path_value: str, base_file: str | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path

    if base_file:
        base_path = Path(base_file)
        if not base_path.is_absolute():
            base_path = Path(__file__).resolve().parent / base_path
        return base_path.parent / path

    return Path(__file__).resolve().parent / path


class RelationshipSuggestionStore:
    def __init__(self, suggestions_file: str, ontology_file: str, profile_name: str):
        self.suggestions_path = resolve_local_path(suggestions_file, ontology_file)
        self.profile_name = profile_name

    def record_unknown_relationships(
        self,
        *,
        source_url: str,
        graph: ExtractedGraph,
        unknown_edges: list[Edge],
    ) -> None:
        if not unknown_edges:
            return

        data = self._load()
        profile_bucket = data.setdefault("profiles", {}).setdefault(
            self.profile_name,
            {"relationships": {}},
        )
        relationships = profile_bucket.setdefault("relationships", {})
        nodes_by_id = {node.id: node for node in graph.nodes}

        for edge in unknown_edges:
            relationship_bucket = relationships.setdefault(
                edge.relationship,
                {
                    "count": 0,
                    "examples": [],
                },
            )
            relationship_bucket["count"] += 1
            relationship_bucket["examples"].append(
                {
                    "source_url": source_url,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "relationship": edge.relationship,
                    "source_node": self._serialize_node(nodes_by_id.get(edge.source_id)),
                    "target_node": self._serialize_node(nodes_by_id.get(edge.target_id)),
                }
            )

        self._save(data)

    def _load(self) -> dict[str, Any]:
        if not self.suggestions_path.exists():
            return {
                "description": "Ontology suggestions captured from LLM outputs that were not allowed by the active profile.",
                "profiles": {},
            }

        with self.suggestions_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, data: dict[str, Any]) -> None:
        self.suggestions_path.parent.mkdir(parents=True, exist_ok=True)
        with self.suggestions_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")

    @staticmethod
    def _serialize_node(node):
        if node is None:
            return None
        return node.model_dump()


class LLMExtractionPipeline:
    def __init__(
        self,
        ontology_file: str,
        profile_name: str,
        model_name: str,
        suggestions_file: str,
    ):
        self.ontology_file = ontology_file
        self.profile_name = profile_name
        self.model_name = model_name
        self.profile = load_ontology_profile(ontology_file, profile_name)
        self.relationship_suggestions = RelationshipSuggestionStore(
            suggestions_file=suggestions_file,
            ontology_file=ontology_file,
            profile_name=profile_name,
        )
        self.client = instructor.from_provider(model_name)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            ontology_file=crawler.settings.get("ONTOLOGY_FILE", "ontology.yaml"),
            profile_name=crawler.settings.get("ONTOLOGY_PROFILE", "cyber_threats"),
            model_name=crawler.settings.get("LLM_MODEL", "google/gemini-2.5-flash-lite"),
            suggestions_file=crawler.settings.get("ONTOLOGY_SUGGESTIONS_FILE", "ontology_suggestions.json"),
        )

    def process_item(self, item, spider):
        raw_text = item.get("raw_text", "").strip()
        source_url = item.get("url", "")

        if not raw_text:
            return ExtractedGraph()

        allowed_labels = self.profile.get("allowed_node_labels", [])
        allowed_relationships = self.profile.get("allowed_relationships", [])

        system_prompt = f"""
You are Project LidlessEye's schema-agnostic knowledge graph extraction engine.

Domain context:
{self.profile.get("context_description", "")}

Ontology rules:
- Only use these node labels: {allowed_labels}
- Only use these relationship types: {allowed_relationships}
- Every node id must be stable, concise, and derived from the entity value.
- Store source evidence fields in node properties where useful.
- Do not invent entities that are not supported by the text.
- Return an ExtractedGraph object with nodes and edges only.
""".strip()

        user_prompt = f"""
Source URL: {source_url}

Extract a knowledge graph from this text:
{raw_text}
""".strip()

        graph = self.client.create(
            response_model=ExtractedGraph,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_retries=2,
        )

        graph = self._normalize_graph(graph, source_url, spider)
        return graph

    def _normalize_graph(self, graph: ExtractedGraph, source_url: str, spider) -> ExtractedGraph:
        allowed_labels = set(self.profile.get("allowed_node_labels", []))
        allowed_relationships = set(self.profile.get("allowed_relationships", []))
        relationship_aliases = self.profile.get("relationship_aliases", {})

        invalid_labels = sorted({node.label for node in graph.nodes if node.label not in allowed_labels})
        if invalid_labels:
            raise ValueError(f"LLM returned labels outside ontology profile: {invalid_labels}")

        valid_edges = []
        unknown_edges = []

        for edge in graph.edges:
            if edge.relationship in allowed_relationships:
                valid_edges.append(edge)
                continue

            normalized_relationship = relationship_aliases.get(edge.relationship)
            if normalized_relationship in allowed_relationships:
                valid_edges.append(edge.model_copy(update={"relationship": normalized_relationship}))
            else:
                unknown_edges.append(edge)

        self.relationship_suggestions.record_unknown_relationships(
            source_url=source_url,
            graph=graph,
            unknown_edges=unknown_edges,
        )

        if unknown_edges:
            unknown_counts = {}
            for edge in unknown_edges:
                unknown_counts[edge.relationship] = unknown_counts.get(edge.relationship, 0) + 1
            spider.logger.warning(
                "Recorded and skipped %d unknown relationship edges for ontology review: %s",
                len(unknown_edges),
                unknown_counts,
            )

        return graph.model_copy(update={"edges": valid_edges})


class Neo4jStoragePipeline:
    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        ontology_file: str,
        profile_name: str,
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.profile = load_ontology_profile(ontology_file, profile_name)
        self.allowed_labels = set(self.profile.get("allowed_node_labels", []))
        self.allowed_relationships = set(self.profile.get("allowed_relationships", []))
        self.driver = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            uri=crawler.settings.get("NEO4J_URI", "bolt://localhost:7687"),
            user=crawler.settings.get("NEO4J_USER", "neo4j"),
            password=crawler.settings.get("NEO4J_PASSWORD", "password"),
            ontology_file=crawler.settings.get("ONTOLOGY_FILE", "ontology.yaml"),
            profile_name=crawler.settings.get("ONTOLOGY_PROFILE", "cyber_threats"),
        )

    def open_spider(self, spider):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            spider.logger.info("Connected to Neo4j at %s", self.uri)
        except Exception as exc:
            spider.logger.error("Failed to connect to Neo4j: %s", exc)
            self.driver = None

    def process_item(self, item, spider):
        graph = item if isinstance(item, ExtractedGraph) else ExtractedGraph.model_validate(item)

        if self.driver is None:
            spider.logger.warning("Skipping graph because Neo4j connection is unavailable")
            return graph

        with self.driver.session() as session:
            for node in graph.nodes:
                if node.label not in self.allowed_labels:
                    raise ValueError(f"Node label is not allowed by ontology: {node.label}")

                label = validate_cypher_identifier(node.label, "node label")
                query = f"MERGE (n:{label} {{id: $id}}) SET n += $properties"
                properties = {"id": node.id, **node.properties}
                session.run(query, id=node.id, properties=properties)

            for edge in graph.edges:
                if edge.relationship not in self.allowed_relationships:
                    raise ValueError(f"Relationship is not allowed by ontology: {edge.relationship}")

                relationship = validate_cypher_identifier(edge.relationship, "relationship type")
                query = (
                    "MATCH (source {id: $source_id}) "
                    "MATCH (target {id: $target_id}) "
                    f"MERGE (source)-[r:{relationship}]->(target)"
                )
                session.run(
                    query,
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                )

        spider.logger.info("Stored graph in Neo4j: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        return graph

    def close_spider(self, spider):
        if self.driver is not None:
            self.driver.close()
            spider.logger.info("Neo4j connection closed")
