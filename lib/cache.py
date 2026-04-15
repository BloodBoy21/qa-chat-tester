import redis
import os


class RedisCache:
    _instance = None  # Almacena la única instancia de la clase

    def __new__(cls, *args, **kwargs):
        # Si no existe una instancia, la crea
        if cls._instance is None:
            cls._instance = super(RedisCache, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Configuración de la conexión a Redis
        self.HOST = os.getenv("REDIS_HOST", "localhost")
        self.PORT = os.getenv("REDIS_PORT", 6379)
        self.DB = os.getenv("REDIS_DB", 0)
        self.URI = os.getenv("REDIS_URI", None)

        # Inicializa la conexión a Redis
        if self.URI:
            self.cache = redis.Redis.from_url(self.URI)
        else:
            self.cache = redis.Redis(
                host=self.HOST, port=int(self.PORT), db=int(self.DB)
            )

        if self.cache is None:
            raise Exception("Failed to initialize cache")

    def get_cache(self):
        # Devuelve la instancia de Redis
        return self.cache


# Uso del Singleton
def get_cache():
    return RedisCache().get_cache()
