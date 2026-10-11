"""从 NYCU SharePoint 压缩包里按需分段提取文件 (可断点续跑)"""
from remotezip import RemoteZip
import os, time, sys, re, subprocess
D = '/sessions/eager-exciting-fermat/mnt/outputs/dev_data'
def fresh_url():
    U = 'https://nycu1-my.sharepoint.com/:u:/g/personal/tik_m365_nycu_edu_tw/EWisYhAiai9Ju7L-tQp0ykEBZJd9VQkKqsFrjcqqYIDP-g?e=S0AB1Z'
    html = subprocess.run(['curl', '-s', '-L', '-c', '/tmp/jar', '-b', '/tmp/jar', U], capture_output=True, text=True, timeout=60).stdout
    m = re.search(r'download\.aspx\?UniqueId=[^"\\]*tempauth=[^"\\&]*', html)
    return 'https://nycu1-my.sharepoint.com/personal/tik_m365_nycu_edu_tw/_layouts/15/' + m.group(0)
want_prefix = sys.argv[1] if len(sys.argv) > 1 else 'TrackNetV2/Test/'
per_match = int(sys.argv[2]) if len(sys.argv) > 2 else 3
t0 = time.time()
with RemoteZip(fresh_url()) as z:
    info = [i for i in z.infolist() if i.filename.startswith(want_prefix) and not i.is_dir()]
    vids = sorted(i.filename for i in info if i.filename.endswith('.mp4'))
    pick = []
    for m in ('match1', 'match2', 'match3'):
        pick += [v for v in vids if f'/{m}/' in v][:per_match]
    files = []
    for v in pick:
        rid = os.path.basename(v)[:-4]
        files += [v, v.replace('/video/', '/csv/').replace('.mp4', '_ball.csv')]
    byname = {i.filename: i for i in info}
    done = 0
    for f in files:
        i = byname.get(f)
        if not i: continue
        out = os.path.join(D, f.replace('TrackNetV2/', 'nycu/'))
        if os.path.exists(out) and os.path.getsize(out) == i.file_size: done += 1; continue
        if time.time() - t0 > 120: break
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with z.open(i) as src, open(out + '.part', 'wb') as dst: dst.write(src.read())
        os.replace(out + '.part', out); done += 1
        print('got', f, '%.1f MB' % (i.file_size / 1e6), '%.0fs' % (time.time() - t0), flush=True)
    print(f'{done}/{len(files)} files ready')
