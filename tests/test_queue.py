import os

import redis
from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy_redis.scheduler import QUEUE_KEY

from dd_crawler.queue import BaseRequestQueue


# allow test settings from environment
# TODO - use a custom testing db?
REDIS_URL = os.environ.get('REDIST_URL', 'redis://localhost')


class ATestSpider(Spider):
    name = 'test_dd_spider'


def make_server():
    redis_server = redis.from_url(REDIS_URL)
    keys = redis_server.keys(QUEUE_KEY % {'spider': ATestSpider.name} + '*')
    redis_server.delete(*keys)
    return redis_server


def make_queue(redis_server, cls=BaseRequestQueue, slots=None):
    crawler = Crawler(Spider, settings={'QUEUE_CACHE_TIME': 0})
    if slots is None:
        slots = {}
    spider = Spider.from_crawler(crawler, 'test_dd_spider')
    return cls(server=redis_server, spider=spider, key=QUEUE_KEY,
               slots_mock=slots)


def test_push_pop():
    server = make_server()
    q = make_queue(server)
    assert q.pop() is None
    assert q.get_queues() == []
    r1 = Request('http://example.com', priority=100, meta={'depth': 10})
    q.push(r1)
    assert q.get_queues() == [b'test_dd_spider:requests:domain:example.com']
    assert q.select_queue_key() == b'test_dd_spider:requests:domain:example.com'
    r1_ = q.pop()
    assert r1_.url == r1.url
    assert r1_.priority == r1.priority
    assert r1_.meta['depth'] == r1.meta['depth']


def test_priority():
    server = make_server()
    q = make_queue(server)
    q.push(Request('http://example.com/1', priority=10))
    q.push(Request('http://example.com/2', priority=100))
    q.push(Request('http://example.com/3', priority=1))
    assert [q.pop().url for _ in range(3)] == [
        'http://example.com/2',
        'http://example.com/1',
        'http://example.com/3']


def test_domain_distribution():
    server = make_server()
    q1 = make_queue(server)
    q2 = make_queue(server)
    for url in ['http://a.com', 'http://a.com/foo', 'http://b.com',
                'http://b.com/foo', 'http://c.com']:
        q1.push(Request(url=url))  # queue does not matter
    # TODO