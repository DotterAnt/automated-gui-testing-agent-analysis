import unittest
from model_gap_current import counterfactuals, average_apps


class ModelGapTests(unittest.TestCase):
    def test_decomposition_adds_to_total_and_averages_both_orders(self):
        old={'uncached_input_tokens':200000,'cached_input_tokens':4000000,'output_tokens':20000}
        new={'uncached_input_tokens':100000,'cached_input_tokens':3000000,'output_tokens':10000}
        cells, effect=counterfactuals(old,new)
        self.assertEqual([round(c['total_usd'],3) for c in cells],[3.6,1,2.3,.6])
        self.assertAlmostEqual(effect['price_effect_usd'],2.15)
        self.assertAlmostEqual(effect['usage_effect_usd'],.85)
        self.assertAlmostEqual(effect['price_effect_usd']+effect['usage_effect_usd'],effect['total_reduction_usd'])
        self.assertAlmostEqual(effect['price_share']+effect['usage_share'],1)
        self.assertEqual(cells[1]['usage_model'],'gpt-5.5')
        self.assertEqual(cells[1]['price_model'],'gpt-6.1-sol')

    def test_metric_means_give_each_application_equal_weight(self):
        rows=[{'app':'Excel','value':1}]*5+[{'app':'PowerPoint','value':4},{'app':'Word','value':7}]
        self.assertEqual(average_apps(rows,'value'),4)


if __name__=='__main__':unittest.main()
