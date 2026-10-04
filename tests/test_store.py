from src.config_store import ConfigStore

def test_store(tmp_path):
    s=ConfigStore(str(tmp_path))
    s.set_webhook("https://discord.com/api/webhooks/123/abc")
    assert s.get_webhook().endswith("/123/abc")
    s.add_watch("Test","big-w-au","https://www.bigw.com.au/test",100.0,False)
    rows=s.list_watches()
    assert len(rows)==1
    assert rows[0]["max_price"]==100.0
