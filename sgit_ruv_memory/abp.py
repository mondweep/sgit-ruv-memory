"""Strict adapter profile of SGit's ABP 0.1-poc structure.

The three memory primitives extend SGit's vocabulary. This compiler does not
claim to support every upstream primitive or path-style instance expression.
"""
import datetime as dt
import hashlib
import json
import re

PROFILE = 'sgit-ruv-memory/v1'
ACTIONS = {
    'write.memory.project': 'memory.checkpoint',
    'read.memory.project': 'memory.restore',
    'read.record.history': 'memory.inspect',
    'delete.memory.project': 'memory.delete',
}
EFFECTS = {'yes': 'allow', 'no': 'deny', 'approval': 'require_approval'}


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def expiry(value):
    if not isinstance(value, str):
        raise ValueError('ABP valid_until must be an ISO date or timestamp')
    parsed = dt.datetime.fromisoformat(value)
    if len(value) == 10:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return parsed


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing or invalid ' + label)
    return value


def compile_abp(abp, namespaces):
    """Compile or reject the entire document; never silently skip a row."""
    if not isinstance(abp, dict):
        raise ValueError('ABP must be an object')
    if set(abp) - {'abp_version','adapter_profile','deployment','owner','valid_until','roles'}:
        raise ValueError('Unknown ABP document fields')
    if abp.get('abp_version') != '0.1-poc' or abp.get('adapter_profile') != PROFILE:
        raise ValueError('Unsupported ABP version/profile')
    for name in ('owner', 'deployment'):
        text(abp.get(name), name)
    expires = expiry(abp.get('valid_until'))
    roles = abp.get('roles')
    if not isinstance(roles, list) or not roles:
        raise ValueError('ABP roles must be a nonempty list')
    if not namespaces or not all(isinstance(n, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', n) for n in namespaces):
        raise ValueError('Namespaces must be simple identifiers')
    rules, seen_roles = [], set()
    for role in roles:
        if not isinstance(role, dict):
            raise ValueError('Invalid role')
        if set(role) - {'id','purpose','rows'}:
            raise ValueError('Unknown ABP role fields')
        principal = text(role.get('id'), 'role id')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', principal) or principal in seen_roles:
            raise ValueError('Invalid or duplicate role')
        seen_roles.add(principal)
        text(role.get('purpose'), 'role purpose')
        rows = role.get('rows')
        if not isinstance(rows, list) or not rows:
            raise ValueError('Role rows must be nonempty')
        seen_caps = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) - {'capability','reach','mandate','why','barrier','instances'}:
                raise ValueError('Unknown or malformed ABP row fields')
            cap = row.get('capability')
            mandate = row.get('mandate')
            if not isinstance(cap, str) or cap not in ACTIONS or cap in seen_caps:
                raise ValueError('Unknown or duplicate capability')
            seen_caps.add(cap)
            if not isinstance(mandate, str) or mandate not in EFFECTS or type(row.get('reach')) is not bool:
                raise ValueError('Invalid mandate/reach')
            why = text(row.get('why'), 'reason')
            if mandate != 'yes':
                text(row.get('barrier'), 'deny/approval barrier')
            instances = row.get('instances')
            if (not isinstance(instances, list) or not instances
                    or not all(isinstance(n, str) and n in namespaces for n in instances)
                    or len(instances) != len(set(instances))):
                raise ValueError('Instances must be explicit allowlisted namespaces; no wildcards')
            if mandate == 'yes' and row['reach'] is False:
                raise ValueError('Cannot grant an unreachable capability')
            # Never widen a scoped deny or approval to all resources.
            rules.append({'id': f'abp:{principal}:{cap}', 'principals': [principal],
                          'actions': [ACTIONS[cap]], 'resources': instances,
                          'effect': EFFECTS[mandate], 'enabled': row['reach'],
                          'priority': {'yes':10,'no':100,'approval':90}[mandate],
                          'description': why + (' | ' + row['barrier'] if row.get('barrier') else '')})
    return {'rules': rules, 'roles': sorted(seen_roles), 'expires': expires,
            'abp_sha256': canonical_digest(abp), 'rules_sha256': canonical_digest(rules),
            'profile': PROFILE, 'owner': abp['owner']}


def example_abp(namespace='demo', principal='local-agent'):
    """Explicit sample mandate; hosts should review before granting operations."""
    return {'abp_version':'0.1-poc', 'adapter_profile':PROFILE,
            'owner':'local operator', 'deployment':'local SGit memory MCP',
            'valid_until':'2027-01-01',
            'roles':[{'id':principal, 'purpose':'checkpoint and recover project memory',
                      'rows':[{'capability':cap, 'reach':True, 'mandate':'yes',
                               'why':'local memory recovery', 'instances':[namespace]}
                              for cap in ACTIONS]}]}
