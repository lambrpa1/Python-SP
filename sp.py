#!/usr/bin/env python3
#
# Python-based test service provider for OP Identity Service Broker's OIDC api

import aiohttp
import base64
import binascii
import jwcrypto
import os
import responder
import requests
import sys
import time
import uuid
import datetime

from jwcrypto.jwk import JWK, JWKSet
from jwcrypto import jwk, jws, jwe
from jwcrypto.common import json_encode, json_decode

AUTHORIZE_ENDPOINT='https://isb-test.op.fi/oauth/authorize'
TOKEN_ENDPOINT='https://isb-test.op.fi/oauth/token'
ISBKEY_ENDPOINT='https://isb-test.op.fi/jwks/broker'
ISBEMBEDDED_ENDPOINT='https://isb-test.op.fi/api/embedded-ui/'
#AUTHORIZE_ENDPOINT='https://identity-service-broker.docker/oauth/authorize'
#TOKEN_ENDPOINT='https://identity-service-broker.docker/oauth/token'

CLIENT_ID='saippuakauppias'
#CLIENT_ID='test'
HOSTNAME='localhost'
#HOSTNAME='localhost:5042'

# Global sessions db (in-memory)
sessions = dict()
# This is a global variable used to display previously used landing page (standard or embedded)
# must be put inside session
#layout = ''

# Keys
#
# In this example (sandbox) this keypair is fixed. 
# In real production environment this value must be replaced with private key which
# is a pair for public key published in JWKS endpoint. ISB get this public key and 
# crypt token with public key and in SP side token can be extracted with private key

with open('sandbox-sp-key.pem', 'rb') as dec_key_file:
    decryption_key = jwk.JWK.from_pem(dec_key_file.read())

# with open('isb-cert.pem', 'rb') as isb_cert_file:
#    isb_cert = jwk.JWK.from_pem(isb_cert_file.read())

# This key is used to sign payload so that ISB can verify it. ISB fetch public key from 
# JWKS endpoint and check signature

with open('sp-signing-key.pem', 'rb') as sig_key_file:
    signing_key = jwk.JWK.from_pem(sig_key_file.read())

class Session:
    """Session class

    Pass attributes to the constructor as named parameters. Attributes
    can be accessed as class attributes. The session is automatically
    registered in the global in-memory session db object.

    These attributes are automatically generate: sessionid, created
    """
    
    def __init__(self, **kwargs):
        self.params = kwargs
        if "sessionid" not in self.params:
            self.params['sessionid'] = str(uuid.uuid4())
        if "created" not in self.params:
            self.params['created'] = time.time()
        sessions[self.params['sessionid']] = self

    def __getattribute__(self, key):
        params = object.__getattribute__(self, 'params')
        if key in params:
            return params[key]
        return object.__getattribute__(self, key)


api = responder.API(static_dir="/app/static", static_route="/static")
#api = responder.API(static_dir="C:/Users/Lambropoulos/projects/Python-SP/static", static_route="/static")

api.add_route("/static/css", static=True)
api.add_route("/static/images", static=True)

@api.route("/")
def front_view(req, resp):
    """Front page"""   
    resp.html = api.template('standard.html')

@api.route("/embedded")
def front_view(req, resp):
    """Front page"""
    embeddedendpoint = ISBEMBEDDED_ENDPOINT + CLIENT_ID + '?lang=en'
    embedded=requests.get(embeddedendpoint, verify=False).json()
    idps=embedded["identityProviders"]
    disturbance=embedded['disturbanceInfo']
     
    resp.html = api.template('embedded.html', embedded=embedded, idps=idps, disturbance=disturbance)

@api.route("/authenticate")
def jump_view(req, resp):
    """Jump view linked to from front page. Redirects to Identity Service Broker."""

    idButton = req.params.get('idButton')
    consent = req.params.get('promptBox')
    purpose = req.params.get('purpose')

    if (consent is None):
        consent = 'no consent'

    print('IdButton = ' + str(idButton) + ' and consent = ' + consent + ' and purpose = ' + purpose)
    sys.stdout.flush()
    
    if (idButton is not None):
        #global layout
        #layout = 'embedded'
        sessions['layout']='embedded'
        session = Session(nonce=binascii.hexlify(os.urandom(10)).decode('ascii'),idButton=idButton, consent=consent)
        resp.html = api.template(
            'jump.html',
            endpoint=AUTHORIZE_ENDPOINT,
            request=make_auth_jwt_embedded(session, purpose)
            )
    else:
        #layout = ''
        sessions['layout']=''
        session = Session(nonce=binascii.hexlify(os.urandom(10)).decode('ascii'), consent=consent)
        resp.html = api.template(
            'jump.html',
            endpoint=AUTHORIZE_ENDPOINT,
            request=make_auth_jwt(session, purpose)
            )       
    
