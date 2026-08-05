import redis

# protocol=2 évite la commande HELLO qui fait planter
r = redis.Redis(
    host="localhost", port=6379, db=0, decode_responses=True, protocol=2
)
r.set("test_key", "ça marche")
print(r.get("test_key"))