"""RNA-FM secondary-structure head (bpRNA-trained ResNet) on the pilot manifests. Run on a CUDA machine.
Set RNAFM_HOME to a folder holding RNA-FM/ (the RNA-FM repository), weights/ and the two manifests.
Saves per-item pair-probability maps (sigmoid applied if outputs are logits) to an npz."""
import json, os, sys, time
import numpy as np, torch
H = os.environ.get("RNAFM_HOME", os.path.expanduser("~/rnafm"))
sys.path.insert(0, f"{H}/RNA-FM")
import fm.pretrained as _fmp
# The repo's hub URL (proj.cse.cuhk.edu.hk/rnafm/api/download) returns 403; read the same files from the HF copy on disk.
_LOCAL = {"RNA-FM_pretrained.pth": f"{H}/weights/RNA-FM_pretrained.pth"}
def _local_hub(url, download_name=None):
    return torch.load(_LOCAL[download_name], map_location="cpu")
_fmp.load_hub_workaround = _local_hub
import fm
W = f"{H}/weights/SS/RNA-FM-ResNet_bpRNA.pth"
model, alphabet = fm.downstream.build_rnafm_resnet(type="ss", model_location=W)
model = model.cuda().eval()
bc = alphabet.get_batch_converter()
for man, out in [("manifest.jsonl", "rnafm_archiveii.npz"), ("manifest_nf.jsonl", "rnafm_nf.npz")]:
    items = [json.loads(l) for l in open(f"{H}/{man}") if l.strip()]
    res, meta = {}, {}
    for it in items:
        t0 = time.time()
        _, _, tok = bc([(it["id"], it["seq"])])
        with torch.no_grad():
            r = model({"description": [it["id"]], "token": tok.cuda()})["r-ss"]
        p = r[0].float().cpu().numpy()
        logits = bool(p.min() < 0 or p.max() > 1)
        if logits:
            p = 1 / (1 + np.exp(-p))
        assert p.shape == (len(it["seq"]), len(it["seq"])), (p.shape, len(it["seq"]))
        res[it["id"]] = p.astype(np.float16)
        meta[it["id"]] = {"latency_s": round(time.time() - t0, 3), "was_logits": logits}
    np.savez_compressed(f"{H}/{out}", **res)
    json.dump(meta, open(f"{H}/{out}.meta.json", "w"))
    print(man, len(res), "done", flush=True)
print("torch", torch.__version__, "gpu", torch.cuda.get_device_name(0))
