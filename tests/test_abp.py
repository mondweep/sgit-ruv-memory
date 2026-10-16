import copy, unittest
from sgit_ruv_memory.abp import compile_abp, example_abp

class ABPCompilerTest(unittest.TestCase):
    def test_mapping_and_scoped_effects(self):
        for mandate,effect in [('yes','allow'),('no','deny'),('approval','require_approval')]:
            a=example_abp()
            for row in a['roles'][0]['rows']:
                row.update(mandate=mandate,barrier='test boundary')
            out=compile_abp(a,{'demo','other'})
            self.assertEqual(len(out['rules']),4)
            for r in out['rules']:
                self.assertEqual(r['effect'],effect)
                self.assertEqual(r['resources'],['demo'])
                self.assertEqual(r['principals'],['local-agent'])
            self.assertEqual({r['actions'][0] for r in out['rules']},
                             {'memory.checkpoint','memory.restore','memory.inspect','memory.delete'})

    def test_reject_invalid_policy_matrix(self):
        mutations=[lambda a:a.update(adapter_profile='unknown'),
                   lambda a:a.update(owner=''),
                   lambda a:a.update(valid_until='2027-01-01T12:00:00'),
                   lambda a:a['roles'].append(copy.deepcopy(a['roles'][0])),
                   lambda a:a['roles'][0]['rows'].append(copy.deepcopy(a['roles'][0]['rows'][0])),
                   lambda a:a['roles'][0]['rows'][0].update(capability='execute.process.host'),
                   lambda a:a['roles'][0]['rows'][0].update(instances=['*']),
                   lambda a:a['roles'][0]['rows'][0].update(instances=[]),
                   lambda a:a['roles'][0]['rows'][0].update(instances=['unknown']),
                   lambda a:a['roles'][0]['rows'][0].update(mandate='maybe'),
                   lambda a:a['roles'][0]['rows'][0].update(mandate='no'),
                   lambda a:a['roles'][0]['rows'][0].update(reach='true'),
                   lambda a:a['roles'][0]['rows'][0].update(reach=False),
                   lambda a:a['roles'][0]['rows'][0].update(resource=['demo'])]
        for mutate in mutations:
            a=example_abp();mutate(a)
            with self.subTest(policy=a),self.assertRaises(ValueError):compile_abp(a,{'demo'})

    def test_hashes_bind_changes_not_key_order(self):
        a=example_abp();b=dict(reversed(list(a.items())))
        self.assertEqual(compile_abp(a,{'demo'})['abp_sha256'],compile_abp(b,{'demo'})['abp_sha256'])
        b=copy.deepcopy(a);b['roles'][0]['rows'][0]['why']='changed reason'
        self.assertNotEqual(compile_abp(a,{'demo'})['abp_sha256'],compile_abp(b,{'demo'})['abp_sha256'])

    def test_no_reach_means_no_grant(self):
        a=example_abp();a['roles'][0]['rows'][0].update(reach=False,mandate='no',barrier='unreachable')
        self.assertFalse(compile_abp(a,{'demo'})['rules'][0]['enabled'])
