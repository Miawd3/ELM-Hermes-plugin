import unittest
from types import SimpleNamespace
from elm_plugin.public_search_agent import search, parse_queries, SearchAgentError

class FakeLLM:
    def __init__(self, text='{"queries":["door texture","painted door"]}', error=False):
        self.text, self.error, self.calls = text, error, []
    def complete(self, **kwargs):
        self.calls.append(kwargs)
        if self.error: raise RuntimeError('SECRET_PROVIDER_ERROR')
        return SimpleNamespace(text=self.text, provider='fake', model='fake-model')

class PublicAgentTests(unittest.TestCase):
    def run_agent(self, llm, **kwargs):
        calls=[]
        result=search(SimpleNamespace(llm=llm), 'door', lambda q: calls.append(q) or [{'synthetic':q}], **kwargs)
        return result,calls
    def test_local_default_no_model(self):
        llm=FakeLLM();r,c=self.run_agent(llm)
        self.assertEqual(llm.calls,[]);self.assertEqual(c,['door']);self.assertEqual(r['status'],'local_only')
    def test_real_execution_path_calls_public_api(self):
        llm=FakeLLM();r,c=self.run_agent(llm,allow_query_egress=True)
        self.assertEqual(len(llm.calls),1);self.assertEqual(len(c),3)
        self.assertEqual(r['status'],'agent_completed')
        self.assertEqual(llm.calls[0]['messages'][1],{'role':'user','content':'door'})
        self.assertEqual(llm.calls[0]['max_tokens'],192)
        self.assertEqual(llm.calls[0]['timeout'],15)
        self.assertNotIn('provider',llm.calls[0]);self.assertNotIn('model',llm.calls[0])
    def test_invalid_plan_falls_back_without_retry(self):
        llm=FakeLLM('{"queries":[],"scope":"all"}');r,c=self.run_agent(llm,allow_query_egress=True)
        self.assertEqual(len(llm.calls),1);self.assertEqual(c,['door']);self.assertEqual(r['status'],'agent_unavailable_local_fallback')
    def test_provider_error_not_leaked(self):
        r,c=self.run_agent(FakeLLM(error=True),allow_query_egress=True)
        self.assertNotIn('SECRET',str(r));self.assertEqual(c,['door'])
    def test_duplicate_queries_removed(self):
        r,c=self.run_agent(FakeLLM('{"queries":[" DOOR ","door"]}'),allow_query_egress=True)
        self.assertEqual(c,['door'])
    def test_invalid_inputs_never_call_provider(self):
        llm=FakeLLM()
        for query in ['', 'a'*513, None]:
            with self.assertRaises(SearchAgentError):search(SimpleNamespace(llm=llm),query,lambda q:[],allow_query_egress=True)
        self.assertEqual(llm.calls,[])
    def test_invalid_plans(self):
        for text in ['{"queries":[],"queries":[]}', '{"queries":[1]}', '{"queries":["a","b","c"]}', 'not json', '{"queries":[""]}']:
            with self.assertRaises(SearchAgentError):parse_queries(text)
    def test_scope_callback_refusal_propagates(self):
        def deny(q):raise PermissionError('scope')
        with self.assertRaises(PermissionError):search(SimpleNamespace(llm=FakeLLM()),'door',deny)

if __name__=='__main__':unittest.main()
