import pandas as pd
from graphql import build_schema
df = pd.read_excel('test_part2.xlsx')
errs = 0
for i, s in df['CleanSchema'].items():
    print(f'Checking schema {i}...')
    try:
        build_schema(str(s))
    except:
        errs += 1
print(f'Errors after save: {errs}')
