import hashlib, os, sys
out = sys.argv[1]
G = 'JLH_project_handoff/jlh-handoff/game files'
ref = {'default.xbe': os.path.join(G, 'default.xbe')}
for n in os.listdir(os.path.join(G, 'res')):
    ref['res/' + n] = os.path.join(G, 'res', n)
for n in os.listdir('levels_hq'):
    ref['res/' + n] = os.path.join('levels_hq', n)
h = lambda p: hashlib.sha1(open(p, 'rb').read()).hexdigest()
ok = bad = 0
for k in sorted(ref):
    p = os.path.join(out, k)
    if not os.path.exists(p):
        print('MISSING', k); bad += 1; continue
    same = h(p) == h(ref[k])
    ok += same; bad += not same
    print('ok  ' if same else 'DIFF', k, os.path.getsize(p), os.path.getsize(ref[k]))
extra = set('res/' + n for n in os.listdir(os.path.join(out, 'res'))) - set(ref)
print('extra:', sorted(extra))
print(f'{ok} identical, {bad} different/missing')
