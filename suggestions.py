import argparse
import json
import os
from pathlib import Path

from neo4j import GraphDatabase

from pipelines import load_ontology_profile, validate_cypher_identifier


def load_suggestions(suggestions_file: str) -> dict:
    path = Path(suggestions_file)
    if not path.exists():
        raise FileNotFoundError(f"Suggestions file does not exist: {path}")

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def list_suggestions(suggestions_file: str, profile_name: str) -> None:
    data = load_suggestions(suggestions_file)
    relationships = (
        data.get("profiles", {})
        .get(profile_name, {})
        .get("relationships", {})
    )

    if not relationships:
        print(f"No relationship suggestions found for profile '{profile_name}'.")
        return

    for relationship, payload in sorted(relationships.items()):
        print(f"{relationship}: {payload.get('count', 0)}")


def replay_relationship(
    *,
    suggestions_file: str,
    ontology_file: str,
    profile_name: str,
    relationship: str,
    dry_run: bool,
) -> None:
    profile = load_ontology_profile(ontology_file, profile_name)
    allowed_relationships = set(profile.get("allowed_relationships", []))

    if relationship not in allowed_relationships:
        raise ValueError(
            f"Relationship '{relationship}' is not allowed by ontology profile '{profile_name}'. "
            "Add it to allowed_relationships before replaying."
        )

    relationship_type = validate_cypher_identifier(relationship, "relationship type")
    data = load_suggestions(suggestions_file)
    relationship_payload = (
        data.get("profiles", {})
        .get(profile_name, {})
        .get("relationships", {})
        .get(relationship)
    )

    if not relationship_payload:
        print(f"No saved suggestions found for relationship '{relationship}'.")
        return

    examples = relationship_payload.get("examples", [])
    if dry_run:
        print(f"Would replay {len(examples)} edges for relationship '{relationship}'.")
        return

    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "password"),
        ),
    )

    try:
        with driver.session() as session:
            for example in examples:
                merge_node_snapshot(session, example.get("source_node"))
                merge_node_snapshot(session, example.get("target_node"))
                session.run(
                    (
                        "MATCH (source {id: $source_id}) "
                        "MATCH (target {id: $target_id}) "
                        f"MERGE (source)-[r:{relationship_type}]->(target) "
                        "SET r.source_url = $source_url, r.replayed_from_suggestions = true"
                    ),
                    source_id=example["source_id"],
                    target_id=example["target_id"],
                    source_url=example.get("source_url"),
                )
    finally:
        driver.close()

    print(f"Replayed {len(examples)} edges for relationship '{relationship}'.")


def merge_node_snapshot(session, node_snapshot: dict | None) -> None:
    if not node_snapshot:
        return

    label = validate_cypher_identifier(node_snapshot["label"], "node label")
    properties = {"id": node_snapshot["id"], **node_snapshot.get("properties", {})}
    session.run(
        f"MERGE (n:{label} {{id: $id}}) SET n += $properties",
        id=node_snapshot["id"],
        properties=properties,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Review and replay Project LidlessEye ontology suggestions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List suggested relationship types and counts.")
    list_parser.add_argument("--suggestions-file", required=True)
    list_parser.add_argument("--profile", required=True)

    replay_parser = subparsers.add_parser("replay", help="Replay saved edges after promoting a relationship.")
    replay_parser.add_argument("--suggestions-file", required=True)
    replay_parser.add_argument("--ontology-file", required=True)
    replay_parser.add_argument("--profile", required=True)
    replay_parser.add_argument("--relationship", required=True)
    replay_parser.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == "list":
        list_suggestions(args.suggestions_file, args.profile)
    elif args.command == "replay":
        replay_relationship(
            suggestions_file=args.suggestions_file,
            ontology_file=args.ontology_file,
            profile_name=args.profile,
            relationship=args.relationship,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
