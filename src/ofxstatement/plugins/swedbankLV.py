"""Parser implementation for swedbank generated statement reports"""
# pipenv test
import re
import csv
import logging
from io import BufferedIOBase, TextIOWrapper, BytesIO

from ofxstatement.parser import CsvStatementParser
from ofxstatement.plugin import Plugin

LINETYPE_TRANSACTION = "20"
LINETYPE_STARTBALANCE = "10"
LINETYPE_ENDBALANCE = "86"

CARD_PURCHASE_RE = re.compile(
    r"PIRKUMS \d+ (\d\d\d\d\.\d\d\.\d\d) .* \((\d+)\).*")


class SwedbankLVCsvStatementParser(CsvStatementParser):
    mappings = {"date": 2,
                "payee": 3,
                "memo": 4,
                "amount": 5,
                "id": 8}
    date_format = "%d.%m.%Y"

    debug = (logging.getLogger().getEffectiveLevel() == logging.DEBUG)

    def split_records(self):
        csv_file = csv.reader(self.fin, delimiter=';', quotechar='"')
        return csv_file

    def parse_record(self, line):
        if self.cur_record == 1:
            # Skip header line
            return None

        # Set account_id, if its not already set
        if not self.statement.account_id:
            self.statement.account_id = line[0]

        lineType = line[1]

        if lineType == LINETYPE_TRANSACTION:
            # Fix numbers
            line[5] = line[5].replace(',', '.')

            # Convert LVL to EUR (seriously????)
            if line[6] == 'LVL':
                line[5] = round(float(line[5]) / 0.702804, 2)

            # parse transaction line in standard fasion
            stmtline = super(SwedbankLVCsvStatementParser, self).parse_record(line)
            stmtline.trntype = "DEP"
            if line[7] == "D":
                stmtline.amount = -stmtline.amount
                stmtline.trntype = "DEBIT"

            if line[9] == 'KOM':
                stmtline.trntype = "SRVCHG"

            m = CARD_PURCHASE_RE.match(stmtline.memo)
            if m:
                # this is an electronic purchase. extract some useful
                # information from memo field
                dt = m.group(1).replace(".", "-")
                stmtline.date_user = self.parse_datetime(dt)
                stmtline.check_no = m.group(2)

            # DEBUG
            if self.debug:
                print(stmtline, stmtline.trntype)

            return stmtline

        elif lineType == LINETYPE_ENDBALANCE:
            self.statement.end_balance = self.parse_float(line[5])
            self.statement.end_date = self.parse_datetime(line[2])

            # DEBUG
            if self.debug:
                print("End balance: %s" % self.statement.end_balance)

        elif lineType == LINETYPE_STARTBALANCE and self.statement.start_balance == None:
            self.statement.start_balance = self.parse_float(line[5])
            self.statement.start_date = self.parse_datetime(line[2])

            # DEBUG
            if self.debug:
                print("Start balance: %s" % self.statement.start_balance)

    def parse_float(self, value):
        return value if isinstance(value, float) else float(value.replace(',', '.'))

    # TODO: considef movindg __enter__ and __exit__ to parent class
    def __enter__(self):
        self.close_fin = False
        if (isinstance(self.fin, TextIOWrapper)):
            self.fin.encodoing = 'utf-8'
            self.close_fin = True
        elif (isinstance(self.fin, BufferedIOBase)):
            self.fin = TextIOWrapper(self.fin, encoding = 'utf-8')
            self.close_fin = True
        elif (isinstance(self.fin, bytes)):
            self.fin = TextIOWrapper(BytesIO(self.fin), encoding = 'utf-8')
            self.close_fin = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if (self.close_fin):
            self.fin.close()

class SwedbankLVPlugin(Plugin):
    """Latvian Swedbank CSV"""

    def get_parser(self, fin):
        encoding = self.settings.get('charset', 'utf-8')
        f = open(fin, "r", encoding=encoding)
        parser = SwedbankLVCsvStatementParser(f)
        parser.statement.currency = self.settings.get('currency', 'EUR')
        return parser

    def with_parser(self, input):
        return SwedbankLVCsvStatementParser(input)
