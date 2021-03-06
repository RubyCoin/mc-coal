import fix_path  # noqa

import datetime
import json
import logging

from pyoauth2.provider import AuthorizationProvider, ResourceAuthorization, ResourceProvider
from pyoauth2.utils import url_query_params, random_ascii_string

from google.appengine.api import lib_config
from google.appengine.ext import ndb

import webapp2
from webapp2_extras.routes import RedirectRoute

from wtforms import fields
from wtforms.ext.csrf.session import SessionSecureForm

from user_auth import UserHandler, authentication_required, authenticate


oauth_config = lib_config.register('oauth', {
    'SECRET_KEY': 'a_secret_string',
    'TOKEN_EXPIRES_IN': 3600*24*30
})


class Client(ndb.Model):
    client_id = ndb.StringProperty(required=True)
    server_key = ndb.KeyProperty()
    instance_key = ndb.KeyProperty()
    name = ndb.StringProperty()
    uri = ndb.StringProperty()
    logo_uri = ndb.StringProperty()
    redirect_uris = ndb.StringProperty(repeated=True)
    scope = ndb.StringProperty(repeated=True)
    secret = ndb.StringProperty()
    secret_expires_at = ndb.IntegerProperty(default=0)
    secret_expires = ndb.ComputedProperty(lambda self: datetime.datetime(year=1970, month=1, day=1) + datetime.timedelta(seconds=self.secret_expires_at) if self.secret_expires_at else None)  # noqa
    registration_access_token = ndb.StringProperty()
    active = ndb.BooleanProperty(default=True)
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)

    @property
    def is_secret_expired(self):
        secret_expires = self.secret_expires
        return datetime.datetime.utcnow() > secret_expires if secret_expires is not None else False

    @property
    def server(self):
        return self.server_key.get() if self.server_key else None

    def instance(self):
        return self.instance_key.get() if self.instance_key else None

    def validate_secret(self, secret):
        if self.secret is not None and not self.is_secret_expired:
            return secret == self.secret
        return False

    @classmethod
    def is_agent(cls, client_or_id):
        if isinstance(client_or_id, cls):
            client = client_or_id
        else:
            client = Client.get_key(client_or_id).get()
        if client is not None:
            return client.server_key is not None
        return False

    @classmethod
    def is_controller(cls, client_or_id):
        if isinstance(client_or_id, cls):
            client = client_or_id
        else:
            client = Client.get_key(client_or_id).get()
        if client is not None:
            return client.instance_key is not None
        return False

    @classmethod
    def get_key_name(cls, client_id):
        return client_id

    @classmethod
    def get_key(cls, client_id):
        return ndb.Key(cls, cls.get_key_name(client_id))

    @classmethod
    def get_by_client_id(cls, client_id):
        key = cls.get_key(client_id)
        return key.get()

    @classmethod
    def get_by_secret(cls, secret):
        return cls.query().filter(cls.secret == secret).get()


class AuthorizationCode(ndb.Model):
    code = ndb.StringProperty(required=True)
    client_id = ndb.StringProperty(required=True)
    user_key = ndb.KeyProperty()
    scope = ndb.StringProperty(repeated=True)
    expires_in = ndb.IntegerProperty(default=0)
    expires = ndb.ComputedProperty(
        lambda self: self.created + datetime.timedelta(seconds=self.expires_in) if self.expires_in else None
    )
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)

    @property
    def is_expired(self):
        return datetime.datetime.utcnow() > self.expires if self.expires is not None else False

    @classmethod
    def get_key_name(cls, client_id, code):
        return '{0}-{1}'.format(client_id, code)

    @classmethod
    def get_key(cls, client_id, code):
        return ndb.Key(cls, cls.get_key_name(client_id, code))


