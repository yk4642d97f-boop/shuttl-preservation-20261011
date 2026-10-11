"""Bounded BST fine-tuning: one initializer, validation selection, atomic resume, explicit freeze."""
from __future__ import annotations
import argparse,fcntl,hashlib,json,signal,sys,time
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.tracking.bst import CLASSES
from app.services.tracking.bst_vendor.bst import BST_CG_AP


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path,value):
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def atomic_save(path,value):
    tmp=path.with_suffix('.pt.tmp');torch.save(value,tmp);tmp.replace(path)


def dataset(manifest,split):
    doc=json.loads(manifest.read_text())
    if doc['classes']!=CLASSES: raise ValueError('Class ordering mismatch')
    item=doc['splits'][split];path=(manifest.parent/item['file']).resolve()
    if not path.is_relative_to(manifest.parent.resolve()) or sha(path)!=item['sha256']:
        raise ValueError('Dataset checksum/path mismatch')
    with np.load(path,allow_pickle=False) as z: data={k:z[k] for k in z.files}
    n=len(data['label']);required={'jnb':(n,30,2,72),'shuttle':(n,30,2),'pos':(n,30,2,2),'length':(n,),'label':(n,),'name':(n,)}
    for k,shape in required.items():
        if data[k].shape!=shape: raise ValueError(f'Invalid {k} shape')
        if k!='name' and not np.isfinite(data[k]).all(): raise ValueError(f'Nonfinite {k}')
    if not n or np.any((data['length']<1)|(data['length']>30)) or np.any((data['label']<0)|(data['label']>24)):
        raise ValueError('Invalid or empty dataset')
    actual={x.split('/')[0] for x in data['name'].tolist()}
    if actual!=set(item['matches']) or len(set(data['name'].tolist()))!=n:
        raise ValueError('Match provenance/duplicate example mismatch')
    data['matches']=actual
    for k in required:
        if k!='name': data[k]=torch.from_numpy(data[k])
    return data


def batch(data,indices,device):
    return [data[k][indices].to(device) for k in ('jnb','shuttle','pos','length')]


@torch.inference_mode()
def evaluate(net,data,device,batch_size):
    net.eval();conf=np.zeros((25,25),np.int64)
    for start in range(0,len(data['label']),batch_size):
        idx=slice(start,start+batch_size)
        logits=net(*batch(data,idx,device))
        if not torch.isfinite(logits).all(): raise ValueError('Nonfinite evaluation')
        pred=logits.argmax(1).cpu().numpy();truth=data['label'][idx].numpy()
        np.add.at(conf,(truth,pred),1)
    denom=conf.sum(0)+conf.sum(1)
    f1=np.divide(2*conf.diagonal(),denom,out=np.zeros(25),where=denom>0)
    return {'macro_f1_24':float(f1[1:].mean()),'accuracy':float(conf.trace()/conf.sum()),'examples':int(conf.sum())}


def rng_state(device):
    state={'cpu':torch.get_rng_state()}
    if device.startswith('cuda'): state['cuda']=torch.cuda.get_rng_state_all()
    if device=='mps': state['mps']=torch.mps.get_rng_state()
    return state


def restore_rng(state):
    torch.set_rng_state(state['cpu'])
    if 'cuda' in state: torch.cuda.set_rng_state_all(state['cuda'])
    if 'mps' in state: torch.mps.set_rng_state(state['mps'])


