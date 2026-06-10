import json
from typing import Any

from lidlesseye.models import Edge, ExtractedGraph
from lidlesseye.ontology import resolve_local_path


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