class Token(ndb.Model):
    access_token = ndb.StringProperty(required=True)
    refresh_token = ndb.StringProperty(required=True)
    client_id = ndb.StringProperty(required=True)
    user_key = ndb.KeyProperty()
    scope = ndb.StringProperty(repeated=True)
    token_type = ndb.StringProperty()
    expires_in = ndb.IntegerProperty(default=0)
    expires = ndb.ComputedProperty(
        lambda self: self.created + datetime.timedelta(seconds=self.expires_in) if self.expires_in is not None else None
    )
    created = ndb.DateTimeProperty(auto_now_add=True)
    updated = ndb.DateTimeProperty(auto_now=True)

    @property
    def is_expired(self):
        return datetime.datetime.utcnow() > self.expires if self.expires is not None else False

    def validate_scope(self, scope):
        if scope is None:
            return False
        if scope == self.scope:
            return True
        if not scope:
            return False
        for s in scope.split():
            if s not in self.scope:
                return False
        return True

    @classmethod
    def get_key(cls, access_token):
        return ndb.Key(cls, access_token)

    @classmethod
    def query_expired(cls, expires):
        return cls.query().filter(cls.expires < expires)


class COALAuthorizationProvider(AuthorizationProvider):
    def _handle_exception(self, exc):
        logging.error(exc)

    @property
    def token_expires_in(self):
        return oauth_config.TOKEN_EXPIRES_IN

    def generate_client_id(self, client_id=None):
        """Generate a unique client_id based on the given client_id, if any.

        :param client_id: A client_id to base the new unique one on.
        :type grant_type: str

        :rtype: str
        """
        if client_id is None:
            client_id = random_ascii_string(10)
        while Client.get_by_client_id(client_id) is not None:
            client_id = u'{0}-{1}'.format(client_id, random_ascii_string(3))
        return client_id

    def validate_client_id(self, client_id):
        client = Client.get_by_client_id(client_id)
        if client is not None and client.active:
            return True
        return False

    def validate_client_secret(self, client_id, client_secret):
        client = Client.get_by_client_id(client_id)
        if client is not None and client.active:
            return client.validate_secret(client_secret)
        return False

    def validate_redirect_uri(self, client_id, redirect_uri):
        if Client.is_agent(client_id) or Client.is_controller(client_id):
            return True
        client = Client.get_by_client_id(client_id)
        if client is not None and redirect_uri in client.redirect_uris:
            return True
        return False

    def validate_scope(self, client_id, scope):
        client = Client.get_by_client_id(client_id)
        if client is None or scope is None:
            return False
        if scope == client.scope:
            return True
        if not scope:
            return False
        for s in scope.split():
            if s not in client.scope:
                return False
        return True

    def validate_access(self, client_id):
        if Client.is_agent(client_id) or Client.is_controller(client_id):
            return True
        return webapp2.get_request().user.is_client_id_authorized(client_id)

    def from_authorization_code(self, client_id, code, scope):
        if Client.is_agent(client_id):
            agent = Client.get_by_client_id(client_id)
            if code is not None and scope is not None and code == agent.secret and scope in agent.scope:
                return code
            return None
        if Client.is_controller(client_id):
            controller = Client.get_by_client_id(client_id)
            if code is not None and scope is not None and code == controller.secret and scope in controller.scope:
                return code
            return None
        key = AuthorizationCode.get_key(client_id, code)
        auth_code = key.get()
        if auth_code is not None and auth_code.is_expired:
            key.delete()
            auth_code = None
        return auth_code

    def from_refresh_token(self, client_id, refresh_token, scope):
        token_query = Token.query()
        token_query = token_query.filter(Token.client_id == client_id)
        token_query = token_query.filter(Token.refresh_token == refresh_token)
        return token_query.get()

    def persist_authorization_code(self, client_id, code, scope):
        user = webapp2.get_request().user
        key = AuthorizationCode.get_key(client_id, code)
        if key.get() is not None:
            raise Exception("duplicate_authorization_code")
        scope = scope.split() if scope else ['data']
        auth_code = AuthorizationCode(
            key=key, code=code, client_id=client_id, scope=scope,
            user_key=user.key, expires_in=oauth_config.TOKEN_EXPIRES_IN
        )
        auth_code.put()

    def persist_token_information(self, client_id, scope, access_token, token_type, expires_in, refresh_token, data):
        key = Token.get_key(access_token)
        if key.get() is not None:
            raise Exception("duplicate_access_token")
        if self.from_refresh_token(client_id, refresh_token, scope):
            raise Exception("duplicate_refresh_token")
        scope = scope.split() if scope else ['data']
        user_key = getattr(data, 'user_key', None) if data is not None else None
        token = Token(
            key=key, access_token=access_token, refresh_token=refresh_token, client_id=client_id,
            user_key=user_key, scope=scope, token_type=token_type, expires_in=expires_in
        )
        token.put()

    def discard_authorization_code(self, client_id, code):
        if not Client.is_agent(client_id) and not Client.is_controller(client_id):
            key = AuthorizationCode.get_key(client_id, code)
            key.delete()

    def discard_refresh_token(self, client_id, refresh_token):
        token = self.from_refresh_token(client_id, refresh_token, None)
        if token is not None:
            token.key.delete()

    def discard_client_user_tokens(self, client_id, user_key):
        if not Client.is_agent(client_id) and not Client.is_controller(client_id):
            token_query = Token.query()
            token_query = token_query.filter(Token.client_id == client_id)
            token_query = token_query.filter(Token.user_key == user_key)
            keys = [key for key in token_query.iter(keys_only=True)]
            ndb.delete_multi(keys)

    def get_registration_client_uri(self, client_id):
        """Get the fully qualified URL of the client configuration endpoint for the client_id.

        :param client_id: Client ID.
        :type client_id: str
        :rtype: str
        """
        return webapp2.uri_for('oauth_client', client_id=client_id, _scheme='https')

    def from_client_id(self, client_id):
        """Return mixed data or None on invalid.

        :param client_id: Client ID.
        :type client_id: str
        """
        data = None
        client = Client.get_by_client_id(client_id)
        if client is not None:
            data = {
                'client_id': client.client_id,
                'redirect_uris': client.redirect_uris,
                'scope': ' '.join(client.scope),
                'client_secret': client.secret,
                'client_secret_expires_at': client.secret_expires_at,
                'registration_access_token': client.registration_access_token,
                'registration_client_uri': self.get_registration_client_uri(client_id)
            }
            if client.name is not None:
                data['client_name'] = client.name
            if client.uri is not None:
                data['client_uri'] = client.uri
            if client.logo_uri is not None:
                data['logo_uri'] = client.logo_uri
        return data

    def persist_client_information(
        self, client_id, redirect_uris, client_name, client_uri, logo_uri,
        scope=None, client_secret=None, client_secret_expires_at=None, registration_access_token=None
    ):
        data = {
            'redirect_uris': redirect_uris or [],
            'name': client_name,
            'uri': client_uri,
            'logo_uri': logo_uri,
        }
        if scope is not None:
            data['scope'] = scope.split()
        if client_secret is not None:
            data['secret'] = client_secret
        if client_secret_expires_at is not None:
            data['secret_expires_at'] = client_secret_expires_at
        if registration_access_token is not None:
            data['registration_access_token'] = registration_access_token
        client = Client.get_by_client_id(client_id)
        if client is None:
            data['scope'] = ['data']
            key = Client.get_key(client_id)
            client = Client(key=key, client_id=client_id, **data)
        else:
            client.populate(**data)
        client.put()

    def persist_client_secret(self, client_id, client_secret, client_secret_expires_at):
        client = Client.get_by_client_id(client_id)
        if client is not None:
            client.secret = client_secret
            client.secret_expires_at = client_secret_expires_at
            client.put()

    def discard_client_tokens(self, client_id):
        token_query = Token.query()
        token_query = token_query.filter(Token.client_id == client_id)
        keys = [key for key in token_query.iter(keys_only=True)]
        code_query = AuthorizationCode.query()
        code_query = code_query.filter(AuthorizationCode.client_id == client_id)
        keys += [key for key in code_query.iter(keys_only=True)]
        ndb.delete_multi(keys)

    def discard_client_information(self, client_id):
        key = Client.get_key(client_id)
        key.delete()
        self.discard_client_tokens(client_id)

    def get_default_client_scope(self):
        return 'data'

    def get_authorization_header(self):
        return webapp2.get_request().headers.get('Authorization', None)

    def validate_registration_access_token(self, client_id, registration_access_token):
        client = Client.get_by_client_id(client_id)
        if client is not None and client.registration_access_token is not None:
            return client.registration_access_token == registration_access_token
        return False

    def validate_client_secret_expired(self, client_id):
        client = Client.get_by_client_id(client_id)
        if client is not None and client.is_secret_expired:
            return True
        return False

