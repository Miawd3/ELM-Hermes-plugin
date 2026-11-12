"""Original public procedures, served through native progressive skill disclosure.

This registers metadata, not memory grants, tool capabilities, or eager skill bodies.
The host owns per-skill disabling, skill_view, and registration cleanup on unload.
"""
from pathlib import Path
import stat


SKILL_NAMES = (
    'source-research', 'documentation-lookup', 'debugging-recovery',
    'verification', 'delegation', 'creative-continuity',
)
MAX_SKILL_BYTES = 16 * 1024
MAX_DESCRIPTION_CHARS = 240


def _regular_path(path, root):
    """Reject known link escapes before reading; not a hostile-filesystem sandbox."""
    for parent in (root, path.parent, path):
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise ValueError('ELM starter skill links are unsupported')
    if not stat.S_ISREG(path.stat().st_mode) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('ELM starter skill path is invalid')


def _read_skill(root, name):
    import hermes_yaml as yaml

    path = root / name / 'SKILL.md'
    _regular_path(path, root)
    if path.stat().st_size > MAX_SKILL_BYTES:
        raise ValueError('ELM starter skill exceeds its size limit')
    with path.open('rb') as stream:
        raw = stream.read(MAX_SKILL_BYTES + 1)
    if len(raw) > MAX_SKILL_BYTES:
        raise ValueError('ELM starter skill exceeds its size limit')
    text = raw.decode('utf-8')
    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
        raise ValueError('ELM starter skill frontmatter is missing')
    header, body = text[4:].split('\n---\n', 1)
    frontmatter = yaml.safe_load(header)
    if not isinstance(frontmatter, dict) or set(frontmatter) != {'name', 'description', 'license'}:
        raise ValueError('ELM starter skill frontmatter is invalid')
    description = frontmatter['description']
    if (frontmatter['name'] != name or frontmatter['license'] != 'Apache-2.0'
            or not isinstance(description, str) or not description.strip()
            or len(description) > MAX_DESCRIPTION_CHARS
            or any(ord(char) < 32 for char in description)):
        raise ValueError('ELM starter skill metadata is invalid')
    if not body.strip() or '!`' in text or '${' in text or '\x00' in text:
        raise ValueError('ELM starter skills must be static text')
    return name, path, description, frontmatter


def register_starter_skills(ctx):
    """Validate all six first; native registrar owns their scoped lifetime.

    Existing conversations may retain cached metadata. Registration never rewrites
    their prompts; use a new session after changing the installed pack.
    """
    register = getattr(ctx, 'register_general_skill', None)
    if not callable(register):
        return False
    root = Path(__file__).parent.parent / 'starter_skills'
    entries = [_read_skill(root, name) for name in SKILL_NAMES]
    for name, path, description, frontmatter in entries:
        register(name, path, description, frontmatter)
    return True
