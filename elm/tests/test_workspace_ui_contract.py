"""Capture an actual HTTP/RecordStore wire, not a fabricated backend fixture."""
import json
import unittest
import test_workspace_api as api_fixtures


class WorkspaceUiContractTests(unittest.TestCase):
    setUp = api_fixtures.WorkspaceApiTests.setUp
    client = api_fixtures.WorkspaceApiTests.client

    def test_real_http_dependency_pin_wire_for_renderer(self):
        client = self.client()
        p = '/api/plugins/elm'
        self.assertEqual(client.post(p+'/setup', json={'confirm':True}).status_code, 200)
        current = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        scope = current['selected_scope_id']
        response = client.post(p+'/record', json=dict(scope_id=scope, title='Fictional release source',
            text='Amber rollout needs a signed rollback.', domain='work', kind='explicit_fact',
            basis='explicit_statement', sources=[{'ref':'fictional:renderer-contract'}], state='approved'))
        self.assertEqual(response.status_code, 200, response.text)
        source = response.json()['result']
        before = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        response = client.post(p+'/record', json=dict(scope_id=scope, title='Fictional source-backed summary',
            text='The fictional source requires a signed rollback for amber rollout.', domain='work', kind='summary',
            basis='inference', sources=[{'ref':'record:'+source['id'], 'revision':source['revision'], 'quote':source['text']}],
            dependencies=[{'id':source['id'],'revision':source['revision']}]))
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        after = client.get(p+'/overview', params={'session_id':'chat-a'}).json()
        self.assertEqual(result['dependencies'], [{'id':source['id'],'revision':source['revision']}])
        self.assertEqual(after['records'][-1]['dependencies'], result['dependencies'])
        print('UI_WIRE_FIXTURE:' + json.dumps(dict(
            qualification='Actual ASGI/RecordStore schema with fictional human-authored records; not model generation or host authentication',
            before=before, result=result, after=after,
            draft_request=dict(scope_id=scope, record_ids=[source['id']], kind='summary')), ensure_ascii=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
