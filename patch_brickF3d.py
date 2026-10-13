#!/usr/bin/env python3
"""
patch_brickF3d.py - Remove the framework name from DM Copilot text only.

Four exact anchors, each expected once, all verified before any write:
 A1: 'Conversation step (ECAFI)' becomes 'Conversation step'.
 A2: Remove ECAFI: from the comma-separated conversation-step prompt label.
 A3: Add the BRICK F.3d marker immediately above function leadPrompt(l).
 A4: Remove ECAFI from the one-step-forward prompt instruction.

Requires BRICK F.3c; refuses BRICK F.3d or an existing backup.
Only chat_test.html is edited. Backup: chat_test.html.bak-brickF3d.
Preserves UTF-8 content, file mode and LF or CRLF; atomic fsynced replacement.
Self-tests: exact edit footprint, labels and prompt have zero ECAFI text,
protected code unchanged, and node --check on every inline script.
If node is unavailable, syntax/runtime checks warn and skip.
The Python patch itself is ASCII and has no literal angle brackets or ampersand.

Usage:
 python3 patch_brickF3d.py --dry-run --dir /root/e5-ai-coach
 python3 patch_brickF3d.py --dir /root/e5-ai-coach
Rollback:
 cp chat_test.html.bak-brickF3d chat_test.html
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MARKER = 'BRICK F.3d'
PREREQ = 'BRICK F.3c'
ANCHORS = [
    ('A1 label', "'Conversation step (ECAFI)'", "'Conversation step'", 1),
    ('A2 prompt label', 'Conversation step (ECAFI: Engage, Connect, Assess, Frame, Invite): ',
     'Conversation step (Engage, Connect, Assess, Frame, Invite): ', 1),
    ('A3 marker', 'function leadPrompt(l){\n',
     '// BRICK F.3d: no framework name in DM Copilot label or prompt (step names kept).\nfunction leadPrompt(l){\n', 1),
    ('A4 prompt instruction', 'Move the conversation exactly one ECAFI step forward.',
     'Move the conversation exactly one step forward.', 1),
]


def decode(s):
    return (s.replace('@LT@', chr(60)).replace('@GT@', chr(62))
            .replace('@AMP@', chr(38)).replace('@MDASH@', chr(8212)))


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def node_run(node, source, syntax=False):
    fd, name = tempfile.mkstemp(suffix='.js', prefix='brickF3d-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(source)
        command = [node, '--check', name] if syntax else [node, name]
        result = subprocess.run(command, capture_output=True, text=True)
        require(result.returncode == 0, 'node check failed: ' + result.stderr[-1800:])
        return result.stdout.strip()
    finally:
        os.unlink(name)


def self_test(before, after):
    restored = after
    for name, old, new, expected in reversed(ANCHORS):
        restored = restored.replace(decode(new), decode(old), expected)
    require(restored == before, 'edit footprint differs from the four approved anchors')
    require(after.count(MARKER) == 1, 'marker must appear exactly once')
    labels = re.findall(r"\blf\(\s*'((?:\\.|[^'\\])*)'", after)
    require(bool(labels), 'no form labels found')
    require(not any('ECAFI' in label for label in labels), 'ECAFI remains in a form label')
    # Single-quoted strings containing ECAFI are forbidden; the protected
    # BF_JARGON_CAPS entry is double-quoted and is not a display label.
    single_strings = re.findall(r"'((?:\\.|[^'\\\n])*)'", after)
    require(not any('ECAFI' in value for value in single_strings),
            'ECAFI remains in a single-quoted label/string')
    match = re.search(r'function leadPrompt\(l\)\{\n.*?\n\}', after, re.S)
    require(match is not None, 'leadPrompt function not found')
    function = match.group(0)
    prompt = re.search(r'return langOnly\(`(.*?)`\);', function, re.S)
    require(prompt is not None, 'leadPrompt template not found')
    literal = re.sub(r'\$\{[^{}]*\}', '', prompt.group(1))
    require('ECAFI' not in literal, 'ECAFI remains in literal prompt text')
    require('Conversation step (Engage, Connect, Assess, Frame, Invite): ' in literal,
            'comma-separated step list changed')
    require('Move the conversation exactly one step forward.' in literal,
            'step instruction missing')
    # Every remaining ECAFI occurrence must be one of the approved internal uses.
    remaining = re.sub(r'\blab\(ECAFI,', 'lab(INTERNAL,', after)
    remaining = remaining.replace('const ECAFI=', 'const INTERNAL=')
    remaining = remaining.replace('{options:ECAFI}', '{options:INTERNAL}')
    remaining = remaining.replace('ecafi:ECAFI,', 'ecafi:INTERNAL,')
    jargon = next((line for line in after.splitlines()
                   if line.startswith('const BF_JARGON_CAPS=')), '')
    require(jargon and '"ECAFI"' in jargon, 'protected banned-term list missing')
    remaining = remaining.replace(jargon, jargon.replace('"ECAFI"', '"INTERNAL"'))
    require('ECAFI' not in remaining, 'unexpected remaining ECAFI occurrence')
    print('  Self-test: labels ECAFI=0; literal prompt ECAFI=0; protected code unchanged')
    node = shutil.which('node')
    if not node:
        print('  WARNING: node not found; node --check and runtime prompt test skipped')
        return
    lt, gt = chr(60), chr(62)
    pattern = lt + r'script\b([^' + gt + r']*)' + gt + r'(.*?)' + lt + r'/script\s*' + gt
    blocks = re.findall(pattern, after, re.S | re.I)
    checked = 0
    for attrs, source in blocks:
        if re.search(r'\bsrc\s*=', attrs, re.I):
            continue
        kind = re.search(r'''\btype\s*=\s*["']([^"']+)["']''', attrs, re.I)
        if kind and kind.group(1).lower() not in ('text/javascript', 'application/javascript', 'module'):
            continue
        node_run(node, source, syntax=True)
        checked += 1
    require(checked != 0, 'no inline JavaScript found for node --check')
    array = re.search(r'^const ECAFI=.*?;$', after, re.M)
    require(array is not None, 'ECAFI array not found')
    runtime = (array.group(0) + '\nconst TEMPS=[],SIGNALS=[],SCENARIOS=[];\n'
               'function dnaBlock(){return "";}\nfunction langOnly(s){return s;}\n'
               'function num(v){return Number(v)||0;}\n'
               'function lab(a,k){const p=a.find(function(x){return x[0]===k;});return p?p[1]:k;}\n' + function + '\n'
               'for(const step of ECAFI){const p=leadPrompt({name:"Test",ecafi:step[0],conversation:[]});'
               'if(p.includes("ECAFI"))throw Error("ECAFI in rendered prompt");'
               'if(!p.includes(step[1]))throw Error("selected step missing");}\n'
               'console.log("rendered prompt ECAFI=0 for all five steps");\n')
    print('  node --check: PASS (%d inline scripts)' % checked)
    print('  Runtime self-test: ' + node_run(node, runtime))


def atomic_replace(path, payload, mode):
    fd, temp = tempfile.mkstemp(prefix='.brickF3d-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            os.fchmod(f.fileno(), mode)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', default='.', help='directory containing chat_test.html')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    path = Path(args.dir).resolve() / 'chat_test.html'
    backup = path.with_name(path.name + '.bak-brickF3d')
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    require(PREREQ in text, 'BRICK F.3c is required in chat_test.html')
    require(MARKER not in text, 'BRICK F.3d already present; refusing second run')
    require(not backup.exists(), 'backup already exists; it will never be overwritten')
    normalized = text.replace('\r\n', '\n')
    require('\r' not in normalized, 'unsupported bare-CR line endings')
    crlf = '\r\n' in text
    require(not crlf or '\n' not in text.replace('\r\n', ''), 'mixed LF/CRLF line endings')
    print('Target: ' + str(path))
    for name, old, new, expected in ANCHORS:
        count = normalized.count(decode(old))
        print('  %s: found %d, expected %d' % (name, count, expected))
        require(count == expected, name + ' exact anchor count mismatch')
    output = normalized
    for name, old, new, expected in ANCHORS:
        output = output.replace(decode(old), decode(new), expected)
    self_test(normalized, output)
    payload = (output.replace('\n', '\r\n') if crlf else output).encode('utf-8')
    if args.dry_run:
        print('DRY RUN PASS: no target or backup written')
        return
    require(path.read_bytes() == raw, 'target changed during checks; refusing write')
    mode = stat.S_IMODE(path.stat().st_mode)
    # Exclusive creation ensures that an existing backup can never be overwritten.
    with open(backup, 'xb') as f:
        f.write(raw)
        os.fchmod(f.fileno(), mode)
        f.flush()
        os.fsync(f.fileno())
    atomic_replace(path, payload, mode)
    print('APPLIED: ' + str(path))
    print('BACKUP: ' + str(backup))
    print('Hard-refresh the browser after deployment.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, UnicodeError, RuntimeError) as exc:
        print('ABORT: ' + str(exc), file=sys.stderr)
        print('If a backup was created, it remains available for recovery.', file=sys.stderr)
        sys.exit(1)
