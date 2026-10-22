"""One full original-oracle/ABI/source-owner pass over actual CSV rows."""
import csv
from pathlib import Path
import successor_handler as successor
from checker import require, csv_source

def analyze(path,spec):
    q=successor.Checker(spec)
    try:
        with Path(path).open() as stream:
            rows=csv.DictReader(stream)
            require(rows.fieldnames==csv_source.FIELDS,'Exact full CSV header')
            for row in rows:q.row(row)
        return q.finish()
    except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
        return dict(status='NOT_PASS_FOF',error=str(error),rows=q.rows,retired=q.retired,
                    last_cycle=q.last_cycle,checks=q.checks,actions=q.actions,checkpoints=q.points)
