"""Profile-independent presence check, not a host authorization adapter.

Only imports the installed trusted Hermes modules. Never opens a profile/store.
Passing this check is not evidence of correct ownership semantics or support.
"""
import importlib
import json


def inspect_host():
    """Return redacted symbol availability, never paths or exception contents."""
    required = {
        'hermes_state': ('SessionDB',),
        'hermes_cli.projects_db': ('resolve_session_project', 'get_project'),
    }
    checks = {}
    for name, attributes in required.items():
        try:
            module = importlib.import_module(name)
            checks[name] = {attribute: callable(getattr(module, attribute, None))
                            for attribute in attributes}
        except Exception:
            # A diagnostic cannot expose host import exception secrets or assume
            # a failed import means the optional API is absent but safe to use.
            checks[name] = {attribute: False for attribute in attributes}
    present = all(value for module in checks.values() for value in module.values())
    return {'schema_version': 1,
            'status': 'required_symbols_present_unverified' if present else 'workspace_host_unsupported',
            'checks': checks,
            'verified': ['required_callable_presence'],
            'not_verified': ['ownership_semantics', 'installation', 'profile', 'permissions',
                             'gui', 'model_access', 'windows', 'full_compatibility']}


def main():
    result = inspect_host()
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'required_symbols_present_unverified' else 2


if __name__ == '__main__':
    raise SystemExit(main())
