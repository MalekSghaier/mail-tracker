from db import engine, get_conn

def test_pool_checkout_and_return():
    before = engine.pool.checkedout()
    with get_conn() as conn:
        assert engine.pool.checkedout() == before + 1
        cur = conn.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
    # après le with, la connexion doit être rendue au pool
    assert engine.pool.checkedout() == before

def test_pool_rollback_on_exception():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE t (id int)")
    try:
        with get_conn() as conn2:
            cur = conn2.cursor()
            cur.execute("INSERT INTO nonexistent_table VALUES (1)")
    except Exception:
        pass
    # vérifie que la connexion suivante est saine (pas de transaction avortée qui traîne)
    with get_conn() as conn3:
        cur = conn3.cursor()
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)

def test_concurrent_connections():
    import threading
    errors = []
    def worker():
        try:
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT pg_sleep(0.2)")
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors