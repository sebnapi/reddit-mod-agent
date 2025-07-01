import json
import os
import time
import requests
import logging
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedditScraper:
    SORT_OPTIONS = {
        'hot': 'hot',
        'new': 'new',
        'top': 'top',
        'rising': 'rising',
        'controversial': 'controversial'
    }

    def __init__(self, user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"):
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})
        self.base_url = "https://www.reddit.com"

    def _make_request_with_backoff(self, url, params=None, max_retries=10, base_delay=1):
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params)

                if response.status_code == 429:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Rate limited (429) for {url}. Retrying in {delay:.2f} seconds (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                time.sleep(0.5)
                return response.json()

            except requests.RequestException as e:
                if response.status_code == 429:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Rate limited (429) for {url}. Retrying in {delay:.2f} seconds (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Request failed for {url}: {e}")
                    if attempt == max_retries - 1:
                        return None
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)

        logger.error(f"Max retries ({max_retries}) exceeded for {url}")
        return None

    def _make_request(self, url, params=None):
        return self._make_request_with_backoff(url, params)

    def get_subreddit_info(self, subreddit_name):
        url = f"{self.base_url}/r/{subreddit_name}/about.json"
        return self._make_request(url)

    def get_subreddit_rules(self, subreddit_name):
        url = f"{self.base_url}/r/{subreddit_name}/about/rules.json"
        return self._make_request(url)

    def get_subreddit_posts(self, subreddit_name, limit=50, sort='hot'):
        if sort not in self.SORT_OPTIONS:
            sort = 'hot'
        url = f"{self.base_url}/r/{subreddit_name}/{sort}.json"
        params = {'limit': limit}
        return self._make_request(url, params)

    def get_post_comments(self, subreddit_name, post_id, limit=50):
        url = f"{self.base_url}/r/{subreddit_name}/comments/{post_id}.json"
        params = {'limit': limit}
        return self._make_request(url, params)

    def load_json(self, path):
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def save_json(self, path, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def merge_comments(self, existing, new):
        if not existing:
            return new
        ids = {c['id'] for c in existing}
        merged = existing + [c for c in new if c['id'] not in ids]
        return merged

    def scrape_subreddit(self, subreddit_name, post_limit=25, sorts=None):
        if sorts is None:
            sorts = list(self.SORT_OPTIONS.keys())
        outdir = os.path.join('data', subreddit_name)
        os.makedirs(outdir, exist_ok=True)
        info_path = os.path.join(outdir, 'subreddit_info.json')
        rules_path = os.path.join(outdir, 'rules.json')

        logger.info(f"Starting scrape of r/{subreddit_name}")

        info = self.load_json(info_path)
        if not info:
            info = self.get_subreddit_info(subreddit_name)
            if info:
                self.save_json(info_path, info)
                logger.info(f"Saved subreddit info for r/{subreddit_name}")

        rules = self.load_json(rules_path)
        if not rules:
            rules = self.get_subreddit_rules(subreddit_name)
            if rules:
                self.save_json(rules_path, rules)
                logger.info(f"Saved rules for r/{subreddit_name}")

        total_posts_saved = 0
        total_comments_saved = 0

        for sort in sorts:
            logger.info(f"Scraping r/{subreddit_name} - {sort} posts")
            posts_data = self.get_subreddit_posts(subreddit_name, limit=post_limit, sort=sort)
            if posts_data and 'data' in posts_data and 'children' in posts_data['data']:
                posts = posts_data['data']['children']
                logger.info(f"Found {len(posts)} posts in r/{subreddit_name} - {sort}")

                for i, post in enumerate(posts, 1):
                    post_id = post['data']['id']
                    post_title = post['data'].get('title', 'Unknown Title')[:50] + "..." if len(post['data'].get('title', '')) > 50 else post['data'].get('title', 'Unknown Title')

                    post_dir = os.path.join(outdir, post_id)
                    os.makedirs(post_dir, exist_ok=True)

                    post_file = os.path.join(post_dir, 'post.json')
                    comments_file = os.path.join(post_dir, 'comments.json')

                    self.save_json(post_file, post)
                    total_posts_saved += 1
                    logger.info(f"[{i}/{len(posts)}] Saved post: {post_title} (ID: {post_id})")

                    existing_comments = self.load_json(comments_file)
                    comm = self.get_post_comments(subreddit_name, post_id, limit=50)
                    new_comments = []
                    if comm and isinstance(comm, list) and len(comm) > 1 and 'data' in comm[1]:
                        comms = comm[1]['data'].get('children', [])
                        new_comments = [c['data'] for c in comms if c['kind'] == 't1']

                    merged_comments = self.merge_comments(existing_comments, new_comments)
                    self.save_json(comments_file, merged_comments)

                    comments_count = len(merged_comments)
                    total_comments_saved += len(new_comments)
                    logger.info(f"  └─ Saved {len(new_comments)} new comments (total: {comments_count})")

                    time.sleep(0.5)
            else:
                logger.warning(f"No posts found for r/{subreddit_name} - {sort}")

        logger.info(f"Completed scraping r/{subreddit_name}: {total_posts_saved} posts, {total_comments_saved} new comments saved")

def main():
    target_subreddits = [
        # 'AskHistorians',
        # 'science',
        #'AskScience',
        #'ChangeMyView',
        # 'explainlikeimfive',
        #'todayilearned',
         'writing',
        #'personalfinance',
        #'legaladvice'
    ]
    scraper = RedditScraper()

    logger.info(f"Starting Reddit scraper for {len(target_subreddits)} subreddits")

    for i, subreddit in enumerate(target_subreddits, 1):
        try:
            logger.info(f"Processing subreddit {i}/{len(target_subreddits)}: r/{subreddit}")
            scraper.scrape_subreddit(subreddit)
            logger.info(f"Completed r/{subreddit}, waiting 2 seconds before next subreddit")
            time.sleep(2)
        except Exception as e:
            logger.error(f"Error scraping r/{subreddit}: {e}")
            continue

    logger.info("Reddit scraping completed")

if __name__ == "__main__":
    main()