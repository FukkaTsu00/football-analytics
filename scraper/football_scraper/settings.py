"""Scrapy settings: identify ourselves honestly and crawl politely."""

BOT_NAME = "football_scraper"
SPIDER_MODULES = ["football_scraper.spiders"]
NEWSPIDER_MODULE = "football_scraper.spiders"

# Say who we are instead of pretending to be a browser
USER_AGENT = "FootballAnalyticsBot/0.1 (student data engineering project)"

# Respect each site's robots.txt rules
ROBOTSTXT_OBEY = True

# Politeness: one request at a time per site, and slow down if the server is slow
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10

# Robustness
RETRY_TIMES = 2
DOWNLOAD_TIMEOUT = 30

# Output: keep accented characters readable in the JSON
FEED_EXPORT_ENCODING = "utf-8"
LOG_LEVEL = "INFO"
