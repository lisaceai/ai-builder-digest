"""
调用 gentle_cloud/twitter-tweets-scraper Actor
"""

import asyncio
from datetime import datetime, timedelta, timezone
from apify_client import ApifyClient


async def main():
    # 从环境变量获取 Apify API Token
    APIFY_TOKEN = os.environ.get('APIFY_TOKEN', '')

    client = ApifyClient(APIFY_TOKEN)

    # Actor ID
    actor_id = 'gentle_cloud/twitter-tweets-scraper'

    # 计算前一天日期
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # 输入参数 - 使用正确的参数格式
    actor_input = {
        'start_urls': [
            {'url': 'https://x.com/karpathy'},
            {'url': 'https://x.com/gregisenberg'},
            {'url': 'https://x.com/zarazhangrui'},
            {'url': 'https://x.com/petergyang'},
        ],
        'since_date': yesterday,  # 前一天
        'result_count': '100',  # 注意是字符串格式
    }

    # 运行 Actor - 使用 start() 方法
    print(f'Running actor: {actor_id}')
    print(f'Input: {actor_input}')

    # 使用 start() 并等待完成
    run = client.actor(actor_id).start(
        run_input=actor_input,
        wait_for_finish=120
    )

    # 获取结果
    print('\n--- Results ---')
    if run and run.get('defaultDatasetId'):
        dataset_id = run['defaultDatasetId']
        dataset = client.dataset(dataset_id)
        items = dataset.list_items().items

        print(f'Total items: {len(items)}')
        print('\n--- Tweets ---')
        for tweet in items:
            text = tweet.get('full_text', tweet.get('text', ''))[:150]
            created = tweet.get('created_at', 'unknown')
            # 获取用户名
            user_data = tweet.get('user', {})
            legacy = user_data.get('legacy', {})
            username = legacy.get('screen_name', 'unknown')
            print(f'@{username} - {created}:')
            print(f'  {text}...')
            print()
    else:
        print('No results found')


if __name__ == '__main__':
    asyncio.run(main())