def train(a):
    if a.steps<1 or a.batch<1 or a.hours<=0 or a.eval_every<1: raise ValueError('Invalid budget')
    if (a.out/'frozen.json').exists(): raise ValueError('Frozen run cannot be retrained')
    manifest=a.data.resolve();tr=dataset(manifest,'train');va=dataset(manifest,'val')
    if tr['matches'] & va['matches'] or tr['matches'] & {'033','036','037','039','040','041','042','043','044'}:
        raise ValueError('Held-out match present in training')
    cfg={'manifest_sha256':sha(manifest),'init_sha256':sha(a.init),'steps':a.steps,'batch':a.batch,
         'eval_every':a.eval_every,'lr':a.lr,'seed':a.seed,'hours':a.hours,'device':a.device,
         'initialization':'one released member; never parameter averaging','test_access':False,
         'train_matches':sorted(tr['matches']),'val_matches':sorted(va['matches'])}
    a.out.mkdir(parents=True,exist_ok=True)
    if (a.out/'config.json').exists():
        if not a.resume or json.loads((a.out/'config.json').read_text())!=cfg:
            raise ValueError('Existing run requires --resume with identical configuration')
    elif a.resume: raise ValueError('No run to resume')
    else:
        atomic_json(a.out/'config.json',cfg)
        (a.out/'trainer_snapshot.py').write_bytes(Path(__file__).read_bytes())
    torch.manual_seed(a.seed);torch.set_num_threads(4)
    net=BST_CG_AP(72,30,n_class=25,depth_tem=2,depth_inter=1).to(a.device)
    opt=torch.optim.AdamW(net.parameters(),lr=a.lr,weight_decay=.01)
    stop=[False]
    signal.signal(signal.SIGTERM,lambda *_:stop.__setitem__(0,True))
    signal.signal(signal.SIGINT,lambda *_:stop.__setitem__(0,True))
    start=time.monotonic();spent=0.;step=0;history=[]
    if a.resume:
        ck=torch.load(a.out/'last.pt',map_location='cpu',weights_only=True)
        net.load_state_dict(ck['state'],strict=True);opt.load_state_dict(ck['optimizer'])
        restore_rng(ck['rng']);spent=ck['spent_seconds'];step=ck['step'];history=ck['history'];best=ck['best']
        if spent>=a.hours*3600: raise ValueError('Cumulative time budget exhausted')
    else:
        net.load_state_dict(torch.load(a.init,map_location='cpu',weights_only=True),strict=True)
        baseline=evaluate(net,va,a.device,a.batch);best=baseline['macro_f1_24']
        history=[{'step':0,'validation':baseline}]
        atomic_save(a.out/'best.pt',{'state':net.state_dict(),'step':0,'validation':baseline})
    def save():
        atomic_save(a.out/'last.pt',{'state':net.state_dict(),'optimizer':opt.state_dict(),'step':step,
                    'rng':rng_state(a.device),'spent_seconds':spent+time.monotonic()-start,
                    'best':best,'history':history})
        atomic_json(a.out/'progress.json',{'step':step,'spent_seconds':spent+time.monotonic()-start,'best_val_macro_f1_24':best,'history':history})
    save()
    while step<a.steps and not stop[0] and spent+time.monotonic()-start<a.hours*3600:
        net.train();idx=torch.randint(len(tr['label']),(a.batch,));opt.zero_grad(set_to_none=True)
        logits=net(*batch(tr,idx,a.device));loss=torch.nn.functional.cross_entropy(logits,tr['label'][idx].to(a.device),label_smoothing=.1)
        if not torch.isfinite(loss): raise ValueError('Nonfinite loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),1.);opt.step();step+=1
        if step%a.eval_every==0 or step==a.steps:
            metric=evaluate(net,va,a.device,a.batch)
            history.append({'step':step,'train_loss':float(loss.detach()),'validation':metric})
            if metric['macro_f1_24']>best:
                best=metric['macro_f1_24'];atomic_save(a.out/'best.pt',{'state':net.state_dict(),'step':step,'validation':metric})
            print(history[-1],flush=True)
        if step%25==0 or step%a.eval_every==0: save()
        if a.stop_after and step>=a.stop_after: stop[0]=True
    save()
    print(json.dumps({'step':step,'stopped':stop[0],'out':str(a.out),'test_access':False}))


def freeze(a):
    cfg=json.loads((a.out/'config.json').read_text());ck=torch.load(a.out/'best.pt',map_location='cpu',weights_only=True)
    path=a.out/'frozen.json'
    if path.exists(): raise ValueError('Run already frozen')
    atomic_json(path,{'checkpoint':'best.pt','sha256':sha(a.out/'best.pt'),'step':ck['step'],
                     'validation':ck['validation'],'config':cfg,'scope':'candidate only; compare downstream chain before deployment'})
    print(path)


def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('train');p.add_argument('--data',type=Path,required=True);p.add_argument('--init',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--device',default='cpu');p.add_argument('--steps',type=int,default=2000)
    p.add_argument('--batch',type=int,default=32);p.add_argument('--eval-every',type=int,default=100)
    p.add_argument('--lr',type=float,default=1e-5);p.add_argument('--seed',type=int,default=20261007)
    p.add_argument('--hours',type=float,default=2);p.add_argument('--resume',action='store_true')
    p.add_argument('--stop-after',type=int,default=0,help='Smoke interruption after this step; not a quality experiment')
    p=sub.add_parser('freeze');p.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    with (a.out/'.run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        train(a) if a.cmd=='train' else freeze(a)
if __name__=='__main__':main()
