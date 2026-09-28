import json, logging, sys, time


class JsonFormatter(logging.Formatter):
    def format(self, record):
        d = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
             "level": record.levelname, "component": record.name, "message": record.getMessage()}
        if record.exc_info:
            d["error"] = self.formatException(record.exc_info)
        return json.dumps(d)


def setup_logging(level: str = "INFO"):
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h]
    root.setLevel(level)
