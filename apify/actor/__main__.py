"""
X Twitter Scraper - Apify Actor
抓取指定用户的推文
"""

import asyncio
from datetime import datetime, timedelta
from apify import Actor
from playwright.async_api import async_playwright


async def main():
    """Main function for Apify Actor"""
    async with Actor:
        # 获取输入
        actor_input = await Actor.get_input()
        users = actor_input.get('users', [])
        days_ago = actor_input.get('days_ago', 1)
        max_tweets_per_user = actor_input.get('max_tweets_per_user', 20)
        cookie = actor_input.get('cookie', '')

        if not users:
            await Actor.log.error('No users specified in input')
            return

        Actor.log.info(f'Starting to scrape {len(users)} users')

        # 计算时间阈值
        time_threshold = datetime.now() - timedelta(days=days_ago)

        all_tweets = []

        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )

            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )

            # 设置Cookie
            if cookie:
                # 解析Cookie字符串
                cookies = []
                for item in cookie.split(';'):
                    if '=' in item:
                        name, value = item.strip().split('=', 1)
                        cookies.append({
                            'name': name,
                            'value': value,
                            'domain': '.x.com',
                            'path': '/'
                        })
                await context.add_cookies(cookies)
                Actor.log.info('Cookie set successfully')

            for username in users:
                Actor.log.info(f'Scraping user: {username}')
                tweets = await scrape_user_tweets(
                    context, username, time_threshold, max_tweets_per_user
                )
                all_tweets.extend(tweets)
                Actor.log.info(f'Got {len(tweets)} tweets from {username}')

            await browser.close()

        # 推送到数据集
        await Actor.push_data(all_tweets)
        Actor.log.info(f'Total tweets collected: {len(all_tweets)}')


async def scrape_user_tweets(context, username, time_threshold, max_tweets):
    """抓取单个用户的推文"""
    tweets = []

    try:
        page = await context.new_page()

        # 访问用户页面
        url = f'https://x.com/{username}'
        await page.goto(url, wait_until='networkidle', timeout=30000)

        # 等待页面加载
        await page.wait_for_timeout(2000)

        # 滚动加载推文
        tweets_collected = 0
        consecutive_no_new = 0
        max_scrolls = 10

        while tweets_collected < max_tweets and consecutive_no_new < 3:
            # 获取当前页面的推文
            articles = await page.query_selector_all('article[data-testid="tweet"]')

            for article in articles:
                try:
                    tweet_data = await extract_tweet_data(article, username)

                    if tweet_data and tweet_data['timestamp'] >= time_threshold:
                        # 检查是否已存在
                        if not any(t['id'] == tweet_data['id'] for t in tweets):
                            tweets.append(tweet_data)
                            tweets_collected += 1

                            if tweets_collected >= max_tweets:
                                break
                except Exception as e:
                    continue

            if tweets_collected >= max_tweets:
                break

            # 滚动页面
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)

            # 检查是否有新推文
            new_articles = await page.query_selector_all('article[data-testid="tweet"]')
            if len(new_articles) <= len(articles):
                consecutive_no_new += 1
            else:
                consecutive_no_new = 0

        await page.close()

    except Exception as e:
        Actor.log.error(f'Error scraping {username}: {e}')

    return tweets


async def extract_tweet_data(article, target_username):
    """从article元素提取推文数据"""
    try:
        # 获取推文ID和URL
        time_elem = await article.query_selector('time')
        if not time_elem:
            return None

        datetime_attr = await time_elem.get_attribute('datetime')
        if not datetime_attr:
            return None

        tweet_time = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))

        # 获取用户名
        user_link = await article.query_selector('[data-testid="User-Name"] a')
        if not user_link:
            return None

        href = await user_link.get_attribute('href')
        if not href:
            return None

        username = href.lstrip('/')

        # 获取推文内容
        text_elem = await article.query_selector('[data-testid="tweetText"]')
        text = await text_elem.inner_text() if text_elem else ''

        # 获取链接
        tweet_url = f'https://x.com{href}/status/{datetime_attr.split(".")[0]}'

        # 提取推文ID
        tweet_id = datetime_attr.split('.')[0].split('T')[-1]

        return {
            'id': tweet_id,
            'url': tweet_url,
            'text': text,
            'username': username,
            'display_name': username,
            'timestamp': tweet_time,
            'datetime': datetime_attr
        }

    except Exception as e:
        return None


# 入口点
if __name__ == '__main__':
    asyncio.run(main())
