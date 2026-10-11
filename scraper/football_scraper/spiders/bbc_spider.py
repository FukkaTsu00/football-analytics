from datetime import datetime, timezone

import scrapy


class BBCFootballSpider(scrapy.Spider):
    name = "bbc_football"
    allowed_domains = ["bbc.com", "bbc.co.uk"]
    start_urls = ["https://www.bbc.com/sport/football"]

    def parse(self, response):
        links = response.css('a[href*="/sport/football/articles/"]::attr(href)').getall()
        self.logger.info("Found %d article links", len(links))
        for href in links:
            yield response.follow(href, callback=self.parse_article)

    def parse_article(self, response):
        title = " ".join(response.css("h1 ::text").getall()).strip()
        published_at = response.css("time::attr(datetime)").get()
        if not title or not published_at:
            self.logger.warning("Skipping %s: missing title or date", response.url)
            return

        paragraphs = response.css("article p ::text").getall()
        content = " ".join(t.strip() for t in paragraphs if t.strip())

        yield {
            "title": title,
            "author": (response.css("span.byline-link-text::text").get() or "Unknown").strip(),
            "published_at": published_at,
            "content": content,
            "url": response.url,
            "source": "BBC Sport",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
