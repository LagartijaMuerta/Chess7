import csv, ast
p='RaspberryChessBoard/field_leds.csv'
with open(p,'r',encoding='utf-8',newline='') as f:
    r=csv.DictReader(f)
    print('fieldnames', r.fieldnames)
    for i,row in enumerate(r):
        if i<3:
            print('row',i)
            for k,v in row.items():
                print('  key:',repr(k))
                print('   val:',repr(v[:120]))
            try:
                g1=row[r.fieldnames[1]]
                print('g1 raw:',g1)
                print('g1 ast:', ast.literal_eval(g1))
            except Exception as e:
                print('g1 parse error',e)
        else:
            break
