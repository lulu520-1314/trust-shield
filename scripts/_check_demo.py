import json, os, re

DOCS = 'docs'
js = open(os.path.join(DOCS, 'demo-data.js'), encoding='utf-8').read()
payload = json.loads(js[len('window.__DEMO__ = '):].rstrip(';\n'))

need = set()
for rep in payload['reports'].values():
    for im in rep.get('images', []):
        need.add(im['url'])
        need.update((im.get('heat') or {}).values())

have = set(os.listdir(os.path.join(DOCS, 'cache')))
missing = sorted(need - have)
print(f'引用 {len(need)} 个资产，缺失 {len(missing)} 个')
for m in missing:
    print('  缺:', m)

for sc, lst in payload['samples'].items():
    print(f'{sc}: {len(lst)} 组 -> ' + '、'.join(s['id'] for s in lst))
print(f"问答 {len(payload['answers'])} 条")
