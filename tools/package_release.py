"""Assemble a standalone release without private workspace data."""
from pathlib import Path
import shutil, hashlib
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'dist/Cosfolio'
def main():
    if not (DEST/'Cosfolio.exe').exists():raise RuntimeError('Build the application first.')
    model=ROOT/'models/birefnet-general-lite.onnx'
    if not model.exists() or hashlib.sha256(model.read_bytes()).hexdigest()!='5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333':
        raise RuntimeError('Download and verify the model before packaging.')
    if (DEST/'workspace').exists() and any((DEST/'workspace').iterdir()):
        raise RuntimeError('Use a clean dist directory; refusing to package a workspace.')
    for name in ('resources','licenses'):
        shutil.copytree(ROOT/name,DEST/name,dirs_exist_ok=True)
    (DEST/'models').mkdir(exist_ok=True)
    shutil.copy2(model,DEST/'models'/model.name)
    shutil.copy2(ROOT/'models/birefnet-general-lite.json',DEST/'models/birefnet-general-lite.json')
    for name in ('LICENSE','NOTICE','LICENSE-SCOPE.md','ASSET_RIGHTS.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name,DEST/name)
    shutil.copytree(ROOT/'docs',DEST/'docs',dirs_exist_ok=True)
    shutil.copy2(ROOT/'docs/使用说明.md',DEST/'使用说明.md')
    (DEST/'开始使用.txt').write_text('Cosfolio · 偶像写真工房 0.9\n完整解压后双击 Cosfolio.exe。保留整个程序目录。\n本地模型已包含，日常使用无需联网。\n非商业授权；商业用途需另行取得许可。\n说明：使用说明.md；许可：LICENSE-SCOPE.md。\n',encoding='utf-8-sig')
    print('Portable resources and notices assembled.')
if __name__=='__main__':main()
