import instructor

from lidlesseye.models import ExtractedGraph
from lidlesseye.ontology import load_ontology_profile
from lidlesseye.pipelines.suggestions_store import RelationshipSuggestionStore


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

        return self._normalize_graph(graph, source_url, spider)

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

