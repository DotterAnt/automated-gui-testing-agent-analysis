"""Result provenance checks requiring only the Python standard library."""
import json
import unittest
from extract import observed_steps, parse_steps, first_attempt_steps

ACTIONS = ['Open', 'Edit', 'Save', 'Reopen', 'Print']

class ResultProvenanceTests(unittest.TestCase):
    def test_diagnostic_summary_is_not_a_whole_test_pass(self):
        value = {'runKind': 'Diagnostic', 'qualifying': False,
                 'summary': {'total': 5, 'passed': 5, 'failed': 0},
                 'steps': [{'stepIndex': i, 'status': 'PASS'} for i in range(1, 6)]}
        self.assertEqual(parse_steps(value, ACTIONS), {})
        self.assertEqual(observed_steps(json.dumps(value), ACTIONS), {})

    def test_first_attempt_success_counts_separately(self):
        value = {'runKind': 'Diagnostic', 'qualifying': False, 'stepIndex': 2,
                 'status': 'FIRST_ATTEMPT_SUCCESS', 'countsAsSuccessfulStep': True}
        text = json.dumps([{'type': 'text', 'text': json.dumps(value)}, {'type': 'image', 'data': 'ignored'}])
        self.assertEqual(first_attempt_steps(text, ACTIONS), {2: 'PASS'})
        self.assertEqual(observed_steps(text, ACTIONS), {})

    def test_recovery_is_not_a_first_attempt(self):
        value = {'stepIndex': 2, 'status': 'RECOVERY_SUCCESS', 'countsAsSuccessfulStep': False}
        self.assertEqual(first_attempt_steps(json.dumps(value), ACTIONS), {})

    def test_input_content_blocks_preserve_first_attempt_without_fabricating_whole_pass(self):
        value = {'runKind': 'Diagnostic', 'qualifying': False, 'stepIndex': 2,
                 'status': 'FIRST_ATTEMPT_SUCCESS', 'countsAsSuccessfulStep': True}
        text = json.dumps([{'type': 'input_text', 'text': 'Wall time: 1 seconds\nOutput:'},
                           {'type': 'input_text', 'text': json.dumps(value)},
                           {'type': 'input_image', 'image_url': 'ignored'}])
        self.assertEqual(first_attempt_steps(text, ACTIONS), {2: 'PASS'})
        self.assertEqual(observed_steps(text, ACTIONS), {})

    def test_input_content_blocks_preserve_qualifying_result(self):
        value = {'runKind': 'Replay', 'qualifying': True,
                 'steps': [{'stepIndex': i, 'status': 'PASS'} for i in range(1, 6)]}
        text = json.dumps([{'type': 'input_text', 'text': json.dumps(value)}])
        self.assertEqual(observed_steps(text, ACTIONS), dict.fromkeys(range(1, 6), 'PASS'))

    def test_failed_verify_keeps_successful_prefix_measurements(self):
        value = {'runKind': 'Diagnostic', 'qualifying': False, 'status': 'DIAGNOSTIC_FAILURE',
                 'firstAttemptSuccesses': [{'stepIndex': 1, 'status': 'FIRST_ATTEMPT_SUCCESS',
                                           'countsAsSuccessfulStep': True}]}
        self.assertEqual(first_attempt_steps(json.dumps(value), ACTIONS), {1: 'PASS'})
        self.assertEqual(observed_steps(json.dumps(value), ACTIONS), {})

    def test_qualifying_mcp_result_remains_a_pass(self):
        value = {'runKind': 'Replay', 'qualifying': True,
                 'steps': [{'stepIndex': i, 'status': 'PASS'} for i in range(1, 6)]}
        text = json.dumps({'content': [{'type': 'text', 'text': json.dumps(value)}]})
        self.assertEqual(observed_steps(text, ACTIONS), dict.fromkeys(range(1, 6), 'PASS'))

    def test_legacy_summary_remains_supported(self):
        text = '{"summary":{"total":5,"passed":5,"failed":0},"steps":[... truncated'
        self.assertEqual(observed_steps(text, ACTIONS), dict.fromkeys(range(1, 6), 'PASS'))

if __name__ == '__main__':
    unittest.main()
