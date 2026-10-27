"""Packaged-app verification. Only run explicitly with --self-check."""
def run():
    import os
    import socket
    import json
    import copy
    import hashlib
    import traceback
    import time
    os.environ['QT_QPA_PLATFORM']='offscreen'
    from .core import DATA, MODEL, LocalSegmenter, Asset, Project, prepare_directories, save_project, load_project
    prepare_directories()
    def blocked(*args,**kwargs):
        raise RuntimeError('Network access forbidden in offline check')
    socket.socket.connect=blocked
    socket.getaddrinfo=blocked
    socket.create_connection=blocked
    report={'python_network':'blocked','model_exists':MODEL.is_file(),'passed':False}
    try:
        from PySide6.QtWidgets import QApplication
        from .app import Studio, configure_app, shutdown_gui
        from .render import Renderer
        from .catalog import TEMPLATES
        from .app import TemplateDialog,MaskDialog
        from PySide6.QtCore import Qt,QPoint,QPointF
        from PySide6.QtGui import QWheelEvent
        from .core import ROOT
        app=QApplication([])
        configure_app(app)
        from PIL import Image, ImageDraw
        studio=Studio(Project())
        assert not studio.project.assets and not Studio.initial_project().assets
        report['startup_assets']=0
        assert 'Cosfolio · 偶像写真工房' in studio.windowTitle()
        assert studio.project.text_mode=='original'
        report['product_name']='Cosfolio · 偶像写真工房'
        report['default_text_mode']=studio.project.text_mode
        report['template_count']=len(TEMPLATES)
        assert studio.export_size.currentData()==6000 and studio.export_size.findData(8000)>=0
        assert studio.settings_tabs.count()==5
        report['default_export_long_edge']=6000
        report['maximum_export_long_edge']=8000
        report['calibrated_dream_middle']=TEMPLATES['dream_mosaic']['slots'][2]
        assert tuple(report['calibrated_dream_middle'])==(560,866,489,606)
        manifest=json.loads((ROOT/'resources'/'templates'/'v04'/'index.json').read_text(encoding='utf-8'))
        assert len(manifest)==20
        for record in manifest:
            config=TEMPLATES[record['template']]
            with Image.open(ROOT/'resources'/'templates'/config['plate']) as plate:
                assert hashlib.sha256(plate.convert('RGB').tobytes()).hexdigest()==record['decoded_rgb_sha256']
            reference=ROOT/'resources'/'templates'/config['reference']
            assert hashlib.sha256(reference.read_bytes()).hexdigest()==record['reference_sha256']
        report['faithful_source_templates']=len(manifest)
        report['paired_original_references']=len(manifest)
        for key,config in TEMPLATES.items():
            assert (ROOT/'resources'/'templates'/'previews'/f'{key}.jpg').is_file()
            if config.get('plate'):
                assert (ROOT/'resources'/'templates'/config['plate']).is_file()
        picker=TemplateDialog('party',studio)
        picker.gallery.setCurrentRow(list(TEMPLATES).index('balloon_five'))
        assert picker.chosen=='balloon_five'
        picker.show()
        app.processEvents()
        picker.open_reference()
        assert picker.reference_window.key=='balloon_five' and picker.reference_window.canvas.picture is not None
        report['original_reference_viewer']=True
        picker.grab().save(str(DATA/'reports'/'packaged-gallery.png'))
        picker.reject()
        picker.deleteLater()
        start=time.monotonic()
        # Generated test shapes exercise the installed model without shipping or
        # copying any of the user's portrait photographs into the new release.
        image=Image.new('RGB',(480,720),'#e9edf4')
        draw=ImageDraw.Draw(image)
        draw.ellipse((153,58,327,260),fill='#262f59')
        draw.ellipse((177,105,304,244),fill='#e9b59a')
        draw.polygon(((169,242),(310,242),(366,573),(111,573)),fill='#416aaa')
        draw.line((168,270,95,440),fill='#e9b59a',width=30)
        draw.line((313,270,391,438),fill='#e9b59a',width=30)
        draw.rectangle((165,566,204,690),fill='#343f68')
        draw.rectangle((271,566,310,690),fill='#343f68')
        source=DATA/'reports'/'generated-probe.png'
        mask_path=DATA/'reports'/'generated-probe-mask.png'
        image.save(source)
        segmenter=LocalSegmenter()
        mask=segmenter.predict(image)
        mask.save(mask_path)
        assert mask.getextrema()==(0,255)
        report['inference_seconds']=round(time.monotonic()-start,2)
        tuned=copy.deepcopy(studio.project)
        tuned.assets=[Asset('probe','generated-probe.png',str(source),str(mask_path),str(mask_path),width=480,height=720)]
        verify_v08(app,studio,segmenter,tuned.assets[0],report)
        verify_v09(app,studio,segmenter,tuned.assets[0],report)
        tuned.placements[0].asset_id='probe'
        tuned.text_mode='custom'
        tuned.body='在本机记录每一次闪光。'
        tuned.placements[0].contrast=1.12
        tuned.placements[0].saturation=.8
        tuned.placements[0].warmth=-.15
        tuned.placements[0].flip=True
        editor_mask=DATA/'reports'/'generated-editor-mask.png'
        Image.new('L',image.size,255).save(editor_mask)
        editor_asset=Asset('editor-probe','generated-probe.png',str(source),str(editor_mask),str(editor_mask),width=480,height=720)
        editor=MaskDialog(editor_asset,studio)
        editor.show()
        app.processEvents()
        center=QPointF(editor.canvas.rect().center())
        event=QWheelEvent(center,QPointF(editor.canvas.mapToGlobal(center.toPoint())),QPoint(),QPoint(0,120),
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(editor.canvas,event)
        assert editor.canvas.zoom>1
        radius=editor.canvas.radius
        event=QWheelEvent(center,QPointF(editor.canvas.mapToGlobal(center.toPoint())),QPoint(),QPoint(120,0),
                          Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(editor.canvas,event)
        assert editor.canvas.radius>radius
        editor.canvas.fit_view()
        editor.canvas.actual_size()
        editor.canvas.set_brush_size(1)
        point=QPointF(editor.canvas.paper.x()+240,editor.canvas.paper.y()+360)
        editor.canvas.stroke(point)
        assert editor.canvas.mask.getpixel((240,360))==0
        assert editor.canvas.picture.toImage().pixelColor(240,360).alpha()==0
        editor.reject()
        editor.deleteLater()
        report['precision_mask_controls']=True
        save_project(tuned,DATA/'reports'/'roundtrip.cosfolio')
        reopened=load_project(DATA/'reports'/'roundtrip.cosfolio')
        assert reopened.text_mode=='custom' and reopened.body==tuned.body
        assert reopened.placements[0].contrast==1.12 and reopened.placements[0].flip
        report['new_adjustments_roundtrip']=True
        tuned.add_page(True)
        tuned.title='OFFLINE BOOK PAGE 2'
        tuned.page_numbers=True
        tuned.placements[0].edge_shift=-1
        tuned.placements[0].shadow=True
        tuned.placements[0].shadow_x=-10
        save_project(tuned,DATA/'reports'/'book-roundtrip.cosfolio')
        book=load_project(DATA/'reports'/'book-roundtrip.cosfolio')
        assert book.page_count==2 and book.active_page==1 and book.page_numbers
        assert book.page_project(0).asset(book.page_project(0).placements[0].asset_id) is not None
        assert book.placements[0].edge_shift==-1 and book.placements[0].shadow_x==-10
        report['book_roundtrip']=True
        verify_v06(app,studio,segmenter,source,DATA/'reports'/'book-roundtrip.cosfolio',report)
        size=Renderer().export(reopened,DATA/'reports'/'packaged-export.png',2000)
        report['export_size']=size
        with __import__('PIL.Image',fromlist=['Image']).open(DATA/'reports'/'packaged-export.png') as output:
            report['embedded_srgb']=bool(output.info.get('icc_profile'))
            assert report['embedded_srgb']
        high_size=Renderer().export(book,DATA/'reports'/'packaged-8000.jpg',8000)
        assert max(high_size)==8000
        report['actual_8000_export']=high_size
        studio.show()
        app.processEvents()
        studio.canvas.render_page()
        app.processEvents()
        studio.grab().save(str(DATA/'reports'/'packaged-ui.png'))
        studio.dirty=False
        studio.close()
        report['passed']=True
    except Exception:
        report['error']=traceback.format_exc()
    (DATA/'reports'/'packaged-self-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if 'app' in locals():
        shutdown_gui(app)
    if not report['passed']:
        raise SystemExit(1)


def verify_v08(app,studio,segmenter,asset,report):
    import tempfile
    from pathlib import Path
    from .core import DATA
    from .library import PhotoLibrary,digest
    from .library_ui import PhotoLibraryDialog
    from PySide6.QtCore import QItemSelectionModel
    with tempfile.TemporaryDirectory(prefix='cosfolio-packaged-library-') as folder:
        root=Path(folder);library=PhotoLibrary(root/'library')
        album=library.create_album('离线照片库验证');key,_=library.capture(asset,album)
        library.update([key],tags=['海未','验证'],favorite=True)
        archive=root/'test.cosphotos';library.export_archive([key],archive)
        restored=PhotoLibrary(root/'restored');restored.import_archive(archive)
        assert restored.rows()[0]['tags']==['海未','验证']
        independent=library.materialize(key,root/'independent')
        assert digest(independent.mask)==digest(asset.mask)
        dialog=PhotoLibraryDialog(segmenter,[asset],studio,library=library)
        dialog.show();app.processEvents()
        dialog.grid.selectionModel().select(dialog.model.index(0),QItemSelectionModel.SelectionFlag.ClearAndSelect)
        assert dialog.selected_keys()==[key]
        dialog.toggle_favorite();assert not library.get(key)['favorite']
        dialog.undo();assert library.get(key)['favorite']
        dialog.grab().save(str(DATA/'reports'/'packaged-photo-library.png'))
        dialog.reject();dialog.deleteLater();app.processEvents()
        report['photo_library_v08']={'three_panes':True,'reuse_masks':True,'portable_archive':True,'independent_project_assets':True,'undo':True}


def verify_v09(app,studio,segmenter,asset,report):
    import tempfile,time
    from pathlib import Path
    from PIL import Image
    from .core import DATA,Asset
    from .library import PhotoLibrary
    from .library_export import export_cutouts,export_contact_sheets
    from .compare import CompareDialog
    from .app import TemplateDialog
    from . import template_preferences as preferences
    old_path=preferences.PATH
    with tempfile.TemporaryDirectory(prefix='cosfolio-packaged-v09-') as folder:
        root=Path(folder);preferences.PATH=root/'template-preferences.json'
        try:
            picker=TemplateDialog('party',studio);picker.show();app.processEvents()
            picker.metadata_change(lambda:preferences.rename('party','我的海未照片模板'))
            picker.toggle_template_favorite();picker.favorites_only.setChecked(True);picker.search.setText('海未')
            assert picker.name.text()=='我的海未照片模板'
            assert sum(not picker.gallery.item(i).isHidden() for i in range(picker.gallery.count()))==1
            picker.grab().save(str(DATA/'reports'/'packaged-template-library-v09.png'))
            picker.reject();picker.deleteLater();app.processEvents()
            library=PhotoLibrary(root/'photos');first,_=library.capture(asset)
            other=root/'other.png';Image.new('RGB',(720,480),'#174d8b').save(other)
            second,_=library.capture(Asset('other','第二张.png',str(other),asset.mask,asset.initial_mask,width=720,height=480))
            png=export_cutouts(library,[first,second],root)
            assert len(png['files'])==2 and not png['errors']
            contact=export_contact_sheets(library,[first,second],root,'海未 · 选片联系表')
            assert len(contact['files'])==1 and (Path(contact['folder'])/'选片编号.csv').is_file()
            from shutil import copy2
            copy2(Path(contact['folder'])/contact['files'][0]['file'],DATA/'reports'/'packaged-contact-v09.png')
            compare=CompareDialog(library,[first,second],studio);compare.show();app.processEvents()
            deadline=time.monotonic()+30
            while not all(v.picture is not None and v.worker is None for v in compare.views) and time.monotonic()<deadline:
                app.processEvents();time.sleep(.01)
            assert all(v.picture is not None for v in compare.views)
            compare.actual_all();state_a=compare.views[0].view_state();state_b=compare.views[1].view_state()
            assert abs(state_a[0]-1)<.001 and abs(state_b[0]-1)<.001
            compare.grab().save(str(DATA/'reports'/'packaged-compare-v09.png'))
            compare.reject();compare.deleteLater();app.processEvents()
            report['iteration_v09']={'deeper_umi_blue':True,'comparison':True,'template_search_favorites_rename':True,
                                     'batch_transparent_png':len(png['files']),'numbered_contact_sheet':True,'new_models':[]}
        finally:
            preferences.PATH=old_path;studio.refresh_template_labels()


def verify_v06(app,studio,segmenter,source,book_path,report):
    """Exercise the trial with the bundled model and an isolated user library."""
    from pathlib import Path
    import io
    import tempfile
    import time
    import zipfile
    from PIL import Image,ImageChops
    from PySide6.QtCore import Qt,QPointF,QEvent
    from PySide6.QtGui import QMouseEvent
    from .core import Project,save_project,load_project,DATA
    from .catalog import TEMPLATES
    from .controls import ResetSlider
    from .projects_ui import project_summary,ProjectGallery
    from .template_wizard import TemplateWizard
    from .render import Renderer
    import cosfolio.template_store as store
    assert studio.shadow.isChecked() and Project().placements[0].shadow
    assert 'edge_shift' not in studio.sliders and 'edge_softness' not in studio.sliders
    slider=studio.sliders['brightness']
    assert isinstance(slider,ResetSlider)
    slider.setValue(slider.default+12)
    center=QPointF(slider.rect().center())
    event=QMouseEvent(QEvent.Type.MouseButtonDblClick,center,QPointF(slider.mapToGlobal(center.toPoint())),
                      Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    app.sendEvent(slider,event)
    assert slider.value()==slider.default
    report['photo_controls_v06']=True
    with zipfile.ZipFile(book_path) as archive:
        with Image.open(io.BytesIO(archive.read('cover.jpg'))) as cover:assert max(cover.size)==640
    summary=project_summary(book_path)
    assert summary['pages']==2 and summary['cover']
    gallery=ProjectGallery([str(book_path)],str(book_path.parent),studio)
    gallery.show();app.processEvents();gallery.grab().save(str(DATA/'reports'/'packaged-project-gallery.png'))
    gallery.reject();gallery.deleteLater();report['project_cover_gallery']=True
    old_library=store.LIBRARY;keys=set(TEMPLATES)
    with tempfile.TemporaryDirectory(prefix='cosfolio-packaged-template-') as folder:
        folder=Path(folder);store.LIBRARY=folder/'library'
        wizard=TemplateWizard(segmenter,studio)
        try:
            assert wizard.acceptDrops() and wizard.source_canvas.isEnabled() and wizard.source_canvas.acceptDrops()
            assert wizard.mask_btn.text()=='手动添加/减去蒙版'
            wizard.load_source(source);wizard.show();wizard.next_step()
            deadline=time.monotonic()+60
            while wizard.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
            assert not wizard.busy and wizard.mask.getbbox()
            wizard.next_step()
            deadline=time.monotonic()+60
            while wizard.busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
            assert not wizard.busy and wizard.plate is not None
            expected=wizard.plate.copy()
            assert wizard.recipes[0]['mode']=='repair'
            from .clone_editor import CloneDialog
            clone=CloneDialog(wizard.image,wizard.plate,wizard.mask,wizard.source_canvas.regions,studio)
            clone.canvas.remember();clone.canvas.offset=(-150,-250);clone.canvas.stamp(200,300)
            clone.canvas.undo();assert ImageChops.difference(clone.canvas.result,expected).getbbox() is None
            clone.canvas.redo();clone.reject();clone.deleteLater()
            report['iteration_v07']={'drag_import':True,'subtract_mask':True,'scoped_undo':True,'patch_repair':True,'clone_repair':True}
            wizard.grab().save(str(DATA/'reports'/'packaged-template-wizard.png'))
            wizard.name.setText('Local template check');wizard.save_result()
            key=wizard.created_key
            assert key in TEMPLATES and Path(TEMPLATES[key]['reference']).read_bytes()==source.read_bytes()
            project=Project(template=key)
            assert ImageChops.difference(Renderer().render(project,max(expected.size)),expected).getbbox() is None
            path=folder/'trial.cosfolio';save_project(project,path)
            TEMPLATES.pop(key);store.LIBRARY=folder/'fresh-library'
            restored=load_project(path)
            assert restored.template==key and ImageChops.difference(Renderer().render(restored,max(expected.size)),expected).getbbox() is None
            report['local_template_trial']={'passed':True,'model':'existing','portable':True,'new_models':[]}
        finally:
            if wizard.worker and wizard.worker.isRunning():
                wizard.worker.requestInterruption();wizard.worker.wait()
            wizard.reject();wizard.deleteLater()
            for key in set(TEMPLATES)-keys:TEMPLATES.pop(key)
            store.LIBRARY=old_library