@api.route("/return")
async def return_view(req, resp):
    """Return view for processing authentication results from the Identity Service Broker."""

    code = req.params.get('code')
    error = req.params.get('error')
    sessionid = req.params.get('state')
    error_description = req.params.get('error_description')
    
    #global layout
    #print('Layout = ' + layout)
    #print('Layout = ' + sessions['layout'])

    layout = sessions['layout']

    if not error and (not sessionid or sessionid not in sessions):
        error = 'Invalid session'

    if error:
        if (error=='cancel'):
            resp.html = api.template('cancel.html', error=error, layout=layout)
            return
        else:
            resp.html = api.template('error.html', error=error, error_description=error_description, layout=layout)
            return       


    # Resolve the access code
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field('code', code)
        data.add_field('redirect_uri', 'https://{0}/return'.format(HOSTNAME))
        data.add_field('grant_type', 'authorization_code')
        data.add_field('client_assertion', make_token_jwt())
        data.add_field('client_assertion_type', 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer')

        headers=dict(
            Accept='application/json'
            )

        async with session.post(TOKEN_ENDPOINT, data=data, headers=headers, ssl=False) as tokenresp:
                token_data = await tokenresp.text()
                print('token', repr(token_data))
                sys.stdout.flush()

        try:
            id_token = json_decode(token_data)['id_token']
        except KeyError:
            raise ValueError(token_data)

        #print('decrypting token')

        jwetoken = jwe.JWE()
        jwetoken.deserialize(id_token)
        jwetoken.decrypt(decryption_key)

        #print('token decrypted (kid): ' + str(jwetoken.jose_header['kid']))

        jwstoken = jws.JWS()
        jwstoken.deserialize(jwetoken.payload.decode('ascii'))     

        sig_key = jwstoken.jose_header['kid']
        #print('Signing key = ' + str(sig_key))
 
        keys=requests.get(ISBKEY_ENDPOINT, verify=False).json()
        #print('keys from ISB = ' + str(keys))

        keyset=JWKSet()
        for key in keys['keys']:
            kid = key['kid']
            keyset.add(JWK(**key))
            if kid==sig_key:
                isb_cert=JWK(**key)

        jwstoken.verify(isb_cert)
        print(str(json_decode(jwstoken.payload)))  
        sys.stdout.flush()

        id_token = json_decode(jwstoken.payload)

        date = datetime.datetime.now()
        datestring = date.strftime("%c")
        variables = repr(id_token)

        sys.stdout.flush()

        resp.html = api.template('result.html', variables=variables, id_token=id_token, layout=layout, datestring=datestring)

        
def make_private_key_jwt(payload):
    """Generate a new compact JWS to identify us to ISB"""
    jwstoken = jws.JWS(payload)
    jwstoken.add_signature(
        signing_key,
        alg="RS256",
        protected=json_encode(dict(
            alg='RS256',
            kid=signing_key.thumbprint()
            )))
    return jwstoken.serialize(True)


def make_token_jwt():
    payload = json_encode(dict(
        iss=CLIENT_ID,
        sub=CLIENT_ID,
        aud=AUTHORIZE_ENDPOINT,
        jti=str(uuid.uuid4()),
        exp=int(time.time()) + 600
        ))
    return make_private_key_jwt(payload)


def make_auth_jwt(session, purpose):

    if (purpose=='normal'):
        purpose=''

    params = dict(
        client_id=CLIENT_ID,
        redirect_uri='http://{0}/return'.format(HOSTNAME),
        nonce=session.nonce,
        state=session.sessionid,
        scope="openid profile personal_identity_code " + purpose,
        response_type="code"
        )

    if (session.consent=='consent'):
        params = dict(
        client_id=CLIENT_ID,
        redirect_uri='http://{0}/return'.format(HOSTNAME),
        nonce=session.nonce,
        state=session.sessionid,
        scope="openid profile personal_identity_code " + purpose,
        response_type="code",
        prompt="consent"
        )

    payload = json_encode(params)

    return make_private_key_jwt(payload)

def make_auth_jwt_embedded(session, purpose):

    if (purpose=='normal'):
        purpose=''

    params = dict(
        client_id=CLIENT_ID,
        redirect_uri='http://{0}/return'.format(HOSTNAME),
        nonce=session.nonce,
        state=session.sessionid,
        scope="openid profile personal_identity_code " + purpose,
        response_type="code",
        ftn_idp_id=session.idButton
        )

    if (session.consent=='consent'):
        params = dict(
        client_id=CLIENT_ID,
        redirect_uri='http://{0}/return'.format(HOSTNAME),
        nonce=session.nonce,
        state=session.sessionid,
        scope="openid profile personal_identity_code " + purpose,
        response_type="code",
        ftn_idp_id=session.idButton,
        prompt="consent"
        )

    payload = json_encode(params)
    return make_private_key_jwt(payload)

if __name__=='__main__':
    api.run()
