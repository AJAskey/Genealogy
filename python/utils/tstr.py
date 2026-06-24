import csv

import gen_logging


if __name__ == '__main__':
    tst_logger = gen_logging.setup_logging(logger_name="TEST")
    filepath = r"E:\Users\Andy\PycharmProjects\Genealogy\gedcom_sources\gedcom_individuals.csv"
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        gen_logging.log_reader(tst_logger, reader, filepath)
