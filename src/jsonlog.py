import json
import logging
import sys
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):

    def __init__(self, component, worker_id=None):
        super().__init__()
        self.component = component
        self.worker_id = worker_id
    
    def format(self, record):
        format_dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "component": self.component,
            "msg": record.getMessage()
        }

        if self.worker_id is not None:
            format_dict["worker_id"] = self.worker_id
        else:
            worker_id = getattr(record, "worker_id", None)
            if worker_id is not None:
                format_dict["worker_id"] = worker_id

        if getattr(record, "job_id", None) is not None:
            format_dict["job_id"] = record.job_id

        if getattr(record, "attempt_number", None) is not None:
            format_dict["attempt_number"] = record.attempt_number

        if record.exc_info is not None:
            format_dict["exc"] = self.formatException(record.exc_info)



        return json.dumps(format_dict, default=str)

def setup(component, worker_id=None):
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(component, worker_id))
    root.handlers.clear()
    root.addHandler(handler)