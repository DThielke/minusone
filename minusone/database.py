import logging
import sqlite3

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, path):
        self.path = path
        self.connection = None

    def connect(self):
        """Connect to the database"""
        self.connection = sqlite3.connect(self.path)

    def disconnect(self):
        """Disconnect from the database"""
        if self.connection is not None:
            self.connection.close()

    def execute(self, query):
        """Execute a query on the database"""
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            self.connection.commit()
        except sqlite3.Error:
            logger.error("Failed on query: %s", query)
            raise
        return cursor
