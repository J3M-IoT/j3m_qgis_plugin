"""Check packaging, Python baseline and Qt import conventions without QGIS."""
import ast
from configparser import ConfigParser
from pathlib import Path
from zipfile import ZipFile


def main():
    root=Path(__file__).resolve().parents[1]
    meta=ConfigParser()
    meta.read(root/'j3m_connect'/'metadata.txt',encoding='utf-8-sig')
    general=meta['general']
    assert general['version']=='1.2.0'
    assert general['qgisMinimumVersion']=='3.28'
    assert general['qgisMaximumVersion']=='4.99'
    assert general['license']=='GNU GPL v3'
    checked=[]
    for path in (root/'j3m_connect').glob('*.py'):
        source=path.read_text(encoding='utf-8-sig')
        tree=ast.parse(source,filename=str(path),feature_version=(3,9))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith(('PyQt5','PyQt6','PySide')),path
            if isinstance(node,ast.Import):
                assert not any(alias.name.startswith(('PyQt5','PyQt6','PySide')) for alias in node.names),path
        checked.append(path.name)
    zip_path=root/'dist'/('j3m_connect-'+general['version']+'.zip')
    with ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        names=set(archive.namelist())
        assert all(name.startswith('j3m_connect/') for name in names)
        assert not any('__pycache__' in name or name.endswith('.env') or '/tests/' in name for name in names)
        for filename in checked:
            assert archive.read('j3m_connect/'+filename)==(root/'j3m_connect'/filename).read_bytes(),filename
        for filename in ('metadata.txt','config.json','LICENSE','j3m-logo.jpeg'):
            assert archive.read('j3m_connect/'+filename)==(root/'j3m_connect'/filename).read_bytes(),filename
        for filename in ('i18n/en-us.json', 'i18n/es-es.json'):
            assert archive.read('j3m_connect/'+filename)==(root/'j3m_connect'/filename).read_bytes(),filename
        for filename in ('README.md','CHANGELOG.md'):
            assert archive.read('j3m_connect/'+filename)==(root/filename).read_bytes(),filename
    print('OK: ZIP, '+str(len(checked))+' Python modules, Python 3.9 syntax, qgis.PyQt imports, GPL v3 and QGIS 3.28-4.99 metadata.')
    print('Static checks do not replace QGIS runtime tests.')


if __name__=='__main__':
    main()
