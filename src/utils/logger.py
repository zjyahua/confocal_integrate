import logging
import os

# define log file path
current_path = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(current_path)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# Create log directory if it doesn't exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 设置最低日志级别为 DEBUG

# create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# create file handler, output to log file
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# create console handler, output to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# test logger
logger.debug("Logger setup complete")