"""Offline, content-addressed photo library. Projects receive independent copies."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image
from .core import DATA, Asset, oriented_image, make_cutout

STATUSES = {'ready': '可使用', 'review': '待精修', 'archived': '已归档'}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def tags_from_text(value):
    return list(dict.fromkeys(s.strip()[:60] for s in re.split(r'[,，;；\n]', value) if s.strip()))[:40]


class PhotoLibrary:
    def __init__(self, root=None):
        self.root = Path(root or DATA / 'library')
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'files').mkdir(exist_ok=True)
        self.database = self.root / 'library.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS albums(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS photos(
                    id TEXT PRIMARY KEY, source_hash TEXT UNIQUE NOT NULL, source TEXT NOT NULL,
                    name TEXT NOT NULL, album TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
                    favorite INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'ready',
                    notes TEXT NOT NULL DEFAULT '', width INTEGER, height INTEGER, seconds REAL,
                    current_version TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS versions(
                    id TEXT PRIMARY KEY, photo TEXT NOT NULL, mask TEXT NOT NULL,
                    initial_mask TEXT NOT NULL, preview TEXT NOT NULL, created REAL NOT NULL,
                    UNIQUE(photo,mask,initial_mask));
                CREATE INDEX IF NOT EXISTS by_photo ON versions(photo);
                CREATE INDEX IF NOT EXISTS by_album ON photos(album);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _put(self, path):
        path = Path(path)
        key = digest(path)
        suffix = path.suffix.lower()
        if suffix not in ('.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff'):
            raise ValueError('照片库只接受图片文件')
        relative = f'files/{key}{suffix}'
        target = self.root / relative
        if not target.exists():
            temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.writing')
            try:
                shutil.copyfile(path, temporary)
                if digest(temporary) != key:
                    raise OSError('复制过程中素材发生变化，请重试')
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        elif digest(target) != key:
            raise OSError('照片库文件校验失败，请从归档包恢复素材')
        return relative, key

    def albums(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT a.*,COUNT(p.id) count FROM albums a '
                    'LEFT JOIN photos p ON p.album=a.id GROUP BY a.id ORDER BY a.name COLLATE NOCASE')]

    def create_album(self, name):
        name = name.strip()[:100]
        if not name:
            raise ValueError('请输入专辑名称')
        with self.connect() as db:
            found = db.execute('SELECT id FROM albums WHERE name=?', (name,)).fetchone()
            if found:
                return found['id']
            key = uuid.uuid4().hex
            db.execute('INSERT INTO albums VALUES(?,?)', (key, name))
            return key

    def rename_album(self, key, name):
        name = name.strip()[:100]
        if not name:
            raise ValueError('请输入专辑名称')
        with self.connect() as db:
            db.execute('UPDATE albums SET name=? WHERE id=?', (name, key))

    def remove_album(self, key):
        with self.connect() as db:
            db.execute("UPDATE photos SET album='' WHERE album=?", (key,))
            db.execute('DELETE FROM albums WHERE id=?', (key,))

    def original_preview(self, source):
        target = self.root / 'files' / (Path(source).stem + '.original.jpg')
        if not target.exists():
            oriented_image(self.root / source, 420).save(target, quality=85)

    def rows(self):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT p.*,v.mask,v.initial_mask,v.preview,'
                    '(SELECT COUNT(*) FROM versions WHERE photo=p.id) version_count '
                    'FROM photos p JOIN versions v ON v.id=p.current_version ORDER BY p.created DESC,p.id')]
        for row in rows:
            row['tags'] = json.loads(row['tags'])
        return rows

    def get(self, key):
        with self.connect() as db:
            found=db.execute('SELECT p.*,v.mask,v.initial_mask,v.preview,'
                '(SELECT COUNT(*) FROM versions WHERE photo=p.id) version_count '
                'FROM photos p JOIN versions v ON v.id=p.current_version WHERE p.id=?',(key,)).fetchone()
        if not found:return None
        row=dict(found);row['tags']=json.loads(row['tags']);return row

    def asset_view(self, key):
        row=self.get(key)
        if not row:raise ValueError('照片不存在')
        return Asset(row['id'],row['name'],str(self.root/row['source']),str(self.root/row['mask']),
                     str(self.root/row['initial_mask']),row['seconds'],row['width'],row['height'])

    def versions(self, key):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM versions WHERE photo=? ORDER BY created DESC,id', (key,))]

    def find_source(self, path):
        key = digest(path)
        return next((r for r in self.rows() if r['source_hash'] == key), None)

    def capture(self, asset, album=''):
        # Only already processed assets enter the library; no model is invoked.
        with Image.open(asset.mask) as mask:
            mask.verify()
        with Image.open(asset.initial_mask or asset.mask) as baseline:
            baseline.verify()
        source, source_hash = self._put(asset.source)
        self.original_preview(source)
        mask, _ = self._put(asset.mask)
        initial, _ = self._put(asset.initial_mask or asset.mask)
        with self.connect() as db:
            row = db.execute('SELECT * FROM photos WHERE source_hash=?', (source_hash,)).fetchone()
            photo = row['id'] if row else uuid.uuid4().hex
            version = db.execute('SELECT id FROM versions WHERE photo=? AND mask=? AND initial_mask=?',
                                 (photo, mask, initial)).fetchone()
            if version:
                if album:
                    db.execute('UPDATE photos SET album=? WHERE id=?', (album, photo))
                return photo, False
            version_id = uuid.uuid4().hex
            # A small, ready-to-display cutout thumbnail avoids decoding originals while browsing.
            preview_image = make_cutout(asset, 420)
            preview_path = self.root / 'files' / f'{version_id}.png'
            preview_image.save(preview_path)
            preview, _ = self._put(preview_path)
            preview_path.unlink(missing_ok=True)
            now = time.time()
            db.execute('INSERT INTO versions(id,photo,mask,initial_mask,preview,created) VALUES(?,?,?,?,?,?)',
                       (version_id, photo, mask, initial, preview, now))
            if row:
                db.execute('UPDATE photos SET current_version=?,album=? WHERE id=?',
                           (version_id, album or row['album'], photo))
            else:
                with Image.open(asset.source) as image:
                    width, height = image.size
                db.execute('INSERT INTO photos(id,source_hash,source,name,album,width,height,seconds,current_version,created) '
                           'VALUES(?,?,?,?,?,?,?,?,?,?)', (photo, source_hash, source, asset.name[:200], album,
                           asset.width or width, asset.height or height, asset.seconds, version_id, now))
        return photo, True

    def update(self, keys, **changes):
        allowed = {'name','album','tags','favorite','status','notes','current_version'}
        if not changes or set(changes) - allowed:
            raise ValueError('照片信息字段不正确')
        changes = dict(changes)
        if 'status' in changes and changes['status'] not in STATUSES:
            raise ValueError('处理状态不正确')
        if 'tags' in changes:
            value = changes['tags']
            if not isinstance(value, list):
                raise ValueError('标签格式不正确')
            changes['tags'] = json.dumps(tags_from_text(','.join(str(t) for t in value)), ensure_ascii=False)
        if 'favorite' in changes:
            changes['favorite'] = int(bool(changes['favorite']))
        if 'name' in changes:
            changes['name'] = str(changes['name']).strip()[:200]
            if not changes['name']:
                raise ValueError('照片名称不能为空')
        if 'notes' in changes:
            changes['notes'] = str(changes['notes'])[:4000]
        with self.connect() as db:
            if changes.get('album') and not db.execute('SELECT id FROM albums WHERE id=?', (changes['album'],)).fetchone():
                raise ValueError('专辑不存在')
            for key in keys:
                if 'current_version' in changes and not db.execute('SELECT id FROM versions WHERE id=? AND photo=?',
                        (changes['current_version'], key)).fetchone():
                    raise ValueError('蒙版版本不属于这张照片')
                db.execute('UPDATE photos SET ' + ','.join(f'{k}=?' for k in changes) + ' WHERE id=?',
                           [*changes.values(), key])

    def materialize(self, key, destination=DATA, version=None):
        row = self.get(key)
        if not row:
            raise ValueError('照片不存在')
        selected = next((v for v in self.versions(key) if v['id'] == (version or row['current_version'])), None)
        if not selected:
            raise ValueError('蒙版版本不存在')
        destination = Path(destination)
        key = uuid.uuid4().hex[:16]
        paths = {}
        for field, relative in [('source', row['source']), ('mask', selected['mask']), ('initial_mask', selected['initial_mask'])]:
            folder = destination / ('sources' if field == 'source' else 'masks')
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f'{key}.{field}{Path(relative).suffix}'
            shutil.copyfile(self.root / relative, target)
            paths[field] = str(target)
        return Asset(key, row['name'], **paths, width=row['width'], height=row['height'], seconds=row['seconds'])

    def snapshot(self):
        with self.connect() as db:
            return {table: [dict(r) for r in db.execute('SELECT * FROM ' + table)]
                    for table in ('albums', 'photos', 'versions')}

    def restore_snapshot(self, snapshot):
        # Undo changes only index entries. Immutable files remain available for redo.
        with self.connect() as db:
            for table in ('versions', 'photos', 'albums'):
                db.execute('DELETE FROM ' + table)
            for table in ('albums', 'photos', 'versions'):
                for row in snapshot[table]:
                    db.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', list(row.values()))

    def export_archive(self, keys, filename, notify=lambda _: None, cancelled=lambda: False):
        wanted = set(keys)
        rows = [r for r in self.rows() if r['id'] in wanted]
        if not rows:
            raise ValueError('请先选择要归档的照片')
        album_names = {r['id']: r['name'] for r in self.albums()}
        manifest = {'format': 'cosfolio-photo-library', 'version': 1, 'photos': [], 'checksums': {}}
        members = set()
        for row in rows:
            row = dict(row)
            row['album_name'] = album_names.get(row['album'], '')
            row['versions'] = self.versions(row['id'])
            members.add(row['source'])
            for version in row['versions']:
                members.update(version[f] for f in ('mask', 'initial_mask', 'preview'))
            manifest['photos'].append(row)
        target = Path(filename)
        temporary = target.with_name(target.name + '.' + uuid.uuid4().hex + '.writing')
        try:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                for index, relative in enumerate(sorted(members)):
                    if cancelled():
                        raise InterruptedError('归档已取消，原照片保留')
                    notify(f'打包并校验素材 {index+1}/{len(members)}')
                    source = self.root / relative
                    checksum = hashlib.sha256()
                    with source.open('rb') as src, archive.open(relative, 'w', force_zip64=True) as dst:
                        for block in iter(lambda: src.read(1024 * 1024), b''):
                            if cancelled(): raise InterruptedError('归档已取消，原照片保留')
                            dst.write(block); checksum.update(block)
                    actual = checksum.hexdigest()
                    if actual != Path(relative).stem:
                        raise OSError('照片库素材校验失败，已有归档未修改，请检查原素材')
                    manifest['checksums'][relative] = actual
                archive.writestr('library.json', json.dumps(manifest, ensure_ascii=False))
            # Validate the saved ZIP bytes before replacing any previous archive.
            with zipfile.ZipFile(temporary) as archive:
                for relative, expected in manifest['checksums'].items():
                    if cancelled(): raise InterruptedError('归档已取消，原照片保留')
                    with archive.open(relative) as stream:
                        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                    if checksum != expected:
                        raise OSError('归档校验失败，请重试')
            os.replace(temporary, target)
            return len(rows)
        finally:
            temporary.unlink(missing_ok=True)

    def import_archive(self, filename, notify=lambda _: None, cancelled=lambda: False):
        with tempfile.TemporaryDirectory(prefix='restore-', dir=self.root) as temporary, zipfile.ZipFile(filename) as archive:
            stage = Path(temporary)
            info = archive.getinfo('library.json')
            if info.file_size > 8 * 1024**2:
                raise ValueError('归档目录信息过大')
            manifest = json.loads(archive.read(info))
            if manifest.get('format') != 'cosfolio-photo-library' or manifest.get('version') != 1:
                raise ValueError('不是支持的 Cosfolio 照片归档包')
            photos = manifest.get('photos', [])
            checksums = manifest.get('checksums', {})
            if not isinstance(photos, list) or not 1 <= len(photos) <= 10000 or not isinstance(checksums, dict):
                raise ValueError('归档目录格式不正确')
            for index, (relative, expected) in enumerate(checksums.items()):
                if cancelled(): raise InterruptedError('恢复已取消')
                if not re.fullmatch(r'files/[a-f0-9]{64}\.(png|jpg|jpeg|webp|tif|tiff)', relative):
                    raise ValueError('归档素材路径不正确')
                item = archive.getinfo(relative)
                if item.file_size > 512 * 1024**2:
                    raise ValueError('单张归档素材超过 512 MB')
                dest = stage / Path(relative).name
                notify(f'校验并恢复素材 {index+1}/{len(checksums)}')
                checksum = hashlib.sha256()
                with archive.open(item) as src, dest.open('wb') as dst:
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        if cancelled(): raise InterruptedError('恢复已取消')
                        checksum.update(block); dst.write(block)
                if checksum.hexdigest() != expected or Path(relative).stem != expected:
                    raise ValueError('归档素材校验失败，照片库未修改')
                with Image.open(dest) as image:
                    image.verify()
            # Validate every reference before changing the index.
            for row in photos:
                versions = row.get('versions', [])
                if not versions or row.get('source') not in checksums:
                    raise ValueError('归档缺少原图或蒙版')
                if row.get('source_hash') != checksums[row['source']]:
                    raise ValueError('归档原图标识不正确')
                if row.get('current_version') not in [v.get('id') for v in versions]:
                    raise ValueError('归档当前蒙版不存在')
                for version in versions:
                    if any(version.get(f) not in checksums for f in ('mask','initial_mask','preview')):
                        raise ValueError('归档缺少处理结果')
                if row.get('status') not in STATUSES or not isinstance(row.get('tags'), list):
                    raise ValueError('归档照片信息不正确')
            if cancelled(): raise InterruptedError('恢复已取消')
            # Files are immutable and content addressed; existing originals never change.
            for path in stage.iterdir():
                if cancelled(): raise InterruptedError('恢复已取消，照片库目录未修改')
                self._put(path)
            for row in photos:
                self.original_preview(row['source'])
            if cancelled(): raise InterruptedError('恢复已取消，照片库目录未修改')
            with self.connect() as db:
                for row in photos:
                    existing = db.execute('SELECT * FROM photos WHERE source_hash=?', (row['source_hash'],)).fetchone()
                    key = existing['id'] if existing else uuid.uuid4().hex
                    album = ''
                    if row.get('album_name'):
                        name = str(row['album_name'])[:100]
                        found = db.execute('SELECT id FROM albums WHERE name=?', (name,)).fetchone()
                        album = found['id'] if found else uuid.uuid4().hex
                        if not found: db.execute('INSERT INTO albums VALUES(?,?)', (album, name))
                    mapping = {}
                    for version in row['versions']:
                        found = db.execute('SELECT id FROM versions WHERE photo=? AND mask=? AND initial_mask=?',
                                           (key,version['mask'],version['initial_mask'])).fetchone()
                        new_id = found['id'] if found else uuid.uuid4().hex
                        if not found:
                            db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)',
                                (new_id,key,version['mask'],version['initial_mask'],version['preview'],time.time()))
                        mapping[version['id']] = new_id
                    if not existing:
                        db.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key,row['source_hash'],row['source'],str(row['name'])[:200],album,
                             json.dumps(tags_from_text(','.join(str(t) for t in row['tags'])),ensure_ascii=False),
                             int(bool(row['favorite'])),row['status'],str(row.get('notes',''))[:4000],
                             int(row['width']),int(row['height']),float(row.get('seconds',0)),
                             mapping[row['current_version']],time.time()))
            return len(photos)
