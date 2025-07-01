import os
import sys
import math
from typing import Dict, Any, List
from dotenv import load_dotenv

from agents.base_agent import BaseAgent




class ConfidenceRuleAgent(BaseAgent):
    def __init__(self, model="gpt-4o-mini", temperature=0, confidence_method="log_odds"):
        super().__init__(model=model, temperature=temperature, max_tokens=1)
        self.response_format = None
        self.confidence_method = confidence_method  # "log_odds" or "normalized_diff"

    def get_system_prompt(self) -> str:
        return """You are a rule violation detection agent. You will receive exactly one rule and one target (post or comment) to evaluate.

Your task is to determine if the target violates the rule.

CRITICAL INSTRUCTIONS:
- You MUST respond with exactly one character: Y or N
- Y means the rule IS violated
- N means the rule is NOT violated
- Do not include any explanation, punctuation, or additional text
- Do not respond in JSON format
- Your entire response must be exactly one letter: Y or N"""

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rule = data.get('rule', '')
        target = data.get('target', '')

        if not rule or not target:
            return {
                "error": True,
                "message": "Both 'rule' and 'target' are required"
            }

        user_message = f"Rule: {rule}\n\nTarget to evaluate: {target}\n\nDoes the target violate the rule? Answer Y or N only."

        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": user_message}
        ]

        return self._make_confidence_api_call(messages)

    def _make_confidence_api_call(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=1,
                logprobs=True,
                top_logprobs=2
            )

            content = response.choices[0].message.content.strip()
            logprobs = response.choices[0].logprobs

            if not logprobs or not logprobs.content:
                return {
                    "error": True,
                    "message": "No log probabilities available"
                }

            token_logprob = logprobs.content[0]
            confidence = self._calculate_confidence(token_logprob)

            return {
                "answer": content,
                "confidence": confidence,
                "raw_logprob": token_logprob.logprob,
                "token": token_logprob.token,
                "top_logprobs": [{"token": lp.token, "logprob": lp.logprob} for lp in token_logprob.top_logprobs] if token_logprob.top_logprobs else []
            }

        except Exception as e:
            return {
                "error": True,
                "message": str(e)
            }

    def _calculate_confidence(self, token_logprob) -> float:
        if self.confidence_method == "log_odds":
            return self._calculate_confidence_log_odds(token_logprob)
        else:
            return self._calculate_confidence_normalized_diff(token_logprob)

    def _calculate_confidence_log_odds(self, token_logprob) -> float:
        if not token_logprob.top_logprobs or len(token_logprob.top_logprobs) < 2:
            probability = math.exp(token_logprob.logprob)
            return probability

        log_p_y = None
        log_p_n = None

        for logprob_item in [token_logprob] + token_logprob.top_logprobs:
            if logprob_item.token.upper() == 'Y':
                log_p_y = logprob_item.logprob
            elif logprob_item.token.upper() == 'N':
                log_p_n = logprob_item.logprob

        if log_p_y is not None and log_p_n is not None:
            log_odds = log_p_y - log_p_n
            confidence = 1 / (1 + math.exp(-log_odds))
        else:
            probability = math.exp(token_logprob.logprob)
            confidence = probability

        return round(confidence, 4)

    def _calculate_confidence_normalized_diff(self, token_logprob) -> float:
        probability = math.exp(token_logprob.logprob)

        if token_logprob.top_logprobs and len(token_logprob.top_logprobs) >= 2:
            top_prob = math.exp(token_logprob.logprob)
            second_prob = math.exp(token_logprob.top_logprobs[1].logprob)
            confidence = (top_prob - second_prob) / (top_prob + second_prob)
        else:
            confidence = probability

        return round(confidence, 4)


