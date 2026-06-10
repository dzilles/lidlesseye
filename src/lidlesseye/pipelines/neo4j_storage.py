from neo4j import GraphDatabase

from lidlesseye.cypher import validate_cypher_identifier
from lidlesseye.models import ExtractedGraph
from lidlesseye.ontology import load_ontology_profile


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