authorization_provider = COALAuthorizationProvider()


class COALResourceAuthorization(ResourceAuthorization):
    def __init__(self, *args, **kwargs):
        super(COALResourceAuthorization, self).__init__(*args, **kwargs)
        self.user_key = None


class COALResourceProvider(ResourceProvider):
    SCOPE = 'data'

    @property
    def authorization_class(self):
        return COALResourceAuthorization

    def get_authorization_header(self):
        return webapp2.get_request().headers.get('Authorization', None)

    def validate_access_token(self, access_token, authorization):
        key = Token.get_key(access_token)
        token = key.get()
        if token is not None and not token.is_expired and token.validate_scope(self.SCOPE):
            authorization.is_valid = True
            authorization.client_id = token.client_id
            authorization.user_key = token.user_key
            if token.expires is not None:
                d = datetime.datetime.utcnow() - token.expires
                authorization.expires_in = d.seconds

resource_provider = COALResourceProvider()


class COALAgentResourceProvider(COALResourceProvider):
    SCOPE = 'agent'

agent_resource_provider = COALAgentResourceProvider()


class COALControllerResourceProvider(COALResourceProvider):
    SCOPE = 'controller'

controller_resource_provider = COALControllerResourceProvider()


class BaseSecureForm(SessionSecureForm):
    SECRET_KEY = oauth_config.SECRET_KEY
    TIME_LIMIT = datetime.timedelta(minutes=20)


