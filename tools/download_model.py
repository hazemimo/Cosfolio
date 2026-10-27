"""One-time developer setup; the desktop application never downloads models."""
from pathlib import Path
import hashlib, urllib.request
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'models/birefnet-general-lite.onnx'
URL='https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx'
SHA256='5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):h.update(block)
    return h.hexdigest()
def main():
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    if TARGET.exists() and sha(TARGET)==SHA256:
        print('Existing model verified.');return
    partial=TARGET.with_suffix('.download')
    request=urllib.request.Request(URL,headers={'User-Agent':'Cosfolio-Developer-Setup'})
    with urllib.request.urlopen(request,timeout=90) as response, partial.open('wb') as output:
        while block:=response.read(1024*1024):output.write(block)
    if sha(partial)!=SHA256:raise RuntimeError('Model SHA256 mismatch; target model was not replaced.')
    partial.replace(TARGET)
    print('Local model downloaded and verified.')
if __name__=='__main__':main()
