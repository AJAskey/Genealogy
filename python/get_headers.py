import pandas as pd

for year in [1850, 1860, 1870, 1880, 1920, 1930, 1940, 1950]:
    df = pd.read_csv(rf"E:\Census\IPUMS\Original\census-{year}.csv", nrows=1)
    has_name = "NAMELAST" in df.columns or "NAMEFRST" in df.columns
    print(f"{year}: {list(df.columns[:8])}  names={has_name}")
