"""Independent extractor -> production adapter parity on validation rallies only."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(ROOT/'research/hitnet'))
import common as reference
import infer
from app.services.tracking import hitnet
from app.services.tracking.data_types import Track2D, VideoMeta, PlayerObservation


def main():
    torch.set_num_threads(4)
    model = hitnet.load(HERE/'artifacts/hitnet_single_v2.pt')
    checkpoint = torch.load(model.path,map_location='cpu',weights_only=True)
    net = reference.HitTCN(51,checkpoint['hidden']).eval()
    net.load_state_dict(checkpoint['state'],strict=True)
    report = {'weights_sha256':model.sha256,'matches':{},'device':'cpu',
              'torch':torch.__version__,'scope':'adapter parity; validation rallies, not quality retuning'}
    for mid in ('033','041'):
        source = ROOT/'research/extract/out'/f'{mid}.npz'
        with np.load(source,allow_pickle=True) as z:
            rallies = reference.load_match(mid)['rallies']
            maximum = 0.
            n_hits = 0
            for ri,r in enumerate(rallies):
                a,b = map(int,z['rally_row_start'][ri:ri+2])
                n = b-a
                ts = z['t'][a:b].astype(float)
                track = Track2D(ts,z['shuttle_xy'][a:b],z['shuttle_conf'][a:b],
                                z['shuttle_visible'][a:b],z['shuttle_interp'][a:b])
                meta = VideoMeta(r['fps'],int(z['width']),int(z['height']),n,ts.copy())
                players = [PlayerObservation(i,p+1,z['player_box'][a+i,p],1.,side,
                                             z['player_foot_world'][a+i,p])
                           for i in range(n) for p,side in enumerate(('far','near'))]
                raw = hitnet.raw_matrix(track,meta,players)
                np.testing.assert_array_equal(raw,r['raw'],strict=True)
                np.testing.assert_array_equal(hitnet.core.derive(raw,r['fps']),reference.derive(r['raw'],r['fps']),strict=True)
                expected = infer.predict_windowed([net],r['raw'],r['fps'],'cpu')
                actual = model.logits(raw,r['fps'])
                maximum = max(maximum,float(np.abs(actual-expected).max()))
                np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-6)
                events = model.detect(track,meta,players)
                expected_frames = reference.decode_nms(reference.sigmoid(expected[:,0]),r['fps'],.4,.3)
                assert [h.frame for h in events] == list(expected_frames)
                for h in events:
                    assert h.hitter == ('far' if expected[h.frame,1]>0 else 'near')
                    assert h.t == ts[h.frame]
                n_hits += len(events)
            report['matches'][mid] = {'rallies':len(rallies),'frames':len(z['frame']),
                                      'hits':n_hits,'max_abs_logit_error':maximum,
                                      'raw_exact':True,'features_exact':True,'events_exact':True,
                                      'npz_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
            print(mid,report['matches'][mid],flush=True)
    (HERE/'cloud_hitnet_parity.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__': main()
