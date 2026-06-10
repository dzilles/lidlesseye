import scrapy


class PublicSandboxSpider(scrapy.Spider):
    name = "public_sandbox"

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, start_urls=None, max_chars=6000, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = start_urls or ["https://en.wikipedia.org/wiki/Computer_security"]
        self.max_chars = int(max_chars)

    def parse(self, response):
        paragraphs = response.css("p ::text, p::text").getall()
        raw_text = " ".join(text.strip() for text in paragraphs if text.strip())

        yield {
            "url": response.url,
            "raw_text": raw_text[: self.max_chars],
        }

