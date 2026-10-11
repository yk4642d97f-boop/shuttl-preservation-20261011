#!/usr/bin/env python3
"""Exercise split and legacy upload deliveries against isolated fake gh executables."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

import upload_to_github as upload

FAKE_CLI = r'''#!/usr/bin/env python3
import fcntl,hashlib,json,os,pathlib,shutil,sys,time
state_path=pathlib.Path(os.environ['SHUTTL_MOCK_STATE']);state_lock=state_path.with_suffix('.lock').open('a+b');fcntl.flock(state_lock.fileno(),fcntl.LOCK_EX);s=json.loads(state_path.read_text());root=pathlib.Path(os.environ['SHUTTL_MOCK_REMOTE']);args=sys.argv[1:];tool=pathlib.Path(sys.argv[0]).name
repo='yk4642d97f-boop/shuttl-preservation-20261011'
def save():state_path.write_text(json.dumps(s))
def transfer(kind,name):
 global s
 counts=s.setdefault(kind+'_attempts',{});counts[name]=counts.get(name,0)+1
 s['active']=s.get('active',0)+1;s['max_active']=max(s.get('max_active',0),s['active']);save()
 fcntl.flock(state_lock.fileno(),fcntl.LOCK_UN);time.sleep(0.08);fcntl.flock(state_lock.fileno(),fcntl.LOCK_EX)
 s=json.loads(state_path.read_text());s['active']-=1
 remaining=s.get(kind+'_failures_left',{}).get(name,0)
 if remaining:s[kind+'_failures_left'][name]=remaining-1
 save()
 if remaining or s.get('fail_'+kind+'_name')==name:fail('fixture '+kind+' failure')
def out(x):print(json.dumps(x))
def fail(text):print(text,file=sys.stderr);sys.exit(1)
if os.environ.get('GH_HOST')!='github.com':fail('unexpected gh host')
if tool=='gitleaks':
 if s.get('scan_fail'):fail('fixture scanner failure')
 sys.exit(0)
if tool=='git':
 if args[:1]==['init']:pathlib.Path('.git').mkdir(exist_ok=True)
 elif args[:2]==['rev-parse','--show-toplevel']:print(pathlib.Path.cwd())
 elif args[:2]==['branch','--show-current']:print('main')
 elif args[:2]==['rev-parse','HEAD']:print(s['head'])
 elif args[:1]==['diff']:sys.exit(0)
 elif args==['remote']:print('origin' if s['remote'] else '')
 elif args[:2]==['remote','add']:s['remote']=args[3];save()
 elif args[:2]==['remote','get-url']:print(s['remote'])
 elif args[:1]==['push']:s['remote_head']=s['head'];save()
 sys.exit(0)
if args[:1]==['api']:
 path=args[1]
 if path=='user':out({'login':s['login']})
 elif path=='repos/'+repo:
  if not s['repo_exists']:fail('HTTP 404')
  out({'id':7,'private':s['private'],'owner':{'login':'yk4642d97f-boop'},'full_name':repo})
 elif '/releases/tags/' in path:
  if not s['release_exists']:fail('HTTP 404')
  out({'id':11})
 elif '/releases/11/assets?' in path:out([list(s['assets'].values())])
 elif '/releases/assets/' in path:
  ident=int(path.rsplit('/',1)[1]);asset=next(a for a in s['assets'].values() if a['id']==ident)
  transfer('download',asset['name']);s['downloads'].append(asset['name']);save();sys.stdout.buffer.write((root/str(ident)).read_bytes())
 elif '/git/ref/heads/main' in path:out({'object':{'sha':s['remote_head']}})
 else:fail('unexpected api '+path)
elif args[:2]==['repo','create']:
 if '--private' not in args:fail('missing --private')
 s['repo_exists']=True;s['private']=True;save()
elif args[:2]==['release','create']:s['release_exists']=True;save()
elif args[:2]==['release','upload']:
 p=pathlib.Path(args[3])
 transfer('upload',p.name)
 s['next_id']+=1;ident=s['next_id'];b=p.read_bytes();(root/str(ident)).write_bytes(b)
 s['assets'][p.name]={'id':ident,'name':p.name,'size':len(b),'state':'uploaded','digest':'sha256:'+hashlib.sha256(b).hexdigest()};s['uploads'].append(p.name);save()
elif args[:2]==['auth','setup-git']:pass
else:fail('unexpected gh '+str(args))
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='shuttl-upload-parts-test-') as temporary:
        root = Path(temporary)
        base, remote, mockbin = root / 'backup', root / 'remote', root / 'bin'
        for directory in (base, remote, mockbin, base / 'delivery', base / 'repository'):
            directory.mkdir()
        delivery = base / 'delivery'
        (base / 'repository' / 'README.md').write_text('isolated fixture')
        (base / 'repository' / 'RELEASE_NOTES.md').write_text('isolated fixture')
        state_path = root / 'state.json'
        initial = {'login': upload.OWNER, 'private': True, 'repo_exists': False,
                   'release_exists': False, 'assets': {}, 'next_id': 100, 'downloads': [],
                   'uploads': [], 'remote': '', 'head': 'a' * 40, 'remote_head': 'a' * 40}
        state_path.write_text(json.dumps(initial))
        for name in ('gh', 'git', 'gitleaks'):
            executable = mockbin / name
            executable.write_text(FAKE_CLI)
            executable.chmod(0o755)
        upload.GH_ENV = dict(os.environ, PATH=str(mockbin) + os.pathsep + os.environ['PATH'],
                             GH_HOST='github.com', SHUTTL_MOCK_STATE=str(state_path),
                             SHUTTL_MOCK_REMOTE=str(remote))
        upload.time.sleep = lambda _: None

        def state():
            return json.loads(state_path.read_text())

        def update(**values):
            value = state()
            value.update(values)
            state_path.write_text(json.dumps(value))

        def write_index(index, checksum_names=None):
            index_path = delivery / 'payload-index.json'
            index_path.write_text(json.dumps(index, indent=2) + '\n')
            transfers = [part for asset in index['assets'] for part in asset.get('parts', [asset])]
            sums = {item['name']: item['sha256'] for item in transfers}
            sums[index_path.name] = digest(index_path.read_bytes())
            if checksum_names is not None:
                sums = {name: value for name, value in sums.items() if name in checksum_names}
            (delivery / 'SHA256SUMS').write_text(''.join(value + '  ' + name + '\n' for name, value in sums.items()))

        def publish():
            with contextlib.redirect_stdout(io.StringIO()):
                upload.publish(base, workers=4)

        def rejected(index, label, checksum_names=None):
            write_index(index, checksum_names)
            before = state_path.read_bytes()
            try:
                publish()
            except (RuntimeError, ValueError, FileNotFoundError, TypeError):
                pass
            else:
                raise AssertionError('Invalid fixture was accepted: ' + label)
            assert before == state_path.read_bytes(), 'Remote state changed before rejecting ' + label
            checks.append(label)

        parent_data = os.urandom(25000)
        parent = {'name': 'manifest.sqlite3.age', 'bytes': len(parent_data), 'sha256': digest(parent_data),
                  'plaintext_sha256': '1' * 64, 'restore_path': 'manifest.sqlite3'}
        small_data, video_data = os.urandom(113), b'fixture standalone mp4'
        small = {'name': 'volume-000001.bin.age', 'bytes': len(small_data), 'sha256': digest(small_data),
                 'plaintext_sha256': '2' * 64, 'restore_path': 'volumes/volume-000001.bin'}
        video = {'name': 'Shuttl-fixture.mp4', 'bytes': len(video_data), 'sha256': digest(video_data), 'standalone_video': True}
        for item, data in ((parent, parent_data), (small, small_data), (video, video_data)):
            (delivery / item['name']).write_bytes(data)
        legacy = {'format': 'shuttl-delivery-v1', 'archive_format': 'shuttl-preservation-v1',
                  'complete': True, 'private_key_included': False, 'assets': [parent, small, video]}
        write_index(legacy)
        publish()
        assert json.loads((base / 'github-upload-receipt.json').read_text())['complete']
        checks.append('legacy v1 delivery uploads and reads every original asset back')

        split = copy.deepcopy(legacy)
        split['transport'] = 'ciphertext-parts-v1'
        split['assets'][0]['parts'] = []
        for number, offset in enumerate(range(0, len(parent_data), 9000), 1):
            data = parent_data[offset:offset + 9000]
            name = 'manifest.sqlite3.part-%06d.age' % number
            (delivery / name).write_bytes(data)
            split['assets'][0]['parts'].append({'name': name, 'bytes': len(data), 'sha256': digest(data)})
        (delivery / parent['name']).unlink()
        before = state()
        write_index(split)
        publish()
        current = state()
        report = json.loads((base / 'github-verification.json').read_text())
        actual_names = {item['name'] for item in split['assets'][0]['parts']} | {small['name'], video['name'], 'payload-index.json', 'SHA256SUMS'}
        assert report['complete'] and report['asset_count'] == len(actual_names) == 7
        assert set(report['assets']) == actual_names
        assert parent['name'] not in current['uploads'][len(before['uploads']):]
        assert small['name'] not in current['uploads'][len(before['uploads']):]
        assert video['name'] not in current['uploads'][len(before['uploads']):]
        assert small['name'] in current['downloads'][len(before['downloads']):]
        assert video['name'] in current['downloads'][len(before['downloads']):]
        for name, proof in report['assets'].items():
            assert proof['downloaded_sha256'] == digest((delivery / name).read_bytes())
        assert 'github-verification.json' in current['downloads']
        checks.append('split index without parent file validates joined hash, transfers actual parts, counts physical assets, and reuses existing small/video assets by readback')
        before_downloads = len(current['downloads'])
        publish()
        assert state()['downloads'][before_downloads:] == ['github-verification.json']
        checks.append('split resume preserves verified part checkpoints and reads final report back')

        first = split['assets'][0]['parts'][0]
        first_path = delivery / first['name']
        original = first_path.read_bytes()
        first_path.write_bytes(b'X' * len(original))
        rejected(split, 'corrupted part fails before any remote mutation')
        adjusted = copy.deepcopy(split)
        adjusted['assets'][0]['parts'][0]['sha256'] = digest(first_path.read_bytes())
        rejected(adjusted, 'individually valid replacement part still fails parent concatenation SHA256')
        first_path.unlink()
        rejected(split, 'missing part fails even though the old whole asset exists remotely')
        first_path.symlink_to(delivery / small['name'])
        rejected(split, 'symlink part is rejected')
        first_path.unlink()
        first_path.write_bytes(original)

        mutations = [
            ('unsupported transport is rejected', lambda x: x.update(transport='other')),
            ('parts without transport declaration are rejected', lambda x: x.pop('transport')),
            ('empty parts list is rejected', lambda x: x['assets'][0].update(parts=[])),
            ('unsafe part path is rejected', lambda x: x['assets'][0]['parts'][0].update(name='../escape.age')),
            ('nonconsecutive part numbering is rejected', lambda x: x['assets'][0]['parts'][0].update(name='manifest.sqlite3.part-000002.age')),
            ('invalid part hash is rejected', lambda x: x['assets'][0]['parts'][0].update(sha256='x' * 64)),
            ('boolean part byte length is rejected', lambda x: x['assets'][0]['parts'][0].update(bytes=True)),
            ('oversized part metadata is rejected', lambda x: x['assets'][0]['parts'][0].update(bytes=upload.PART_LIMIT + 1)),
            ('parent total byte mismatch is rejected', lambda x: x['assets'][0].update(bytes=1)),
            ('duplicate logical asset is rejected', lambda x: x['assets'].append(copy.deepcopy(x['assets'][1]))),
            ('part and logical asset name collision is rejected', lambda x: x['assets'].append(copy.deepcopy(x['assets'][0]['parts'][0]))),
            ('unexpected fields in part record are rejected', lambda x: x['assets'][0]['parts'][0].update(parts=[])),
            ('split standalone video is rejected', lambda x: x['assets'][2].update(parts=[copy.deepcopy(x['assets'][0]['parts'][0])])),
            ('incomplete index is rejected', lambda x: x.update(complete=False)),
        ]
        for label, change in mutations:
            invalid = copy.deepcopy(split)
            change(invalid)
            rejected(invalid, label)
        rejected(split, 'checksum list missing one physical part is rejected', actual_names - {first['name']})
        write_index(split)
        (delivery / 'SHA256SUMS').write_text((delivery / 'SHA256SUMS').read_text() + parent['sha256'] + '  ' + parent['name'] + '\n')
        before_state = state_path.read_bytes()
        try:
            publish()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Parent-only obsolete checksum accepted')
        assert state_path.read_bytes() == before_state
        checks.append('checksum list containing obsolete unsplit parent is rejected')

        # Fresh mocked release: a broken part readback preserves successful siblings.
        write_index(split)
        update(assets={}, uploads=[], downloads=[], upload_attempts={}, download_attempts={}, fail_download_name=first['name'])
        (base / 'github-verification.json').unlink()
        try:
            publish()
        except RuntimeError:
            pass
        else:
            raise AssertionError('Permanent readback failure was accepted')
        failed = state()
        assert failed['upload_attempts'][first['name']] == 1
        assert failed['download_attempts'][first['name']] == 3
        assert not json.loads((base / 'github-upload-receipt.json').read_text())['complete']
        update(fail_download_name=None)
        publish()
        assert state()['upload_attempts'][first['name']] == 1
        assert state()['download_attempts'][first['name']] == 4
        assert json.loads((base / 'github-upload-receipt.json').read_text())['complete']
        checks.append('part readback failure retries three times without reupload; resume completes every physical asset and final report')

    result = {'passed': len(checks), 'checks': checks, 'network_used': False,
              'formal_archive_touched': False, 'actual_fake_cli_processes': True}
    destination = Path(__file__).with_name('upload-test-report.json')
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
