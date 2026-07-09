import os
import time
import logging
import threading
import pandas as pd
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal
from dotenv import load_dotenv
load_dotenv()



logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

QUERY_CACHE_TTL_SECONDS = int(os.getenv("QUERY_CACHE_TTL_SECONDS", "300"))
QUERY_CACHE_MAX_ENTRIES = int(os.getenv("QUERY_CACHE_MAX_ENTRIES", "256"))
SERVER_HOSTNAME = os.getenv("DATABRICKS_SERVER_HOSTNAME")


def credentials_provider():
    config = Config(
        host=f"https://{SERVER_HOSTNAME}",
        client_id=os.getenv("DATABRICKS_CLIENT_ID"),
        client_secret=os.getenv("DATABRICKS_CLIENT_SECRET")
    )
    return oauth_service_principal(config)


class QueryService:
    _instance = None

    @staticmethod
    def get_instance():
        if QueryService._instance is None:
            QueryService._instance = QueryService()
        return QueryService._instance

    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = QUERY_CACHE_TTL_SECONDS
        self._cache_max_entries = QUERY_CACHE_MAX_ENTRIES

    def _cache_get(self, key):
        now = time.time()
        with self._cache_lock:
            hit = self._cache.get(key)
            if not hit:
                return None
            expires_at, df = hit
            if now >= expires_at:
                del self._cache[key]
                return None
            return df

    def _cache_set(self, key, df):
        expires_at = time.time() + self._cache_ttl
        with self._cache_lock:
            if len(self._cache) >= self._cache_max_entries:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = (expires_at, df)

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()
        logging.info("Query cache cleared")

    def execute_query(self, query):
        cached = self._cache_get(query)
        if cached is not None:
            logging.info("CACHE HIT for query (TTL=%ss): %s", self._cache_ttl, query)
            return cached.copy(deep=True)

        start = time.time()
        with sql.connect(
            server_hostname=SERVER_HOSTNAME,
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            credentials_provider=credentials_provider,
        ) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            df = cursor.fetchall_arrow().to_pandas()

        logging.info(f"DB query took {time.time() - start:.2f} sec: {query}")
        self._cache_set(query, df)
        return df.copy(deep=True)

    def get_gld_variable_coverage(self):
        query = """
            SELECT *
            FROM prd_mega.sgld48.gld_variable_coverage
        """
        return self.execute_query(query)

