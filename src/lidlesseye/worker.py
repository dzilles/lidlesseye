import argparse
import json
import logging
import os
import signal
from pathlib import Path

import pika
import yaml

from lidlesseye.models import ScrapedArticle
from lidlesseye.pipelines.llm_extraction import LLMExtractionPipeline
from lidlesseye.pipelines.neo4j_storage import Neo4jStoragePipeline
from lidlesseye.vault import load_env_from_vault


LOGGER = logging.getLogger("lidlesseye.worker")


def parse_args():
    parser = argparse.ArgumentParser(description="Run a Project LidlessEye Phase 3 worker.")
    parser.add_argument("--project-file", help="Optional project YAML file containing pipeline settings.")
    parser.add_argument("--profile", default=None, help="Ontology profile name.")
    parser.add_argument("--ontology-file", default=None, help="Path to ontology YAML.")
    parser.add_argument("--llm-model", default=None, help="Gemini model name used through Instructor.")
    parser.add_argument("--queue", default=None, help="RabbitMQ queue name.")
    parser.add_argument("--rabbitmq-url", default=None, help="RabbitMQ AMQP URL.")
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


class ScrapeWorker:
    def __init__(
        self,
        *,
        rabbitmq_url: str,
        queue_name: str,
        llm_pipeline: LLMExtractionPipeline,
        storage_pipeline: Neo4jStoragePipeline,
    ):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.llm_pipeline = llm_pipeline
        self.storage_pipeline = storage_pipeline
        self.connection = None
        self.channel = None
        self.shutting_down = False

    def start(self) -> None:
        parameters = pika.URLParameters(self.rabbitmq_url)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._handle_message,
            auto_ack=False,
        )

        LOGGER.info("Worker listening on RabbitMQ queue '%s'", self.queue_name)
        self.channel.start_consuming()

    def stop(self, *_args) -> None:
        if self.shutting_down:
            return

        self.shutting_down = True
        LOGGER.info("Graceful shutdown requested")

        if self.channel and self.channel.is_open:
            self.channel.stop_consuming()

    def close(self) -> None:
        self.storage_pipeline.close()
        if self.connection and self.connection.is_open:
            self.connection.close()

    def _handle_message(self, channel, method, _properties, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            article = ScrapedArticle.model_validate(payload)

            LOGGER.info("Processing scrape: %s", article.url)
            graph = self.llm_pipeline.extract(article, logger=LOGGER)
            self.storage_pipeline.store_graph(graph, source_url=article.url, logger=LOGGER)

            channel.basic_ack(delivery_tag=method.delivery_tag)
            LOGGER.info("Acknowledged scrape: %s", article.url)
        except Exception:
            LOGGER.exception("Failed to process message; requeueing")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def build_worker(args) -> ScrapeWorker:
    project, project_path = load_project(args.project_file)

    ontology_file = args.ontology_file or project.get("ontology_file", "ontology.yaml")
    ontology_file = resolve_project_path(ontology_file, project_path)
    profile = args.profile or project.get("profile", "cyber_threats")
    suggestions_file = project.get("suggestions_file", "ontology_suggestions.json")
    suggestions_file = resolve_project_path(suggestions_file, project_path)
    llm_model = (
        args.llm_model
        or project.get("llm_model")
        or os.getenv("LIDLESSEYE_LLM_MODEL", "google/gemini-2.5-flash-lite")
    )

    llm_pipeline = LLMExtractionPipeline(
        ontology_file=ontology_file,
        profile_name=profile,
        model_name=llm_model,
        suggestions_file=suggestions_file,
    )
    storage_pipeline = Neo4jStoragePipeline(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        user=os.getenv("NEO4J_USER", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
        ontology_file=ontology_file,
        profile_name=profile,
    )
    storage_pipeline.connect()

    return ScrapeWorker(
        rabbitmq_url=args.rabbitmq_url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"),
        queue_name=args.queue or os.getenv("RABBITMQ_QUEUE", "raw_scrapes"),
        llm_pipeline=llm_pipeline,
        storage_pipeline=storage_pipeline,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    load_env_from_vault()
    worker = build_worker(parse_args())

    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)

    try:
        worker.start()
    finally:
        worker.close()
        LOGGER.info("Worker stopped")


if __name__ == "__main__":
    main()

