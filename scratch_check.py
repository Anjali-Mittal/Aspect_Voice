import urllib.request, json
from collections import Counter

features_data = json.loads(urllib.request.urlopen('http://localhost:8000/features?vehicle=Hero+Vida+V2').read())
unique_features = sorted(list(set(d['feature'] for d in features_data)))
issues_data = json.loads(urllib.request.urlopen('http://localhost:8000/issues?vehicle=Hero+Vida+V2').read())
issue_counts = Counter(d['feature'] for d in issues_data)

res = []
for f in unique_features:
    summary = json.loads(urllib.request.urlopen('http://localhost:8000/features/' + urllib.request.quote(f) + '/summary?vehicle=Hero+Vida+V2').read())
    res.append({'feature': f, 'mentions': summary.get('mentions', 0), 'issues': issue_counts[f]})

print(json.dumps(res, ensure_ascii=True, indent=2))
