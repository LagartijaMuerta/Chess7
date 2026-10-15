import csv
p='RaspberryChessBoard/field_leds.csv'
with open(p,'r',encoding='utf-8',newline='') as csvfile:
    sn=csv.Sniffer()
    sample=csvfile.read(2048)
    csvfile.seek(0)
    try:
        dialect=sn.sniff(sample)
    except Exception:
        dialect=csv.excel
    reader=csv.DictReader(csvfile,dialect=dialect)
    print('raw fieldnames',reader.fieldnames)
    if not reader.fieldnames or 'coord' not in [fn.lower() for fn in (reader.fieldnames or [])]:
        csvfile.seek(0)
        reader=csv.DictReader(csvfile,delimiter=';')
    if reader.fieldnames:
        fnorm=[fn.lstrip('\ufeff').strip() for fn in reader.fieldnames]
        print('normalized fieldnames',fnorm)
    actual_names = {fn.lower(): fn for fn in (reader.fieldnames or [])}
    def find_header(token):
        token = token.lower().replace('_','').replace(' ','')
        for low, orig in actual_names.items():
            key = low.replace('_','').replace(' ','')
            if token in key or key in token:
                return orig
        return None
    hdr_coord = find_header('coord') or 'coord'
    hdr_g1 = find_header('led_group_1') or find_header('ledgroup1') or 'LED_group_1'
    hdr_g2 = find_header('led_group_2') or find_header('ledgroup2') or 'LED_group_2'
    hdr_color = find_header('fieldcolor') or find_header('field_color') or 'fieldColor'
    print('mapped headers:', hdr_coord, hdr_g1, hdr_g2, hdr_color)
    csvfile.seek(0)
    reader2=csv.DictReader(csvfile,dialect=dialect)
    # apply normalized fieldnames to reader2
    reader2.fieldnames = [fn.lstrip('\ufeff').strip() for fn in reader2.fieldnames]
    print('reader2 fieldnames:', reader2.fieldnames)
    row=next(iter(reader2),None)
    print('first row sample:', row)
