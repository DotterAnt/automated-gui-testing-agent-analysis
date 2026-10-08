import unittest
from cost_current import price_run, cost_summaries


class CostTests(unittest.TestCase):
    def run_record(self, **changes):
        run = {'id': 'R1', 'model': 'gpt-6.1-sol', 'setup': 'mcp', 'app': 'Excel',
               'success': True, 'minutes': 10, 'input_tokens': 1000000,
               'cached_input_tokens': 800000, 'output_tokens': 100000,
               'reasoning_output_tokens': 60000, 'total_tokens': 1100000,
               'usage': {'line': 10, 'cache_write_input_tokens': 100000},
               'file': 'example.jsonl', 'sha256': 'example'}
        run.update(changes)
        return run

    def test_input_partition_write_replaces_ordinary_charge_and_reasoning_not_extra(self):
        row = price_run(self.run_record(), {'max_request_input_tokens': 200000})
        self.assertEqual(row['ordinary_input_tokens'], 100000)
        self.assertAlmostEqual(row['ordinary_input_usd'], .2)
        self.assertAlmostEqual(row['cached_read_usd'], .08)
        self.assertAlmostEqual(row['cache_write_usd'], .25)
        self.assertAlmostEqual(row['output_usd'], 1)
        self.assertAlmostEqual(row['total_usd'], 1.53)
        self.assertAlmostEqual(row['no_cache_usd'], 3)

    def test_cumulative_input_above_threshold_does_not_trigger_request_surcharge(self):
        price_run(self.run_record(), {'max_request_input_tokens': 272000})
        with self.assertRaisesRegex(ValueError, 'long-context'):
            price_run(self.run_record(), {'max_request_input_tokens': 272001})

    def test_invalid_partition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'partition'):
            price_run(self.run_record(cached_input_tokens=950000), {'max_request_input_tokens': 100000})

    def test_uneven_app_counts_are_balanced_and_zero_success_cost_is_undefined(self):
        rows=[]
        for app, costs in [('Excel', [1,1,1]), ('PowerPoint', [4]), ('Word', [7])]:
            for cost in costs:
                row=price_run(self.run_record(model='gpt-5.6-luna', setup='native', app=app, success=False),
                              {'max_request_input_tokens': 200000})
                row['total_usd']=cost
                rows.append(row)
        cohorts, balanced, byapp = cost_summaries(rows)
        self.assertAlmostEqual(cohorts[0]['mean_total_usd'], 2.8)
        self.assertAlmostEqual(balanced[0]['mean_total_usd'], 4)
        self.assertEqual(cohorts[0]['total_observed_usd'], 14)
        self.assertIsNone(cohorts[0]['spent_usd_per_observed_success'])
        self.assertEqual(len(byapp), 3)


if __name__ == '__main__':
    unittest.main()