class AuthForm(BaseSecureForm):
    grant = fields.SubmitField('Grant', id='submit_button')
    deny = fields.SubmitField('Deny', id='submit_button')


class PyOAuth2Base(object):
    @property
    def client_id(self):
        return url_query_params(self.request.url).get('client_id', None)

    @property
    def redirect_uri(self):
        return url_query_params(self.request.url).get('redirect_uri', None)

    def set_response(self, response):
        self.response.set_status(response.status_code)
        self.response.headers.update(response.headers)
        self.response.write(response.text)


class AuthorizationCodeHandler(UserHandler, PyOAuth2Base):
    def set_authorization_code_response(self):
        response = authorization_provider.get_authorization_code_from_uri(self.request.url)
        self.set_response(response)

    @authentication_required(authenticate=authenticate)
    def get(self):
        if self.user.is_client_id_authorized(self.client_id):
            self.set_authorization_code_response()
        else:
            form = AuthForm(csrf_context=self.session)
            context = {'url': self.request.url, 'form': form, 'client_id': self.client_id}
            self.render_template('auth.html', context=context)

    @authentication_required(authenticate=authenticate)
    def post(self):
        form = AuthForm(self.request.POST, csrf_context=self.session)
        if form.validate():
            if form.grant.data:
                self.user.authorize_client_id(self.client_id)
            else:
                self.user.unauthorize_client_id(self.client_id)
            self.set_authorization_code_response()
        elif form.csrf_token.errors:
            logging.error(form.csrf_token.errors)
        else:
            form = AuthForm(csrf_context=self.session)
            context = {'url': self.request.url, 'form': form, 'client_id': self.client_id}
            self.render_template('auth.html', context=context)


class TokenHandler(webapp2.RequestHandler, PyOAuth2Base):
    def set_access_token_response(self):
        if self.request.headers.get('Content-Type', '').startswith('application/json'):
            data = json.loads(self.request.body)
        else:
            data = self.request.POST
        response = authorization_provider.get_token_from_post_data(data)
        self.set_response(response)

    def post(self):
        self.set_access_token_response()


class RegistrationHandler(webapp2.RequestHandler, PyOAuth2Base):
    def set_registration_response(self):
        response = authorization_provider.get_registration_from_post_body(self.request.body)
        self.set_response(response)

    def post(self):
        self.set_registration_response()


