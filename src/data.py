import os
import json

from pathlib import Path

class DataLoader:
    def __init__(self, data_dir="data", subreddit_name=None, post_ids=None):
        self.data_dir = Path(data_dir)
        self.subreddit_name = subreddit_name
        self.post_ids = post_ids
        self.raw_data = None

    def load_raw_data(self):
        if self.subreddit_name:
            subreddit_dir = self.data_dir / self.subreddit_name
            if not subreddit_dir.exists() or not subreddit_dir.is_dir():
                raise FileNotFoundError(f"Subreddit directory '{self.subreddit_name}' not found in {self.data_dir}")
        else:
            subreddits = [d for d in self.data_dir.iterdir() if d.is_dir() and not d.name.endswith('.json')]
            if not subreddits:
                raise FileNotFoundError(f"No subreddit directories found in {self.data_dir}")
            subreddit_dir = subreddits[0]
            self.subreddit_name = subreddit_dir.name

        with open(subreddit_dir / "subreddit_info.json", "r") as f:
            subreddit_info = json.load(f)

        with open(subreddit_dir / "rules.json", "r") as f:
            rules = json.load(f)

        post_dirs = [d for d in subreddit_dir.iterdir() if d.is_dir()]
        if not post_dirs:
            raise FileNotFoundError(f"No post directories found in {subreddit_dir}")

        if self.post_ids:
            filtered_post_dirs = []
            for post_dir in post_dirs:
                post_file = post_dir / "post.json"
                if post_file.exists():
                    try:
                        with open(post_file, "r") as f:
                            post_data = json.load(f)

                        post_id = post_data["data"].get("id", "")

                        if post_id in self.post_ids:
                            filtered_post_dirs.append(post_dir)
                    except Exception as e:
                        # print(f"Warning: Could not read post data from {post_file}: {e}")
                        continue

            if not filtered_post_dirs:
                raise FileNotFoundError(f"No posts found with IDs {self.post_ids} in subreddit {self.subreddit_name}")
            post_dirs = filtered_post_dirs

        posts = []
        all_comments = []

        for post_dir in post_dirs:
            with open(post_dir / "post.json", "r") as f:
                post_data = json.load(f)

            post = {
                "id": post_data["data"].get("id", ""),
                "title": post_data["data"].get("title", ""),
                "body": post_data["data"].get("selftext", "")
            }

            comments = []
            comments_file = post_dir / "comments.json"
            if comments_file.exists():
                with open(comments_file, "r") as f:
                    comments_data = json.load(f)
                    comments = [comment.get("body", "") for comment in comments_data if comment.get("body")]

            posts.append(post)
            all_comments.extend(comments)

        self.raw_data = {
            "subreddit_name": self.subreddit_name,
            "subreddit_info": subreddit_info,
            "rules": rules,
            "posts": posts,
            "comments": all_comments
        }

        return self.raw_data

    def get_formatted_data(self):
        if self.raw_data is None:
            self.load_raw_data()

        formatted_rules = []
        rules_data = self.raw_data["rules"]

        # Handle nested structure where rules might be under a 'rules' key
        if isinstance(rules_data, dict) and "rules" in rules_data:
            rules_list = rules_data["rules"]
        elif isinstance(rules_data, list):
            rules_list = rules_data
        elif isinstance(rules_data, dict):
            # If it's a dict but not with 'rules' key, treat values as rules
            rules_list = list(rules_data.values())
        else:
            rules_list = []

        for idx, rule in enumerate(rules_list):
            if isinstance(rule, dict):
                formatted_rule = {
                    "id": f"rule_{idx+1}",
                    "kind": rule.get("kind", ""),
                    "description": rule.get("description", ""),
                    "short_name": rule.get("short_name", ""),
                    "violation_reason": rule.get("violation_reason", ""),
                    "priority": rule.get("priority", 0)
                }
                formatted_rules.append(formatted_rule)

        return {
            "subreddit_name": self.raw_data["subreddit_name"],
            "subreddit_info": self.raw_data["subreddit_info"],
            "rules": formatted_rules,
            "posts": self.raw_data["posts"],
            "comments": self.raw_data["comments"]
        }

if __name__ == "__main__":
    loader = DataLoader(subreddit_name="Viol_AskHistorians", post_ids=["violation_rule_0_example_1"])
    #loader.load_raw_data()
    data = loader.get_formatted_data()
    print(json.dumps(data, indent=2))

    loader = DataLoader(subreddit_name="AskHistorians", post_ids=["1lk9keh"])
    #loader.load_raw_data()
    data = loader.get_formatted_data()
    print(json.dumps(data, indent=2))