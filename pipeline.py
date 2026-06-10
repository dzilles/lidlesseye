import logging

import scrapy
from neo4j import GraphDatabase
from scrapy.crawler import CrawlerProcess


class QuotesSpider(scrapy.Spider):
    name = "quotes_spider"
    start_urls = ["http://quotes.toscrape.com"]

    def parse(self, response):
        for quote in response.css("div.quote")[:5]:
            quote_text = quote.css("span.text::text").get()
            author_name = quote.css("small.author::text").get()

            if quote_text and author_name:
                yield {
                    "quote_text": quote_text,
                    "author_name": author_name,
                }


class Neo4jPipeline:
    def __init__(self):
        self.driver = None

    def open_spider(self, spider):
        uri = "bolt://localhost:7687"
        user = "neo4j"
        password = "password"

        try:
            self.driver = GraphDatabase.driver(uri, auth=(user, password))
            self.driver.verify_connectivity()
            spider.logger.info("Connected to Neo4j at %s", uri)
        except Exception as exc:
            spider.logger.error("Failed to connect to Neo4j: %s", exc)
            self.driver = None

    def process_item(self, item, spider):
        if self.driver is None:
            spider.logger.warning("Skipping item because Neo4j connection is unavailable: %s", item)
            return item

        query = """
        MERGE (author:Author {name: $author_name})
        MERGE (quote:Quote {text: $quote_text})
        MERGE (author)-[:WROTE]->(quote)
        """

        try:
            with self.driver.session() as session:
                session.run(
                    query,
                    author_name=item["author_name"],
                    quote_text=item["quote_text"],
                )
        except Exception as exc:
            spider.logger.error("Failed to write item to Neo4j: %s | item=%s", exc, item)

        return item

    def close_spider(self, spider):
        if self.driver is not None:
            self.driver.close()
            spider.logger.info("Neo4j connection closed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    process = CrawlerProcess(
        settings={
            "ITEM_PIPELINES": {
                "__main__.Neo4jPipeline": 300,
            },
            "LOG_LEVEL": "INFO",
            "ROBOTSTXT_OBEY": True,
        }
    )

    process.crawl(QuotesSpider)
    process.start()
