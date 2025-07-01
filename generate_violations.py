#!/usr/bin/env python3
import json
import os
import shutil

VIOLATING_POSTS_BY_SUBREDDIT = {
    "AskHistorians": {
        0: {
            "title": "Why are all these historians so stupid and biased?",
            "content": "I can't believe the garbage these so-called 'historians' are posting. You're all idiots who don't know anything about real history. And don't even get me started on how biased you all are - clearly you're just pushing your own agenda. This subreddit is a joke filled with morons who can't even spell properly.",
            "rule_violated": "Users shall behave with courtesy and politeness",
            "violation_type": "Incivility or Rudeness"
        },
        1: {
            "title": "What do you think about the current political situation?",
            "content": "I'm doing a survey for my class and need to know what everyone thinks about the current political climate. Also, what's your opinion on whether we should change the voting system? This is totally not homework, I promise!",
            "rule_violated": "Questions should be clear and specific, be asked in good faith, and seek an in-depth answer",
            "violation_type": "Poll-Type, Schoolwork, or Soapboxing"
        },
        2: {
            "title": "What if Hitler had won World War 2?",
            "content": "I'm curious about what the world would be like today if Hitler had won World War 2. How would technology be different? Would we have flying cars by now? What about space exploration?",
            "rule_violated": "Questions should be historical in nature, and ask for more than basic facts",
            "violation_type": "Non-History Question, 'Basic Facts' Request, 'What-If', or Valuation Request"
        },
        3: {
            "title": "How did the Roman Empire fall?",
            "content": "I heard that the Roman Empire fell because of lead poisoning in their water pipes. Is this true?",
            "rule_violated": "Users should be able to provide sources on request",
            "violation_type": "Sources requested: No response in reasonable time"
        },
        4: {
            "title": "What was the cause of the American Civil War?",
            "content": "The Civil War was about states' rights. That's all there is to it.",
            "rule_violated": "Answers must be in-depth and comprehensive",
            "violation_type": "Response lacks depth or does not otherwise adequately engage with the topic"
        },
        5: {
            "title": "How did ancient Egyptians build the pyramids?",
            "content": "The ancient Egyptians built the pyramids using advanced alien technology that was given to them by extraterrestrials. The evidence for this is clear if you look at the precision of the stone cutting.",
            "rule_violated": "Answers should reflect knowledge and familiarity with the topic at hand",
            "violation_type": "Response includes significant mistakes or incorrect info"
        },
        6: {
            "title": "What was life like during the Great Depression?",
            "content": "My grandfather told me stories about the Great Depression. He said everyone was really poor and had to eat beans every day. He also mentioned that people would stand in bread lines for hours just to get a loaf of bread. It must have been really hard times.",
            "rule_violated": "Answers should not be speculative or anecdotal",
            "violation_type": "Personal anecdote or ungrounded speculation"
        },
        7: {
            "title": "Why is the current government so corrupt and what can we do about it?",
            "content": "The current administration is clearly the most corrupt in history. We need to take action now to prevent this from continuing. What historical examples can we learn from to overthrow this tyranny?",
            "rule_violated": "No questions that are soapboxing, or about events and politics <20 years",
            "violation_type": "Content is soapboxing, engaging in current politics, or topic less than 20 years old"
        },
        8: {
            "title": "How did colonialism affect Africa?",
            "content": "Colonialism was the worst thing that ever happened to Africa. The Europeans were pure evil and destroyed everything good about African culture. We should all feel guilty about this and work to make reparations. The historical record clearly shows that colonialism was nothing but exploitation and genocide.",
            "rule_violated": "No political agendas or moralising in answers",
            "violation_type": "Content is soapboxing, engaging in current politics, or moralizing"
        },
        9: {
            "title": "What books should I read about World War 1?",
            "content": "You should read 'The Guns of August' by Barbara Tuchman. Here's the link: https://www.amazon.com/Guns-August-Barbara-W-Tuchman/dp/034538623X",
            "rule_violated": "Answers should not be only links or quotations",
            "violation_type": "Answer primarily consists of just quote, a book title, or a link not to an AskHistorians thread"
        },
        10: {
            "title": "How did the Industrial Revolution change society?",
            "content": "The Industrial Revolution was a period of major industrialization and innovation during the late 18th and early 19th centuries. The Industrial Revolution began in Great Britain and quickly spread throughout the world. The American Industrial Revolution commonly referred to as the Second Industrial Revolution, started sometime between 1820 and 1870. This period saw the mechanization of agriculture and textile manufacturing and a revolution in power, including steam ships and railroads, that affected social, cultural and economic conditions.",
            "rule_violated": "Answers must be original work, and cite all quotes",
            "violation_type": "Plagiarism (including use of AI like ChatGPT)"
        },
        11: {
            "title": "What was the most important battle of World War 2?",
            "content": "Why did the chicken cross the road? To get to the other side! Just like how the Allies crossed the English Channel to get to Normandy! 😂😂😂",
            "rule_violated": "Comments should not consist solely of jokes",
            "violation_type": "Joke response"
        },
        12: {
            "title": "What really happened during the Holocaust?",
            "content": "The Holocaust never actually happened. It's all a lie made up by the Jews to gain sympathy and money. The concentration camps were just work camps and the gas chambers were for delousing. The numbers are completely exaggerated.",
            "rule_violated": "Racist or bigoted comments are not tolerated here",
            "violation_type": "Bigotry, racism, Holocaust denial, or other offensive or obscene content"
        },
        13: {
            "title": "How did the ancient Greeks influence modern democracy?",
            "content": "This is a really interesting question! I'm not sure about the answer but I wanted to comment anyway. Has anyone seen the new Marvel movie? It's pretty good. Also, what's everyone's favorite pizza topping?",
            "rule_violated": "Top level comments should be answers only, and ALL comments should be on-topic, and constructive",
            "violation_type": "Clutter, digression, or content which otherwise does not constructively contribute to the thread"
        }
    }
}

