#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2012 João Alves <joaoqalves@gmail.com> and Tiago Pereira
# <tiagomiguelmoreirapereira@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import pymongo
import datetime
from gluon import current
from bson.objectid import ObjectId

def add_seconds_to_date(date, seconds):
    return date + datetime.timedelta(0, seconds)

class OAuthStorage(object):
    """Storage interface in order to use the OAuth2 server. It's just an
    interface and you should extend it to your database engine.
    """
    
    @staticmethod
    def generate_hash_512(length = 32, salt = True):
        """Generates a SHA512 random hash. It takes two arguments:
        * length (default: 32)
        * salt (default: True). You should change the salt used for the hash 
        """
        
        import os
        import hashlib
        import base64
        
        SALT = 'TlG}LJV[nplC5^jZn+Z]TCal`)2[^(_h' #CHANGE ME
        encode_str = base64.urlsafe_b64encode(os.urandom(length))
        m = hashlib.sha512()
        if salt:
            encode_str = SALT + encode_str
            
        m.update(encode_str)
        return m.hexdigest()

    @staticmethod
    def generate_hash_sha1(length = 32, salt = False):
        """Generates a SHA512 random hash. It takes two arguments:
        * length (default: 32)
        * salt (default: False). You should change the salt used for the hash 
        """
        
        import os
        import hashlib
        import base64
        
        SALT = 'TlG}LJV[nplC5^jZn+Z]TCal`)2[^(_h' #CHANGE ME
        encode_str = base64.urlsafe_b64encode(os.urandom(length))
        m = hashlib.sha1()
        if salt:
            encode_str = SALT + encode_str
        m.update(encode_str)
        return m.hexdigest()
        
    #CHANGE ME
    def __init__(self, server='localhost', port=27017, db_name='oauth'):
        """The Storage constructor takes 3 arguments:
        * The database server
        * The database server port
        * The database name
        """
        
        self.server = server
        self.port = port
        self.db_name = db_name
        
class MongoStorage(OAuthStorage):
    """A MongoDB adapter for the Storage super-class. It uses pymongo"""
    
    def connect(self):
        """Connects to the database with the credentials provided in the
        constructor
        """
        
        self.conn = pymongo.Connection(self.server, self.port)
        #CHANGE ME if you do not use web2py
        self.db = current.cache.ram('mongodb', lambda: self.conn[self.db_name], None)


    def add_client(self, client_name, redirect_uri):
        """Adds a client application to the database, with its client name and
        redirect URI. It returns the generated client_id and client_secret
        """
        
        client_id = MongoStorage.generate_hash_sha1()
        client_secret = MongoStorage.generate_hash_sha1()

        self.db.clients.save({'_id': client_id,
                              'client_secret': client_secret,
                              'redirect_uri': redirect_uri,
                              'client_name': client_name})

        return client_id, client_secret
        
    def exists_client(self, client_id):
        """Checks if a client exists, given its client_id"""
        
        return self.db.clients.find({'_id': client_id}) != None

    def get_client_credentials(self, client_id):
        """Gets the client credentials by the client application ID given."""
        
        return self.db.clients.find_one({'_id': client_id})

    def add_code(self, client_id, user_id, lifetime):
        """Adds a temporary authorization code to the database. It takes 3
        arguments:
        * The client application ID
        * The user ID who wants to authenticate
        * The lifetime of the temporary code
        It returns the generated code
        """
        
        user_id = ObjectId(user_id)
        expires = add_seconds_to_date(datetime.datetime.now(), lifetime)

        # It guarantees the uniqueness of the code. Better way?
        while True:
            code = OAuthStorage.generate_hash_sha1()
            if self.db.codes.find_one({'_id': code}) == None:
                break
            

        self.db.codes.save({'_id': code,
                         'client_id': client_id,
                         'user_id': user_id, 
                         'expires': expires})

        return code

    def valid_code(self, client_id, code):
        """Validates if a code is (still) a valid one. It takes two arguments:
        * The client application ID
        * The temporary code given by the application
        It returns True if the code is valid. Otherwise, False
        """
        
        data = self.db.codes.find_one({'_id': code,
                         'client_id': client_id})
        if data != None:
            return datetime.datetime.now() < data['expires']

        return False

    def exists_code(self, code):
        """Checks if a given code exists on the database or not"""
        
        return self.db.codes.find_one({'_id': code}) != None

    def remove_code(self, code):
        """Removes a temporary code of the database"""

        self.db.codes.remove({'_id': code})

    def get_user_id(self, client_id, code):
        """Gets the user ID, given a client application ID and a temporary
        authentication code
        """
        
        return self.db.codes.find_one({'_id': code, 
                                       'client_id': client_id})['user_id']

    def expired_access_token(self, token):
        """Checks if the access token remains valid or if it has expired"""
        
        return token['expires_access'] < datetime.datetime.now()

    def expired_refresh_token(self, token):
        """Checks if the refresh token remains valid or if it has expired"""
        
        return token['expires_refresh'] < datetime.datetime.now()

    def add_access_token(self, client_id, user_id, access_lifetime,
                         refresh_token = None, refresh_lifetime = None,
                         expires_refresh = None, scope = None):
        """Generates an access token and adds it to the database. If the refresh
        token does not exist, it will create one. The method takes 6 arguments:
        * The client application ID
        * The user ID
        * The access token lifetime
        * [OPTIONAL] The refresh token
        * [OPTIONAL] The refresh token lifetime
        * [OPTIONAL] The scope of the access
        """
        
        now = datetime.datetime.now()
        
        # It guarantees uniqueness. Better way?
        while True:
            access_token = MongoStorage.generate_hash_512()
            if self.db.tokens.find_one({'access_token': access_token}) == None:
                break

        expires_access = add_seconds_to_date(now, access_lifetime)

        # It guarantees uniqueness. Better way?
        if refresh_token == None:
            while True:
                refresh_token = MongoStorage.generate_hash_512()
                if self.db.tokens.find_one({'_id': refresh_token}) == None:
                    break
            expires_refresh = add_seconds_to_date(now, refresh_lifetime)

        self.db.tokens.save({'_id': refresh_token,
                         'client_id': client_id,
                         'user_id': user_id,
                         'expires_access': expires_access,
                         'expires_refresh': expires_refresh,
                         'scope': scope,
                         'access_token': access_token})

        return access_token, refresh_token, expires_access

    def refresh_access_token(self, client_id, client_secret, refresh_token):
        """Updates an access token, given the refresh token.
        The method takes 3 arguments:
        * The client application ID
        * The client application secret ID
        * The refresh token
        """

        now = datetime.datetime.now()
        credentials = get_client_credentials(client_id)
        old_token = self.db.tokens.find_one({'_id': refresh_token,
                                             'client_id': client_id})
        if old_token and expired_refresh_token(old_token, now) \
        and credentials['client_secret'] == client_secret:
            return self.add_access_token(client_id, 
                                         old_token['user_id'],
                                         self.config[self.CONFIG_ACCESS_LIFETIME],
                                         old_token['refresh_token'],
                                         self.config[self.CONFIG_REFRESH_LIFETIME],
                                         old_token['expires_refresh'],
                                         old_token['scope'])
        return False, False, False
        
    def get_access_token(self, access_token):
        """Returns the token data, if the access token exists"""
        return self.db.tokens.find_one({'access_token': access_token})
        
    def get_refresh_token(self, refresh_token):
        """Returns the token data, if the refresh token exists"""
    
        return self.db.tokens.find_one({'_id': refresh_token})
