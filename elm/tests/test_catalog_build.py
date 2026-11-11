"""Host-free guards for the catalog export's removed plugin-update surface.

Executes the actual NativeUpdates class AST with synthetic identity dependencies.
This is a focused source-level test, not native Hermes qualification.
"""
import ast
from pathlib import Path
import threading
import types
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'elm_plugin/product_ui_api.py'

class Refusal(Exception):
    def __init__(self,code,message): self.code=code;super().__init__(message)

class CatalogBuildTests(unittest.TestCase):
    def setUp(self):
        self.tree=ast.parse(SOURCE.read_text())
        cls=next(n for n in self.tree.body if isinstance(n,ast.ClassDef) and n.name=='NativeUpdates')
        env={'InboxError':Refusal,'_UPDATE_LOCK':threading.Lock()}
        exec(compile(ast.Module(body=[cls],type_ignores=[]),str(SOURCE),'exec'),env)
        self.cls=env['NativeUpdates'];self.service=self.cls.__new__(self.cls)
        self.service.scope=lambda:None;self.service.context={}
        env['ResultInbox']=types.SimpleNamespace(_context=lambda value:value)

    def test_plugin_apply_refused_before_any_check_or_write(self):
        self.service.check=lambda:self.fail('Plugin selection must refuse before check')
        self.service.skill=lambda _:self.fail('Plugin selection must never reach skill writes')
        with self.assertRaises(Refusal) as caught:
            self.service.apply({'type':'plugin','name':'elm'})
        self.assertEqual(caught.exception.code,'update_refused')
        with self.assertRaises(Refusal):self.service.apply({'type':'plugin','name':'another-plugin'})
        self.assertFalse(hasattr(self.cls,'plugin'))

    def test_check_has_only_skill_consumer_and_declares_plugin_disabled(self):
        hub=types.ModuleType('tools.skills_hub');hub.HubLockFile=lambda:object()
        install=types.ModuleType('tools.skills_hub_install');install.check_for_skill_updates=lambda **kw:[]
        with patch.dict('sys.modules',{'tools.skills_hub':hub,'tools.skills_hub_install':install}):
            result=self.service.check()
        self.assertEqual(result['rows'],[])
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['plugin_updates'],'disabled_in_catalog_build')

    def test_no_runtime_plugin_update_import_or_call_remains(self):
        text=SOURCE.read_text()
        for forbidden in ('hermes_cli.plugins_updates','plugins_transaction','plugins_auto_update','plugins_cmd','update_plugin('):
            self.assertNotIn(forbidden,text)
        self.assertIn("if type=='plugin':",text)
        self.assertIn('Plugin update inspection is disabled',text)


    def test_foreign_bridge_context_skips_without_any_host_lookup_or_registration(self):
        bridge=SOURCE.with_name('workspace_draft_bridge.py')
        tree=ast.parse(bridge.read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register_workspace_draft_command')
        def forbidden(*args,**kwargs):self.fail('Foreign context reached a host side effect')
        env={'PLUGIN_ID':'elm','get_hermes_home':forbidden,'get_plugin_commands':forbidden}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(bridge),'exec'),env)
        register=env['register_workspace_draft_command']
        for identity in ('another-plugin',None,'generic-recorder'):
            ctx=types.SimpleNamespace(plugin_id=identity,llm=object(),register_command=forbidden)
            self.assertEqual(register(ctx),{'registered':False,'reason':'foreign_plugin_context'})

    def test_memory_only_context_still_skips_without_constructing_llm(self):
        bridge=SOURCE.with_name('workspace_draft_bridge.py')
        tree=ast.parse(bridge.read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='register_workspace_draft_command')
        env={'PLUGIN_ID':'elm'}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(bridge),'exec'),env)
        self.assertEqual(env['register_workspace_draft_command'](types.SimpleNamespace()),
                         {'registered':False,'reason':'context_has_no_llm'})

if __name__=='__main__':unittest.main(verbosity=2)