def copy_subreddit_files(subreddit_name, output_dir):
    source_dir = f"data/{subreddit_name}"

    rules_source = os.path.join(source_dir, "rules.json")
    rules_dest = os.path.join(output_dir, "rules.json")
    if os.path.exists(rules_source):
        shutil.copy2(rules_source, rules_dest)
        print(f"Copied rules.json to {output_dir}/")
    else:
        print(f"Warning: rules.json not found in {source_dir}/")

    info_source = os.path.join(source_dir, "subreddit_info.json")
    info_dest = os.path.join(output_dir, "subreddit_info.json")
    if os.path.exists(info_source):
        shutil.copy2(info_source, info_dest)
        print(f"Copied subreddit_info.json to {output_dir}/")
    else:
        print(f"Warning: subreddit_info.json not found in {source_dir}/")

def create_post_json(post_data, post_id, subreddit_name):
    return {
        "kind": "t3",
        "data": {
            "approved_at_utc": None,
            "subreddit": subreddit_name,
            "selftext": post_data["content"],
            "author_fullname": "t2_violation_example_user",
            "saved": False,
            "mod_reason_title": None,
            "gilded": 0,
            "clicked": False,
            "title": post_data["title"],
            "link_flair_richtext": [],
            "subreddit_name_prefixed": f"r/{subreddit_name}",
            "hidden": False,
            "pwls": 6,
            "link_flair_css_class": None,
            "downs": 0,
            "top_awarded_type": None,
            "hide_score": False,
            "name": f"t3_{post_id}",
            "quarantine": False,
            "link_flair_text_color": "dark",
            "upvote_ratio": 0.0,
            "author_flair_background_color": None,
            "subreddit_type": "public",
            "ups": 0,
            "total_awards_received": 0,
            "media_embed": {},
            "author_flair_template_id": None,
            "is_original_content": False,
            "user_reports": [],
            "secure_media": None,
            "is_reddit_media_domain": False,
            "is_meta": False,
            "category": None,
            "secure_media_embed": {},
            "link_flair_text": None,
            "can_mod_post": False,
            "score": 0,
            "approved_by": None,
            "is_created_from_ads_ui": False,
            "author_premium": False,
            "thumbnail": "",
            "edited": False,
            "author_flair_css_class": None,
            "author_flair_richtext": [],
            "gildings": {},
            "content_categories": None,
            "is_self": True,
            "mod_note": None,
            "created": 1640995200.0,
            "link_flair_type": "text",
            "wls": 6,
            "removed_by_category": None,
            "banned_by": None,
            "author_flair_type": "text",
            "domain": f"self.{subreddit_name}",
            "allow_live_comments": False,
            "selftext_html": f"&lt;!-- SC_OFF --&gt;&lt;div class=\"md\"&gt;&lt;p&gt;{post_data['content']}&lt;/p&gt;\n&lt;/div&gt;&lt;!-- SC_ON --&gt;",
            "likes": None,
            "suggested_sort": None,
            "banned_at_utc": None,
            "view_count": None,
            "archived": False,
            "no_follow": True,
            "is_crosspostable": False,
            "pinned": False,
            "over_18": False,
            "all_awardings": [],
            "awarders": [],
            "media_only": False,
            "can_gild": False,
            "spoiler": False,
            "locked": False,
            "author_flair_text": None,
            "treatment_tags": [],
            "visited": False,
            "removed_by": None,
            "num_reports": None,
            "distinguished": None,
            "subreddit_id": f"t5_{subreddit_name.lower()}",
            "author_is_blocked": False,
            "mod_reason_by": None,
            "removal_reason": None,
            "link_flair_background_color": "",
            "id": post_id,
            "is_robot_indexable": True,
            "report_reasons": None,
            "author": "violation_example_user",
            "discussion_type": None,
            "num_comments": 0,
            "send_replies": True,
            "contest_mode": False,
            "mod_reports": [],
            "author_patreon_flair": False,
            "author_flair_text_color": None,
            "permalink": f"/r/{subreddit_name}/comments/{post_id}/",
            "stickied": False,
            "url": f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}/",
            "subreddit_subscribers": 1000000,
            "created_utc": 1640995200.0,
            "num_crossposts": 0,
            "media": None,
            "is_video": False
        }
    }

