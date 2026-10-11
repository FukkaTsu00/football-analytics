from datetime import datetime, timezone

import scrapy


class GoalSpider(scrapy.Spider):
    name = "goal_football"
    allowed_domains = ["goal.com"]
    start_urls = ["https://www.goal.com/en/news"]

    def parse(self, response):
        links = response.css('article a[data-testid="card-title-url"]::attr(href)').getall()
        self.logger.info("Found %d article links", len(links))
        for href in links:
            yield response.follow(href, callback=self.parse_article)

    def parse_article(self, response):
        title = response.css("h1::text").get()
        published_at = response.css("time::attr(datetime)").get()
        if not title or not published_at:
            self.logger.warning("Skipping %s: missing title or date", response.url)
            return

        # Goal.com loads the full article with JavaScript: Scrapy only sees the teaser.
        paragraphs = response.css("main p ::text").getall()
        content = " ".join(t.strip() for t in paragraphs if t.strip() and "GOAL.com" not in t)

        yield {
            "title": title.strip(),
            "author": "Unknown",
            "published_at": published_at,
            "content": content,
            "content_type": "teaser_only",
            "url": response.url,
            "source": "Goal.com",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
