"""Bounded CRAN source collection and static Rd parsing; never installs or runs R."""
import gzip
import hashlib
import io
import json
import re
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CRAN_HOSTS = {'https://cran.r-project.org', 'https://cloud.r-project.org'}
NAME = re.compile(r'[A-Za-z][A-Za-z0-9.]*\Z')
VERSION = re.compile(r'[A-Za-z0-9.+-]+\Z')
PARSER_VERSION = 'rd-static-3'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_url(url, limit=30_000_000):
    request = urllib.request.Request(url, headers={'User-Agent': 'StatAgent-CRAN-profile/0.3'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('CRAN resource exceeds the collection size limit.')
    return raw


def dcf(text):
    result, key = {}, None
    for line in text.splitlines():
        if line[:1].isspace() and key:
            result[key] += ' ' + line.strip()
        elif ':' in line:
            key, value = line.split(':', 1)
            result[key] = value.strip()
    return result


def lock_sources(config_path, lock_path, cache):
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    base = config['repository'].rstrip('/')
    if base not in CRAN_HOSTS:
        raise ValueError('Use an explicitly supported official CRAN repository.')
    names = [p['name'] for p in config['packages']]
    if len(names) != len(set(names)) or any(not NAME.fullmatch(n) for n in names):
        raise ValueError('Invalid or duplicate package names.')
    index = read_url(base+'/src/contrib/PACKAGES.gz', 8_000_000)
    with gzip.GzipFile(fileobj=io.BytesIO(index)) as handle:
        text = handle.read(40_000_001)
    if len(text) > 40_000_000:
        raise ValueError('Decompressed package index exceeds the limit.')
    entries = {e['Package']: e for block in text.decode('utf-8').split('\n\n')
               if 'Package' in (e := dcf(block)) and 'Path' not in e}
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    (cache/(digest(index)+'.PACKAGES.gz')).write_bytes(index)
    packages = []
    for item in config['packages']:
        name = item['name']
        if name not in entries:
            raise ValueError('Package is absent from CRAN index: '+name)
        version = entries[name]['Version']
        if not VERSION.fullmatch(version):
            raise ValueError('Invalid CRAN version.')
        functions = item['functions']
        if not functions or len(functions) != len(set(functions)) or any(not NAME.fullmatch(f) for f in functions):
            raise ValueError('Invalid or duplicate function names.')
        url = f'{base}/src/contrib/{name}_{version}.tar.gz'
        raw = read_url(url)
        checksum = digest(raw)
        # CRAN's MD5 is an additional transport consistency check, not a security claim.
        if entries[name].get('MD5sum') and hashlib.md5(raw).hexdigest() != entries[name]['MD5sum']:
            raise ValueError('CRAN package does not match its index checksum.')
        (cache/(checksum+'.tar.gz')).write_bytes(raw)
        packages.append({'name': name, 'version': version, 'functions': functions, 'url': url,
                         'sha256': checksum, 'bytes': len(raw), 'index_metadata': entries[name]})
    lock = {'schema_version': '1.0', 'repository': base, 'collected_at': datetime.now(timezone.utc).isoformat(),
            'index_sha256': digest(index), 'packages': packages}
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    Path(lock_path).write_text(json.dumps(lock, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return lock


def group(text, start):
    """Read one balanced Rd brace group, preserving nested R code and escaped braces."""
    if start >= len(text) or text[start] != '{':
        raise ValueError('Expected an Rd group.')
    depth, i = 1, start+1
    while i < len(text):
        if text[i] == '\\' and i+1 < len(text) and text[i+1] in '{}\\':
            i += 2
            continue
        depth += (text[i] == '{') - (text[i] == '}')
        if not depth:
            return text[start+1:i], i+1
        i += 1
    raise ValueError('Unbalanced Rd braces.')


def sections(text):
    """Extract top-level sections; Rd is not evaluated and unsupported macros remain visible."""
    output, i = {}, 0
    while i < len(text):
        if text[i] == '%':
            end = text.find('\n', i)
            i = len(text) if end < 0 else end+1
            continue
        match = re.match(r'\\([A-Za-z]+)\s*\{', text[i:])
        if match:
            start = i+match.end()-1
            value, i = group(text, start)
            output.setdefault(match[1], []).append(value)
        else:
            i += 1
    return output


def plain(text):
    # Preserve semantic content; this is a conservative renderer, not an R Rd compiler.
    text = re.sub(r'(?<!\\)%[^\n]*', '', text)
    text = re.sub(r'\\(?:method|S3method)\{([^{}]+)\}\{([^{}]+)\}', r'\1.\2', text)
    text = re.sub(r'\\(?:dots|ldots)(?:\{\})?', '...', text)
    text = re.sub(r'\\R(?:\{\})?', 'R', text)
    text = re.sub(r'\\(?:link|code)\[[^\]]*\]', '', text)
    text = re.sub(r'\\(?:[A-Za-z]+)\*?', ' ', text)
    text = text.replace('{', ' ').replace('}', ' ')
    text = text.replace('\\%', '%')
    return re.sub(r'\s+', ' ', text).strip()


def arguments(text):
    values, i = [], 0
    while i < len(text):
        found = re.search(r'\\item\s*\{', text[i:])
        if not found:
            break
        name, pos = group(text, i+found.end()-1)
        while pos < len(text) and text[pos].isspace():
            pos += 1
        description, i = group(text, pos)
        values.append({'name': plain(name), 'description': plain(description)})
    return values


def collect_locked(lock_path, cache, fetch=read_url):
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    if lock['repository'] not in CRAN_HOSTS:
        raise ValueError('Unsupported CRAN repository in lock.')
    documents = []
    for package in lock['packages']:
        name, version = package['name'], package['version']
        if not NAME.fullmatch(name) or not VERSION.fullmatch(version) or not re.fullmatch('[a-f0-9]{64}', package['sha256']):
            raise ValueError('Invalid locked package identity.')
        expected_url = f"{lock['repository']}/src/contrib/{name}_{version}.tar.gz"
        if package['url'] != expected_url:
            raise ValueError('Locked package URL is not its canonical CRAN location.')
        path = Path(cache)/(package['sha256']+'.tar.gz')
        if path.exists():
            raw = path.read_bytes()
        else:
            try:
                raw = fetch(expected_url)
            except OSError:
                raw = fetch(f"{lock['repository']}/src/contrib/Archive/{name}/{name}_{version}.tar.gz")
            if digest(raw) != package['sha256']:
                raise ValueError('Downloaded source hash differs from lock.')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        if len(raw) > 30_000_000 or digest(raw) != package['sha256']:
            raise ValueError('Cached source hash/size differs from lock.')
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = archive.getmembers()
            if len(members) > 20000 or sum(m.size for m in members) > 200_000_000:
                raise ValueError('Expanded archive exceeds limits.')
            # Read selected regular members in memory; never extract paths to disk.
            desc = archive.getmember(name+'/DESCRIPTION')
            if not desc.isfile() or desc.size > 100000:
                raise ValueError('Invalid package DESCRIPTION.')
            metadata = dcf(archive.extractfile(desc).read().decode('utf-8'))
            if metadata.get('Package') != name or metadata.get('Version') != version:
                raise ValueError('Package DESCRIPTION differs from lock.')
            found = set()
            for member in members:
                if not member.isfile() or not member.name.startswith(name+'/man/') or not member.name.endswith('.Rd'):
                    continue
                if member.size > 300000:
                    raise ValueError('Rd reference exceeds the document limit.')
                rd = archive.extractfile(member).read()
                encoding = re.search(rb'\\encoding\{([^}]+)\}', rd)
                text = rd.decode(encoding[1].decode('ascii') if encoding else metadata.get('Encoding', 'utf-8'))
                parsed = sections(text)
                aliases = [plain(v) for v in parsed.get('alias', [])]
                for function in package['functions']:
                    if function not in aliases:
                        continue
                    if function in found:
                        raise ValueError('Ambiguous Rd aliases for '+name+'::'+function)
                    found.add(function)
                    if not parsed.get('usage'):
                        raise ValueError('Selected reference is not a documented function: '+function)
                    selected = {key: plain('\n'.join(parsed[key])) for key in
                        ['title', 'description', 'usage', 'arguments', 'details', 'value', 'note', 'seealso'] if key in parsed}
                    if sum(map(len, selected.values())) > 45000:
                        raise ValueError('Selected reference needs explicit chunking before extraction.')
                    documents.append({'function_id': name+'::'+function, 'package': name, 'package_version': version,
                        'function_name': function, 'license': metadata.get('License', 'unknown'),
                        'source_url': package['url'], 'package_sha256': package['sha256'], 'rd_path': member.name,
                        'rd_sha256': digest(rd), 'collected_at': lock['collected_at'], 'parser_version': PARSER_VERSION,
                        'aliases': aliases, 'usage_rd': '\n'.join(parsed['usage']),
                        'parameters': arguments('\n'.join(parsed.get('arguments', []))), 'sections': selected,
                        'parser_warnings': ['Static Rd subset renderer; original usage retained; no R code or examples executed.']})
            if found != set(package['functions']):
                raise ValueError('Functions missing from source: '+', '.join(sorted(set(package['functions'])-found)))
    return documents