def create_comments_json(post_id, subreddit_name):
    return []

def generate_violations_for_subreddit(subreddit_name):
    if subreddit_name not in VIOLATING_POSTS_BY_SUBREDDIT:
        print(f"Error: No violating posts defined for subreddit '{subreddit_name}'")
        return False

    violating_posts = VIOLATING_POSTS_BY_SUBREDDIT[subreddit_name]

    output_dir = f"data/Viol_{subreddit_name}"
    os.makedirs(output_dir, exist_ok=True)

    copy_subreddit_files(subreddit_name, output_dir)

    for rule_num, post_data in violating_posts.items():
        post_id = f"violation_rule_{rule_num}_example_1"
        post_dir = os.path.join(output_dir, post_id)
        os.makedirs(post_dir, exist_ok=True)

        post_json = create_post_json(post_data, post_id, subreddit_name)
        post_filepath = os.path.join(post_dir, "post.json")
        with open(post_filepath, 'w', encoding='utf-8') as f:
            json.dump(post_json, f, indent=2, ensure_ascii=False)

        comments_json = create_comments_json(post_id, subreddit_name)
        comments_filepath = os.path.join(post_dir, "comments.json")
        with open(comments_filepath, 'w', encoding='utf-8') as f:
            json.dump(comments_json, f, indent=2, ensure_ascii=False)

        print(f"Created {post_id}/ with post.json and comments.json")

    print(f"\nGenerated {len(violating_posts)} violating posts in {output_dir}/")
    return True

def main():
    subreddit_name = "AskHistorians"
    print(f"Generating violations for subreddit: {subreddit_name}")
    success = generate_violations_for_subreddit(subreddit_name)

    if success:
        print(f"Successfully generated violations for {subreddit_name}")
    else:
        print(f"Failed to generate violations for {subreddit_name}")

if __name__ == "__main__":
    main()