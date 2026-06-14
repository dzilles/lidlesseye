import os

import pika

from lidlesseye.models import ScrapedArticle


class RabbitMQPublisherPipeline:
    def __init__(self, rabbitmq_url: str, queue_name: str):
        self.rabbitmq_url = rabbitmq_url
        self.queue_name = queue_name
        self.connection = None
        self.channel = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            rabbitmq_url=crawler.settings.get(
                "RABBITMQ_URL",
                os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"),
            ),
            queue_name=crawler.settings.get("RABBITMQ_QUEUE", os.getenv("RABBITMQ_QUEUE", "raw_scrapes")),
        )

    def open_spider(self, spider):
        parameters = pika.URLParameters(self.rabbitmq_url)
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        spider.logger.info("Connected to RabbitMQ queue '%s'", self.queue_name)

    def process_item(self, item, spider):
        article = ScrapedArticle.model_validate(item)
        payload = article.model_dump_json().encode("utf-8")

        self.channel.basic_publish(
            exchange="",
            routing_key=self.queue_name,
            body=payload,
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
            ),
        )
        spider.logger.info("Published scrape to RabbitMQ: %s", article.url)
        return item

    def close_spider(self, spider):
        if self.connection and self.connection.is_open:
            self.connection.close()
            spider.logger.info("RabbitMQ connection closed")