class ConfidenceRuleAgentTester:
    def __init__(self):
        self.agent_log_odds = ConfidenceRuleAgent(confidence_method="log_odds")
        self.agent_normalized = ConfidenceRuleAgent(confidence_method="normalized_diff")
        self.test_cases = self._generate_test_cases()

    def _generate_test_cases(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "Clear Violation - Explicit Spam",
                "rule": "No spam or promotional content",
                "target": "BUY NOW!!! 50% OFF VIAGRA PILLS!!! CLICK HERE: www.spam-site.com",
                "expected_answer": "Y",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Clear Non-Violation - Normal Discussion",
                "rule": "No spam or promotional content",
                "target": "I really enjoyed reading this book. The character development was excellent and the plot kept me engaged throughout.",
                "expected_answer": "N",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Clear Violation - Obvious Hate Speech",
                "rule": "No hate speech or discriminatory language",
                "target": "All [ethnic group] are stupid and should be banned from this country. I hate them all.",
                "expected_answer": "Y",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Clear Non-Violation - Factual Statement",
                "rule": "No misinformation about health",
                "target": "According to the CDC, washing your hands frequently can help prevent the spread of germs.",
                "expected_answer": "N",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Ambiguous - Borderline Self-Promotion",
                "rule": "No self-promotion or advertising",
                "target": "I just finished writing my first blog post about my experience learning Python. It was challenging but rewarding.",
                "expected_answer": "N",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Ambiguous - Subjective Opinion",
                "rule": "No off-topic discussions",
                "target": "This reminds me of something that happened to me last week, which is kind of related but not exactly the same situation.",
                "expected_answer": "N",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Ambiguous - Subtle Rudeness",
                "rule": "Be respectful and civil",
                "target": "Well, I guess if you actually bothered to read the documentation, you might understand why your approach doesn't work.",
                "expected_answer": "Y",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Ambiguous - Borderline Medical Advice",
                "rule": "No medical advice or health claims",
                "target": "I had similar symptoms and found that drinking chamomile tea before bed helped me sleep better. Maybe it could work for you too?",
                "expected_answer": "Y",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Clear Violation - Explicit Harassment",
                "rule": "No harassment or personal attacks",
                "target": "You're an idiot and everyone knows it. Stop posting your stupid opinions here, nobody wants to hear from you.",
                "expected_answer": "Y",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Clear Non-Violation - Constructive Feedback",
                "rule": "No harassment or personal attacks",
                "target": "I respectfully disagree with your analysis. Here are some additional factors you might want to consider in your argument.",
                "expected_answer": "N",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Ambiguous - Sarcastic Tone",
                "rule": "Maintain a professional tone",
                "target": "Oh wow, what a brilliant solution! I'm sure nobody has ever thought of trying that before.",
                "expected_answer": "Y",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Ambiguous - Borderline Political",
                "rule": "No political discussions",
                "target": "The recent changes in education funding really affect teachers' ability to provide quality instruction.",
                "expected_answer": "Y",
                "expected_confidence": "low",
                "category": "ambiguous"
            },
            {
                "name": "Clear Violation - Explicit Profanity",
                "rule": "No profanity or vulgar language",
                "target": "This is f***ing ridiculous, what the hell is wrong with you people? This s*** doesn't make any damn sense.",
                "expected_answer": "Y",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Clear Non-Violation - Technical Discussion",
                "rule": "Stay on topic about programming",
                "target": "Here's a Python function that solves the problem: def calculate_sum(numbers): return sum(numbers)",
                "expected_answer": "N",
                "expected_confidence": "high",
                "category": "clear_cut"
            },
            {
                "name": "Ambiguous - Indirect Criticism",
                "rule": "No personal attacks",
                "target": "Some people clearly don't understand the basics of how this system works, which explains the confusion in this thread.",
                "expected_answer": "N",
                "expected_confidence": "low",
                "category": "ambiguous"
            }
        ]

    def run_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        print(f"\n--- Testing: {test_case['name']} ---")
        print(f"Category: {test_case['category']}")
        print(f"Rule: {test_case['rule']}")
        print(f"Target: {test_case['target'][:100]}{'...' if len(test_case['target']) > 100 else ''}")

        result_log_odds = self.agent_log_odds.process({
            'rule': test_case['rule'],
            'target': test_case['target']
        })

        result_normalized = self.agent_normalized.process({
            'rule': test_case['rule'],
            'target': test_case['target']
        })

        if result_log_odds.get('error') or result_normalized.get('error'):
            print(f"Error: {result_log_odds.get('message', '')} {result_normalized.get('message', '')}")
            return {**test_case, 'result_log_odds': result_log_odds, 'result_normalized': result_normalized, 'test_passed': False}

        answer_log_odds = result_log_odds['answer']
        confidence_log_odds = result_log_odds['confidence']
        answer_normalized = result_normalized['answer']
        confidence_normalized = result_normalized['confidence']

        print(f"Answer: {answer_log_odds} (both methods should match)")
        print(f"Confidence (Log Odds): {confidence_log_odds}")
        print(f"Confidence (Normalized): {confidence_normalized}")
        print(f"Expected: {test_case['expected_answer']} (confidence: {test_case['expected_confidence']})")

        answer_correct = answer_log_odds == test_case['expected_answer']
        confidence_appropriate_log_odds = (
            (test_case['expected_confidence'] == 'high' and confidence_log_odds > 0.7) or
            (test_case['expected_confidence'] == 'low' and confidence_log_odds < 0.7)
        )
        confidence_appropriate_normalized = (
            (test_case['expected_confidence'] == 'high' and confidence_normalized > 0.7) or
            (test_case['expected_confidence'] == 'low' and confidence_normalized < 0.7)
        )

        test_passed_log_odds = answer_correct and confidence_appropriate_log_odds
        test_passed_normalized = answer_correct and confidence_appropriate_normalized

        print(f"Answer Correct: {answer_correct}")
        print(f"Confidence Appropriate (Log Odds): {confidence_appropriate_log_odds}")
        print(f"Confidence Appropriate (Normalized): {confidence_appropriate_normalized}")
        print(f"Test Passed (Log Odds): {test_passed_log_odds}")
        print(f"Test Passed (Normalized): {test_passed_normalized}")

        return {
            **test_case,
            'result_log_odds': result_log_odds,
            'result_normalized': result_normalized,
            'answer_correct': answer_correct,
            'confidence_appropriate_log_odds': confidence_appropriate_log_odds,
            'confidence_appropriate_normalized': confidence_appropriate_normalized,
            'test_passed_log_odds': test_passed_log_odds,
            'test_passed_normalized': test_passed_normalized
        }

    def run_all_tests(self) -> Dict[str, Any]:
        results = []
        total_tests = len(self.test_cases)
        passed_tests_log_odds = 0
        passed_tests_normalized = 0

        print("="*80)
        print("CONFIDENCE RULE AGENT TESTING - COMPARING BOTH METHODS")
        print("="*80)

        for test_case in self.test_cases:
            result = self.run_test(test_case)
            results.append(result)
            if result['test_passed_log_odds']:
                passed_tests_log_odds += 1
            if result['test_passed_normalized']:
                passed_tests_normalized += 1

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total Tests: {total_tests}")
        print(f"Passed (Log Odds Method): {passed_tests_log_odds}")
        print(f"Passed (Normalized Method): {passed_tests_normalized}")
        print(f"Success Rate (Log Odds): {(passed_tests_log_odds / total_tests) * 100:.1f}%")
        print(f"Success Rate (Normalized): {(passed_tests_normalized / total_tests) * 100:.1f}%")

        clear_cut_results = [r for r in results if r['category'] == 'clear_cut']
        ambiguous_results = [r for r in results if r['category'] == 'ambiguous']

        clear_cut_passed_log_odds = sum(1 for r in clear_cut_results if r['test_passed_log_odds'])
        ambiguous_passed_log_odds = sum(1 for r in ambiguous_results if r['test_passed_log_odds'])
        clear_cut_passed_normalized = sum(1 for r in clear_cut_results if r['test_passed_normalized'])
        ambiguous_passed_normalized = sum(1 for r in ambiguous_results if r['test_passed_normalized'])

        print(f"\nClear-cut cases (Log Odds): {clear_cut_passed_log_odds}/{len(clear_cut_results)} passed")
        print(f"Ambiguous cases (Log Odds): {ambiguous_passed_log_odds}/{len(ambiguous_results)} passed")
        print(f"Clear-cut cases (Normalized): {clear_cut_passed_normalized}/{len(clear_cut_results)} passed")
        print(f"Ambiguous cases (Normalized): {ambiguous_passed_normalized}/{len(ambiguous_results)} passed")

        avg_confidence_clear_log_odds = sum(r['result_log_odds']['confidence'] for r in clear_cut_results if not r['result_log_odds'].get('error')) / len(clear_cut_results)
        avg_confidence_ambiguous_log_odds = sum(r['result_log_odds']['confidence'] for r in ambiguous_results if not r['result_log_odds'].get('error')) / len(ambiguous_results)
        avg_confidence_clear_normalized = sum(r['result_normalized']['confidence'] for r in clear_cut_results if not r['result_normalized'].get('error')) / len(clear_cut_results)
        avg_confidence_ambiguous_normalized = sum(r['result_normalized']['confidence'] for r in ambiguous_results if not r['result_normalized'].get('error')) / len(ambiguous_results)

        print(f"\nAverage confidence - Clear-cut (Log Odds): {avg_confidence_clear_log_odds:.3f}")
        print(f"Average confidence - Ambiguous (Log Odds): {avg_confidence_ambiguous_log_odds:.3f}")
        print(f"Average confidence - Clear-cut (Normalized): {avg_confidence_clear_normalized:.3f}")
        print(f"Average confidence - Ambiguous (Normalized): {avg_confidence_ambiguous_normalized:.3f}")

        return {
            'total_tests': total_tests,
            'passed_tests_log_odds': passed_tests_log_odds,
            'passed_tests_normalized': passed_tests_normalized,
            'success_rate_log_odds': (passed_tests_log_odds / total_tests) * 100,
            'success_rate_normalized': (passed_tests_normalized / total_tests) * 100,
            'avg_confidence_clear_log_odds': avg_confidence_clear_log_odds,
            'avg_confidence_ambiguous_log_odds': avg_confidence_ambiguous_log_odds,
            'avg_confidence_clear_normalized': avg_confidence_clear_normalized,
            'avg_confidence_ambiguous_normalized': avg_confidence_ambiguous_normalized,
            'detailed_results': results
        }


def main():
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY environment variable is not set")
        print("Please set it in your .env file or environment")
        return

    tester = ConfidenceRuleAgentTester()
    results = tester.run_all_tests()

    print("\n" + "="*80)
    print("DETAILED ANALYSIS")
    print("="*80)

    failed_tests_log_odds = [r for r in results['detailed_results'] if not r['test_passed_log_odds']]
    failed_tests_normalized = [r for r in results['detailed_results'] if not r['test_passed_normalized']]

    if failed_tests_log_odds:
        print(f"\nFailed Tests - Log Odds Method ({len(failed_tests_log_odds)}):")
        for test in failed_tests_log_odds:
            print(f"- {test['name']}: Expected {test['expected_answer']}, Got {test['result_log_odds']['answer']}, Confidence: {test['result_log_odds']['confidence']}")

    if failed_tests_normalized:
        print(f"\nFailed Tests - Normalized Method ({len(failed_tests_normalized)}):")
        for test in failed_tests_normalized:
            print(f"- {test['name']}: Expected {test['expected_answer']}, Got {test['result_normalized']['answer']}, Confidence: {test['result_normalized']['confidence']}")


if __name__ == "__main__":
    load_dotenv()
    main()