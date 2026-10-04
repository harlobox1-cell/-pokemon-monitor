from src.retailers import parse_product, infer_retailer

def test_jsonld_product():
    html='''<html><script type="application/ld+json">{"@type":"Product","name":"Pokemon Test ETB","sku":"ABC123","offers":{"price":"99.00","priceCurrency":"AUD","availability":"https://schema.org/InStock"}}</script></html>'''
    p=parse_product("https://www.bigw.com.au/product/test/p/123", html)
    assert p.title == "Pokemon Test ETB"
    assert p.price == 99.0
    assert p.in_stock is True
    assert p.sku == "ABC123"
    assert p.retailer == "big-w-au"

def test_pokemon_center_regions():
    assert infer_retailer("https://www.pokemoncenter.com/en-au/product/abc") == "pokemon-centre-au"
    assert infer_retailer("https://www.pokemoncenter.com/product/abc") == "pokemon-center-us"
