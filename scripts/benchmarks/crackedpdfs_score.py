import pandas as pd, json, sys, collections
t = pd.read_csv('test_meta.csv'); R = {json.loads(l)['file_path']: json.loads(l) for l in open(sys.argv[1])}
t['flag'] = t.file_path.map(lambda p: len(R[p]['findings']) > 0); t['instr'] = t.file_path.map(lambda p: bool(R[p]['instruction_like']))
t['err'] = t.file_path.map(lambda p: bool(R[p].get('error')) or bool(R[p].get('scan_incomplete')))
print('errors/incomplete:', int(t.err.sum()), '| median seconds per file:', pd.Series([r['seconds'] for r in R.values()]).median())
def prf(pos_col):
    inj = t[t.label == 1]; neg = t[t.label == 0]; tp = int(inj[pos_col].sum()); fn = len(inj) - tp; fp = int(neg[pos_col].sum()); tn = len(neg) - fp
    p = tp / (tp + fp) if tp + fp else 0; r = tp / (tp + fn); f1 = 2 * p * r / (p + r) if p + r else 0
    return dict(TP=tp, FN=fn, FP=fp, TN=tn, precision=round(p, 4), recall=round(r, 4), F1=round(f1, 4), accuracy=round((tp + tn) / len(t), 4), false_alarm=round(fp / len(neg), 4))
print('\nSTAGE 1  any concealment finding      :', prf('flag'))
print('STAGE 1+2 concealed AND instruction-like:', prf('instr'))
print('\nby role (flag / instruction-like):'); print(t.groupby('pdf_role')[['flag', 'instr']].agg(['sum', 'count']).to_string())
inj = t[t.label == 1]
print('\ninjected by rendering regime:'); print(inj.groupby('rendering_regime')[['flag', 'instr']].agg(['sum', 'count']).to_string())
print('\ninjected by attack family (stage 1+2):'); print(inj.groupby('attack_family')['instr'].agg(['sum', 'count', 'mean']).round(3).to_string())
print('\ninjected by message type (stage 1+2):'); print(inj.groupby('message_type')['instr'].agg(['sum', 'count', 'mean']).round(3).to_string())
con = t[t.pdf_role == 'benign_confounder']; print('\nconfounder families flagged as instruction-like:', con[con.instr].benign_confounder_family.value_counts().to_dict())
bal = pd.concat([inj, con]); tp = int(inj.instr.sum()); fp = int(con.instr.sum())
print('\nBALANCED PAIRED SUBSET (973 injected + 973 confounders): accuracy', round((tp + len(con) - fp) / len(bal), 4))
print('mechanisms fired on injected:', collections.Counter(f['mechanism'] for p in inj.file_path for f in R[p]['findings']).most_common(6))
t.to_csv('scored_v2.csv', index=False)
