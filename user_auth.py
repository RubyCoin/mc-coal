import datetime
import logging
import urllib2

from google.appengine.api import users

import webapp2
from webapp2_extras import auth, sessions
from webapp2_extras.routes import RedirectRoute

from base_handler import JinjaHandler
from config import coal_config
from models import get_whitelist_user, User, Server, ScreenShot


def get_callback_url(handler, next_url=None):
    if next_url is None:
        next_url = handler.request.path_qs
    try:
        callback_url = handler.uri_for('login_callback')
    except:
        callback_url = '/login_callback'
    if next_url:
        callback_url = "{0}?next_url={1}".format(callback_url, urllib2.quote(next_url))
    return callback_url


def get_login_url(handler, next_url=None):
    return users.create_login_url(get_callback_url(handler, next_url=next_url))


def authenticate(handler, required=True, admin=False):
    user = handler.user
    if user is not None:
        update = False
        wlu = get_whitelist_user(user.email)
        if wlu:
            if not user.active:
                user.active = True
                update = True
            if user.admin != wlu['admin']:
                user.admin = wlu['admin']
                update = True
            if user.username != wlu['username']:
                user.username = wlu['username']
                update = True
        if update:
            user.put()
    if required and not (user and user.active):
        handler.redirect(get_login_url(handler), abort=True)
    if admin and not user.admin:
        handler.redirect(get_login_url(handler), abort=True)
    return user


def authenticate_public(handler):
    return authenticate(handler, required=False, admin=False)


def authenticate_admin(handler):
    return authenticate(handler, required=True, admin=True)


class UserBase(object):
    @webapp2.cached_property
    def session_store(self):
        return sessions.get_store(request=self.request)

    @webapp2.cached_property
    def session(self):
        return self.session_store.get_session(backend="datastore")

    @webapp2.cached_property
    def auth(self):
        return auth.get_auth(request=self.request)

    @webapp2.cached_property
    def user_info(self):
        return self.auth.get_user_by_session()

    @webapp2.cached_property
    def user(self):
        return self.auth.store.user_model.get_by_id(self.user_info['user_id']) if self.user_info else None


class UserHandler(JinjaHandler, UserBase):
    def logged_in(self):
        return self.user is not None

    def logout(self, redirect_url=None):
        redirect_url = redirect_url or webapp2.uri_for('home')
        self.auth.unset_session()
        logout_url = users.create_logout_url(redirect_url)
        self.redirect(logout_url)

    def dispatch(self):
        try:
            super(UserHandler, self).dispatch()
        finally:
            self.session_store.save_sessions(self.response)

    def get_template_context(self, context=None):
        template_context = dict()
        if context:
            template_context.update(context)
        template_context['flashes'] = self.session.get_flashes()
        template_context['request'] = self.request
        template_context['user'] = self.user
        template_context['config'] = coal_config
        template_context['server'] = Server.global_key().get()
        bg_img = ScreenShot.random()
        if bg_img is not None:
            template_context['bg_img'] = bg_img.blurred_image_serving_url
        return template_context

    def head(self, *args):
        """Head is used by Twitter. If not there the tweet button shows 0"""
        pass


class GoogleAppEngineUserAuthHandler(UserHandler):
    def login_callback(self):
        next_url = self.request.params.get('next_url', '')
        user = None
        gae_user = users.get_current_user()
        logging.info("GAE_USER: {0}".format(gae_user.email()))
        if gae_user:
            auth_id = User.get_gae_user_auth_id(gae_user=gae_user)
            user = self.auth.store.user_model.get_by_auth_id(auth_id)
            if user:
                logging.info("EXISTING_USER: {0}".format(user.email))
                # existing user. just log them in.
                self.auth.set_session(self.auth.store.user_to_dict(user), remember=True)
                # update access for gae admins
                if users.is_current_user_admin():
                    if not (user.active and user.admin):
                        user.active = True
                        user.admin = True
                user.last_login = datetime.datetime.now()
                user.put()
            else:
                # check whether there's a user currently logged in
                # then, create a new user if no one is signed in,
                # otherwise add this auth_id to currently logged in user.
                if self.logged_in and self.user:
                    u = self.user
                    if auth_id not in u.auth_ids:
                        u.auth_ids.append(auth_id)
                    u.populate(
                        email=gae_user.email(),
                        nickname=gae_user.nickname(),
                        last_login=datetime.datetime.now()
                    )
                    if users.is_current_user_admin():
                        u.admin = True
                    u.put()
                else:
                    logging.info("NEW_USER")
                    ok, user = self.auth.store.user_model.create_user(
                        auth_id,
                        email=gae_user.email(),
                        nickname=gae_user.nickname(),
                        active=users.is_current_user_admin(),
                        admin=users.is_current_user_admin(),
                        last_login=datetime.datetime.now()
                    )
                    if ok:
                        self.auth.set_session(self.auth.store.user_to_dict(user), remember=True)
                    else:
                        logging.error('create_user() returned False with strings: %s' % user)
                        user = None
                        self.auth.unset_session()
        if not (user and user.active):
            next_url = webapp2.uri_for('home')
        self.redirect(next_url or webapp2.uri_for('home'))


routes = [
        RedirectRoute('/login_callback', handler='user_auth.GoogleAppEngineUserAuthHandler:login_callback', name='login_callback'),
        RedirectRoute('/logout', handler='user_auth.GoogleAppEngineUserAuthHandler:logout', name='logout')
]