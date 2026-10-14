from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import webgal_backend.payments as payments

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('WECHATPAY_ENABLED','true')
    monkeypatch.setattr(payments,'user_from_request',lambda *_:{'id':'owner','auth_type':'sso'})
    monkeypatch.setattr(payments,'get_payment_store',lambda:SimpleNamespace(is_payment_tester=lambda uid:uid=='owner'))
    app=FastAPI();app.include_router(payments.router)
    return TestClient(app)

@pytest.mark.parametrize('identity',['other','revoked-owner'])
def test_private_access_hidden_from_others(client,monkeypatch,identity):
    monkeypatch.setattr(payments,'user_from_request',lambda *_:{'id':identity,'auth_type':'sso'})
    monkeypatch.setattr(payments,'get_payment_store',lambda:SimpleNamespace(is_payment_tester=lambda _:False))
    assert client.get('/payments/test/products').status_code==404
    assert client.post('/payments/test/orders',json={'request_key':'test-key-123456789'}).status_code==404
    assert client.get('/payments/test/orders/'+'a'*32+'/verification').status_code==404


def test_owner_sees_server_defined_product(client,monkeypatch):
    monkeypatch.setattr(payments,'get_payment_service',lambda:object())
    monkeypatch.setattr(payments,'get_payment_store',lambda:SimpleNamespace(is_payment_tester=lambda uid:uid=='owner', private_test_product=lambda:{'id':'a'*32,'price_fen':1,'credits':1}))
    assert client.get('/payments/test/products').json()['product']['price_fen']==1
    assert client.post('/payments/test/orders',json={'request_key':'test-key-123456789','price_fen':1}).status_code==422
    assert client.post('/payments/test/orders',json={'request_key':'test-key-123456789'},headers={'Origin':'https://evil.example'}).status_code==404


def test_owner_test_order_uses_fixed_server_product(client,monkeypatch):
    monkeypatch.setattr(payments,'get_payment_store',lambda:SimpleNamespace(is_payment_tester=lambda uid:uid=='owner', private_test_product=lambda:{'id':'a'*32,'price_fen':1,'credits':1}))
    async def create(payload,user_id,*,private_test=False):
        assert user_id=='owner' and private_test is True
        assert payload.product_id=='a'*32
        return {'status':'PENDING'}
    monkeypatch.setattr(payments,'_create_order_for_user',create)
    assert client.post('/payments/test/orders',json={'request_key':'test-key-123456789'}).json()['status']=='PENDING'
