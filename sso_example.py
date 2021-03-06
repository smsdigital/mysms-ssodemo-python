import os
import json
import requests
from nacl.public import Box, PrivateKey, PublicKey
from nacl.encoding import Base64Encoder
from base64 import b64encode
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote

# Base URL for the SSO API
SSO_BASE_URL = 'https://api.my.sms-group.com'
# The product name for authenticating the SSO call (provided by SMS digital)
PRODUCT_NAME = 'sms-app-sso-test'
# The public key of the platform (obtained from https://api.my.sms-group.com/config)
PLATFORM_PUBLIC_KEY = PublicKey('sQsT5C+Bst2i+hbBZIrBroHhDy7LopgFwUR9PFprans=', encoder=Base64Encoder)
# The private key (generated by the application developer)
APPLICATION_PRIVATE_KEY = PrivateKey('I2D6BWycz+bNWkcS1ul820uK5Jx1qGvsRfilDy09o94=', encoder=Base64Encoder)

# Public-key encryption provided by PyNaCl (https://pynacl.readthedocs.io/en/stable/public/)

# The private/public key pair of the application can be generated as follows:
# private_key = PrivateKey.generate()
# print('Private key: {}'.format(private_key.encode(encoder=Base64Encoder).decode()))
# public_key = private_key.public_key
# print('Public key: {}'.format(public_key.encode(encoder=Base64Encoder).decode()))

class HTTPHandler(BaseHTTPRequestHandler):

    def send_str(self, msg):
        self.wfile.write(msg.encode())

    def authenticate(self):
        """Performs SSO by looking up query parameter and crafting an encrypted, signed request
        to the mySMS API. The encrypted, signed response can be decyphered and parsed as JSON"""

        # Extract query parameter 'mysms_group[auth]'
        url = urlparse(self.path)
        query = parse_qs(unquote(url.query))
        auth_param = 'mysms_group[auth]'
        if auth_param not in query:
            return
        token = query[auth_param][0]
        if token is None:
            return

        # Create a Box for communication with the mySMS using the platforms public key and the applications private key
        box = Box(APPLICATION_PRIVATE_KEY, PLATFORM_PUBLIC_KEY)
        # Encrypt and sign random 64 bytes - they are just used to proof the request issuer possesses the private key
        encrypted = box.encrypt(os.urandom(64))

        # Base64 encode the nonce + cyphertext into a UTF-8 string
        payload = b64encode(encrypted.nonce + encrypted.ciphertext).decode()

        # Perform HTTP call to platform
        sso_url = '{}/auth/lookup/{}'.format(SSO_BASE_URL, token)
        headers = {'Authorization': 'PRODUCTAUTH {}:{}'.format(
            PRODUCT_NAME,
            payload
        )}

        r = requests.get(sso_url, headers=headers)
        if r.status_code != 200:
            return

        # The platform response contains 24 nonce-bytes + the encrypted user data
        encrypted_response = r.content
        message = box.decrypt(
            encrypted_response[box.NONCE_SIZE:],
            encrypted_response[:box.NONCE_SIZE]
        )
        # after decryption, we can parse the JSON string and create a application-specific session for the user
        return json.loads(message)


    def do_GET(self):
        user = self.authenticate()
        if user is None:
            self.send_response(401)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()
        self.send_str('User data: {}'.format(json.dumps(user)))


httpd = HTTPServer(('', 4200), HTTPHandler)
httpd.serve_forever()
