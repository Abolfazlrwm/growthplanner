"""Generate the Preview route list from actual Django page route names."""
import os
import sys
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.urls import get_resolver, URLResolver
PAGE_NAMES = {'home','stats','focus','offline','login','register','settings','password_reset','password_reset_done','password_reset_confirm','password_reset_complete','password_change','password_change_done','list','search','board','smart_add','detail','create','edit','delete','month','week','timeline','subscription','index','confirm_delete'}
rows = []
def walk(resolver, prefix='', namespace=''):
    for p in resolver.url_patterns:
        path = prefix + str(p.pattern)
        if isinstance(p, URLResolver):
            ns = namespace + ((p.namespace or '') + ':' if p.namespace else '')
            if ns.startswith(('admin:',)) or path.startswith('api/'):
                continue
            walk(p, path, ns)
        elif p.name in PAGE_NAMES:
            # POST-only task endpoints named create/delete are not page routes.
            if path.startswith('tasks/') and p.name in ('create','delete'):
                continue
            if path.startswith('journal/') and p.name != 'list':
                continue
            page = '/' + re.sub(r'<(?:[^:>]+:)?([^>]+)>', r':\1', path)
            rows.append({'path': page, 'title': namespace + str(p.name)})
walk(get_resolver())
rows = list({r['path']:r for r in rows}.values())
(ROOT/'static'/'manus-routes.json').write_text(json.dumps({'routes':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Generated {len(rows)} page routes from Django URLconf.')
