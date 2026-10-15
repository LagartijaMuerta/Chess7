import csv
p='RaspberryChessBoard/field_leds.csv'
with open(p,'r',encoding='utf-8',newline='') as f:
    data=f.read()
print('len file',len(data))
# try delimiter ; directly
f=open(p,'r',encoding='utf-8',newline='')
r=csv.DictReader(f,delimiter=';')
print('fieldnames',r.fieldnames)
for i,row in enumerate(r):
    if i<5:
        print(i,row)
    else:
        break
f.close()
