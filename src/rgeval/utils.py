
import logging

def setup_logger(log_file):
    """Set up the logger with a specific log file."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    

    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    

    stream_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)
    

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger
