"""Public standalone dashboard entry; resolve implementation from this package.

The host imports this file without a parent package. An owned, path-qualified
module namespace avoids mutating sys.path or importing another installed ELM.
Host authentication, enablement and request profile scoping remain host-owned.
"""
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sys

_package = Path(__file__).resolve().parent.parent / 'elm_plugin'
_name = '_elm_workspace_api_' + hashlib.sha256(str(_package).encode('utf-8')).hexdigest()[:24]
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, _package/'__init__.py',
                                                 submodule_search_locations=[str(_package)])
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    try:
        _spec.loader.exec_module(_module)
    except BaseException:
        sys.modules.pop(_name, None)
        raise
router = importlib.import_module(_name + '.workspace_api').router