class ClientHandler(webapp2.RequestHandler, PyOAuth2Base):
    def get(self, client_id):
        response = authorization_provider.get_client(client_id)
        self.set_response(response)

    def put(self, client_id):
        response = authorization_provider.get_client_from_put_body(client_id, self.request.body)
        self.set_response(response)

    def delete(self, client_id):
        registration_access_token = authorization_provider.get_registration_access_token()
        is_valid_client_id = authorization_provider.validate_client_id(client_id)
        if not is_valid_client_id:
            self.set_response(authorization_provider._make_response(status_code=401))
            return
        is_valid_registration_access_token = authorization_provider.validate_registration_access_token(client_id, registration_access_token)  # noqa
        if not is_valid_registration_access_token:
            self.set_response(authorization_provider._make_error_response('invalid_token'))
            return
        authorization_provider.discard_client_information(client_id)
        del self.response.headers['Content-Type']
        self.response.set_status(204)


class ShowAuthorizationCodeHandler(UserHandler, PyOAuth2Base):
    @authentication_required(authenticate=authenticate)
    def get(self):
        code = self.request.GET.get('code', None)
        error = self.request.GET.get('error', None)
        context = {'code': code, 'error': error}
        self.render_template('oauth_show.html', context=context)


class TestHandler(webapp2.RequestHandler):
    def get(self):
        authorization = resource_provider.get_authorization()
        if not (authorization.is_oauth and authorization.is_valid):
            self.abort(401)
        self.response.headers['Content-Type'] = "application/json"
        client_id = authorization.client_id
        user = authorization.user_key.get()
        auth_header = self.request.headers.get('Authorization', None)
        body = u"{{'authorization': {0}, 'client_id': {1}".format(auth_header, client_id)
        if user:
            body += u", 'user': {0}}}".format(user.nickname)
        else:
            body = u"}}"
        self.response.set_status(200)
        self.response.out.write(body)


def authenticate_agent_oauth(handler):
    authorization = agent_resource_provider.get_authorization()
    return authorization if authorization is not None and authorization.is_valid else None


def authenticate_agent_oauth_required(handler):
    authorization = authenticate_agent_oauth(handler)
    if authorization is None:
        handler.abort(401)
    return authorization


def authenticate_controller_oauth(handler):
    authorization = controller_resource_provider.get_authorization()
    return authorization if authorization is not None and authorization.is_valid else None


def authenticate_controller_oauth_required(handler):
    authorization = authenticate_controller_oauth(handler)
    if authorization is None:
        handler.abort(401)
    return authorization


def authenticate_oauth(handler):
    authorization = resource_provider.get_authorization()
    return authorization if authorization is not None and authorization.is_valid else None


def authenticate_oauth_required(handler):
    authorization = authenticate_oauth(handler)
    if authorization is None:
        handler.abort(401)
    return authorization


def authenticate_user(handler):
    user = None
    authorization = authenticate_oauth_required(handler)
    if authorization.is_valid:
        user = authorization.user_key.get() if authorization.user_key is not None else None
    return user


def authenticate_user_required(handler):
    user = authenticate_user(handler)
    if not (user and user.active):
        handler.abort(403)
    return user


def authenticate_admin_required(handler):
    user = authenticate_user(handler)
    if not (user and user.active and user.admin):
        handler.abort(403)
    return user


routes = [
    RedirectRoute('/oauth/v1/auth', handler='oauth.AuthorizationCodeHandler', methods=['GET', 'POST'], name='oauth_auth'),  # noqa
    RedirectRoute('/oauth/v1/token', handler='oauth.TokenHandler', methods=['POST'], name='oauth_token'),
    RedirectRoute('/oauth/v1/register', handler='oauth.RegistrationHandler', methods=['POST'], name='oauth_register'),
    RedirectRoute('/oauth/v1/clients/<client_id>', handler='oauth.ClientHandler', methods=['GET', 'PUT', 'DELETE'], name='oauth_client'),  # noqa
    RedirectRoute('/oauth/v1/show', handler='oauth.ShowAuthorizationCodeHandler', methods=['GET'], name='oauth_show'),
    RedirectRoute('/oauth/v1/test', handler='oauth.TestHandler', methods=['GET'], name='oauth_test')
]
