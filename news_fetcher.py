#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys

from Tools.aries_news import get_latest_news


async def main():
    parser = argparse.ArgumentParser(description='Fetch latest news for the Aries frontend.')
    parser.add_argument('--category', '-c', default='india', help='News category or location (india, world, technology, business, sports, entertainment)')
    parser.add_argument('--count', '-n', type=int, default=10, help='Number of headlines to fetch (maximum 10)')
    parser.add_argument('--topic', '-t', default='', help='Optional search topic')
    parser.add_argument('--location', '-l', default='world', help='Optional location for news, like Mumbai or Maharashtra')
    args = parser.parse_args()

    response = await get_latest_news(
        topic=args.topic,
        location=args.location,
        category=args.category,
        count=args.count,
    )

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    sys.stdout.write(json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
