import os, csv, ast
p=os.path.join('RaspberryChessBoard','field_leds.csv')
encodings=['utf-8','utf-8-sig','cp1252','iso-8859-1']
for enc in encodings:
    try:
        with open(p,'r',encoding=enc,newline='') as f:
            sn=csv.Sniffer()
            sample=f.read(2048)
            f.seek(0)
            try:
                d=sn.sniff(sample)
            except Exception:
                d=csv.excel
            reader=csv.DictReader(f,dialect=d)
            rows=list(reader)
        print('enc',enc,'rows',len(rows),'fieldnames',reader.fieldnames)
        # test first row
        if rows:
            row=rows[0]
            print('first coord',row.get('coord') or row.get('\ufeffcoord') or list(row.keys())[0])
            g1=(row.get('LED_group_1') or row.get('"LED_group_1[(ledIndex, ChannelID),(ledIndex, ChannelID),(ledIndex, ChannelID),(ledIndex, ChannelID)]"') or row.get(list(row.keys())[1]))
            print('g1 raw',g1)
            print('g1 ast',ast.literal_eval(g1))
        break
    except Exception as e:
        print('enc',enc,'failed',e)
