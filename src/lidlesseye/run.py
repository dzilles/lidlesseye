import argparse
import os
from pathlib import Path

import yaml
from scrapy.crawler import CrawlerProcess

from lidlesseye.spider import PublicSandboxSpider
from lidlesseye.vault import load_env_from_vault


def parse_args():
    parser = argparse.ArgumentParser(description="Run Project LidlessEye pipeline.")
    parser.add_argument(
        "--project-file",
        help="Optional project YAML file containing source URLs and pipeline settings.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Ontology profile name from ontology.yaml.",
    )
    parser.add_argument(
        "--ontology-file",
        default=None,
        help="Path to the ontology YAML configuration file.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Gemini model name used through Instructor.",
    )
    return parser.parse_args()


def load_project(project_file: str | None) -> tuple[dict, Path | None]:
    if not project_file:
        return {}, None

    project_path = Path(project_file).resolve()
    with project_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}, project_path


def resolve_project_path(path_value: str, project_path: Path | None) -> str:
    path = Path(path_value)
    if path.is_absolute() or project_path is None:
        return str(path)
    return str((project_path.parent / path).resolve())


def main():
    load_env_from_vault()

    args = parse_args()
    project, project_path = load_project(args.project_file)

    ontology_file = args.ontology_file or project.get("ontology_file", "ontology.yaml")
    ontology_file = resolve_project_path(ontology_file, project_path)
    profile = args.profile or project.get("profile", "cyber_threats")
    llm_model = (
        args.llm_model
        or project.get("llm_model")
        or os.getenv("LIDLESSEYE_LLM_MODEL", "google/gemini-2.5-flash-lite")
    )
    source_urls = project.get("source_urls") or ["https://en.wikipedia.org/wiki/Computer_security"]
    spider_settings = project.get("spider", {})
    max_chars = spider_settings.get("max_chars", 6000)
    suggestions_file = project.get("suggestions_file", "ontology_suggestions.json")
    suggestions_file = resolve_project_path(suggestions_file, project_path)

    process = CrawlerProcess(
        settings={
            "ITEM_PIPELINES": {
                "lidlesseye.pipelines.LLMExtractionPipeline": 300,
                "lidlesseye.pipelines.Neo4jStoragePipeline": 400,
            },
            "ONTOLOGY_FILE": ontology_file,
            "ONTOLOGY_PROFILE": profile,
            "ONTOLOGY_SUGGESTIONS_FILE": suggestions_file,
            "LLM_MODEL": llm_model,
            "NEO4J_URI": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            "NEO4J_USER": os.getenv("NEO4J_USER", "neo4j"),
            "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD", "password"),
            "LOG_LEVEL": "INFO",
            "ROBOTSTXT_OBEY": True,
            "TELNETCONSOLE_ENABLED": False,
        }
    )

    process.crawl(PublicSandboxSpider, start_urls=source_urls, max_chars=max_chars)
    process.start()


if __name__ == "__main__":
    main()

